"""
weather.py - 確定性本地天氣系統 (Zero-Network, Seed-Based, Temporal)
"""

import time
import hashlib
from enum import Enum
from dataclasses import dataclass

class WeatherType(str, Enum):
    CLEAR = "CLEAR"               # 晴空萬里
    CLOUDY = "CLOUDY"             # 多雲陰天
    DRIZZLE = "DRIZZLE"           # 細雨霏霏
    HEAVY_RAIN = "HEAVY_RAIN"     # 傾盆大雨
    THUNDERSTORM = "THUNDERSTORM" # 雷雨交加
    FOGGY = "FOGGY"               # 迷霧籠罩
    WINDY = "WINDY"               # 強風呼嘯

@dataclass
class WeatherState:
    weather_type: WeatherType
    display_name: str
    icon: str
    temperature_c: int
    visibility_mod: float       # 視野/相機觀測乘數 (0.5 ~ 1.2)
    movement_mod: float         # 移動速度累積乘數 (0.7 ~ 1.0)
    event_bias: str             # 影響事件偏向 (water, electric, mystery, normal)

class WeatherEngine:
    def __init__(self, world_seed: int = 12345):
        self.world_seed = world_seed

    def get_weather(self, timestamp: float = None) -> WeatherState:
        now = int(timestamp or time.time())
        # 每 3 小時 (10800秒) 切換一次天氣區段，保證同一時段內穩定
        time_slot = now // 10800
        seed_key = f"{self.world_seed}:weather:{time_slot}"
        h = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:8], 16)
        roll = (h % 1000) / 1000.0

        # 天氣機率分佈 (台灣常見微氣候)
        if roll < 0.40:
            return WeatherState(WeatherType.CLEAR, "晴朗", "☀️", 28, 1.1, 1.0, "normal")
        elif roll < 0.65:
            return WeatherState(WeatherType.CLOUDY, "陰天", "⛅", 25, 1.0, 1.0, "normal")
        elif roll < 0.80:
            return WeatherState(WeatherType.DRIZZLE, "綿綿細雨", "🌦️", 23, 0.9, 0.9, "water")
        elif roll < 0.88:
            return WeatherState(WeatherType.HEAVY_RAIN, "大雨", "🌧️", 21, 0.7, 0.75, "water_danger")
        elif roll < 0.93:
            return WeatherState(WeatherType.THUNDERSTORM, "雷陣雨", "⛈️", 20, 0.6, 0.7, "electric")
        elif roll < 0.97:
            return WeatherState(WeatherType.FOGGY, "濃霧", "🌫️", 22, 0.5, 0.85, "mystery")
        else:
            return WeatherState(WeatherType.WINDY, "強風", "💨", 24, 0.95, 0.9, "wind")
