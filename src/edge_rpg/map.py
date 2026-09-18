import math
import sqlite3
from pathlib import Path
from collections import OrderedDict


def project(lat,lon,zoom):
    lat = max(-85.05112878,min(85.05112878,lat))
    n = 256*2**zoom
    return (lon+180)/360*n, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n


class MBTiles:
    def __init__(self,path,cache_size=128):
        self.db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) if Path(path).exists() else None
        self.cache = OrderedDict()
        self.limit = cache_size
        self.attribution = "Offline grid — no map tiles installed"
        if self.db:
            rows = dict(self.db.execute('SELECT name,value FROM metadata'))
            if rows.get('format','png') not in ('png','jpg','jpeg','webp'):
                raise ValueError('Only raster MBTiles are supported; convert vector tiles first')
            self.attribution = rows.get('attribution','Offline map — verify source attribution')

    def tile(self,z,x,y):
        key = z,x,y
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        row = self.db.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',(z,x%(2**z),2**z-1-y)).fetchone() if self.db else None
        value = row[0] if row else None
        self.cache[key] = value
        while len(self.cache)>self.limit:
            self.cache.popitem(last=False)
        return value

    def close(self):
        if self.db:
            self.db.close()
