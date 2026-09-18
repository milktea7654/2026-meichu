"""
world.py - 世界狀態中樞、角色成長與已探索區域任務推進閉環
"""

import math
from typing import Dict, Any, Optional
from edge_rpg.storage import WorldStorage
from edge_rpg.events import EventEngine, GameEvent
from edge_rpg.weather import WeatherEngine, WeatherState
from edge_rpg.scene import SceneObservation

class WorldManager:
    def __init__(self, db_path: str = "data/world.db", world_seed: int = 12345):
        self.storage = WorldStorage(db_path)
        self.event_engine = EventEngine(world_seed)
        self.weather_engine = WeatherEngine(world_seed)

    def get_current_weather(self) -> WeatherState:
        return self.weather_engine.get_weather()

    def get_player_stats(self) -> Dict[str, Any]:
        p = self.storage.get_player()
        lvl = p.get("level", 1)
        p["xp_needed"] = int(100 * math.pow(lvl, 1.4))
        return p

    def add_player_xp(self, amount: int) -> Dict[str, Any]:
        p = self.get_player_stats()
        current_xp = p["xp"] + amount
        level = p["level"]
        leveled_up = False

        while current_xp >= p["xp_needed"]:
            current_xp -= p["xp_needed"]
            level += 1
            leveled_up = True
            p["max_hp"] += 20
            p["hp"] = p["max_hp"]
            p["perception"] += 2
            p["endurance"] += 2
            p["lore"] += 1
            p["skill_points"] += 1
            p["level"] = level
            p["xp_needed"] = int(100 * math.pow(level, 1.4))

            self.storage.add_event_log(
                "LEVEL_UP",
                f"🎉 恭喜升級至 Lv.{level}！最大生命值提升至 {p['max_hp']}，全屬性提升！"
            )

        p["xp"] = current_xp
        self.storage.update_player(p)
        return {"leveled_up": leveled_up, "new_level": level, "current_xp": current_xp}

    def check_cell_quest_interaction(self, cell_id: str) -> Optional[GameEvent]:
        """已探索區域閉環：若身上有指向此格的任務，提供手動推進事件"""
        active_quests = self.storage.get_active_quests()
        for q in active_quests:
            if q.get("target_cell") == cell_id:
                return GameEvent(
                    event_id=f"quest_act_{q['quest_id']}",
                    cell_id=cell_id,
                    event_type="QUEST_PROGRESS",
                    title=f"任務目標：{q['title']}",
                    description=f"你已抵達任務所指的地點。{q.get('description', '')}",
                    options=[
                        {"label": "仔細調查目標物", "action": "INSPECT_TARGET", "result_text": "成功取得任務信物，任務階段更新！"},
                        {"label": "暫時離開", "action": "LEAVE", "result_text": "你決定稍後再來調查。"}
                    ],
                    xp_reward=100
                )
        return None

    def trigger_cell_event(self, cell_id: str, observation: Optional[SceneObservation] = None) -> GameEvent:
        if observation and not observation.weather:
            observation.weather = self.get_current_weather()

        flags = self.storage.get_world_flags()
        player = self.storage.get_player()

        event = self.event_engine.generate_event(
            cell_id=cell_id,
            observation=observation,
            world_flags=flags,
            player_level=player.get("level", 1)
        )
        self.storage.add_event_log("EVENT_TRIGGER", f"觸發事件：【{event.title}】", cell_id)
        return event

    def resolve_event_choice(self, event: GameEvent, option_idx: int) -> str:
        if option_idx < 0 or option_idx >= len(event.options):
            return "無效的選擇"

        choice = event.options[option_idx]
        result_text = choice.get("result_text", "事件已結束。")

        if event.xp_reward > 0:
            res = self.add_player_xp(event.xp_reward)
            result_text += f" (獲得 {event.xp_reward} XP)"
            if res["leveled_up"]:
                result_text += f" 【晉升至等級 Lv.{res['new_level']}!】"

        if event.flags_on_complete:
            flags = self.storage.get_world_flags()
            flags.update(event.flags_on_complete)
            self.storage.set_world_flags(flags)

        self.storage.add_event_log("EVENT_RESOLVED", f"{event.title}：{result_text}", event.cell_id)
        return result_text
