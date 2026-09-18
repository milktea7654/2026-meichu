"""
events.py - 現實到 RPG 因果連貫事件生成引擎
"""

import time
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from edge_rpg.scene import SceneObservation
from edge_rpg.weather import WeatherType

@dataclass
class GameEvent:
    event_id: str
    cell_id: str
    event_type: str
    title: str
    description: str
    options: List[Dict[str, Any]]
    xp_reward: int = 50
    item_rewards: List[Dict[str, Any]] = field(default_factory=list)
    flags_on_complete: Dict[str, Any] = field(default_factory=dict)
    status: str = "ACTIVE"
    created_at: int = 0

class EventEngine:
    def __init__(self, world_seed: int = 12345):
        self.world_seed = world_seed

    def _get_time_phase(self, timestamp: Optional[int] = None) -> str:
        hour = time.localtime(timestamp or time.time()).tm_hour
        if 5 <= hour < 9: return "DAWN"
        elif 9 <= hour < 17: return "DAY"
        elif 17 <= hour < 21: return "DUSK"
        else: return "NIGHT"

    def _deterministic_rand(self, cell_id: str, extra_seed: str = "") -> float:
        h = hashlib.sha256(f"{self.world_seed}:{cell_id}:{extra_seed}".encode("utf-8")).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

    def generate_event(
        self,
        cell_id: str,
        observation: Optional[SceneObservation],
        world_flags: Dict[str, Any],
        player_level: int = 1,
        road_type: str = "street"
    ) -> GameEvent:
        now = int(time.time())
        time_phase = self._get_time_phase(now)
        detected_objects = set(obj.name.lower() for obj in (observation.objects if observation else []))
        weather_type = observation.weather.weather_type if (observation and observation.weather) else WeatherType.CLEAR
        roll = self._deterministic_rand(cell_id, "main_roll")
        event_id = f"evt_{cell_id[:8]}_{int(roll * 10000):04d}"

        # 1. 因果連貫分支 (先前劇情的影響)
        if world_flags.get("saved_traveler", False) and not world_flags.get("received_traveler_gift", False):
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="NPC_ENCOUNTER",
                title="旅人的信使",
                description="一名佩戴巡林徽章的信使在街角攔住了你：「你就是先前在林地伸出援手的冒險者吧！這是隊長托我交給你的星盤指南針。」",
                options=[
                    {"label": "欣然接受信物", "action": "ACCEPT", "result_text": "獲得了【精製星盤指南針】，探索感度大幅提升！"},
                    {"label": "婉拒並詢問前方路況", "action": "INQUIRE", "result_text": "信使傳授了周圍捷徑，名聲大幅提升。"}
                ],
                xp_reward=120,
                item_rewards=[{"item_id": "star_compass", "name": "星盤指南針", "quantity": 1}],
                flags_on_complete={"received_traveler_gift": True, "reputation_high": True},
                created_at=now
            )

        # 2. 天氣動態特殊事件
        if weather_type in [WeatherType.DRIZZLE, WeatherType.HEAVY_RAIN]:
            if "arcade_walkway" in detected_objects or "convenience_store" in detected_objects or roll < 0.35:
                return GameEvent(
                    event_id=event_id, cell_id=cell_id, event_type="NPC_ENCOUNTER",
                    title="雨幕下的避雨邂逅",
                    description="雨勢傾盆，一位披著深色斗篷的神秘占卜師正在屋簷下烘烤羊皮紙卷軸。",
                    options=[
                        {"label": "上前避雨並請求占卜", "action": "DIVINE", "result_text": "占卜師為你揭示了未探索迷霧中的寶物方位！"},
                        {"label": "分享背包乾糧結緣", "action": "SHARE", "result_text": "占卜師回贈了你一枚【避水護符】。"}
                    ],
                    xp_reward=95,
                    item_rewards=[{"item_id": "water_amulet", "name": "避水護符", "quantity": 1}],
                    created_at=now
                )

        # 3. 40+ 物件庫核心映射
        if "traffic_mirror" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="MYSTERY",
                title="反射鏡的微光裂隙",
                description="道路轉彎凸面鏡表面泛起水波紋般的藍光，鏡中的街景似乎對應著另一片幽靜的神殿廢墟。",
                options=[
                    {"label": "凝神進行感知共鳴", "action": "MEDITATE", "result_text": "你的感知突破了界限，獲得大量【洞察靈光】！"},
                    {"label": "在鏡框拓印下空間座標", "action": "MARK", "result_text": "成功記下此處的時空雜訊。"}
                ],
                xp_reward=90,
                flags_on_complete={"found_mirror_rift": True},
                created_at=now
            )

        if "vending_machine" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="RESOURCE",
                title="自動魔導盲盒機",
                description="機器的按鈕閃爍著五彩光輝，寫著：『投入魔能結晶或金幣，獲取行腳冒險特調』。",
                options=[
                    {"label": "購買一瓶【活力魔水】", "action": "BUY", "result_text": "體力瞬間全滿，精力充沛！"},
                    {"label": "研究機底構造撿取遺落硬幣", "action": "SEARCH", "result_text": "在縫隙撿到了幾枚古銅幣與齒輪！"}
                ],
                xp_reward=60,
                item_rewards=[{"item_id": "vitality_potion", "name": "活力魔水", "quantity": 1}],
                created_at=now
            )

        if "manhole" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="DISCOVERY",
                title="刻印銘文的鑄鐵人孔",
                description="厚重的人孔蓋隱約散發熱氣，金屬表面烙印著矮人工匠的齒輪印記。",
                options=[
                    {"label": "傾聽內部的齒輪轟鳴", "action": "LISTEN", "result_text": "聽辨出地下暗渠走向，點亮地下通道標記！"},
                    {"label": "採集表面凝結的鍛造黑鐵", "action": "COLLECT", "result_text": "獲得了極其堅硬的【黑鐵碎屑】。"}
                ],
                xp_reward=70,
                item_rewards=[{"item_id": "black_iron", "name": "黑鐵碎屑", "quantity": 2}],
                created_at=now
            )

        if "transformer_box" in detected_objects or "utility_pole" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="RESOURCE",
                title="嗡鳴的雷霆節點",
                description="綠色變電箱持續釋放高頻靜電，周遭空氣瀰漫著微弱的雷元素躁動。",
                options=[
                    {"label": "使用絕緣容器汲取雷能", "action": "COLLECT", "result_text": "成功捕獲了跳動的【雷光微粒】！"},
                    {"label": "借助地脈能量靜心校準", "action": "ALIGN", "result_text": "精神一振，感知屬性暫時獲得加成。"}
                ],
                xp_reward=65,
                item_rewards=[{"item_id": "lightning_spark", "name": "雷光微粒", "quantity": 2}],
                created_at=now
            )

        if "temple_shrine" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="DISCOVERY",
                title="街角的守護靈龕",
                description="古樸的小廟香火繚繞，紅燈籠在微風中輕晃，散發著祥和安寧的庇護氣場。",
                options=[
                    {"label": "虔誠參拜祈求旅途平安", "action": "PRAY", "result_text": "獲得土地公的庇佑，獲得【長行祝福】狀態！"},
                    {"label": "求取靈簽探尋吉凶", "action": "DIVINE", "result_text": "抽得上籤！周遭探索度累積加速。"}
                ],
                xp_reward=100,
                flags_on_complete={"temple_blessed": True},
                created_at=now
            )

        # 4. 保底時段豐富化
        phase_map = {
            "DAWN": ("拂曉微光中的行路者", "清晨薄霧瀰漫，一名早起的巡林人正默默清掃石板上的落葉。"),
            "DAY": ("喧鬧市井的巡邏哨", "正午日光直射，兩位衛兵在樹蔭下檢視著過往行者的通關文牒。"),
            "DUSK": ("暮色蒼茫的行腳僧", "夕陽在巷子裡拉出長長的影子，一位托缽僧侶低頭誦經而過。"),
            "NIGHT": ("暗夜提燈的夜行客", "夜深人靜，昏黃的路燈下，一名裹著斗篷的身影正匆匆隱入巷尾。")
        }
        title_text, desc_text = phase_map.get(time_phase, ("街區行者", "街道平靜如常。"))

        return GameEvent(
            event_id=event_id, cell_id=cell_id, event_type="DISCOVERY",
            title=title_text, description=desc_text,
            options=[
                {"label": "上前問候與交流情報", "action": "TALK", "result_text": "交換了冒險情報，獲得地圖指引。"},
                {"label": "保持警惕擦身而過", "action": "PASS", "result_text": "謹慎的步伐磨練了你的警覺度。"}
            ],
            xp_reward=50,
            created_at=now
        )
