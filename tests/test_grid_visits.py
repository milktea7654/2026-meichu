import json
import pytest
from pyproj import Geod
from edge_rpg.config import load_config
from edge_rpg.grid import SquareGrid
from edge_rpg.world import World
from conftest import Clock


@pytest.fixture
def game(tmp_path):
    cfg = load_config()
    cfg["exploration"].update(cell_size_m=25,cells_per_event=5)
    cfg['database'] = str(tmp_path/'grid.db')
    cfg['location']['smoothing_alpha'] = 1
    c = Clock()
    w = World(cfg,c)
    yield w,c,cfg
    w.close()


def visit(w,c,index,**extra):
    root = w.grid.at(24.796,120.996)
    x,y = w.grid.indices(root)
    lat,lon = w.grid.center(w.grid.id(x+index,y))
    c.advance(35)
    w.gps({'type':'location','latitude':lat,'longitude':lon,'accuracy_m':3,'speed_mps':1,'timestamp_ms':c()*1000,**extra})


def test_immediate_lighting_unique_count_and_multiple_events(game):
    w,c,_ = game
    visit(w,c,0)
    assert w.current()['state'] == 'EXPLORED'
    assert w.totals()['pending'] == 1
    for _ in range(5): visit(w,c,0)
    assert w.totals()['visited'] == 1
    for i in range(1,4): visit(w,c,i)
    assert w.totals()['events_created'] == 0
    visit(w,c,4)
    assert w.current()['event_id']
    assert w.totals()['pending'] == 0
    for i in range(5,12): visit(w,c,i)
    assert w.totals() == {'visited':12,'pending':2,'events_created':2,'target':5}


def test_pending_cells_persist_across_restart(game):
    w,c,cfg = game
    for i in range(3): visit(w,c,i)
    restored = World(cfg,c)
    try:
        visit(restored,c,2)
        assert restored.totals()['pending'] == 3
        for i in (3,4): visit(restored,c,i)
        assert restored.totals()['events_created'] == 1
    finally: restored.close()


def test_atomic_event_failure_does_not_consume_new_cell(game,monkeypatch):
    w,c,_ = game
    for i in range(4): visit(w,c,i)
    original = w._create_event
    def fail(now,scene):
        original(now,scene)
        raise RuntimeError('simulate disk failure')
    monkeypatch.setattr(w,'_create_event',fail)
    with pytest.raises(RuntimeError): visit(w,c,4)
    assert w.totals()['visited'] == 4
    assert w.current() is None
    assert not w.store.all('SELECT * FROM events')
    monkeypatch.setattr(w,'_create_event',original)
    visit(w,c,4)
    assert w.totals()['events_created'] == 1


@pytest.mark.parametrize('latitude',[-65,-10,0,25,60])
def test_fixed_area_and_roundtrip(latitude):
    grid = SquareGrid(25)
    cell = grid.at(latitude,120)
    assert grid.at(*grid.center(cell)) == cell
    boundary = grid.boundary(cell)
    area,_ = Geod(ellps='WGS84').polygon_area_perimeter([p[1] for p in boundary],[p[0] for p in boundary])
    assert abs(area) == pytest.approx(625,abs=.01)


def test_no_interpolation_or_inaccurate_gps_credit(game):
    w,c,_ = game
    visit(w,c,0)
    visit(w,c,10)  # Endpoint only, no invented visits to intervening cells.
    assert w.totals()['visited'] == 2
    visit(w,c,11,accuracy_m=30)
    assert w.totals()['visited'] == 2


def test_grid_settings_cannot_reinterpret_existing_save(game):
    w,c,cfg = game
    visit(w,c,0)
    cfg['exploration']['cell_size_m'] = 50
    with pytest.raises(ValueError,match='cell_size_m'):
        World(cfg,c)


def test_boundary_jitter_is_not_new_exploration(game):
    w,c,_ = game
    root = w.grid.at(24.796,120.996)
    x,y = w.grid.indices(root)
    for delta in (-.05,.05,-.04,.04):
        lat,lon = w.grid.point(x+1+delta,y+.5)
        c.advance(5)
        w.gps({'type':'location','latitude':lat,'longitude':lon,'accuracy_m':4,'timestamp_ms':c()*1000})
        assert w.status == 'GPS_BOUNDARY'
        assert w.totals()['visited'] == 0
    visit(w,c,1)
    assert w.totals()['visited'] == 1
