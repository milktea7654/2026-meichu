import sqlite3
import pytest
from edge_rpg.simulator import Simulator


def test_simulator_quest_and_restart(tmp_path):
    sim = Simulator(tmp_path)
    try:
        for _ in range(5): s = sim.action('walk')
        assert s['event']['type'] == 'NPC_ENCOUNTER'
        for command in ('TALK','ACCEPT','INSPECT','TALK'): s = sim.action('command',command)
        assert s['quest']['state'] == 'COMPLETED'
        assert s['player']['xp'] == 50
        sim.action('back')
        s = sim.action('walk')
        assert s['quest']['state'] == 'COMPLETED'
        assert s['totals'] == {'visited':6,'pending':0,'events_created':1,'target':6}
        path = s['database']
    finally: sim.close()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT state FROM quests').fetchone()[0] == 'COMPLETED'
    restored = Simulator(tmp_path)
    try:
        s = restored.snapshot()
        assert s['player']['xp'] == 50
        assert s['totals']['visited'] == 6
        assert s['generator']['candidate'] == 'NPC_ENCOUNTER'
    finally: restored.close()


@pytest.mark.parametrize('condition', ['inaccurate','disconnected'])
def test_invalid_gps_cannot_light_cells(tmp_path, condition):
    sim = Simulator(tmp_path)
    try:
        before = sim.snapshot()['totals']
        sim.action('condition',condition)
        for _ in range(12): sim.action('walk')
        assert sim.snapshot()['totals'] == before
    finally: sim.close()


@pytest.mark.parametrize('condition', ['indoor','camera_off'])
def test_vision_is_optional_for_gps_exploration(tmp_path, condition):
    sim = Simulator(tmp_path)
    try:
        sim.action('condition',condition)
        for _ in range(11): sim.action('walk')
        s = sim.snapshot()
        assert s['totals'] == {'visited':12,'pending':0,'events_created':2,'target':6}
    finally: sim.close()


def test_live_and_simulation_are_separate(tmp_path):
    sim = Simulator(tmp_path)
    try:
        s = sim.action('mode','browser')
        assert s['totals']['visited'] == 0
        assert s['position'] is None
        with pytest.raises(ValueError): sim.action('walk')
        lat,lon = sim.world.grid.center(sim.zones['park'])
        s = sim.action('gps',{'type':'location','latitude':lat,'longitude':lon,'accuracy_m':3,'timestamp_ms':sim.world.clock()*1000})
        assert s['totals']['visited'] == 1
        assert s['cell']['state'] == 'EXPLORED'
        assert s['database'].endswith('gps-grid.db')
        s = sim.action('mode','simulation')
        assert s['database'].endswith('simulation-grid.db')
        assert s['totals']['visited'] == 1
    finally: sim.close()


def test_disconnected_zone_selection_keeps_position(tmp_path):
    sim = Simulator(tmp_path)
    try:
        before = sim.action('condition','disconnected')
        after = sim.action('zone','water')
        assert after['position'] == before['position']
        assert after['totals'] == before['totals']
    finally: sim.close()
