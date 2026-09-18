import json
import pytest
import h3
from edge_rpg.config import load_config
from edge_rpg.world import World


class Clock:
    def __init__(self): self.now=1800000000.0
    def __call__(self): return self.now
    def advance(self,seconds=1): self.now+=seconds


@pytest.fixture
def setup(tmp_path):
    cfg=load_config()
    cfg["exploration"]["mode"]="legacy_h3"
    cfg["safety"]["require_allowed_area"]=True
    cfg['database']=str(tmp_path/'world.db')
    polygon={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[120.9,24.7],[121.1,24.7],[121.1,24.9],[120.9,24.9],[120.9,24.7]]]},'properties':{}}]}
    allowed=tmp_path/'allowed.json'
    allowed.write_text(json.dumps(polygon))
    cfg['safety']['allowed']=str(allowed)
    cfg['location']['smoothing_alpha']=1
    cfg['vision']['enabled']=False
    cfg['audio']['enabled']=False
    clock=Clock()
    world=World(cfg,clock)
    yield world,clock,cfg
    world.close()


def packet(clock,lat=None,lon=None,**kwargs):
    center=h3.cell_to_latlng(h3.latlng_to_cell(24.796,120.996,11))
    return {'type':'location','latitude':center[0] if lat is None else lat,'longitude':center[1] if lon is None else lon,'accuracy_m':4,'speed_mps':1,'timestamp_ms':clock()*1000,**kwargs}


def scene(clock,indoor=0.02,**kwargs):
    return {'timestamp':clock(),'scene':'park','scene_confidence':0.95,'objects':[{'class':'statue','confidence':0.9}],'indoor_probability':indoor,**kwargs}


def complete(world,clock):
    import math
    base=packet(clock)
    for i in range(65):
        clock.advance()
        world.gps(packet(clock,base['latitude']+math.sin(i/10)*0.0001,base['longitude']+math.cos(i/10)*0.0001))
        world.observe(world.cell,scene(clock),bytes([(i//3)%5*55]*128).hex())
        if world.current()['event_triggered']:
            return
    raise AssertionError('Exploration did not complete')
