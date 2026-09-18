import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS world_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS player(id INTEGER PRIMARY KEY CHECK(id=1), hp INTEGER NOT NULL, xp INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS map_cells(
 cell_id TEXT PRIMARY KEY, state TEXT NOT NULL CHECK(state IN ('UNSEEN','DISCOVERING','EXPLORED','BLOCKED')),
 progress REAL NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 1), first_entered_at REAL, last_seen_at REAL,
 event_triggered INTEGER NOT NULL DEFAULT 0, event_id TEXT, blocked INTEGER NOT NULL DEFAULT 0,
 dwell REAL NOT NULL DEFAULT 0, movement REAL NOT NULL DEFAULT 0, landmark INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS scene_observations(id INTEGER PRIMARY KEY, cell_id TEXT NOT NULL REFERENCES map_cells(cell_id),
 timestamp REAL NOT NULL, fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(cell_id,fingerprint));
CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL UNIQUE REFERENCES map_cells(cell_id),
 type TEXT NOT NULL, archetype TEXT, status TEXT NOT NULL, created_at REAL NOT NULL, completed_at REAL, payload_json TEXT);
CREATE TABLE IF NOT EXISTS event_log(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL,
 event_type TEXT NOT NULL, message TEXT NOT NULL, cell_id TEXT);
CREATE TABLE IF NOT EXISTS quests(quest_id TEXT PRIMARY KEY, state TEXT NOT NULL, stage INTEGER NOT NULL DEFAULT 0,
 objective TEXT NOT NULL, target_cell TEXT NOT NULL, rewards TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS npcs(npc_id TEXT PRIMARY KEY, name TEXT NOT NULL, archetype TEXT NOT NULL, cell_id TEXT NOT NULL,
 relationship INTEGER NOT NULL DEFAULT 0, dialogue_state TEXT NOT NULL DEFAULT 'INTRO', quest_id TEXT REFERENCES quests(quest_id), alive INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS npc_memory(npc_id TEXT PRIMARY KEY REFERENCES npcs(npc_id), facts_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items(item_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventory(item_id TEXT PRIMARY KEY REFERENCES items(item_id), quantity INTEGER NOT NULL CHECK(quantity>=0));
CREATE TABLE IF NOT EXISTS world_flags(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exploration_totals(id INTEGER PRIMARY KEY CHECK(id=1), visited INTEGER NOT NULL DEFAULT 0, pending INTEGER NOT NULL DEFAULT 0, events_created INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS observations_cell ON scene_observations(cell_id);
"""


class Store:
    def __init__(self, path, cfg):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        with self.db:
            mode = cfg['exploration'].get('mode', 'legacy_h3')
            old_mode = self.one("SELECT value FROM world_meta WHERE key='exploration_mode'")
            if mode == 'square_visits' and old_mode is None and self.one('SELECT 1 FROM map_cells LIMIT 1'):
                raise ValueError('Existing legacy world: use a new database for square cells')
            meta = {"schema_version": 1, "world_seed": cfg["world_seed"], "exploration_mode": mode}
            if mode == 'square_visits':
                meta.update(grid_projection='WGS84_CEA_lat_ts25_v1', cell_size_m=cfg['exploration']['cell_size_m'], cells_per_event=cfg['exploration']['cells_per_event'])
            else:
                meta['h3_resolution'] = cfg['exploration']['h3_resolution']
            for k, v in meta.items():
                row = self.one("SELECT value FROM world_meta WHERE key=?", (k,))
                if row and row["value"] != str(v):
                    raise ValueError(f"Existing world {k} differs; use a new database")
                self.db.execute("INSERT OR IGNORE INTO world_meta VALUES (?,?)", (k,str(v)))
            self.db.execute("INSERT OR IGNORE INTO exploration_totals(id) VALUES(1)")
            self.db.execute("INSERT OR IGNORE INTO player(id,hp,xp) VALUES(1,?,0)", (cfg["rules"]["max_hp"],))
            self.db.executemany("INSERT OR IGNORE INTO items VALUES (?,?)", [("herb","Trail herb"),("lost_charm","Traveler's charm")])
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('config',?)", (json.dumps(cfg),))

    def one(self, sql, args=()):
        row = self.db.execute(sql,args).fetchone()
        return dict(row) if row else None

    def all(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql,args)]

    def log(self, now, kind, message, cell=None):
        self.db.execute("INSERT INTO event_log(timestamp,event_type,message,cell_id) VALUES(?,?,?,?)", (now,kind,message,cell))

    def close(self):
        self.db.close()
