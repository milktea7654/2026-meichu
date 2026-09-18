import asyncio
import io
import json
import sqlite3
import time
from queue import Empty
import pytest
from PIL import Image
from websockets.asyncio.client import connect
from edge_rpg.network import GpsServer
from edge_rpg.messages import EventBus,Kind
from edge_rpg.map import MBTiles
from conftest import packet


def test_real_websocket_loopback(setup):
    w,c,cfg=setup
    bus=w.bus
    server=GpsServer({'host':'127.0.0.1','port':0,'token':'test'},bus)
    server.start()
    try:
        assert server.ready.wait(3)
        if isinstance(server.error,PermissionError) or (server.error and 'could not bind' in str(server.error)):
            pytest.skip('Sandbox denies local socket; rerun outside sandbox')
        assert server.error is None
        async def scenario():
            url=f'ws://127.0.0.1:{server.port}/location'
            async with connect(url,additional_headers={'Authorization':'Bearer test'},proxy=None) as ws:
                await ws.send(json.dumps(packet(c)))
                assert json.loads(await ws.recv())['type']=='ack'
                await ws.send('{"type":"command","intent":"ACCEPT"}')
                assert json.loads(await ws.recv())['type']=='error'
            async with connect(url,proxy=None) as ws:
                await ws.wait_closed()
                assert ws.close_code==1008
        asyncio.run(scenario())
        message=bus.queue.get(timeout=2)
        assert message.kind==Kind.GPS_UPDATED
        w.gps(message.payload['packet'])
        assert w.current()['state']=='DISCOVERING'
        assert bus.queue.get(timeout=2).kind==Kind.GPS_INVALID
    finally: server.close()


def test_mbtiles_tms_and_missing(tmp_path):
    path=tmp_path/'map.mbtiles'
    image=Image.new('RGB',(256,256),'green')
    buffer=io.BytesIO(); image.save(buffer,format='PNG')
    db=sqlite3.connect(path)
    db.executescript('CREATE TABLE metadata(name TEXT,value TEXT); CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB);')
    db.execute("INSERT INTO metadata VALUES('format','png')")
    db.execute('INSERT INTO tiles VALUES(2,1,2,?)',(buffer.getvalue(),))
    db.commit(); db.close()
    tiles=MBTiles(path,2)
    assert tiles.tile(2,1,1)==buffer.getvalue()
    assert tiles.tile(2,2,1) is None
    tiles.tile(2,3,1)
    assert len(tiles.cache)==2
    tiles.close()
    absent=MBTiles(tmp_path/'missing')
    assert absent.tile(0,0,0) is None
    absent.close()


def test_ui_headless_render_and_buttons(setup,monkeypatch,tmp_path):
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    import pygame
    from edge_rpg.ui import BoardUI
    w,c,cfg=setup
    w.gps(packet(c))
    ui=BoardUI(cfg['ui'])
    try:
        ui.draw(w,'TEST / OFFLINE')
        assert len(ui.buttons)==8
        rect,intent=ui.buttons[1]
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=rect.center,button=1))
        assert ui.input()==['INSPECT']
        pygame.image.save(ui.screen,str(tmp_path/'ui.png'))
        assert (tmp_path/'ui.png').stat().st_size>1000
    finally: ui.close()
