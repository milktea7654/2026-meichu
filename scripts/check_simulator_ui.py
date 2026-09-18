"""Browser smoke test with an isolated temporary world. Requires Playwright Chromium."""
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

with socket.socket() as sock:
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='fieldbound-ui-') as directory:
    process=subprocess.Popen([sys.executable,'-m','edge_rpg.simulator','--data',directory,'--port',str(port),'--gps-port','0'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urlopen(url+'/api/state',timeout=1): break
            except OSError: time.sleep(.1)
        else: raise AssertionError('Simulator failed to start')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            page.wait_for_function("window.document.getElementById('save-state').textContent.includes('SQLite 已同步')")
            for _ in range(15):
                if page.locator('#event-label').inner_text()=='NPC 相遇': break
                with page.expect_response('**/api/action'):
                    page.locator('#walk').click()
                page.wait_for_function('!busy')
            assert page.locator('#event-label').inner_text()=='NPC 相遇'
            for command in ['TALK','ACCEPT','INSPECT','TALK']:
                with page.expect_response('**/api/action'):
                    page.locator(f'[data-command="{command}"]').click()
            assert '50' in page.locator('#player-stats').inner_text()
            assert '任務完成' in page.locator('#quest-hint').inner_text()
            page.locator('[data-page="database"]').click()
            page.locator('[data-table="quests"]').click()
            assert 'COMPLETED' in page.locator('#table-body').inner_text()
            page.locator('[data-page="generator"]').click()
            assert 'NPC_ENCOUNTER' in page.locator('#generated-event').inner_text()
            page.reload()
            page.wait_for_function("window.document.getElementById('player-stats').textContent.includes('50')")
            assert '任務完成' in page.locator('#quest-hint').inner_text()
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(200)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
            # Exercise the browser's actual watchPosition -> HTTP -> World path,
            # with Chromium providing a controlled GPS fix (not a real phone test).
            snapshot=page.request.get(url+'/api/state').json()
            lat,lon=snapshot['zones'][0]['center']
            page.context.grant_permissions(['geolocation'])
            page.context.set_geolocation({'latitude':lat,'longitude':lon,'accuracy':4})
            page.locator('#gps-mode').select_option('browser')
            page.wait_for_function("state.mode==='browser' && state.totals.visited===1")
            assert page.locator('#walk').is_disabled()
            assert page.evaluate('state.database').endswith('gps-grid.db')
            page.locator('#gps-mode').select_option('bridge')
            page.wait_for_function("state.mode==='bridge'")
            import asyncio, json
            from websockets.asyncio.client import connect
            async def gps_bridge():
                async with connect(f"ws://127.0.0.1:{snapshot['gps_port']}/location",proxy=None) as ws:
                    await ws.send(json.dumps({'type':'location','latitude':lat,'longitude':lon,'accuracy_m':3,'timestamp_ms':time.time()*1000}))
                    assert json.loads(await ws.recv())['type']=='ack'
                    await asyncio.sleep(.7)
            asyncio.run(gps_bridge())
            state=page.request.get(url+'/api/state').json()
            assert state['totals']['visited']==1  # Same real cell, no extra credit.
            assert state['position'] is not None
            assert not errors,errors
            browser.close()
        print('PASS: browser exploration, NPC quest, SQLite rows, generator, reload persistence, mobile layout, browser geolocation and Android WebSocket GPS protocol; no JS errors')
    finally:
        process.terminate()
        process.wait(timeout=5)
