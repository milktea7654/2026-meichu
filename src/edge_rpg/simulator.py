"""Local browser simulator. Reuses World; never opens the production world DB."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
from queue import Empty
from .grid import SquareGrid
from .messages import Kind
from .network import GpsServer
from .config import load_config
from .events import BIAS, TYPES, choose_event, map_context
from .world import World

PRESETS = {
    'park': {'name': '林間步道', 'scene': 'park', 'objects': ['tree', 'bench']},
    'water': {'name': '河畔石橋', 'scene': 'riverside', 'objects': ['bridge', 'river']},
    'plaza': {'name': '校園廣場', 'scene': 'plaza', 'objects': ['building', 'bench']},
    'ruins': {'name': '古老石像', 'scene': 'park', 'objects': ['statue', 'tree']},
}
TABLES = ('exploration_totals', 'world_meta', 'player', 'map_cells', 'scene_observations', 'events', 'event_log', 'quests', 'npcs', 'npc_memory', 'inventory', 'items', 'world_flags')
TITLES = {'DISCOVERY': '路徑上的新發現', 'NPC_ENCOUNTER': '林間的旅人', 'RESOURCE': '路旁的藥草', 'QUEST': '遺落的護符', 'COMBAT': '擋路的暗影', 'LANDMARK': '遠方留下的記號', 'REST': '片刻歇息', 'RARE': '意外的收穫'}
TEXTS = {
    'DISCOVERY': '你在這片區域留下了第一筆探索紀錄。調查此處，把發現寫入日誌。',
    'NPC_ENCOUNTER': '一位旅人正低頭尋找什麼。他的護符似乎掉在附近的步道上。',
    'QUEST': '一位旅人向你招手，希望你幫忙找回遺失的護符。',
    'RESOURCE': '你發現了可以收集的藥草。調查後即可放入背包。',
    'COMBAT': '一團虛構的暗影擋在故事中的路上。調查可進行一回合規則戰鬥。',
    'LANDMARK': '環境中的地標成為這個世界的一部分。調查可完成這筆紀錄。',
    'REST': '這裡適合停下腳步。調查可恢復生命值。',
    'RARE': '你留意到一份少見的補給。調查可收集它。',
}


class Simulator:
    def __init__(self, directory, config='config/game.yaml'):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.cfg = load_config(config)
        self.cfg['vision']['enabled'] = False
        self.cfg['audio']['enabled'] = False
        self.cfg['dialogue']['llm_enabled'] = False
        self.cfg['location']['smoothing_alpha'] = 1
        grid = SquareGrid(self.cfg['exploration']['cell_size_m'])
        root = grid.at(24.796, 120.996)
        x, y = grid.indices(root)
        self.zones = {key: grid.id(x,y+i*4) for i,key in enumerate(PRESETS)}
        target_cell = grid.id(x+self.cfg['exploration']['cells_per_event']-1,y)
        context = map_context(None, self.cfg['vision']['confidence'])
        self.cfg['world_seed'] = next(seed for seed in range(10000) if choose_event(seed, target_cell, context)[1] == 'NPC_ENCOUNTER')
        self.cfg['database'] = str(self.directory/'simulation-grid.db')
        self.now = time.time()
        self.zone, self.step, self.condition = 'park', 0, 'normal'
        self.mode = 'simulation'
        self.message = '每走進一個新格子就永久點亮；重走不重複累積。'
        self.sim_world = World(self.cfg, clock=lambda: self.now)
        from copy import deepcopy
        live_cfg = deepcopy(self.cfg)
        live_cfg['database'] = str(self.directory/'gps-grid.db')
        live_cfg['world_seed'] = load_config(config)['world_seed']
        self.live_world = World(live_cfg)
        self.gps_port = None
        saved = self.sim_world.store.one("SELECT value FROM settings WHERE key='simulator'")
        if saved:
            state = json.loads(saved['value'])
            self.zone, self.step = state['zone'], state['step']
            self.now = max(self.now, state['time']+60)
        self.sample()

    @property
    def world(self):
        return self.sim_world if self.mode == 'simulation' else self.live_world

    def pump(self):
        for _ in range(256):
            try:
                message = self.live_world.bus.queue.get_nowait()
            except Empty:
                break
            if self.mode != 'bridge':
                continue
            if message.kind == Kind.GPS_UPDATED:
                self.live_world.gps(message.payload['packet'])
            elif message.kind == Kind.GPS_INVALID:
                self.live_world.location.usable = False
                self.live_world.freeze('GPS_DISCONNECTED')
        if self.mode != 'simulation':
            self.live_world.tick()

    @staticmethod
    def observation(zone, timestamp):
        preset = PRESETS[zone]
        return {'timestamp': timestamp, 'scene': preset['scene'], 'scene_confidence': .94,
                'objects': [{'class': name, 'confidence': .91} for name in preset['objects']], 'indoor_probability': .02}

    def sample(self):
        self.now += self.cfg['exploration']['cell_size_m'] / 1.4  # Virtual walking time, not a dwell requirement.
        w = self.sim_world
        x, y = w.grid.indices(self.zones[self.zone])
        lat, lon = w.grid.center(w.grid.id(x+self.step,y))
        w.gps({'type':'location','latitude':lat,'longitude':lon,'accuracy_m':30 if self.condition=='inaccurate' else 3,'speed_mps':1,'timestamp_ms':self.now*1000})
        scene = self.observation(self.zone, self.now)
        if self.condition == 'indoor':
            scene['indoor_probability'] = .98
        if self.condition != 'camera_off':
            w.observe(w.cell, scene, bytes([((self.step//3)%5)*55]*128).hex())
        with w.store.db:
            w.store.db.execute("INSERT OR REPLACE INTO settings VALUES('simulator',?)", (json.dumps({'zone':self.zone,'step':self.step,'time':self.now}),))

    def action(self, action, value=None):
        if action == 'mode' and value in ('simulation','browser','bridge'):
            self.mode = value
            self.live_world.location.usable = False
            self.live_world.freeze('WAIT_FOR_PHONE_GPS')
            self.message = {'simulation':'模擬定位：每步跨進相鄰格子，存檔與真實 GPS 分開。', 'browser':'等待瀏覽器定位授權；只使用裝置提供的經緯度。', 'bridge':f'等待 Android GPS Bridge：ws://電腦區網IP:{self.gps_port}/location'}[value]
        elif action == 'gps' and self.mode == 'browser':
            if not isinstance(value, dict):
                raise ValueError('GPS packet must be an object')
            self.live_world.gps(value)
        elif action in ('walk','back','zone','condition') and self.mode != 'simulation':
            raise ValueError('真實 GPS 模式不能用模擬按鈕移動')
        elif action in ('walk','back'):
            if self.condition == 'disconnected':
                self.now += 5
                self.world.tick()
                self.message = 'GPS 已中斷，新的格子不會被點亮。'
            else:
                self.step += 1 if action == 'walk' else -1
                self.sample()
                self.message = '位置已更新。只有首次踏入的格子會增加 EVENT 計數。'
        elif action == 'zone' and value in PRESETS:
            if self.condition != 'disconnected':
                self.now += 120
                self.zone, self.step = value, 0
                self.sample()
                self.message = f'切到模擬起點：{PRESETS[value]["name"]}；場景為測試資料。'
        elif action == 'condition' and value in ('normal','indoor','inaccurate','camera_off','disconnected'):
            self.condition = value
            if value in ('camera_off','indoor'):
                self.world._last_scene = None
            if value == 'disconnected':
                self.now += self.cfg['location']['stale_sec']+1
                self.world.tick()
            else:
                self.sample()
            self.message = '相機不再是點亮或觸發事件的必要條件；GPS 無效才暫停累積。'
        elif action == 'command' and value in ('TALK','ACCEPT','REFUSE','INSPECT','LEAVE'):
            self.message = translate(self.world.interaction(value))
        else:
            raise ValueError('Unknown simulator action')
        return self.snapshot()

    def snapshot(self):
        self.pump()
        w = self.world
        current = w.current()
        tables = {name: w.store.all(f'SELECT * FROM {name} ORDER BY rowid DESC LIMIT 100') for name in TABLES}
        counts = {name: w.store.one(f'SELECT COUNT(*) AS n FROM {name}')['n'] for name in TABLES}
        observation = w.scene(w.clock())
        event = w.store.one('SELECT * FROM events WHERE cell_id=?', (w.cell,))
        if event:
            context = json.loads(event['payload_json'])
            observation = context.get('source_observation')
        else:
            context = map_context(observation, self.cfg['vision']['confidence'])
        event_id, kind = choose_event(w.cfg['world_seed'], w.cell, context)
        npc = w.store.one('SELECT * FROM npcs WHERE cell_id=?', (w.cell,))
        quest = w.store.one('SELECT * FROM quests WHERE quest_id=?', (npc['quest_id'],)) if npc else None
        totals = w.totals()
        threshold = totals['target']
        quest_xp = json.loads(quest['rewards'])['xp'] if quest else self.cfg['rules']['quest_xp']
        if not event:
            story = {'title':'每條路，都有尚未寫下的故事。','text':f'每踏入 {threshold} 個未探索格子就觸發一次 EVENT。目前累積 {totals["pending"]} 格；已點亮的格子會永久保留。'}
        else:
            story = {'title':TITLES[event['type']], 'text':TEXTS[event['type']]}
            if quest:
                if quest['state']=='COMPLETED': story['text']='你把護符還給了旅人。他向你道謝。這段故事已經寫入世界，不會因重返此地而重演。'
                elif quest['stage']==1: story['text']='你在步道上找到了護符。再與旅人交談，就能交付並完成任務。'
                elif quest['state']=='ACTIVE': story['text']='旅人正在等你。調查所在區域，尋找遺落的護符。'
        visible = w.grid.disk(w.cell or self.zones['park'],12)
        placeholders = ','.join('?' for _ in visible)
        saved = {r['cell_id']:r for r in w.store.all(f'SELECT cell_id,state,event_id FROM map_cells WHERE cell_id IN ({placeholders})',visible)}
        return {'zone':self.zone,'zones':[{'id':key,'name':PRESETS[key]['name'],'cell':cell,'center':w.grid.center(cell)} for key,cell in self.zones.items()],
                'position':w.location.last.point if w.location.last else None,'cell':current,'status':w.status,'condition':self.condition,'message':self.message,
                'story':story,'event':event,'npc':npc,'quest':quest,'quest_xp':quest_xp,'totals':totals,'threshold':threshold,'mode':self.mode,'gps_port':self.gps_port,'cell_size_m':w.grid.size,
                'player':tables['player'][0], 'tables':tables,'counts':counts,'database':w.cfg['database'],
                'cells':[{'id':cell,'boundary':w.grid.boundary(cell), 'center':w.grid.center(cell), 'saved':saved.get(cell)} for cell in visible],
                'generator':{'observation':observation,'context':context,'seed':w.cfg['world_seed'],'hash':hashlib.sha256(f"{w.cfg['world_seed']}:{w.cell}".encode()).hexdigest(),
                             'observation_note':'事件當下實際使用的觀察；null 表示未使用相機。' if event else '目前場景觀察（可選）；沒有觀察時使用通用戶外事件。',
                             'weights':dict(zip(TYPES,BIAS[context['archetype']])),'candidate':kind,'candidate_id':event_id,'existing':event,'backend':'Template / 規則式生成（未啟用 LLM）'},
                'time':self.now}

    def close(self):
        self.sim_world.close()
        self.live_world.close()


def translate(text):
    completed = re.fullmatch(r'Charm returned\. Quest complete! \+(\d+) XP\.', text)
    if completed:
        return f'護符已交還，任務完成！獲得 {completed.group(1)} XP。'
    return {
        'I lost my charm here. Will you help me look?':'「我的護符掉在這附近了，你願意幫我找找嗎？」',
        'Quest accepted. Investigate here on the permitted path.':'已接受任務：遺失的護符。按「調查」搜尋此處。',
        'You found a charm. Talk to the traveler to return it.':'找到護符！已加入背包。按「交談」交付給旅人。',
        'Charm returned. Quest complete! +50 XP.':'護符已交還，任務完成！獲得 50 XP。',
        'Thank you for helping.':'「謝謝你的幫忙，我會記得你的。」',
        'Investigate this area, then return the charm.':'「請在這附近調查，找到護符後再交給我。」',
        'Maybe another time.':'「沒關係，也許下次吧。」',
        'There is nothing more to do here.':'這裡沒有尚待完成的互動。',
        'Interaction closed.':'已結束交談。',
        'Keep exploring this permitted outdoor area.':'這裡尚未觸發事件，繼續探索吧。',
        'Interaction paused: a valid outdoor position is required.':'互動暫停：需要有效的戶外定位。',
        'Discovery recorded in your journal.':'這次發現已寫入探索日誌。',
        'Trail herb added to your inventory.':'已將藥草加入背包。',
        'You rest and recover.':'你稍作休息，恢復了生命值。',
        'You overcame a shadow. Combat resolved.':'你擊退了暗影，本次戰鬥結束。',
    }.get(text,text)


def serve(simulator, port):
    static = Path(__file__).parent/'web'
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/api/state':
                self.respond(200,json.dumps(simulator.snapshot(),ensure_ascii=False).encode(),'application/json; charset=utf-8')
            elif self.path in ('/','/app.js','/style.css'):
                name = 'index.html' if self.path=='/' else self.path[1:]
                mime = {'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name]
                self.respond(200,(static/name).read_bytes(),mime+'; charset=utf-8')
            else:
                self.respond(404,b'Not found','text/plain')

        def do_POST(self):
            # Simulation controls are localhost-only and require JSON, no cross-origin access.
            origin = self.headers.get('Origin')
            if self.path!='/api/action' or (origin and origin!=f'http://{self.headers.get("Host")}') or self.headers.get('Content-Type')!='application/json':
                self.respond(403,b'Forbidden','text/plain')
                return
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 4096: raise ValueError('Invalid request length')
                data = json.loads(self.rfile.read(size))
                state = simulator.action(data['action'],data.get('value'))
                self.respond(200,json.dumps(state,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            except (ValueError,KeyError,TypeError) as exc:
                self.respond(400,json.dumps({'error':str(exc)}).encode(),'application/json')

        def log_message(self, *_):
            pass
    class Server(HTTPServer):
        def service_actions(self):
            simulator.pump()
    return Server(('127.0.0.1',port),Handler)


def main():
    p = argparse.ArgumentParser(description='Local game + SQLite + story simulator')
    p.add_argument('--port',type=int,default=8787)
    p.add_argument('--gps-port',type=int,default=8765)
    p.add_argument('--data',default='data/simulator')
    p.add_argument('--config',default='config/game.yaml')
    args = p.parse_args()
    sim = Simulator(args.data,args.config)
    network = GpsServer({**sim.cfg['network'], 'port':args.gps_port}, sim.live_world.bus)
    network.start()
    if not network.ready.wait(3) or network.error:
        sim.close()
        raise RuntimeError(f'GPS receiver failed: {network.error}')
    sim.gps_port = network.port
    server = serve(sim,args.port)
    print(f'Simulator: http://127.0.0.1:{server.server_port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        network.close()
        server.server_close()
        sim.close()


if __name__=='__main__':
    main()
