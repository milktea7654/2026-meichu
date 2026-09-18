import io
import math
import time
from collections import OrderedDict
import h3
import pygame
from .map import MBTiles, project

BG=(13,23,30)
TEXT=(223,234,228)
MUTED=(137,165,163)
GREEN=(110,220,166)
GOLD=(237,190,98)


class BoardUI:
    def __init__(self,cfg):
        pygame.display.init()
        pygame.font.init()
        self.cfg = cfg
        self.screen = pygame.display.set_mode((cfg['width'],cfg['height']))
        pygame.display.set_caption('Fieldbound · Offline Exploration RPG')
        font = cfg['font'] or pygame.font.match_font('notosanscjk,dejavusans')
        self.font = pygame.font.Font(font,18)
        self.small = pygame.font.Font(font,14)
        self.title = pygame.font.Font(font,26)
        self.cjk = pygame.font.Font(pygame.font.match_font('notosanscjk,droidsansfallback,arplumingtw') or font,18)
        self.tiles = MBTiles(cfg['tiles'],cfg['tile_cache'])
        self.tile_surfaces = OrderedDict()
        self.mode = 'MAP'
        self.buttons = []
        self.clock = pygame.time.Clock()
        self.running = True
        self.metrics = ''

    def text(self,text,x,y,color=TEXT,font=None):
        self.screen.blit((font or self.font).render(str(text),True,color),(x,y))

    def wrapped(self,text,x,y,width,color=TEXT):
        line=''
        for word in text.split():
            candidate = line+' '+word if line else word
            if self.font.size(candidate)[0]>width and line:
                self.text(line,x,y,color)
                y+=24
                line=word
            else:
                line=candidate
        self.text(line,x,y,color)
        return y+24

    def input(self):
        intents=[]
        keymap={pygame.K_m:'MAP',pygame.K_i:'INSPECT',pygame.K_t:'TALK',pygame.K_a:'ACCEPT',pygame.K_r:'REFUSE',pygame.K_ESCAPE:'LEAVE',pygame.K_q:'QUESTS',pygame.K_b:'INVENTORY'}
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running=False
            elif event.type == pygame.KEYDOWN and event.key in keymap:
                intents.append(keymap[event.key])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                for rect,intent in self.buttons:
                    if rect.collidepoint(event.pos):
                        intents.append(intent)
        for intent in intents:
            if intent in ('MAP','QUESTS','INVENTORY'):
                self.mode=intent
        return intents

    def draw(self,world,metrics=''):
        w,h=self.screen.get_size()
        self.screen.fill(BG)
        self.text('FIELDBOUND',24,15,GREEN,self.title)
        self.text('OUTDOOR JOURNAL  /  LOCAL WORLD',245,24,MUTED,self.small)
        self.text(world.status, w-295,20,GOLD)
        top, map_h = 58, h-360
        rect=pygame.Rect(20,top,w-40,map_h)
        self.screen.set_clip(rect)
        fix=world.location.last
        lat,lon=fix.point if fix else (self.cfg['start_lat'],self.cfg['start_lon'])
        zoom=self.cfg['zoom']
        cx,cy=project(lat,lon,zoom)
        def point(lat,lon):
            px,py=project(lat,lon,zoom)
            return round(rect.centerx+px-cx),round(rect.centery+py-cy)
        left,upper=cx-rect.width/2,cy-rect.height/2
        for tx in range(math.floor(left/256),math.ceil((left+rect.width)/256)):
            for ty in range(math.floor(upper/256),math.ceil((upper+rect.height)/256)):
                dest=pygame.Rect(round(rect.x+tx*256-left),round(rect.y+ty*256-upper),256,256)
                data=self.tiles.tile(zoom,tx,ty)
                if data:
                    try:
                        key=(zoom,tx,ty)
                        if key not in self.tile_surfaces:
                            tile=pygame.image.load(io.BytesIO(data)).convert()
                            self.tile_surfaces[key]=pygame.transform.scale(tile,(256,256))
                            while len(self.tile_surfaces)>self.cfg['tile_cache']:
                                self.tile_surfaces.popitem(last=False)
                        self.tile_surfaces.move_to_end(key)
                        self.screen.blit(self.tile_surfaces[key],dest)
                    except pygame.error:
                        pygame.draw.rect(self.screen,(29,43,48),dest)
                else:
                    pygame.draw.rect(self.screen,(29,43,48),dest)
                    pygame.draw.rect(self.screen,(43,58,61),dest,1)
        meters_px=156543.03392*math.cos(math.radians(lat))/2**zoom
        if world.grid:
            cell=world.grid.at(lat,lon)
            radius=max(2,math.ceil(math.hypot(rect.width,rect.height)*meters_px/world.grid.size)+2)
            visible=world.grid.disk(cell,min(radius,60))
            boundary, center = world.grid.boundary, world.grid.center
        else:
            cell=h3.latlng_to_cell(lat,lon,world.cfg['exploration']['h3_resolution'])
            edge=h3.average_hexagon_edge_length(world.cfg['exploration']['h3_resolution'],unit='m')
            radius=max(2,math.ceil(math.hypot(rect.width,rect.height)*meters_px/(2*edge*1.5))+2)
            visible=list(h3.grid_disk(cell,radius))
            boundary, center = h3.cell_to_boundary, h3.cell_to_latlng
        placeholders=','.join('?' for _ in visible)
        rows={r['cell_id']:r for r in world.store.all(f'SELECT * FROM map_cells WHERE cell_id IN ({placeholders})',visible)}
        fog=pygame.Surface((w,h),pygame.SRCALPHA)
        for idx in visible:
            points=[point(a,b) for a,b in boundary(idx)]
            row=rows.get(idx,{})
            state=row.get('state','UNSEEN')
            if state!='EXPLORED':
                pygame.draw.polygon(fog,(8,17,25,190 if state=='UNSEEN' else 130),points)
            color=GREEN if state=='EXPLORED' else (66,108,112) if state=='DISCOVERING' else (40,58,66)
            pygame.draw.polygon(fog,(*color,180),points,1)
        self.screen.blit(fog,(0,0))
        for poly in world.safety.blocked:
            overlay=pygame.Surface((w,h),pygame.SRCALPHA)
            pygame.draw.polygon(overlay,(225,81,78,100),[point(lat,lon) for lon,lat in poly[0]])
            for hole in poly[1:]:
                pygame.draw.polygon(overlay,(0,0,0,0),[point(lat,lon) for lon,lat in hole])
            self.screen.blit(overlay,(0,0))
        for row in rows.values():
            if row['event_id']:
                x,y=point(*center(row['cell_id']))
                pygame.draw.circle(self.screen,GOLD,(x,y),8)
                self.text('!' if not row['landmark'] else '*',x-4,y-11,BG)
        for quest in world.store.all(f"SELECT target_cell FROM quests WHERE state IN ('AVAILABLE','ACTIVE') AND target_cell IN ({placeholders})",visible):
            x,y=point(*center(quest['target_cell']))
            pygame.draw.rect(self.screen,GREEN,(x-12,y-12,24,24),2)
        if fix:
            p=point(*fix.point)
            pygame.draw.circle(self.screen,(98,156,172),p,max(1,round(fix.accuracy_m/meters_px)),1)
            pygame.draw.circle(self.screen,GREEN,p,7)
            pygame.draw.circle(self.screen,BG,p,3)
        else:
            self.text('Waiting for phone GPS',rect.centerx-110,rect.centery,MUTED)
        self.screen.set_clip(None)
        if world.status=='SAFE_IDLE':
            self.text('目前區域不可探索',36,top+12,GOLD,self.cjk)
        elif world.status in ('GPS_STALE','GPS_DISCONNECTED','GPS_WARNING','GPS_DISPLAY_ONLY'):
            self.text(f'GPS warning: {world.location.status} — exploration paused',36,top+12,GOLD)
        elif world.status=='INDOOR_GUARD':
            self.text('Indoor guard — events paused',36,top+12,GOLD)
        elif world.status=='WAIT_FOR_SCENE':
            self.text('Waiting for camera analysis — event pending',36,top+12,GOLD)
        self.text(self.tiles.attribution[:125],26,top+map_h-21,MUTED,self.small)
        current=world.current()
        totals=world.totals()
        progress=totals['pending']/totals['target'] if world.grid else (current['progress'] if current else 0)
        y=top+map_h+10
        pygame.draw.rect(self.screen,(35,56,62),(20,y,w-40,4))
        pygame.draw.rect(self.screen,GREEN,(20,y,round((w-40)*progress),4))
        self.text(f"NEW CELLS {totals['pending']}/{totals['target']}  | LIT {totals['visited']}" if world.grid else f'AREA PROGRESS {progress:.0%}',24,y+12,GREEN,self.small)
        player=world.store.one('SELECT * FROM player WHERE id=1')
        self.text(f"HP {player['hp']}   XP {player['xp']}",w-210,y+12,MUTED,self.small)
        y+=40
        self.text('FIELD NOTES',24,y,MUTED,self.small)
        logs=world.store.all('SELECT * FROM event_log ORDER BY id DESC LIMIT ?',(self.cfg['log_entries'],))
        for index,row in enumerate(logs[:10]):
            stamp=time.strftime('%H:%M',time.localtime(row['timestamp']))
            self.text(f"{stamp}  {row['message']}"[:65],24,y+25+index*17,TEXT,self.small)
        x=w//2+20
        self.text(self.mode if self.mode!='MAP' else 'CURRENT ENCOUNTER',x,y,MUTED,self.small)
        if self.mode=='QUESTS':
            entries=world.store.all('SELECT state,stage,objective FROM quests ORDER BY rowid DESC LIMIT 4')
            content='\n'.join(f"{r['state']} · {r['objective']} ({r['stage']}/2)" for r in entries) or 'No quests yet.'
        elif self.mode=='INVENTORY':
            entries=world.store.all('SELECT name,quantity FROM inventory JOIN items USING(item_id) WHERE quantity>0')
            content='\n'.join(f"{r['name']} × {r['quantity']}" for r in entries) or 'Your bag is empty.'
        else:
            content=world.dialogue
        line_y=y+25
        for line in content.splitlines():
            line_y=self.wrapped(line,x,line_y,w-x-30)
        self.buttons=[]
        names=[('Map','MAP'),('Inspect','INSPECT'),('Talk','TALK'),('Accept','ACCEPT'),('Refuse','REFUSE'),('Leave','LEAVE'),('Quests','QUESTS'),('Bag','INVENTORY')]
        bw=(w-48)//8
        for i,(label,intent) in enumerate(names):
            button=pygame.Rect(24+i*bw,h-64,bw-8,34)
            pygame.draw.rect(self.screen,(34,64,66),button,border_radius=5)
            self.text(label,button.x+12,button.y+6)
            self.buttons.append((button,intent))
        self.text(metrics[:170],24,h-23,MUTED,self.small)
        pygame.display.flip()
        self.clock.tick(self.cfg['fps'])

    def close(self):
        self.tiles.close()
        pygame.quit()
