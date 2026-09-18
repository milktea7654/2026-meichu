import json
import math
import sqlite3
import socket
import subprocess
import h3
import pytest
from edge_rpg.world import World
from edge_rpg.dialogue import LlamaCppDialogueBackend
from edge_rpg.perception import InferenceGate
from edge_rpg.audio import parse_intent
from conftest import packet,scene,complete


def test_T01_valid_gps(setup):
    w,c,_=setup
    w.gps(packet(c))
    assert w.location.status=='READY' and w.location.last


@pytest.mark.parametrize('accuracy',[16,25,26,100])
def test_T02_inaccurate_does_not_progress(setup,accuracy):
    w,c,_=setup
    w.gps(packet(c))
    for _ in range(5):
        c.advance()
        w.gps(packet(c,accuracy_m=accuracy))
    assert w.current()['progress']==0


def test_T03_new_cell(setup):
    w,c,_=setup
    w.gps(packet(c))
    assert w.current()['state']=='DISCOVERING'


def test_T04_threshold_and_transaction(setup):
    w,c,_=setup
    w.gps(packet(c))
    # Drive persisted component boundary, then real scene callback evaluates it.
    with w.store.db:
        w.store.db.execute('UPDATE map_cells SET dwell=30,movement=?',(25*(0.69-0.35)/0.35,))
        w._last_scene=(w.cell,scene(c,objects=[]))
        w._progress(c())
    assert w.current()['progress']==pytest.approx(.69)
    assert not w.store.all('SELECT * FROM events')
    with w.store.db:
        w.store.db.execute('UPDATE map_cells SET movement=25')
        w._progress(c())
    assert w.current()['state']=='EXPLORED'
    assert len(w.store.all('SELECT * FROM events'))==1
    with w.store.db: w._progress(c())
    assert len(w.store.all('SELECT * FROM events'))==1


def test_T05_reenter(setup):
    w,c,_=setup
    complete(w,c)
    count=len(w.store.all('SELECT * FROM events'))
    p=packet(c)
    c.advance(90)
    w.gps(packet(c,p['latitude']+.001,p['longitude']))
    c.advance(90)
    w.gps(packet(c))
    assert w.current()['state']=='EXPLORED'
    assert len(w.store.all('SELECT * FROM events'))==count


def test_T06_reboot_preserves_world_and_quest(setup):
    w,c,cfg=setup
    complete(w,c)
    before=w.store.all('SELECT * FROM events')
    other=World(cfg,c)
    try:
        assert other.store.all('SELECT * FROM events')==before
        assert other.store.all('SELECT * FROM map_cells')==w.store.all('SELECT * FROM map_cells')
        assert other.store.all('SELECT * FROM quests')==w.store.all('SELECT * FROM quests')
        assert other.previous is None
    finally: other.close()


def test_T07_blocked(setup,tmp_path):
    w,c,cfg=setup
    w.safety.blocked=w.safety.allowed
    w.gps(packet(c))
    for _ in range(40):
        c.advance(); w.gps(packet(c))
        w.observe(w.cell,scene(c),'00'*128)
    assert w.current()['state']=='BLOCKED'
    assert w.current()['progress']==0
    assert not w.store.all('SELECT * FROM events')


def test_T08_indoor(setup):
    w,c,_=setup
    w.gps(packet(c))
    with w.store.db: w.store.db.execute('UPDATE map_cells SET dwell=30,movement=25')
    w.observe(w.cell,scene(c,indoor=.99),'00'*128)
    assert not w.store.all('SELECT * FROM events')
    assert w.status=='INDOOR_GUARD'


def test_T09_disconnect_freezes_time(setup):
    w,c,_=setup
    w.gps(packet(c))
    c.advance(10); w.tick()
    assert w.status=='GPS_STALE'
    w.gps(packet(c))
    assert w.current()['dwell']==0


def test_T10_jump(setup):
    w,c,_=setup
    w.gps(packet(c)); old=w.location.last
    c.advance()
    w.gps(packet(c,latitude=25.1))
    assert w.location.status=='GPS_JUMP'
    assert w.location.last==old


def test_T11_vision_failure_waits(setup):
    w,c,_=setup
    w.gps(packet(c))
    with w.store.db:
        w.store.db.execute('UPDATE map_cells SET dwell=30,movement=25')
        w._progress(c())
    assert w.status=='WAIT_FOR_SCENE'
    assert not w.store.all('SELECT * FROM events')
    assert w.interaction('INVENTORY')=='Inventory open.'


@pytest.mark.parametrize('failure',[OSError('missing'),subprocess.TimeoutExpired('llama',1),subprocess.CalledProcessError(1,'llama')])
def test_T12_llm_failure(setup,monkeypatch,failure):
    _,_,cfg=setup
    cfg['dialogue']['llm_enabled']=True
    monkeypatch.setattr('edge_rpg.dialogue.available_mb',lambda:1000)
    def fail(*a,**k): raise failure
    monkeypatch.setattr(subprocess,'run',fail)
    backend=LlamaCppDialogueBackend(cfg['dialogue'],InferenceGate())
    assert backend.generate({'canonical':'Hello traveler.'})=='Hello traveler.'


