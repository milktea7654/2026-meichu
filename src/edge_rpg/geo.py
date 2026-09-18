"""WGS84 distance and conservative polygon geofencing, including holes."""
import json
import math
from pathlib import Path


def distance(a, b):
    p, q = math.radians(a[0]), math.radians(b[0])
    dp, dl = q - p, math.radians(b[1] - a[1])
    h = math.sin(dp / 2)**2 + math.cos(p) * math.cos(q) * math.sin(dl / 2)**2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def ring_contains(point, ring):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        cross = (x-a[0])*(b[1]-a[1]) - (y-a[1])*(b[0]-a[0])
        tolerance = 1e-12 * max(abs(b[0]-a[0]), abs(b[1]-a[1]))
        if abs(cross) <= tolerance and min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1]):
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def contains(point, polygon):
    return ring_contains(point, polygon[0]) and not any(ring_contains(point, hole) for hole in polygon[1:])


def polygons(path):
    data = json.loads(Path(path).read_text())
    result = []
    for feature in data["features"]:
        g = feature["geometry"]
        if g["type"] == "Polygon":
            result.append(g["coordinates"])
        elif g["type"] == "MultiPolygon":
            result.extend(g["coordinates"])
        else:
            raise ValueError("Geofences must contain Polygon or MultiPolygon geometries")
    for polygon in result:
        if not polygon or any(len(ring) < 4 or ring[0] != ring[-1] for ring in polygon):
            raise ValueError("Geofence rings must be closed and have at least four points")
        for ring in polygon:
            for coordinate in ring:
                if len(coordinate) < 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in coordinate[:2]):
                    raise ValueError('Geofence coordinates must be finite longitude/latitude numbers')
                if not -180 <= coordinate[0] <= 180 or not -90 <= coordinate[1] <= 90:
                    raise ValueError('Geofence coordinates outside WGS84 bounds')
    return result


def segment_cuts(start, end, a, b):
    """Parameters of intersections along start→end, including collinear contact.

    Coordinates are longitude/latitude. No distance-based sampling is used, so
    narrow polygon boundaries cannot fall between trajectory samples.
    """
    rx, ry = end[0]-start[0], end[1]-start[1]
    sx, sy = b[0]-a[0], b[1]-a[1]
    qx, qy = a[0]-start[0], a[1]-start[1]
    denominator = rx*sy-ry*sx
    if denominator != 0:
        t = (qx*sy-qy*sx)/denominator
        u = (qx*ry-qy*rx)/denominator
        return [t] if 0 <= t <= 1 and 0 <= u <= 1 else []
    if qx*ry-qy*rx != 0:
        return []
    length_squared = rx*rx+ry*ry
    if not length_squared:
        return []
    ta = (qx*rx+qy*ry)/length_squared
    tb = ((b[0]-start[0])*rx+(b[1]-start[1])*ry)/length_squared
    lo, hi = max(0, min(ta, tb)), min(1, max(ta, tb))
    return [lo, hi] if lo <= hi else []


class Safety:
    def __init__(self, config):
        # A missing/malformed file fails startup; an empty allowlist denies all.
        self.allow_unlisted = not config.get("require_allowed_area", True)
        self.allowed = polygons(config["allowed"])
        self.blocked = polygons(config["blocked"])

    def permits(self, lat, lon):
        p = (lon, lat)
        return (self.allow_unlisted or any(contains(p, poly) for poly in self.allowed)) and not any(contains(p, poly) for poly in self.blocked)

    def permits_segment(self, a, b):
        if not self.permits(*a) or not self.permits(*b):
            return False
        if a == b:
            return True
        start, end = (a[1], a[0]), (b[1], b[0])
        # Touching a blocked boundary is conservatively denied, including tangency.
        for polygon in self.blocked:
            for ring in polygon:
                if any(segment_cuts(start, end, p, q) for p, q in zip(ring, ring[1:])):
                    return False
        cuts = {0.0, 1.0}
        for polygon in self.allowed:
            for ring in polygon:
                for p, q in zip(ring, ring[1:]):
                    cuts.update(segment_cuts(start, end, p, q))
        ordered = sorted(cuts)
        # Polygon membership is constant in each interval between intersections.
        # Evaluate the union of allowed polygons so overlaps remain traversable.
        return all(self.permits(a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)
                   for lo, hi in zip(ordered, ordered[1:]) for t in [(lo+hi)/2])
