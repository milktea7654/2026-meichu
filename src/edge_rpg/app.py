import argparse
import json
import logging
import os
from pathlib import Path
from queue import Empty, Queue
import signal
import threading
import time
from .audio import AudioWorker
from .config import load_config
from .dialogue import LlamaCppDialogueBackend, available_mb
from .messages import Kind
from .network import GpsServer
from .perception import InferenceGate, VisionWorker
from .world import World


class JsonFormatter(logging.Formatter):
    def format(self,record):
        return json.dumps({'timestamp':time.time(),'subsystem':record.name,'level':record.levelname,'message':record.getMessage()},ensure_ascii=False)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='config/game.yaml')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--seconds',type=float,default=0,help='Exit after a bounded smoke run')
    parser.add_argument('--demo',action='store_true',help='Explicit synthetic GPS/vision; separate database and test geofence')
    parser.add_argument('--screenshot')
    parser.add_argument('--port',type=int,help='Override the GPS port; 0 selects an available port')
    args=parser.parse_args()
    handler=logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    cfg=load_config(args.config)
    if args.port is not None:
        cfg['network']['port']=args.port
    if args.demo:
        from .demo import configure_demo
        configure_demo(cfg)
    world=World(cfg)
    subsystems={Kind.GPS_UPDATED:'LOCATION',Kind.GPS_INVALID:'LOCATION',Kind.CELL_ENTERED:'EXPLORE',
                Kind.CELL_BLOCKED:'EXPLORE',Kind.EXPLORATION_UPDATED:'EXPLORE',Kind.SCENE_OBSERVED:'VISION',
                Kind.THRESHOLD:'EXPLORE',Kind.EVENT_CREATED:'EVENT',Kind.NPC_INTERACTION:'NPC',Kind.QUEST_UPDATED:'QUEST'}
    world.bus.listeners.append(lambda message: logging.getLogger(subsystems.get(message.kind,'WORLD')).info(
        '%s %s',message.kind,json.dumps(message.payload,default=str,ensure_ascii=False)))
    gate=InferenceGate()
    vision=VisionWorker(cfg['vision'],world.bus,gate)
    audio=AudioWorker(cfg['audio'],world.bus,gate)
    dialogue=LlamaCppDialogueBackend(cfg['dialogue'],gate)
    network=GpsServer(cfg['network'],world.bus)
    ui=None
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    start=time.monotonic()
    last_request=0
    requested=None
    last_demo=0
    dialogue_results=Queue()
    dialogue_thread=None
    cpu_time=time.process_time()
    metric_time=time.monotonic()
    cpu=0
    gps_times=[]
    def interact(intent):
        nonlocal dialogue_thread
        canonical=world.interaction(intent)
        if intent=='TALK' and cfg['dialogue']['llm_enabled'] and (dialogue_thread is None or not dialogue_thread.is_alive()):
            cell=world.cell
            facts={'canonical':canonical,'npc':world.store.one('SELECT name,dialogue_state FROM npcs WHERE cell_id=?',(cell,))}
            dialogue_thread=threading.Thread(target=lambda:dialogue_results.put((cell,canonical,dialogue.generate(facts))),daemon=True)
            dialogue_thread.start()
    try:
        if not args.headless:
            from .ui import BoardUI
            ui=BoardUI(cfg['ui'])
        network.start()
        if not network.ready.wait(3) or network.error:
            raise RuntimeError(f'GPS receiver failed: {network.error}')
        logging.getLogger('LOCATION').info('listening port=%s',network.port)
        while running and (ui is None or ui.running):
            now=time.monotonic()
            if args.seconds and now-start>=args.seconds:
                break
            if args.demo and now-last_demo>=1:
                from .demo import feed_demo
                feed_demo(world,now-start)
                last_demo=now
            for _ in range(64):
                try:
                    msg=world.bus.queue.get_nowait()
                except Empty:
                    break
                if msg.kind==Kind.GPS_UPDATED:
                    world.gps(msg.payload['packet'])
                    gps_times.append(now)
                elif msg.kind==Kind.GPS_INVALID:
                    world.location.usable=False
                    world.location.status=msg.payload['reason']
                    world.freeze(msg.payload['reason'])
                elif msg.kind==Kind.SCENE_OBSERVED:
                    world.observe(**msg.payload)
                elif msg.kind==Kind.VOICE_INTENT:
                    interact(msg.payload['intent'])
            world.tick()
            cell=world.current()
            if not args.demo and cell and (world.grid or cell['state']=='DISCOVERING') and world.eligible():
                if requested!=world.cell or now-last_request>=cfg['vision']['retry_sec']:
                    requested=world.cell
                    last_request=now
                    vision.request(world.cell)
            else:
                vision.requested=None
            try:
                cell_id,canonical,text=dialogue_results.get_nowait()
                if cell_id==world.cell and canonical==world.dialogue:
                    world.dialogue=text
            except Empty:
                pass
            if now-metric_time>=1:
                used=time.process_time()
                cpu=100*(used-cpu_time)/(now-metric_time)
                metric_time,cpu_time=now,used
            gps_times=[t for t in gps_times if now-t<5]
            rss=int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')/1048576
            metrics=f"RAM {rss:.0f}MB / free {available_mb():.0f}MB | CPU {cpu:.0f}% | GPS {len(gps_times)/5:.1f}Hz | vision {vision.latency_ms:.0f}ms {vision.camera_fps:.1f}fps | ASR {audio.latency_ms:.0f}ms | LLM {dialogue.latency_ms:.0f}ms | DB {world.last_db_ms:.1f}ms"
            if ui:
                for intent in ui.input():
                    interact(intent)
                ui.draw(world,('SIMULATION | ' if args.demo else '')+metrics)
            else:
                time.sleep(0.02)
        if ui and args.screenshot:
            import pygame
            pygame.image.save(ui.screen,args.screenshot)
    finally:
        if hasattr(network,'thread'):
            network.close()
        audio.close()
        vision.close()
        if ui:
            ui.close()
        world.close()


if __name__=='__main__':
    main()
