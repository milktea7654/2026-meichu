import asyncio
import hmac
import json
import logging
import threading
from websockets.asyncio.server import serve
from .messages import Kind


class GpsServer:
    """One active phone, GPS packets only, bounded frames and world queue."""
    def __init__(self, config, bus):
        self.cfg, self.bus = config, bus
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.port = config["port"]
        self.active = None

    async def handler(self, ws):
        if ws.request.path != "/location":
            await ws.close(1008,"Use /location")
            return
        token = self.cfg.get("token","")
        if token and not hmac.compare_digest(ws.request.headers.get("Authorization",""),"Bearer "+token):
            await ws.close(1008,"Unauthorized")
            return
        if self.active is not None:
            await ws.close(1008,"A GPS bridge is already connected")
            return
        self.active = ws
        try:
            async for raw in ws:
                try:
                    packet = json.loads(raw)
                    if not isinstance(packet,dict) or packet.get("type") != "location":
                        raise ValueError("Only location packets accepted")
                    self.bus.publish(Kind.GPS_UPDATED, packet=packet)
                    await ws.send('{"type":"ack"}')
                    await asyncio.sleep(0.05)
                except (ValueError, TypeError):
                    await ws.send('{"type":"error","reason":"invalid_location_packet"}')
        finally:
            self.active = None
            self.bus.publish(Kind.GPS_INVALID, reason="GPS_DISCONNECTED")

    async def run(self):
        try:
            async with serve(self.handler,self.cfg["host"],self.port,max_size=2048,max_queue=4,ping_interval=2,ping_timeout=5) as server:
                self.port = server.sockets[0].getsockname()[1]
                self.ready.set()
                while not self.stop.is_set():
                    await asyncio.sleep(0.1)
        except Exception as exc:
            self.error = exc
            self.ready.set()
            logging.getLogger("LOCATION").exception("network_failed")

    def start(self):
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()),daemon=True,name="gps-network")
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
