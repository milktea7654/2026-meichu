"""
storage.py - SQLite 持久化資料庫層 (包含角色等級、XP、三維屬性自動遷移)
"""

import sqlite3
import json
from typing import Dict, Any, List, Optional

class WorldStorage:
    def __init__(self, db_path: str = "data/world.db"):
        self.db_path = db_path
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # FRDM-i.MX93 eMMC 優化：開啟 WAL 模式，避免 I/O 阻塞主線程
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_tables(self):
        with self._get_conn() as conn:
            # 1. 玩家主表 (具備等級、XP、三維屬性)
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

            # 確保舊資料表無痛遷移至新欄位
            existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(player);").fetchall()]
            new_cols = {
                "level": "INTEGER NOT NULL DEFAULT 1",
                "xp": "INTEGER NOT NULL DEFAULT 0",
                "hp": "INTEGER NOT NULL DEFAULT 100",
                "max_hp": "INTEGER NOT NULL DEFAULT 100",
                "stamina": "INTEGER NOT NULL DEFAULT 100",
                "max_stamina": "INTEGER NOT NULL DEFAULT 100",
                "perception": "INTEGER NOT NULL DEFAULT 10",
                "endurance": "INTEGER NOT NULL DEFAULT 10",
                "lore": "INTEGER NOT NULL DEFAULT 10",
                "skill_points": "INTEGER NOT NULL DEFAULT 0",
                "perks_json": "TEXT NOT NULL DEFAULT '[]'"
            }
            for col, col_type in new_cols.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE player ADD COLUMN {col} {col_type};")

            # 2. 地圖格子表 (H3)
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

            # 3. 事件持久化表
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

            # 4. 世界旗標表 (因果連貫關鍵)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS world_flags (
                key TEXT PRIMARY KEY,
                val_json TEXT NOT NULL
            );
            """)

            # 5. 事件日誌表
            conn.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                cell_id TEXT
            );
            """)

            # 初始玩家紀錄
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
        fields = []
        vals = []
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
