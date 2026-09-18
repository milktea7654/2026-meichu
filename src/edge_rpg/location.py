"""
location.py - GPS 校驗、平滑濾波與 H3 邊界遲滯保護 (Anti-Ping-Pong)
"""

import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class LocationPacket:
    latitude: float
    longitude: float
    accuracy_m: float
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    timestamp_ms: int = 0

class HysteresisCellTracker:
    """防止玩家在相鄰 H3 格子邊界時因 GPS 抖動產生反覆橫跳 (Ping-Pong)"""
    def __init__(self, min_consecutive_hits: int = 3, dwell_time_sec: float = 2.0):
        self.current_cell: Optional[str] = None
        self.candidate_cell: Optional[str] = None
        self.candidate_count: int = 0
        self.first_candidate_time: float = 0.0
        self.min_consecutive_hits = min_consecutive_hits
        self.dwell_time_sec = dwell_time_sec

    def update_cell(self, raw_cell_id: str) -> str:
        now = time.time()
        if not self.current_cell:
            self.current_cell = raw_cell_id
            return raw_cell_id

        if raw_cell_id == self.current_cell:
            self.candidate_cell = None
            self.candidate_count = 0
            return self.current_cell

        # 檢測到候選新格子
        if raw_cell_id != self.candidate_cell:
            self.candidate_cell = raw_cell_id
            self.candidate_count = 1
            self.first_candidate_time = now
        else:
            self.candidate_count += 1

        # 同時滿足連續次數與駐留時間才確認切換
        if (self.candidate_count >= self.min_consecutive_hits and 
            (now - self.first_candidate_time) >= self.dwell_time_sec):
            self.current_cell = self.candidate_cell
            self.candidate_cell = None
            self.candidate_count = 0

        return self.current_cell

class LocationValidator:
    def __init__(self, max_acc: float = 15.0, display_acc: float = 25.0, max_speed: float = 2.5):
        self.max_acc = max_acc
        self.display_acc = display_acc
        self.max_speed = max_speed
        self.last_valid_packet: Optional[LocationPacket] = None

    def validate(self, pkt: LocationPacket) -> Dict[str, Any]:
        """驗證 GPS 狀態 (VALID, DISPLAY_ONLY, INVALID)"""
        now_ms = int(time.time() * 1000)
        # 1. 檢查時戳 (不得延遲超過 10 秒)
        if abs(now_ms - pkt.timestamp_ms) > 10000 and pkt.timestamp_ms != 0:
            return {"status": "INVALID", "reason": "TIMESTAMP_EXPIRED"}

        # 2. 精度檢查
        if pkt.accuracy_m > self.display_acc:
            return {"status": "INVALID", "reason": "POOR_ACCURACY"}
        if pkt.accuracy_m > self.max_acc:
            return {"status": "DISPLAY_ONLY", "reason": "MODERATE_ACCURACY"}

        # 3. 速度限制 (防止乘車刷地圖)
        if pkt.speed_mps > self.max_speed:
            return {"status": "DISPLAY_ONLY", "reason": "SPEED_TOO_HIGH"}

        self.last_valid_packet = pkt
        return {"status": "VALID", "reason": "OK"}
