from dataclasses import dataclass
from collections import deque
import math
from .geo import distance


@dataclass(frozen=True)
class Fix:
    latitude: float
    longitude: float
    accuracy_m: float
    speed_mps: float
    timestamp_ms: float
    received: float
    eligible: bool

    @property
    def point(self):
        return self.latitude, self.longitude


class LocationFilter:
    def __init__(self, config):
        self.cfg = config
        self.last_raw = None
        self.last = None
        self.status = "WAIT_FOR_PHONE_GPS"
        self.latest_timestamp = -1
        self.usable = False
        self.trajectory = deque()

    def reject(self, reason):
        self.status = reason
        self.usable = False
        return None

    def accept(self, packet, now):
        c = self.cfg
        try:
            if not isinstance(packet, dict) or packet.get("type") != "location":
                return self.reject("GPS_INVALID_PACKET")
            keys = ("latitude", "longitude", "accuracy_m", "timestamp_ms")
            if any(isinstance(packet[k], bool) or not isinstance(packet[k], (int, float)) or not math.isfinite(packet[k]) for k in keys):
                return self.reject("GPS_INVALID_PACKET")
            lat, lon, acc, ts = (packet[k] for k in keys)
            speed = packet.get("speed_mps", 0)
            if isinstance(speed, bool) or not isinstance(speed, (float, int)) or not math.isfinite(speed) or speed < 0:
                return self.reject("GPS_INVALID_PACKET")
            if not -90 <= lat <= 90 or not -180 <= lon <= 180 or acc < 0:
                return self.reject("GPS_INVALID_PACKET")
            for key, limit in (("heading_deg", 360),):
                if key in packet and (not isinstance(packet[key], (float, int)) or not math.isfinite(packet[key]) or not 0 <= packet[key] < limit):
                    return self.reject("GPS_INVALID_PACKET")
            age = now - ts / 1000
            if age > c["stale_sec"] or age < -c["future_tolerance_sec"] or ts <= self.latest_timestamp:
                return self.reject("GPS_INVALID_TIMESTAMP")
            self.latest_timestamp = ts
            if acc > c["gps_display_accuracy_m"]:
                return self.reject("GPS_INVALID_ACCURACY")
            raw = (lat, lon)
            fresh = self.last is not None and now - self.last.received < c["stale_sec"]
            if self.last_raw is not None:
                oldpoint, oldts, oldacc = self.last_raw
                dt = (ts-oldts)/1000
                d = distance(oldpoint, raw)
                if d > c["max_jump_speed_mps"] * dt + max(acc, oldacc):
                    return self.reject("GPS_JUMP")
                if fresh:
                    speed = max(speed, max(0, d - max(acc, oldacc)) / dt)
            self.last_raw = raw, ts, acc
            if not fresh:
                self.trajectory.clear()
            self.trajectory.append((ts, raw, acc))
            while self.trajectory and ts-self.trajectory[0][0] > c['speed_window_sec']*1000:
                self.trajectory.popleft()
            # Infer sustained motion even when optional phone speed is absent.
            # A window is less sensitive to jitter than adding every GPS displacement.
            if len(self.trajectory) > 1:
                first_ts, first_point, first_accuracy = self.trajectory[0]
                noise = max(c['movement_noise_floor_m'], max(acc, first_accuracy)*c['accuracy_noise_factor'])
                speed = max(speed, max(0, distance(first_point, raw)-noise)/((ts-first_ts)/1000))
            if fresh:
                alpha = c["smoothing_alpha"]
                lat = alpha*lat + (1-alpha)*self.last.latitude
                lon = alpha*lon + (1-alpha)*self.last.longitude
            eligible = acc <= c["gps_valid_accuracy_m"] and speed <= c["max_exploration_speed_mps"]
            self.last = Fix(lat, lon, acc, speed, ts, now, eligible)
            self.usable = eligible
            self.status = "READY" if eligible else "GPS_DISPLAY_ONLY"
            return self.last
        except (KeyError, TypeError, ValueError, OverflowError):
            return self.reject("GPS_INVALID_PACKET")

    def fresh(self, now):
        if self.last is None or now-self.last.received >= self.cfg["stale_sec"] or now-self.last.timestamp_ms/1000 >= self.cfg["stale_sec"]:
            self.status = "GPS_STALE"
            self.usable = False
            return False
        return self.usable
