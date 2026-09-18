"""Stable square cells in a WGS84 ellipsoidal equal-area projection.

50 projected metres per side means 2500 m² per cell. Ground edge lengths
vary with latitude; the standard parallel is 25° (near Taiwan).
"""
import math
from pyproj import CRS, Transformer


class SquareGrid:
    crs = CRS.from_proj4('+proj=cea +lat_ts=25 +lon_0=0 +datum=WGS84 +units=m')

    def __init__(self, size=50):
        self.size = float(size)
        self.forward = Transformer.from_crs('EPSG:4326', self.crs, always_xy=True)
        self.inverse = Transformer.from_crs(self.crs, 'EPSG:4326', always_xy=True)

    def at(self, lat, lon):
        x, y = self.forward.transform(lon, lat)
        return self.id(math.floor(x/self.size), math.floor(y/self.size))

    def id(self, x, y):
        return f'sq1:{self.size:g}:{x}:{y}'

    def indices(self, cell):
        version, size, x, y = cell.split(':')
        if version != 'sq1' or float(size) != self.size:
            raise ValueError('Cell belongs to a different grid')
        return int(x), int(y)

    def point(self, x, y):
        lon, lat = self.inverse.transform(x*self.size, y*self.size)
        return lat, lon

    def center(self, cell):
        x, y = self.indices(cell)
        return self.point(x+.5, y+.5)

    def confidently_inside(self, lat, lon, accuracy):
        """Conservative projected error radius; intended for the Taiwan play area."""
        x, y = self.forward.transform(lon, lat)
        margin = max(3, accuracy)
        return min(x % self.size, self.size-x % self.size,
                   y % self.size, self.size-y % self.size) >= margin

    def boundary(self, cell):
        x, y = self.indices(cell)
        return [self.point(x+dx, y+dy) for dx, dy in ((0,0),(1,0),(1,1),(0,1))]

    def disk(self, cell, radius=12):
        x, y = self.indices(cell)
        return [self.id(x+dx,y+dy) for dx in range(-radius,radius+1) for dy in range(-radius,radius+1)]