def test_T13_mic_failure_buttons_work(setup,monkeypatch):
    from edge_rpg.audio import AudioWorker
    w,_,cfg=setup
    cfg['audio']['enabled']=True
    def fail(*a,**k): raise OSError('no ALSA device')
    monkeypatch.setattr(subprocess,'Popen',fail)
    worker=AudioWorker(cfg['audio'],w.bus,InferenceGate())
    worker.thread.join(1)
    assert worker.status=='microphone unavailable'
    assert w.interaction('MAP')=='Map open.'
    worker.close()


def test_T14_unique_database_constraint(setup):
    w,c,_=setup
    complete(w,c)
    e=w.store.one('SELECT * FROM events')
    with pytest.raises(sqlite3.IntegrityError),w.store.db:
        w.store.db.execute("INSERT INTO events(event_id,cell_id,type,status,created_at) VALUES('duplicate',?,'RARE','ACTIVE',?)",(e['cell_id'],c()))


def test_T15_offline(setup,monkeypatch):
    w,c,_=setup
    def denied(*a,**k): raise AssertionError('Internet forbidden')
    monkeypatch.setattr(socket,'create_connection',denied)
    monkeypatch.setattr(socket,'getaddrinfo',denied)
    complete(w,c)
    assert w.current()['state']=='EXPLORED'


def test_quest_workflow_and_idempotent_rewards(setup):
    from edge_rpg.events import choose_event,map_context
    w,c,cfg=setup
    cell=h3.latlng_to_cell(packet(c)['latitude'],packet(c)['longitude'],11)
    context=map_context(scene(c),cfg['vision']['confidence'])
    seed=next(s for s in range(1000) if choose_event(s,cell,context)[1]=='NPC_ENCOUNTER')
    cfg['world_seed']=seed
    complete(w,c)
    assert w.store.one('SELECT * FROM npcs')
    assert 'lost' in w.interaction('TALK')
    w.interaction('ACCEPT'); w.interaction('INSPECT'); w.interaction('TALK')
    assert w.store.one('SELECT * FROM quests')['state']=='COMPLETED'
    assert w.store.one('SELECT * FROM inventory WHERE item_id="lost_charm"')['quantity']==0
    assert w.store.one('SELECT * FROM player')['xp']==50
    w.interaction('TALK'); w.interaction('INSPECT')
    assert w.store.one('SELECT * FROM player')['xp']==50


def test_stationary_jitter_not_movement(setup):
    w,c,_=setup
    p=packet(c)
    for i in range(50):
        c.advance()
        w.gps(packet(c,lat=p['latitude']+(i%2)*0.000005))
    assert w.current()['movement']==0


def test_duplicate_observations(setup):
    w,c,_=setup
    w.gps(packet(c))
    assert w.observe(w.cell,scene(c),'00'*128)
    assert not w.observe(w.cell,scene(c),'01'*128)
    assert len(w.store.all('SELECT * FROM scene_observations'))==1


def test_bad_packets(setup):
    w,c,_=setup
    for p in [None,[],{},packet(c,accuracy_m=float('nan')),packet(c,latitude=True),packet(c,timestamp_ms=c()*1000-6000)]:
        w.gps(p)
        assert not w.location.usable


def test_commands():
    for text,intent in [('調查','INSPECT'),('交談','TALK'),('接受','ACCEPT'),('拒絕','REFUSE'),('離開','LEAVE'),('打開地圖','MAP'),('不要接受','UNKNOWN'),('hello','UNKNOWN')]:
        assert parse_intent(text)==intent


def test_empty_allowlist_denies(setup):
    w,c,_=setup
    w.safety.allowed=[]
    w.gps(packet(c))
    assert w.status=='SAFE_IDLE'


def test_event_rollback_is_atomic(setup,monkeypatch):
    w,c,_=setup
    w.gps(packet(c))
    w._last_scene=(w.cell,scene(c))
    def fail(*a,**k): raise RuntimeError('disk failure simulation')
    monkeypatch.setattr(w.store,'log',fail)
    with pytest.raises(RuntimeError), w.store.db:
        w.store.db.execute('UPDATE map_cells SET dwell=30,movement=25')
        w._progress(c())
    assert not w.store.all('SELECT * FROM events')
    assert w.current()['state']=='DISCOVERING'


def test_missing_speed_still_detects_vehicle_motion(setup):
    w,c,_=setup
    base=packet(c)
    for i in range(8):
        c.advance()
        p=packet(c,lat=base['latitude']+i*0.000045,accuracy_m=15)
        p.pop('speed_mps')
        w.gps(p)
    assert w.location.status=='GPS_DISPLAY_ONLY'
    assert not w.location.usable


def test_low_confidence_uses_generic_context(setup):
    from edge_rpg.events import map_context
    w,c,_=setup
    assert map_context(scene(c,scene_confidence=.1),.65)['archetype']=='generic_outdoor'


