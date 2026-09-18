"""
events.py - 現實語義映射與連貫因果劇情引擎
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
    event_type: str        # DISCOVERY, NPC_ENCOUNTER, RESOURCE, QUEST, COMBAT, MYSTERY
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
        t = time.localtime(timestamp or time.time())
        hour = t.tm_hour
        if 5 <= hour < 9:
            return "DAWN"
        elif 9 <= hour < 17:
            return "DAY"
        elif 17 <= hour < 21:
            return "DUSK"
        else:
            return "NIGHT"

    def _deterministic_rand(self, cell_id: str, extra_seed: str = "") -> float:
        key = f"{self.world_seed}:{cell_id}:{extra_seed}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
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

        # ---------------------------------------------------------------------
        # 1. 因果連貫性事件 (依賴前面的劇情與抉擇)
        # ---------------------------------------------------------------------
        if world_flags.get("saved_traveler", False) and not world_flags.get("received_traveler_gift", False):
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="NPC_ENCOUNTER",
                title="旅人的信使",
                description="一名佩戴巡林徽章的信使在街角攔住了你：「你就是先前出手相助的冒險者吧！這是我們隊長答應給你的回禮。」",
                options=[
                    {"label": "欣然接受信物", "action": "ACCEPT", "result_text": "獲得了【精製星盤指南針】，探索靈敏度大幅提升！"},
                    {"label": "婉拒並詢問前方路況", "action": "INQUIRE", "result_text": "信使傳授了周圍捷徑，並在公會中宣揚了你的美名。"}
                ],
                xp_reward=120,
                item_rewards=[{"item_id": "star_compass", "name": "星盤指南針", "quantity": 1}],
                flags_on_complete={"received_traveler_gift": True, "reputation_positive": True},
                created_at=now
            )

        if world_flags.get("cult_ritual_interrupted", False) and time_phase in ["DUSK", "NIGHT"]:
            if roll < 0.45:
                return GameEvent(
                    event_id=event_id, cell_id=cell_id, event_type="COMBAT",
                    title="暗影復仇者的埋伏",
                    description="街巷陰影中突然閃出兩名披著黑袍的狂信徒：「就是你破壞了地脈陣眼！」",
                    options=[
                        {"label": "拔出武器迎戰", "action": "FIGHT", "result_text": "你熟練地擊退狂信徒，繳獲了【黯淡符文石】。"},
                        {"label": "藉由騎樓地形迅速脫身", "action": "FLEE", "result_text": "你敏捷地繞過巷道甩開敵人，平安無事。"}
                    ],
                    xp_reward=150,
                    item_rewards=[{"item_id": "shadow_rune", "name": "黯淡符文石", "quantity": 1}],
                    flags_on_complete={"cult_ambush_survived": True},
                    created_at=now
                )

        # ---------------------------------------------------------------------
        # 2. 天氣主導的特殊動態事件
        # ---------------------------------------------------------------------
        if weather_type in [WeatherType.DRIZZLE, WeatherType.HEAVY_RAIN]:
            if "arcade_walkway" in detected_objects or "convenience_store" in detected_objects or roll < 0.3:
                return GameEvent(
                    event_id=event_id, cell_id=cell_id, event_type="NPC_ENCOUNTER",
                    title="雨幕下的避雨邂逅",
                    description="嘩啦啦的雨聲籠罩街道，一位全身裹在防水斗篷下的神秘占卜師正在屋簷下烘乾卷軸。",
                    options=[
                        {"label": "借火避雨並請求占卜", "action": "DIVINE", "result_text": "占卜師為你揭示了未探索迷霧中的寶物方位！"},
                        {"label": "分享熱飲增進情誼", "action": "SHARE", "result_text": "占卜師回贈了你一枚能避雷的【避水護符】。"}
                    ],
                    xp_reward=90,
                    item_rewards=[{"item_id": "water_amulet", "name": "避水護符", "quantity": 1}],
                    created_at=now
                )

        if weather_type == WeatherType.FOGGY and ("traffic_mirror" in detected_objects or roll < 0.35):
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="MYSTERY",
                title="霧氣中的曲面倒影",
                description="道路凸面鏡周圍瀰漫著濃重的霧氣，鏡面上的街景竟然不是現實的道路，而是一片幽靜的神殿廢墟！",
                options=[
                    {"label": "集中精神進行感知共鳴", "action": "MEDITATE", "result_text": "你的感知突破了界限，獲得大量【洞察靈光】！"},
                    {"label": "在鏡緣刻上記號穩定空間", "action": "MARK", "result_text": "記下了此處的時空節點，獲得神秘碎片。"}
                ],
                xp_reward=110,
                flags_on_complete={"discovered_fog_rift": True},
                created_at=now
            )

        # ---------------------------------------------------------------------
        # 3. 街景高特徵物件事件 (40+ 物件庫核心映射)
        # ---------------------------------------------------------------------
        # (1) 自動販賣機
        if "vending_machine" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="RESOURCE",
                title="自動魔導盲盒機",
                description="這台機器的按鈕閃爍著奇幻色彩，標示著：『注入能量或金幣，隨機獲取行腳冒險特調』。",
                options=[
                    {"label": "購買一罐【活力魔水】", "action": "BUY", "result_text": "咕嚕喝下，體力瞬間完全回滿！"},
                    {"label": "拍打機器排氣口試圖撬出零件", "action": "KICK", "result_text": "零錢槽掉出幾枚古銅幣與小齒輪！"}
                ],
                xp_reward=60,
                item_rewards=[{"item_id": "vitality_potion", "name": "活力魔水", "quantity": 1}],
                created_at=now
            )

        # (2) 郵筒
        if "mailbox" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="QUEST",
                title="郵筒內的無名封印信",
                description="綠色郵筒的投信口卡著一封封蠟未乾的信件，上面以精靈語寫著：『請交付給林地神龕的守護者』。",
                options=[
                    {"label": "收下信件承接委託", "action": "ACCEPT_QUEST", "result_text": "承接任務：【失落的信使任務】，請尋找神龕。"},
                    {"label": "放回郵筒不插手", "action": "IGNORE", "result_text": "你謹慎地離開，未捲入潛在的紛爭。"}
                ],
                xp_reward=80,
                item_rewards=[{"item_id": "sealed_letter", "name": "封印的信件", "quantity": 1}],
                flags_on_complete={"quest_letter_active": True},
                created_at=now
            )

        # (3) 人孔蓋
        if "manhole" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="DISCOVERY",
                title="鐫刻符印的鑄鐵人孔",
                description="厚重的人孔蓋縫隙泛出微微青煙，金屬表面隱約烙印著矮人工匠的齒輪印記。",
                options=[
                    {"label": "傾聽內部的齒輪聲響", "action": "LISTEN", "result_text": "聽辨出地下暗渠的水流走向，地圖紀錄點亮！"},
                    {"label": "採集表面凝結的矮人鐵鏽", "action": "COLLECT", "result_text": "獲得了極其堅硬的【鍛造黑鐵碎屑】。"}
                ],
                xp_reward=70,
                item_rewards=[{"item_id": "black_iron_scrap", "name": "鍛造黑鐵碎屑", "quantity": 2}],
                created_at=now
            )

        # (4) 變電箱 / 電線桿
        if "transformer_box" in detected_objects or "utility_pole" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="RESOURCE",
                title="嗡鳴的雷霆節點",
                description="綠色金屬變電箱散發出滋滋的靜電微粒，周遭的空氣因充沛的電能而微微發麻。",
                options=[
                    {"label": "使用絕緣瓶汲取雷元素", "action": "COLLECT", "result_text": "成功汲取了跳躍的【雷光微粒】！"},
                    {"label": "以此處地磁校準感官", "action": "ALIGN", "result_text": "精神一振，洞察屬性暫時獲得加成。"}
                ],
                xp_reward=65,
                item_rewards=[{"item_id": "lightning_spark", "name": "雷光微粒", "quantity": 2}],
                created_at=now
            )

        # (5) 宮廟 / 土地公廟
        if "temple_shrine" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="DISCOVERY",
                title="街角的守護靈龕",
                description="古樸的小廟香火裊裊，紅燈籠在簷下輕晃，散發著安定心神的庇佑氣息。",
                options=[
                    {"label": "虔誠參拜祈求旅途平安", "action": "PRAY", "result_text": "獲得土地公的靈力庇佑，獲得【長行祝福】狀態！"},
                    {"label": "求取靈簽探尋吉凶", "action": "DIVINE", "result_text": "上上籤！周圍 200 公尺內的探索進度獲得加成。"}
                ],
                xp_reward=100,
                flags_on_complete={"temple_blessed": True},
                created_at=now
            )

        # (6) 便利超商 / 手搖飲
        if "convenience_store" in detected_objects or "boba_shop" in detected_objects:
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="RESOURCE",
                title="永明的光之驛站",
                description="玻璃門自動滑開，清脆的歡迎鈴聲響起，店內琳瑯滿目的物資在旅途疲憊時顯得格外誘人。",
                options=[
                    {"label": "採購旅者點心補給", "action": "BUY_FOOD", "result_text": "飽餐一頓，體力全滿且精神充沛！"},
                    {"label": "向店員打聽附近的傳聞", "action": "RUMOR", "result_text": "店員熱情地分享了昨晚在轉角巷口看到的奇怪光影。"}
                ],
                xp_reward=55,
                created_at=now
            )

        # ---------------------------------------------------------------------
        # 4. 拓撲與時段保底豐富化
        # ---------------------------------------------------------------------
        if road_type == "intersection":
            return GameEvent(
                event_id=event_id, cell_id=cell_id, event_type="NPC_ENCOUNTER",
                title="命運的十字交會點",
                description="四方氣流匯聚的路口，一位背著行囊的流浪詩人正坐在一旁的石階上調試魯特琴。",
                options=[
                    {"label": "聆聽詩人吟唱古老歌謠", "action": "LISTEN", "result_text": "詩歌中夾雜著遠古寶藏的提示，學識大幅增長！"},
                    {"label": "打聽下一個城區的局勢", "action": "INQUIRE", "result_text": "得知了鄰近區域的魔物分佈與勢力變化。"}
                ],
                xp_reward=85,
                created_at=now
            )

        # 預設街區依時段賦予濃郁 RPG 描述
        phase_map = {
            "DAWN": ("拂曉微光中的行路者", "晨曦初露，清潔工正掃過泛著露水的青石板，空氣清冽而寧靜。"),
            "DAY": ("喧鬧市井的巡邏哨", "正午日光直射，兩位巡邏衛兵正在路口檢查商旅行客的通關文書。"),
            "DUSK": ("暮色蒼茫的行腳僧", "夕陽拉長了巷道裡的影子，遠方傳來隱隱鐘聲，一名僧侶低頭誦經走過。"),
            "NIGHT": ("暗夜提燈的夜行客", "夜深人靜，只有昏暗的路燈在地上投出光暈，一位提著煤油燈的身影隱沒在弄巷深處。")
        }
        title_text, desc_text = phase_map.get(time_phase, ("街區行者", "街道平靜如常。"))

        return GameEvent(
            event_id=event_id, cell_id=cell_id, event_type="DISCOVERY",
            title=title_text, description=desc_text,
            options=[
                {"label": "仔細打量並上前攀談", "action": "TALK", "result_text": "雙方互換了探索心得，獲得了寶貴的情報。"},
                {"label": "提高警覺擦肩而過", "action": "PASS", "result_text": "謹慎的步伐磨練了你的警覺度。"}
            ],
            xp_reward=50,
            created_at=now
        )
