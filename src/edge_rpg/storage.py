"""
storage.py - SQLite 持久化層 (WAL模式, 10s 超時防鎖死, 角色成長自動遷移)
"""

import sqlite3
import json
import time
from typing import Dict, Any, List

class WorldStorage:
    def __init__(self, db_path: str = "data/world.db"):
        self.db_path = db_path
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        # timeout=10.0 防止多線程寫入拋出 database is locked
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _init_tables(self):
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS player (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                xp INTEGER NOT NULL DEFAULT 0,
                hp INTEGER NOT NULL DEFAULT 100,
                max_hp INTEGER NOT NULL DEFAULT 100,
                stamina INTEGER NOT NULL DEFAULT 100,
                max_stamina INTEGER NOT NULL DEFAULT 100,
                perception INTEGER NOT NULL DEFAULT 10,
                endurance INTEGER NOT NULL DEFAULT 10,
                lore INTEGER NOT NULL DEFAULT 10,
                skill_points INTEGER NOT NULL DEFAULT 0,
                perks_json TEXT NOT NULL DEFAULT '[]'
            );
            """)

            # 自動欄位平滑遷移
            existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(player);").fetchall()]
            new_cols = {
                "level": "INTEGER NOT NULL DEFAULT 1", "xp": "INTEGER NOT NULL DEFAULT 0",
                "hp": "INTEGER NOT NULL DEFAULT 100", "max_hp": "INTEGER NOT NULL DEFAULT 100",
                "stamina": "INTEGER NOT NULL DEFAULT 100", "max_stamina": "INTEGER NOT NULL DEFAULT 100",
                "perception": "INTEGER NOT NULL DEFAULT 10", "endurance": "INTEGER NOT NULL DEFAULT 10",
                "lore": "INTEGER NOT NULL DEFAULT 10", "skill_points": "INTEGER NOT NULL DEFAULT 0",
                "perks_json": "TEXT NOT NULL DEFAULT '[]'"
            }
            for col, col_def in new_cols.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE player ADD COLUMN {col} {col_def};")

            conn.execute("""
            CREATE TABLE IF NOT EXISTS map_cells (
                cell_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                first_entered_at INTEGER,
                last_seen_at INTEGER,
                event_triggered INTEGER NOT NULL DEFAULT 0,
                event_id TEXT,
                blocked INTEGER NOT NULL DEFAULT 0
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                cell_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL,
                payload_json TEXT,
                created_at INTEGER NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS quests (
                quest_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                stage INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                target_cell TEXT,
                description TEXT,
                rewards_json TEXT
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS world_flags (
                key TEXT PRIMARY KEY,
                val_json TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                cell_id TEXT
            );
            """)

            cur = conn.execute("SELECT id FROM player WHERE id = 'hero';")
            if not cur.fetchone():
                conn.execute("INSERT INTO player (id, name) VALUES ('hero', '探索者');")
            conn.commit()

    def get_player(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM player WHERE id = 'hero';").fetchone()
            if row:
                d = dict(row)
                d["perks"] = json.loads(d.get("perks_json", "[]"))
                return d
            return {}

    def update_player(self, data: Dict[str, Any]):
        fields, vals = [], []
        for k, v in data.items():
            if k == "perks":
                fields.append("perks_json = ?")
                vals.append(json.dumps(v))
            elif k != "id":
                fields.append(f"{k} = ?")
                vals.append(v)
        vals.append("hero")
        with self._get_conn() as conn:
            conn.execute(f"UPDATE player SET {', '.join(fields)} WHERE id = ?;", vals)
            conn.commit()

    def get_active_quests(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM quests WHERE status = 'ACTIVE';").fetchall()
            return [dict(r) for r in rows]

    def get_world_flags(self) -> Dict[str, Any]:
        flags = {}
        with self._get_conn() as conn:
            for r in conn.execute("SELECT key, val_json FROM world_flags;").fetchall():
                flags[r["key"]] = json.loads(r["val_json"])
        return flags

    def set_world_flags(self, flags: Dict[str, Any]):
        with self._get_conn() as conn:
            for k, v in flags.items():
                conn.execute(
                    "INSERT INTO world_flags (key, val_json) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET val_json = excluded.val_json;",
                    (k, json.dumps(v))
                )
            conn.commit()

    def add_event_log(self, event_type: str, message: str, cell_id: str = ""):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO event_log (timestamp, event_type, message, cell_id) VALUES (?, ?, ?, ?);",
                (int(time.time()), event_type, message, cell_id)
            )
            conn.commit()

    def get_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM event_log ORDER BY id DESC LIMIT ?;", (limit,)).fetchall()
            return [dict(r) for r in rows]
