#!/usr/bin/env python3
"""Replay a GPS JSONL fixture at real-time cadence to a development world only."""
import argparse
import asyncio
import json
import time
from pathlib import Path
from websockets.asyncio.client import connect

p=argparse.ArgumentParser()
p.add_argument('route',type=Path)
p.add_argument('--url',default='ws://127.0.0.1:8765/location')
p.add_argument('--token',default='')
a=p.parse_args()
async def replay():
    headers={'Authorization':'Bearer '+a.token} if a.token else {}
    async with connect(a.url,additional_headers=headers,proxy=None) as ws:
        for line in a.route.read_text().splitlines():
            packet=json.loads(line)
            packet['timestamp_ms']=time.time()*1000
            await ws.send(json.dumps(packet))
            print(await ws.recv())
            await asyncio.sleep(1)
asyncio.run(replay())
