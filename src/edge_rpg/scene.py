"""
scene.py - 40+ 在地化高特徵微地標定義與場景觀測結構
"""

from dataclasses import dataclass, field
from typing import List, Optional
from edge_rpg.weather import WeatherState

OBJECT_CATALOG = {
    # 公共設施
    "vending_machine": "自動販賣機", "mailbox": "郵筒", "manhole": "人孔蓋",
    "traffic_mirror": "反射凸面鏡", "bus_stop": "公車站牌", "utility_pole": "電線桿",
    "transformer_box": "變電箱", "fire_hydrant": "消防栓", "street_lamp": "路燈",
    "traffic_light": "交通號誌", "cctv_camera": "監控攝影機", "payphone": "公共電話亭",
    # 街景地形
    "arcade_walkway": "騎樓廊道", "alley": "窄巷/防火巷", "crosswalk": "斑馬線",
    "stairs": "戶外階梯", "overpass": "天橋", "underpass": "地下道",
    "guardrail": "鐵護欄", "brick_wall": "紅磚圍牆", "metal_gate": "鐵捲門",
    # 商業人文
    "convenience_store": "便利超商", "boba_shop": "手搖飲料店", "food_cart": "攤販推車",
    "temple_shrine": "土地公廟", "scooter": "停放機車", "bicycle": "自行車",
    "bulletin_board": "社區公佈欄", "statue": "公共雕像", "shop_sign": "懸掛招牌",
    # 自然景觀
    "tree": "行道樹", "bench": "長椅", "lawn": "草坪綠帶", "flowerbed": "街道花圃",
    "pond": "水池", "stream": "小溪渠道", "bridge": "橋樑", "rock": "造景岩石"
}

@dataclass
class DetectedObject:
    name: str
    confidence: float
    bbox: Optional[List[float]] = None

@dataclass
class SceneObservation:
    timestamp: int
    scene: str
    scene_confidence: float
    objects: List[DetectedObject] = field(default_factory=list)
    indoor_probability: float = 0.0
    weather: Optional[WeatherState] = None
