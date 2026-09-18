"""Explicit synthetic demo; never used by production GPS/vision receivers."""
import json
import math
import tempfile
from pathlib import Path
import h3


def configure_demo(cfg):
    root=Path(tempfile.gettempdir())/'edge-rpg-demo'
    root.mkdir(exist_ok=True)
    cfg['database']=str(root/'world-grid.db')
    allowed={'type':'FeatureCollection','features':[{'type':'Feature','properties':{},'geometry':{'type':'Polygon','coordinates':[[[120.99,24.79],[121.01,24.79],[121.01,24.81],[120.99,24.81],[120.99,24.79]]]}}]}
    (root/'allowed.geojson').write_text(json.dumps(allowed))
    cfg['safety']['allowed']=str(root/'allowed.geojson')
    cfg['vision']['enabled']=False
    cfg['audio']['enabled']=False


def feed_demo(world,elapsed):
    if world.grid:
        cell=world.grid.at(24.796,120.996)
        x,y=world.grid.indices(cell)
        lat,lon=world.grid.point(x+.5+elapsed/world.grid.size,y+.5)
    else:
        cell=h3.latlng_to_cell(24.796,120.996,world.cfg['exploration']['h3_resolution'])
        lat,lon=h3.cell_to_latlng(cell)
        lat+=math.sin(elapsed/10)*0.00010
        lon+=math.cos(elapsed/10)*0.00010
    now=world.clock()
    world.gps({'type':'location','latitude':lat,'longitude':lon,'accuracy_m':3,'speed_mps':1.1,'timestamp_ms':now*1000})
    intensity=int(elapsed//3)%5*55
    scene={'timestamp':now,'scene':'park','scene_confidence':0.92,'objects':[{'class':'tree','confidence':0.91},{'class':'statue','confidence':0.85}],'indoor_probability':0.02}
    world.observe(world.cell,scene,bytes([intensity]*128).hex())
