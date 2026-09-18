"""
scene.py - 場景與物件定義 (擴充 40+ 在地化高特徵微地標，支援天氣與觀測數據結構)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from edge_rpg.weather import WeatherState

# 擴充的 40+ 種高辨識度現實物件 (依特徵分類)
OBJECT_CATALOG = {
    # 1. 基礎公共設施 (Urban Infrastructure)
    "vending_machine": "自動販賣機",
    "mailbox": "郵筒",
    "manhole": "人孔蓋/下水道孔",
    "traffic_mirror": "道路反射凸面鏡",
    "bus_stop": "公車站牌",
    "utility_pole": "電線桿",
    "transformer_box": "變電箱",
    "fire_hydrant": "消防栓",
    "street_lamp": "路燈",
    "traffic_light": "紅綠燈/交通號誌",
    "cctv_camera": "監控攝影機",
    "payphone": "公共電話亭",
    
    # 2. 街道結構與微地形 (Architecture & Walkways)
    "arcade_walkway": "騎樓廊道",
    "alley": "窄巷/防火巷",
    "crosswalk": "斑馬線",
    "stairs": "戶外階梯",
    "overpass": "天橋",
    "underpass": "地下道",
    "guardrail": "鐵護欄",
    "brick_wall": "紅磚圍牆",
    "metal_gate": "鐵捲門/鐵柵門",
    
    # 3. 商業與人文生活 (Commercial & Culture)
    "convenience_store": "便利超商 (7-11/全家)",
    "boba_shop": "手搖飲料店",
    "food_cart": "路邊攤推車",
    "temple_shrine": "宮廟/土地公廟",
    "scooter": "停放機車",
    "bicycle": "自行車",
    "bulletin_board": "社區公佈欄",
    "statue": "公共雕像/裝置藝術",
    "shop_sign": "懸掛招牌",

    # 4. 自然與綠化景觀 (Nature & Landscaping)
    "tree": "行道樹/老樹",
    "bench": "公園長椅",
    "lawn": "草坪綠帶",
    "flowerbed": "街道花圃",
    "pond": "水池/造景水塘",
    "stream": "人工明渠/小溪",
    "bridge": "景觀橋樑",
    "rock": "造景岩石",
    "bamboo": "竹林/盆栽",
    "pigeon": "廣場鴿群/鳥禽"
}

@dataclass
class DetectedObject:
    name: str
    confidence: float
    bbox: Optional[List[float]] = None  # [ymin, xmin, ymax, xmax]

@dataclass
class SceneObservation:
    timestamp: int
    scene: str                         # park, road, campus, plaza, alley, indoor
    scene_confidence: float
    objects: List[DetectedObject] = field(default_factory=list)
    indoor_probability: float = 0.0
    weather: Optional[WeatherState] = None