def test_stale_or_wrong_cell_observations_rejected(setup):
    w,c,_=setup
    w.gps(packet(c))
    assert not w.observe('not-current',scene(c),'00'*128)
    old=scene(c)
    c.advance(6)
    w.gps(packet(c))
    assert not w.observe(w.cell,old,'00'*128)
    assert not w.store.all('SELECT * FROM scene_observations')


def test_duplicate_indoor_frame_revokes_outdoor_clearance(setup):
    w,c,_=setup
    w.gps(packet(c))
    assert w.observe(w.cell,scene(c),'00'*128)
    assert not w.observe(w.cell,scene(c,indoor=.99),'00'*128)
    with w.store.db:
        w.store.db.execute('UPDATE map_cells SET dwell=30,movement=25')
        w._progress(c())
    assert not w.store.all('SELECT * FROM events')


def test_polygon_holes_and_multipolygon():
    from edge_rpg.geo import contains
    polygon=[[[0,0],[4,0],[4,4],[0,4],[0,0]],[[1,1],[3,1],[3,3],[1,3],[1,1]]]
    assert contains((.5,.5),polygon)
    assert not contains((2,2),polygon)
    assert not contains((5,5),polygon)


def test_simplified_asr_commands():
    for text,intent in [('调查','INSPECT'),('交谈','TALK'),('打开地图','MAP'),('拒绝','REFUSE'),('离开','LEAVE'),('查看任务','QUESTS')]:
        assert parse_intent(text)==intent


def test_llm_ungrounded_output_falls_back(setup,monkeypatch):
    _,_,cfg=setup
    cfg['dialogue']['llm_enabled']=True
    monkeypatch.setattr('edge_rpg.dialogue.available_mb',lambda:1000)
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:subprocess.CompletedProcess([],0,stdout='Enter the building and take a sword.'))
    backend=LlamaCppDialogueBackend(cfg['dialogue'],InferenceGate())
    assert backend.generate({'canonical':'Hello traveler.'})=='Hello traveler.'


def test_seed_is_process_independent():
    from edge_rpg.events import choose_event
    context={'archetype':'waterside'}
    assert choose_event(123,'8b28308280f4fff',context)==choose_event(123,'8b28308280f4fff',context)
    assert choose_event(124,'8b28308280f4fff',context)[0]!=choose_event(123,'8b28308280f4fff',context)[0]


def test_reboot_quest_inventory_and_rewards(setup):
    w,c,cfg=setup
    from edge_rpg.events import choose_event,map_context
    cell=h3.latlng_to_cell(packet(c)['latitude'],packet(c)['longitude'],11)
    context=map_context(scene(c),cfg['vision']['confidence'])
    cfg['world_seed']=next(s for s in range(1000) if choose_event(s,cell,context)[1]=='QUEST')
    with w.store.db:
        w.store.db.execute("UPDATE world_meta SET value=? WHERE key='world_seed'",(str(cfg['world_seed']),))
    complete(w,c)
    w.interaction('ACCEPT'); w.interaction('INSPECT')
    reopened=World(cfg,c)
    try:
        reopened.gps(packet(c))
        assert reopened.store.one('SELECT state FROM quests')['state']=='ACTIVE'
        assert reopened.store.one("SELECT quantity FROM inventory WHERE item_id='lost_charm'")['quantity']==1
        reopened.interaction('TALK')
        assert reopened.store.one('SELECT state FROM quests')['state']=='COMPLETED'
        assert reopened.store.one('SELECT xp FROM player')['xp']==50
        assert len(reopened.store.all('SELECT * FROM events'))==1
    finally: reopened.close()


@pytest.mark.parametrize('invalid', [
    None,
    {},
    {'scene': None},
    {'objects': [{'confidence': .9}]},
    {'objects': [{'class': [], 'confidence': .9}]},
    {'objects': None},
    {'timestamp': float('nan')},
    {'scene_confidence': True},
    {'indoor_probability': float('inf')},
])
def test_invalid_vision_cannot_poison_next_gps_update(setup, invalid):
    w, c, _ = setup
    w.gps(packet(c))
    good = scene(c)
    assert w.observe(w.cell, good, '00'*128)
    malformed = {**good, **invalid} if isinstance(invalid, dict) else invalid
    if invalid == {}:
        malformed.pop('scene')
    assert not w.observe(w.cell, malformed, 'ff'*128)
    assert w.scene(c()) is None
    c.advance()
    w.gps(packet(c))
    assert not w.store.all('SELECT * FROM events')
    assert len(w.store.all('SELECT * FROM scene_observations')) == 1


def test_backend_cannot_mutate_saved_scene_by_reference(setup):
    w, c, _ = setup
    w.gps(packet(c))
    observation = scene(c)
    assert w.observe(w.cell, observation, '00'*128)
    observation['objects'][0]['class'] = None
    observation['scene'] = None
    assert w.scene(c())['scene'] == 'park'
    assert w.scene(c())['objects'][0]['class'] == 'statue'
