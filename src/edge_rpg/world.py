"""Single state authority. Every event and its EXPLORED transition commit together."""
import json
import logging
import time
import h3
from .events import map_context, choose_event
from .geo import Safety, distance
from .location import LocationFilter
from .messages import EventBus, Kind
from .storage import Store
from .scene import validate_observation
from .grid import SquareGrid


class World:
    def __init__(self, config, clock=time.time, bus=None):
        self.cfg, self.clock = config, clock
        self.bus = bus or EventBus()
        self.store = Store(config["database"], config)
        self.grid = SquareGrid(config["exploration"]["cell_size_m"]) if config["exploration"].get("mode") == "square_visits" else None
        self.location = LocationFilter(config["location"])
        self.safety = Safety(config["safety"])
        self.cell = None
        self.anchor = None
        self.previous = None
        self.status = "WAIT_FOR_PHONE_GPS"
        self.dialogue = "Connect the GPS bridge to begin."
        self.last_db_ms = 0

    def freeze(self, status):
        self.status = status
        self.previous = None
        self.anchor = None

    def eligible(self):
        if not self.location.fresh(self.clock()):
            self.freeze(self.location.status)
            return False
        fix = self.location.last
        return bool(fix and self.safety.permits(*fix.point) and self.status not in ("SAFE_IDLE", "GPS_WARNING"))

    def gps(self, packet):
        now = self.clock()
        old = self.previous
        fix = self.location.accept(packet, now)
        if fix is None:
            self.freeze("GPS_WARNING")
            self.bus.notify(Kind.GPS_INVALID, reason=self.location.status)
            return
        self.bus.notify(Kind.GPS_UPDATED, fix=fix)
        cell = self.grid.at(*fix.point) if self.grid else h3.latlng_to_cell(fix.latitude, fix.longitude, self.cfg["exploration"]["h3_resolution"])
        changed = cell != self.cell
        self.cell = cell
        safe = self.safety.permits(*fix.point) and self.safety.permits(packet["latitude"], packet["longitude"])
        if not safe:
            with self.store.db:
                # Blocking a point must not erase existing cell progress/history.
                self.store.db.execute("INSERT OR IGNORE INTO map_cells(cell_id,state,blocked,first_entered_at,last_seen_at) VALUES(?,'BLOCKED',1,?,?)", (cell,now,now))
            self.freeze("SAFE_IDLE")
            self.bus.notify(Kind.CELL_BLOCKED, cell_id=cell)
            return
        if not fix.eligible:
            self.freeze("GPS_DISPLAY_ONLY")
            return
        if self.grid:
            self._visit_square(fix, cell, now)
            return
        start = time.perf_counter()
        with self.store.db:
            self.store.db.execute("INSERT OR IGNORE INTO map_cells(cell_id,state,first_entered_at,last_seen_at) VALUES(?,'UNSEEN',?,?)", (cell,now,now))
            self.store.db.execute("UPDATE map_cells SET state=CASE WHEN state IN ('UNSEEN','BLOCKED') THEN 'DISCOVERING' ELSE state END, blocked=0,last_seen_at=? WHERE cell_id=?", (now,cell))
            row = self.current()
            if changed:
                self.store.log(now,"EXPLORE","Entered area",cell)
                self.bus.notify(Kind.CELL_ENTERED, cell_id=cell)
                self.dialogue = 'Explore the permitted outdoor path. Camera analysis will update this area.'
            if row["state"] == "EXPLORED":
                self.status = "KNOWN_AREA"
                self.previous = (fix, cell)
                self.anchor = fix.point
                return
            self.status = "DISCOVERING"
            dt = moved = 0
            if old and old[1] == cell and 0 < now-old[0].received <= self.cfg["exploration"]["max_sample_gap_sec"]:
                if self.safety.permits_segment(old[0].point, fix.point):
                    dt = min(now-old[0].received, (fix.timestamp_ms-old[0].timestamp_ms)/1000)
                    if self.anchor is not None:
                        d = distance(self.anchor,fix.point)
                        noise = max(self.cfg["location"]["movement_noise_floor_m"], fix.accuracy_m*self.cfg["location"]["accuracy_noise_factor"])
                        if d >= noise:
                            # An anchor can span multiple samples, but only safe same-cell motion.
                            if self.safety.permits_segment(self.anchor, fix.point):
                                moved = d
                            self.anchor = fix.point
            else:
                self.anchor = fix.point
            self.previous = (fix,cell)
            self.store.db.execute("UPDATE map_cells SET dwell=dwell+?, movement=movement+? WHERE cell_id=?", (max(0,dt),moved,cell))
            self._progress(now)
        self.last_db_ms = (time.perf_counter()-start)*1000

    def totals(self):
        row = self.store.one('SELECT visited,pending,events_created FROM exploration_totals WHERE id=1')
        return {**row, 'target': self.cfg['exploration'].get('cells_per_event', 5)}

    def _visit_square(self, fix, cell, now):
        # Only measured positions count; never interpolate unvisited cells between fixes.
        row = self.current()
        if not row or row['state'] != 'EXPLORED':
            if not self.grid.confidently_inside(*fix.point, fix.accuracy_m):
                self.freeze('GPS_BOUNDARY')
                return
        with self.store.db:
            row = self.current()
            if row and row['state'] == 'EXPLORED':
                self.store.db.execute('UPDATE map_cells SET last_seen_at=? WHERE cell_id=?', (now,cell))
            else:
                self.store.db.execute("INSERT INTO map_cells(cell_id,state,progress,first_entered_at,last_seen_at) VALUES(?,'EXPLORED',1,?,?) ON CONFLICT(cell_id) DO UPDATE SET state='EXPLORED',progress=1,blocked=0,last_seen_at=excluded.last_seen_at", (cell,now,now))
                self.store.db.execute('UPDATE exploration_totals SET visited=visited+1,pending=pending+1 WHERE id=1')
                self.store.log(now,'EXPLORE','New grid permanently illuminated',cell)
                self.dialogue = 'New grid illuminated. Keep walking to discover an event.'
                self.bus.notify(Kind.CELL_ENTERED, cell_id=cell)
                totals = self.totals()
                if totals['pending'] >= totals['target']:
                    # Nearby recent vision can flavor an event, but GPS visits alone trigger it.
                    item = getattr(self, '_last_scene', None)
                    scene = None
                    if item and 0 <= now-item[1]['timestamp'] <= self.cfg['vision']['observation_max_age_sec']:
                        if distance(self.grid.center(item[0]), fix.point) <= self.grid.size*2:
                            scene = item[1]
                    if scene and scene['indoor_probability'] > self.cfg['safety']['indoor_threshold']:
                        scene = None
                    self._create_event(now, scene)
                    self.store.db.execute('UPDATE exploration_totals SET pending=pending-?,events_created=events_created+1 WHERE id=1', (totals['target'],))
        self.status = 'KNOWN_AREA'
        self.previous = (fix, cell)
        self.anchor = fix.point

    def current(self):
        return self.store.one("SELECT * FROM map_cells WHERE cell_id=?", (self.cell,))

    def tick(self):
        self.location.fresh(self.clock())
        if not self.location.usable:
            self.freeze(self.location.status)

    def observe(self, cell_id, observation, fingerprint):
        """Only board vision may call this; network never accepts observations."""
        now = self.clock()
        if cell_id != self.cell or not self.eligible() or not self.current() or (not self.grid and self.current()["state"] == "EXPLORED"):
            return False
        try:
            observation = validate_observation(observation, now, self.cfg['vision']['observation_max_age_sec'])
            if not isinstance(fingerprint,str) or len(fingerprint) != 256 or set(fingerprint)-set('0123456789abcdef'):
                return False
            previous = self.store.all("SELECT fingerprint FROM scene_observations WHERE cell_id=?", (cell_id,))
            raw = bytes.fromhex(fingerprint)
            duplicate = any(sum(abs(a-b) for a,b in zip(raw, bytes.fromhex(r["fingerprint"]))) / (128*255) < self.cfg["vision"]["frame_difference"] for r in previous)
            # Even duplicate frames can indicate indoor conditions; never retain an outdoor clearance.
            self._last_scene = (cell_id, observation)
            if duplicate:
                return False
            with self.store.db:
                if len(previous) < self.cfg['vision']['max_saved_observations']:
                    self.store.db.execute("INSERT INTO scene_observations(cell_id,timestamp,fingerprint,payload_json) VALUES(?,?,?,?)", (cell_id,now,fingerprint,json.dumps(observation)))
                confidence = self.cfg["vision"]["confidence"]
                landmark = any(o["class"] in {"bridge","pond","statue","large building","plaza","trail junction"} and o["confidence"] >= confidence for o in observation["objects"])
                self.store.db.execute("UPDATE map_cells SET landmark=MAX(landmark,?) WHERE cell_id=?", (int(landmark),cell_id))
                if not self.grid:
                    self._progress(now)
            self.bus.notify(Kind.SCENE_OBSERVED, cell_id=cell_id)
            return True
        except (KeyError, TypeError, ValueError):
            self._last_scene = None
            logging.getLogger("VISION").warning("invalid_observation")
            return False

    def scene(self, now):
        item = getattr(self,"_last_scene",None)
        if item and item[0] == self.cell and 0 <= now-item[1]["timestamp"] <= self.cfg["vision"]["observation_max_age_sec"]:
            return item[1]
        return None

    def exploration_components(self):
        """Read the same score components used by the world and debug interfaces."""
        row = self.current()
        if row is None:
            return [0, 0, 0, 0]
        e = self.cfg["exploration"]
        observations = [json.loads(r['payload_json']) for r in self.store.all('SELECT payload_json FROM scene_observations WHERE cell_id=?', (self.cell,))]
        count = sum(o['indoor_probability'] <= self.cfg['safety']['indoor_threshold'] and
                    (o['scene_confidence'] >= self.cfg['vision']['confidence'] or any(x['confidence'] >= self.cfg['vision']['confidence'] for x in o['objects'])) for o in observations)
        return [min(row["dwell"]/e["dwell_target_sec"],1), min(row["movement"]/e["movement_target_m"],1), min(count/e["observation_target"],1), row["landmark"]]

    def _progress(self, now):
        row = self.current()
        if row["event_triggered"]:
            return
        e = self.cfg["exploration"]
        components = self.exploration_components()
        progress = min(1, sum(a*b for a,b in zip(e["weights"],components)))
        self.store.db.execute("UPDATE map_cells SET progress=? WHERE cell_id=?", (progress,self.cell))
        self.bus.notify(Kind.EXPLORATION_UPDATED, cell_id=self.cell, progress=progress)
        if progress + 1e-12 < e["event_threshold"]:
            return
        scene = self.scene(now)
        if scene is None:
            self.status = "WAIT_FOR_SCENE"
            return
        if scene["indoor_probability"] > self.cfg["safety"]["indoor_threshold"]:
            self.status = "INDOOR_GUARD"
            return
        if not self.eligible():
            return
        self._create_event(now, scene)

    def _create_event(self, now, scene):
        context = map_context(scene,self.cfg["vision"]["confidence"])
        if self.grid:
            context["source_observation"] = scene
        event_id, kind = choose_event(self.cfg["world_seed"], self.cell, context)
        self.bus.notify(Kind.THRESHOLD, cell_id=self.cell)
        self.store.db.execute("INSERT INTO events(event_id,cell_id,type,archetype,status,created_at,payload_json) VALUES(?,?,?,?,'ACTIVE',?,?)", (event_id,self.cell,kind,context["archetype"],now,json.dumps(context)))
        if kind in ("NPC_ENCOUNTER","QUEST"):
            quest, npc = "q_"+event_id, "npc_"+event_id
            self.store.db.execute("INSERT INTO quests VALUES(?,'AVAILABLE',0,'find_lost_item',?,?)", (quest,self.cell,json.dumps({"xp":self.cfg["rules"]["quest_xp"]})))
            self.store.db.execute("INSERT INTO npcs(npc_id,name,archetype,cell_id,quest_id) VALUES(?,'Traveler','traveler',?,?)", (npc,self.cell,quest))
            self.store.db.execute("INSERT INTO npc_memory VALUES(?,?)", (npc,json.dumps({"player_helped":False,"player_threatened":False,"quest_completed":False})))
        self.store.db.execute("UPDATE map_cells SET state='EXPLORED',event_triggered=1,event_id=? WHERE cell_id=?", (event_id,self.cell))
        self.store.log(now,"EVENT",f"{kind}: {context['archetype']}",self.cell)
        self.status = "KNOWN_AREA"
        self.dialogue = f"Discovered {kind.lower().replace('_',' ')}. Inspect or talk."
        self.bus.notify(Kind.EVENT_CREATED, event_id=event_id)

    def interaction(self, intent):
        now = self.clock()
        if intent in ("MAP","QUESTS","INVENTORY","LEAVE","UNKNOWN"):
            self.dialogue = {"MAP":"Map open.","QUESTS":"Quest journal open.","INVENTORY":"Inventory open.","LEAVE":"Interaction closed.","UNKNOWN":"Choose a button or repeat the command."}[intent]
            return self.dialogue
        # Existing events require a current safe position, never a remotely supplied target.
        if not self.eligible() or self.status in ("INDOOR_GUARD",):
            self.dialogue = "Interaction paused: a valid outdoor position is required."
            return self.dialogue
        event = self.store.one("SELECT * FROM events WHERE cell_id=?", (self.cell,))
        if event is None:
            self.dialogue = "Keep exploring this permitted outdoor area."
            return self.dialogue
        npc = self.store.one("SELECT * FROM npcs WHERE cell_id=?", (self.cell,))
        quest = self.store.one("SELECT * FROM quests WHERE quest_id=?", (npc["quest_id"],)) if npc else None
        result = "There is nothing more to do here."
        with self.store.db:
            if intent == "TALK" and npc:
                result = "I lost my charm here. Will you help me look?" if quest["state"] == "AVAILABLE" else "Thank you for helping." if quest["state"] == "COMPLETED" else "Investigate this area, then return the charm."
                self.bus.notify(Kind.NPC_INTERACTION, npc_id=npc["npc_id"])
                if quest["state"] == "ACTIVE" and quest["stage"] == 1:
                    item = self.store.one("SELECT quantity FROM inventory WHERE item_id='lost_charm'")
                    if item and item["quantity"] > 0:
                        self.store.db.execute("UPDATE inventory SET quantity=quantity-1 WHERE item_id='lost_charm'")
                        self.store.db.execute("UPDATE quests SET state='COMPLETED',stage=2 WHERE quest_id=?", (quest["quest_id"],))
                        self.store.db.execute("UPDATE player SET xp=xp+? WHERE id=1", (json.loads(quest["rewards"])["xp"],))
                        self.store.db.execute("UPDATE npcs SET relationship=relationship+1,dialogue_state='THANKS' WHERE npc_id=?", (npc["npc_id"],))
                        self.store.db.execute("UPDATE npc_memory SET facts_json=? WHERE npc_id=?", (json.dumps({"player_helped":True,"player_threatened":False,"quest_completed":True}),npc["npc_id"]))
                        self.store.db.execute("INSERT OR REPLACE INTO world_flags VALUES (?, 'true')", ("completed_"+quest["quest_id"],))
                        self._complete(event,now)
                        result = f"Charm returned. Quest complete! +{json.loads(quest['rewards'])['xp']} XP."
                        self.bus.notify(Kind.QUEST_UPDATED, quest_id=quest["quest_id"])
            elif intent == "ACCEPT" and quest and quest["state"] == "AVAILABLE":
                self.store.db.execute("UPDATE quests SET state='ACTIVE' WHERE quest_id=?", (quest["quest_id"],))
                result = "Quest accepted. Investigate here on the permitted path."
            elif intent == "REFUSE" and quest and quest["state"] == "AVAILABLE":
                result = "Maybe another time."
            elif intent == "INSPECT" and quest and quest["state"] == "ACTIVE" and quest["stage"] == 0:
                self._item("lost_charm",1)
                self.store.db.execute("UPDATE quests SET stage=1 WHERE quest_id=?", (quest["quest_id"],))
                result = "You found a charm. Talk to the traveler to return it."
            elif intent == "INSPECT" and event["status"] == "ACTIVE" and not quest:
                kind = event["type"]
                if kind in ("RESOURCE","RARE"):
                    self._item("herb",self.cfg["rules"]["resource_quantity"])
                    result = "Trail herb added to your inventory."
                elif kind == "COMBAT":
                    hp = self.store.one("SELECT hp FROM player WHERE id=1")["hp"]
                    damage = self.cfg["rules"]["combat_damage"]
                    if hp <= damage:
                        result = "Too tired to fight. Find a rest encounter."
                        self.dialogue = result
                        return result
                    self.store.db.execute("UPDATE player SET hp=hp-?,xp=xp+? WHERE id=1", (damage,self.cfg["rules"]["combat_xp"]))
                    result = "You overcame a shadow. Combat resolved."
                elif kind == "REST":
                    self.store.db.execute("UPDATE player SET hp=MIN(?,hp+?) WHERE id=1", (self.cfg["rules"]["max_hp"],self.cfg["rules"]["rest_heal"]))
                    result = "You rest and recover."
                else:
                    result = "Discovery recorded in your journal."
                self._complete(event,now)
            self.store.log(now,"WORLD",result,self.cell)
        self.dialogue = result
        return result

    def _item(self, item, quantity):
        self.store.db.execute("INSERT INTO inventory VALUES (?,?) ON CONFLICT(item_id) DO UPDATE SET quantity=quantity+excluded.quantity", (item,quantity))

    def _complete(self,event,now):
        self.store.db.execute("UPDATE events SET status='COMPLETED',completed_at=? WHERE event_id=?", (now,event["event_id"]))

    def close(self):
        self.store.close()
