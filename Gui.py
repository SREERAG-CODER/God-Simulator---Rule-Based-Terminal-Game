"""
Civilisation Simulator — Top-Down 3D GUI  (fixed edition)
Drop next to World.py / Civilization.py / King.py etc.
Run:  pip install pygame   then   python gui.py

Fixes applied:
  1. Top-down orthographic 3D (tiles drawn as squares + thick bottom/right
     depth edges — "chunky 3D" look straight from above)
  2. Post-election immunity (500 ticks), rebels excluded from overthrow counter,
     rebel amnesty on new election
  3. King style locked at coronation — use the fixed King.py alongside this
"""

import pygame
import sys
import random
from World import World
from King import TAX_INTERVAL
from Civilization import Person

# ═══════════════════════════════════════════════════════════════════
#  BOOTSTRAP SIMULATION
# ═══════════════════════════════════════════════════════════════════
STARTING_INTEL = 10
world = World(50, 50, population_cap=10)
adam  = world.spawn_person("Adam", intelligence=STARTING_INTEL)
eve   = None
for _ in range(1000):
    x = adam.x + random.randint(-5, 5)
    y = adam.y + random.randint(-5, 5)
    if 0 <= x < world.width and 0 <= y < world.height:
        tile = world.grid[y][x]
        if tile.terrain == 'grass' and tile.civilization is None:
            eve = Person("Eve", x, y, intelligence=STARTING_INTEL)
            world.grid[y][x].civilization = eve
            world.people.append(eve)
            break
world.seed_food_near(adam.x, adam.y, radius=10, count=30)
for s in [adam, eve]:
    if s:
        for _ in range(6): s.add_to_inventory('food')

class Stats:
    def __init__(self):
        self.total_born=0; self.births_log=[]; self.deaths_log=[]
        self.peak_population=0; self.huts_built=0; self.storehouses_built=0
        self.parents={}; self.generation={}
    def register_birth(self, p, pnames, tick):
        self.total_born += 1
        self.births_log.append((tick, p.name, pnames))
        self.parents[p.name] = pnames
        self.generation[p.name] = (max(self.generation.get(n,0) for n in pnames)+1) if pnames else 0
    def record_death(self, p, tick):
        self.deaths_log.append((tick,p.name,p.age,p.cause_of_death or 'unknown',p.intelligence))

stats = Stats()
stats.register_birth(adam, [], 0)
if eve: stats.register_birth(eve, [], 0)

# ═══════════════════════════════════════════════════════════════════
#  PYGAME INIT
# ═══════════════════════════════════════════════════════════════════
pygame.init()
INFO  = pygame.display.Info()
SCR_W = min(1400, INFO.current_w - 40)
SCR_H = min(860,  INFO.current_h - 60)
screen = pygame.display.set_mode((SCR_W, SCR_H), pygame.RESIZABLE)
pygame.display.set_caption("Civilisation Simulator")
clock  = pygame.time.Clock()
FPS    = 60

# ═══════════════════════════════════════════════════════════════════
#  TOP-DOWN 3D TILE SETTINGS  (Fix 1)
#  Each tile = TW×TH square on screen + DEPTH pixels of bottom/right edge
# ═══════════════════════════════════════════════════════════════════
TW    = 20    # tile face width  (pixels)
TH    = 20    # tile face height (pixels)
DEPTH = 5     # depth edge thickness — gives the 3D pop

PANEL_W = 300   # left UI panel width

def tile_rect(gx, gy):
    """Top-left pixel of a tile's face."""
    sx = PANEL_W + gx * TW - cam_x
    sy = gx * 0 + gy * TH  - cam_y    # pure top-down, no skew
    return sx, sy

# ═══════════════════════════════════════════════════════════════════
#  COLOUR HELPERS
# ═══════════════════════════════════════════════════════════════════
def c(r,g,b): return (r,g,b)
def shade(col, amt):
    return tuple(max(0, min(255, v+amt)) for v in col)

# UI palette
BLACK  = c(10, 10, 14)
DARK   = c(18, 16, 26)
DARKER = c(12, 11, 18)
PANEL  = c(26, 22, 38)
PANEL2 = c(34, 28, 50)
BORDER = c(65, 50, 95)
WHITE  = c(228, 222, 240)
MUTED  = c(125, 115, 145)
ACCENT = c(105, 165, 255)
GOLD   = c(255, 200, 55)
RED    = c(215,  65, 65)
GREEN  = c(75,  195, 105)
ORANGE = c(215, 145, 45)
TEAL   = c(55,  195, 185)
PURPLE = c(155,  95, 235)
PINK   = c(215, 115, 175)
LIME   = c(160, 220,  60)

# terrain face colours
T = {
    'grass':       c(78,  138,  58),
    'grass_alt':   c(68,  122,  50),
    'water':       c(52,  108, 186),
    'water_wave':  c(42,   92, 170),
    'forest':      c(32,   82,  38),
    'rock':        c(118, 112, 108),
    'farm':        c(152, 122,  48),
    'ready':       c(208, 188,  52),
    'food':        c(78,  138,  58),   # same as grass, dot drawn on top
    'seed':        c(78,  138,  58),
    'stump':       c(88,   68,  38),
    'rubble':      c(98,   92,  85),
    'fiber':       c(78,  138,  58),
    'fiber_spent': c(58,  108,  82),
}

def terrain_top(terrain, gx, gy, wave):
    base = T.get(terrain, T['grass'])
    if terrain == 'grass' and (gx+gy) % 2 == 0:
        return T['grass_alt']
    if terrain == 'water':
        return T['water_wave'] if wave and (gx+gy) % 3 != 0 else T['water']
    return base

def terrain_depth(terrain):
    """Bottom depth edge colour."""
    base = T.get(terrain, T['grass'])
    if terrain == 'water': return shade(base, -30)
    if terrain in ('forest','rock'): return shade(base, -50)
    return shade(base, -35)

def terrain_right(terrain):
    """Right depth edge colour."""
    base = T.get(terrain, T['grass'])
    return shade(terrain_depth(terrain), 15)

# How tall (in DEPTH units) each terrain is — affects sprite height
TILE_ELEV = {
    'forest': 3, 'rock': 2, 'hut': 3, 'storehouse': 3,
    'water': 0,
}

# ═══════════════════════════════════════════════════════════════════
#  SPRITE DRAWING  (top-down 3D)
# ═══════════════════════════════════════════════════════════════════

def draw_tile(surf, sx, sy, top_col, depth_col, right_col, elev=1):
    """Draw a top-down 3D tile: flat top face + bottom/right depth edges."""
    d = DEPTH * elev
    # top face
    pygame.draw.rect(surf, top_col,   (sx, sy, TW, TH))
    # bottom depth edge
    pygame.draw.rect(surf, depth_col, (sx, sy+TH, TW, d))
    # right depth edge (slightly lighter)
    pygame.draw.rect(surf, right_col, (sx+TW, sy, d, TH+d))
    # subtle outline on top face
    pygame.draw.rect(surf, shade(top_col,-20), (sx, sy, TW, TH), 1)

def draw_tree(surf, sx, sy):
    """Forest tile: stacked canopy circles."""
    cx = sx + TW//2
    cy = sy + TH//2
    pygame.draw.rect(surf,  c(80,55,28),  (cx-2, cy+2, 5, 6))   # trunk
    pygame.draw.circle(surf, c(28,85,32), (cx, cy-2), 9)          # dark outer
    pygame.draw.circle(surf, c(40,110,42),(cx-1,cy-5), 6)         # mid
    pygame.draw.circle(surf, c(58,145,55),(cx, cy-7), 4)           # bright top
    pygame.draw.circle(surf, c(90,175,75),(cx-1,cy-8), 2)          # highlight

def draw_rock(surf, sx, sy):
    cx, cy = sx+TW//2, sy+TH//2
    pygame.draw.polygon(surf, c(148,140,132), [(cx-7,cy+4),(cx,cy-9),(cx+7,cy+4)])
    pygame.draw.polygon(surf, c(168,160,152), [(cx-2,cy+4),(cx+5,cy-6),(cx+9,cy+4)])
    pygame.draw.polygon(surf, c(188,182,175), [(cx-1,cy-4),(cx+4,cy-8),(cx+8,cy-1)])

def draw_hut(surf, sx, sy):
    """Blue-roofed hut viewed from top-down — see the roof as a pentagon."""
    bx, by = sx+3, sy+5
    bw, bh = TW-6, TH-7
    # walls (visible from above as a thin strip at bottom)
    pygame.draw.rect(surf, c(195,170,125), (bx, by+bh-4, bw, 4))
    # roof top (rhombus / flat poly — dominant surface from above)
    roof_pts = [
        (sx+TW//2, sy+2),        # apex
        (sx+TW-3,  by+bh//2),    # right
        (sx+TW//2, by+bh),       # bottom
        (sx+3,     by+bh//2),    # left
    ]
    pygame.draw.polygon(surf, c(72,112,188), roof_pts)
    pygame.draw.polygon(surf, c(52, 88,155), roof_pts, 1)
    # ridge line
    pygame.draw.line(surf, c(92,135,210), (sx+TW//2,sy+2),(sx+TW//2,by+bh), 1)
    # chimney dot
    pygame.draw.circle(surf, c(130,110,90), (sx+TW-6, by+4), 2)

def draw_storehouse(surf, sx, sy):
    bx, by = sx+2, sy+4
    bw, bh = TW-4, TH-6
    pygame.draw.rect(surf, c(170,150,112), (bx, by+bh-5, bw, 5))
    roof_pts = [
        (sx+TW//2, sy+1),
        (sx+TW-2,  by+bh//2+2),
        (sx+TW//2, by+bh+2),
        (sx+2,     by+bh//2+2),
    ]
    pygame.draw.polygon(surf, c(92,132,200), roof_pts)
    pygame.draw.polygon(surf, c(68,105,168), roof_pts, 1)
    pygame.draw.line(surf, c(115,158,225), (sx+TW//2,sy+1),(sx+TW//2,by+bh+2), 2)
    # two windows
    for ox in (4, TW-8):
        pygame.draw.rect(surf, c(220,198,148), (sx+ox, by+bh-8, 4, 4))

def draw_build_site(surf, sx, sy):
    # dirt patch
    pygame.draw.rect(surf, c(145,115,72), (sx+2,sy+2,TW-4,TH-4))
    # scaffolding poles
    for px2 in (sx+4, sx+TW-6):
        pygame.draw.line(surf, c(180,145,85), (px2,sy+TH-2),(px2,sy+2), 2)
    pygame.draw.line(surf, c(180,145,85), (sx+4,sy+TH//2),(sx+TW-6,sy+TH//2), 2)
    # outline
    pygame.draw.rect(surf, c(200,170,100), (sx+2,sy+2,TW-4,TH-4), 1)

def draw_farm_crop(surf, sx, sy, ripe=False):
    col = c(215,195,50) if ripe else c(95,170,55)
    for row in range(3):
        for col_i in range(3):
            px2 = sx+3 + col_i*6
            py2 = sy+3 + row*6
            pygame.draw.line(surf, col, (px2,py2+4),(px2,py2), 2)
            if ripe:
                pygame.draw.circle(surf, c(235,215,60),(px2,py2),2)

def draw_fiber_patch(surf, sx, sy):
    for i in range(4):
        px2 = sx+3+i*5
        py2 = sy+TH//2+2
        pygame.draw.line(surf, c(55,185,135),(px2,py2),(px2-2,py2-6),2)
        pygame.draw.line(surf, c(55,185,135),(px2,py2),(px2+2,py2-5),2)

def draw_food_dot(surf, sx, sy):
    pygame.draw.circle(surf, c(175,215,75),(sx+TW//2,sy+TH//2),4)
    pygame.draw.circle(surf, c(205,235,100),(sx+TW//2,sy+TH//2),2)

def draw_seed_dot(surf, sx, sy):
    pygame.draw.circle(surf, c(195,170,88),(sx+TW//2,sy+TH//2),3)

def draw_animal(surf, sx, sy):
    cx, cy = sx+TW//2, sy+TH//2
    # body (seen from above = ellipse)
    pygame.draw.ellipse(surf, c(195,128,58),(cx-6,cy-4,12,8))
    pygame.draw.ellipse(surf, c(215,148,75),(cx-4,cy-3,8,6))
    # head
    pygame.draw.circle(surf, c(195,128,58),(cx+6,cy-1),4)
    pygame.draw.circle(surf, BLACK,(cx+8,cy-2),1)

def draw_person(surf, sx, sy, col, is_king=False, is_selected=False):
    cx, cy = sx+TW//2, sy+TH//2
    # shadow ellipse
    pygame.draw.ellipse(surf, shade(T['grass'],-25),(cx-5,cy+3,10,4))
    # body circle (top-down)
    pygame.draw.circle(surf, col, (cx,cy), 6)
    pygame.draw.circle(surf, shade(col,40),(cx-2,cy-2),3)   # highlight
    if is_king:
        # crown points radiating outward
        for dx2,dy2 in ((-5,-5),(0,-7),(5,-5)):
            pygame.draw.circle(surf, GOLD,(cx+dx2,cy+dy2),2)
        pygame.draw.arc(surf, GOLD,
                        (cx-6,cy-7,12,8), 0, 3.14, 2)
    if is_selected:
        pygame.draw.circle(surf, WHITE,(cx,cy),8,2)
        pygame.draw.circle(surf, ACCENT,(cx,cy),10,1)

# ═══════════════════════════════════════════════════════════════════
#  CAMERA
# ═══════════════════════════════════════════════════════════════════
cam_x      = 0
cam_y      = 0
dragging   = False
drag_start = (0,0)
cam_start  = (0,0)

MAX_CAM_X  = world.width  * TW
MAX_CAM_Y  = world.height * TH

def world_to_screen(gx, gy):
    sx = PANEL_W + gx * TW - cam_x
    sy = gy * TH - cam_y
    return sx, sy

def screen_to_grid(mx, my):
    if mx < PANEL_W: return None, None
    gx = (mx - PANEL_W + cam_x) // TW
    gy = (my + cam_y) // TH
    if 0 <= gx < world.width and 0 <= gy < world.height:
        return int(gx), int(gy)
    return None, None

# ═══════════════════════════════════════════════════════════════════
#  FONTS
# ═══════════════════════════════════════════════════════════════════
try:
    F_TITLE = pygame.font.SysFont("Segoe UI",    20, bold=True)
    F_LG    = pygame.font.SysFont("Segoe UI",    15, bold=True)
    F_MD    = pygame.font.SysFont("Segoe UI",    13)
    F_SM    = pygame.font.SysFont("Consolas",    12)
    F_TINY  = pygame.font.SysFont("Consolas",    10)
except:
    F_TITLE = pygame.font.SysFont(None, 22, bold=True)
    F_LG    = pygame.font.SysFont(None, 17, bold=True)
    F_MD    = pygame.font.SysFont(None, 15)
    F_SM    = pygame.font.SysFont(None, 13)
    F_TINY  = pygame.font.SysFont(None, 11)

def txt(surf, text, x, y, font=None, col=None, anchor='topleft', shadow=False):
    font = font or F_SM
    col  = col  or WHITE
    s    = font.render(str(text), True, col)
    if shadow:
        sh = font.render(str(text), True, BLACK)
        surf.blit(sh, sh.get_rect(**{anchor:(x+1,y+1)}))
    r = s.get_rect(**{anchor:(x,y)})
    surf.blit(s, r)
    return r

def draw_bar(surf, x, y, w, h, val, maxv, fg, bg=(28,22,42)):
    pygame.draw.rect(surf, bg, (x,y,w,h), border_radius=2)
    fw = int(w * max(0, min(val,maxv)) / max(1,maxv))
    if fw: pygame.draw.rect(surf, fg, (x,y,fw,h), border_radius=2)
    pygame.draw.rect(surf, BORDER, (x,y,w,h), 1, border_radius=2)

def panel_section(surf, y, label, pw):
    pygame.draw.line(surf, BORDER, (6,y),(pw-6,y))
    pygame.draw.rect(surf, PANEL2, (6,y-1,len(label)*7+12,14), border_radius=3)
    txt(surf, label, 12, y+1, F_TINY, ACCENT)
    return y + 16

# ═══════════════════════════════════════════════════════════════════
#  MINIMAP
# ═══════════════════════════════════════════════════════════════════
MINI_SCALE = 3
MINI_W = world.width  * MINI_SCALE
MINI_H = world.height * MINI_SCALE
mini_surf = pygame.Surface((MINI_W, MINI_H))

MINI_TERRAIN_COL = {
    'grass':c(78,138,58),'water':c(52,108,186),'forest':c(32,82,38),
    'rock':c(118,112,108),'farm':c(152,122,48),'ready':c(208,188,52),
    'fiber':c(60,170,130),'stump':c(88,68,38),'rubble':c(98,92,85),
    'food':c(78,138,58),'seed':c(78,138,58),'fiber_spent':c(58,108,82),
}

def render_minimap():
    mini_surf.fill(BLACK)
    for gy in range(world.height):
        for gx in range(world.width):
            tile = world.grid[gy][gx]
            col  = MINI_TERRAIN_COL.get(tile.terrain, c(78,138,58))
            civ  = tile.civilization
            if civ:
                sym = getattr(civ,'symbol','')
                if sym in ('P','K','O'): col = entity_col(civ)
                elif sym == 'H':        col = c(72,112,188)
                elif sym == 'S':        col = c(92,132,200)
                elif sym == 'A':        col = c(195,128,58)
                elif sym == 'B':        col = c(200,180,80)
            pygame.draw.rect(mini_surf, col,
                             (gx*MINI_SCALE, gy*MINI_SCALE, MINI_SCALE, MINI_SCALE))

# ═══════════════════════════════════════════════════════════════════
#  GAME STATE
# ═══════════════════════════════════════════════════════════════════
tick         = 0
paused       = False
sim_speed    = 6
sim_accum    = 0.0
selected     = None
prev_ids     = {id(p):p for p in world.people}
prev_alive   = {p.name for p in world.people if p.isAlive}
wave_tick    = 0
log_msgs     = []
panel_scroll = 0
LOG_MAX      = 18

def add_log(msg, col=None):
    log_msgs.append((msg, col or MUTED))
    if len(log_msgs) > 120: log_msgs.pop(0)

def entity_col(p):
    if getattr(p,'is_king',False):    return GOLD
    if getattr(p,'is_outcast',False): return MUTED
    if getattr(p,'is_rebel',False):   return RED
    return c(135,195,255)

# ═══════════════════════════════════════════════════════════════════
#  RENDER MAP
# ═══════════════════════════════════════════════════════════════════
def render_map(surf):
    wave = (wave_tick // 40) % 2 == 0
    map_x0 = PANEL_W
    map_w   = SCR_W - PANEL_W

    # determine visible tile range
    gx_min = max(0, cam_x // TW)
    gy_min = max(0, cam_y // TH)
    gx_max = min(world.width,  gx_min + map_w // TW + 2)
    gy_max = min(world.height, gy_min + SCR_H // TH + 2)

    for gy in range(gy_min, gy_max):
        for gx in range(gx_min, gx_max):
            sx, sy = world_to_screen(gx, gy)
            tile    = world.grid[gy][gx]
            terrain = tile.terrain

            top = terrain_top(terrain, gx, gy, wave)
            dep = terrain_depth(terrain)
            rgt = terrain_right(terrain)
            elev = 2 if terrain in ('forest','rock') else (0 if terrain=='water' else 1)
            draw_tile(surf, sx, sy, top, dep, rgt, elev=elev)

            # terrain overlays
            if terrain == 'forest':    draw_tree(surf, sx, sy)
            elif terrain == 'rock':    draw_rock(surf, sx, sy)
            elif terrain == 'farm':    draw_farm_crop(surf, sx, sy, ripe=False)
            elif terrain == 'ready':   draw_farm_crop(surf, sx, sy, ripe=True)
            elif terrain == 'fiber':   draw_fiber_patch(surf, sx, sy)
            elif terrain == 'food':    draw_food_dot(surf, sx, sy)
            elif terrain == 'seed':    draw_seed_dot(surf, sx, sy)

            # civilisation objects
            civ = tile.civilization
            if civ is None: continue
            sym = getattr(civ,'symbol','?')

            if   sym == 'H': draw_hut(surf, sx, sy)
            elif sym == 'S': draw_storehouse(surf, sx, sy)
            elif sym == 'B': draw_build_site(surf, sx, sy)
            elif sym == 'A': draw_animal(surf, sx, sy)
            elif sym in ('P','K','O'):
                is_sel  = civ is selected
                is_king = getattr(civ,'is_king',False)
                draw_person(surf, sx, sy, entity_col(civ),
                            is_king=is_king, is_selected=is_sel)
                if is_sel:
                    txt(surf, civ.name, sx+TW//2, sy-2, F_TINY, WHITE,
                        anchor='midbottom', shadow=True)

# ═══════════════════════════════════════════════════════════════════
#  RENDER LEFT PANEL
# ═══════════════════════════════════════════════════════════════════
def render_panel(surf):
    pw = PANEL_W
    alive  = [p for p in world.people if p.isAlive]
    pop    = len(alive)
    rebels = sum(1 for p in alive if getattr(p,'is_rebel',False))

    ps = pygame.Surface((pw, SCR_H), pygame.SRCALPHA)
    pygame.draw.rect(ps, (*DARKER, 218), (0, 0, pw, SCR_H))
    pygame.draw.rect(ps, BORDER, (0, 0, pw, SCR_H), 1)

    y = 6

    # title bar
    pygame.draw.rect(ps, PANEL2, (4,y,pw-8,38), border_radius=6)
    txt(ps, "CIVILISATION", 12, y+5, F_TITLE, GOLD, shadow=True)
    spd_col = ORANGE if paused else GREEN
    spd_txt = "PAUSED" if paused else f"{sim_speed}x"
    txt(ps, f"Tick {tick}", pw-10, y+5, F_TINY, MUTED, anchor='topright')
    txt(ps, spd_txt, pw-10, y+20, F_SM, spd_col, anchor='topright')
    y += 48

    # stat cards
    for i,(label,val,col) in enumerate([
        ("POP",   f"{pop}/{world.population_cap}", ACCENT),
        ("BORN",  str(stats.total_born),           GREEN),
        ("DEATHS",str(len(stats.deaths_log)),      RED),
        ("HUTS",  str(len(world.huts)),             ORANGE),
    ]):
        bx = 4 + i*(pw//4)
        bw = pw//4 - 4
        pygame.draw.rect(ps, PANEL, (bx,y,bw,36), border_radius=4)
        pygame.draw.rect(ps, BORDER,(bx,y,bw,36), 1, border_radius=4)
        txt(ps, label, bx+bw//2, y+4, F_TINY, MUTED, anchor='midtop')
        txt(ps, val,   bx+bw//2, y+16, F_LG,  col,  anchor='midtop')
    y += 44

    # king section
    y = panel_section(ps, y, "KING & GOVERNANCE", pw)
    if world.king:
        k, kp = world.king, world.king.person
        immune = world.king.immunity_ticks
        txt(ps, kp.name, 10, y, F_LG, GOLD, shadow=True)
        txt(ps, f"Age:{kp.age}  INT:{kp.intelligence}", pw-8, y, F_TINY, MUTED, anchor='topright')
        y += 17
        txt(ps, k.style_name, 10, y, F_TINY, PURPLE)
        txt(ps, f"Tax:{k.tax_amount}  Len:{k.leniency}", pw-8, y, F_TINY, MUTED, anchor='topright')
        y += 13
        # immunity badge
        if immune > 0:
            pygame.draw.rect(ps, c(20,60,20),(10,y,pw-20,14), border_radius=3)
            txt(ps, f"IMMUNE from overthrow: {immune} ticks", pw//2, y+2, F_TINY, GREEN, anchor='midtop')
            y += 16
        loyal_n = pop - rebels - 1
        txt(ps, f"Loyal:{loyal_n}  Rebels:{rebels}", 10, y, F_TINY,
            TEAL if rebels == 0 else RED)
        y += 13
        # overthrow bar (only non-rebel starvation)
        thresh = max(1, max(1,pop-rebels)) * 3
        draw_bar(ps, 10, y, pw-20, 8, world.starvation_count, thresh,
                 RED if world.starvation_count/thresh > 0.6 else ORANGE,
                 bg=c(40,15,15))
        txt(ps, f"Overthrow: {world.starvation_count}/{thresh}", 10, y-12, F_TINY,
            RED if world.starvation_count/thresh > 0.6 else MUTED)
        y += 20
    elif world.council:
        txt(ps, "INTERREGNUM", 10, y, F_MD, ORANGE); y+=16
        txt(ps, f"Council of {len(world.council)}", 10, y, F_TINY, MUTED); y+=14
    else:
        txt(ps, "No ruler yet", 10, y, F_TINY, MUTED); y+=16
    y += 2

    # selected person
    if selected and selected.isAlive:
        p   = selected
        col = entity_col(p)
        y   = panel_section(ps, y, f"SELECTED: {p.name}", pw)
        status = ('KING' if p.is_king else
                  'OUTCAST' if getattr(p,'is_outcast',False) else
                  'REBEL'   if p.is_rebel else '')
        if status:
            pygame.draw.rect(ps, shade(PANEL2,8),(pw-62,y-14,56,13), border_radius=3)
            txt(ps, status, pw-34, y-13, F_TINY, col, anchor='midtop')
        txt(ps, f"Age:{p.age}  INT:{p.intelligence}  LR:{p.learning_rate}  Gen:{stats.generation.get(p.name,0)}",
            10, y, F_TINY, MUTED); y+=13
        # HP / hunger bars
        txt(ps, "HP", 10, y, F_TINY, GREEN)
        draw_bar(ps, 28, y, 116, 8, p.health, 100, GREEN)
        txt(ps, "HNG", 152, y, F_TINY, ORANGE)
        draw_bar(ps, 174, y, pw-182, 8, p.hunger, 100, ORANGE)
        y += 14
        if world.king and p is not world.king.person:
            loy = getattr(p,'loyalty',50)
            loy_col = RED if p.is_rebel else TEAL
            txt(ps, "LOY", 10, y, F_TINY, loy_col)
            draw_bar(ps, 32, y, pw-42, 8, loy, 100, loy_col); y+=14
        txt(ps, f"Task: {p.current_task}", 10, y, F_TINY, ACCENT); y+=13
        f2=p.inventory_count('food'); m=p.inventory_count('meat')
        h2=p.inventory_count('harvested'); w2=p.inventory_count('wood')
        st=p.inventory_count('stone'); fi=p.inventory_count('fiber')
        txt(ps, f"Inv[{len(p.inventory)}/25] F:{f2} M:{m} H:{h2} W:{w2} St:{st} Fi:{fi}",
            10, y, F_TINY, MUTED); y+=13
        farm = f"Farm@({p.farm_x},{p.farm_y})" if p.has_farm else "No farm"
        txt(ps, f"{farm}  Kids:{p.total_children}  Kills:{p.total_kills}",
            10, y, F_TINY, MUTED); y+=13
        pstr = ' & '.join(stats.parents.get(p.name,[])) or 'founders'
        txt(ps, f"Parents: {pstr[:34]}", 10, y, F_TINY, MUTED); y+=8
    y += 4

    # people list
    list_rows = min(len(alive), 10)
    y = panel_section(ps, y, "PEOPLE", pw)
    for p in alive[:list_rows]:
        col = entity_col(p)
        tag = 'K' if p.is_king else 'R' if p.is_rebel else 'O' if getattr(p,'is_outcast',False) else ' '
        txt(ps, f"[{tag}] {p.name:<10} HP:{p.health:<3} {p.current_task[:14]}",
            10, y, F_TINY, col); y+=13
    if len(alive) > list_rows:
        txt(ps, f"  ... +{len(alive)-list_rows} more", 10, y, F_TINY, MUTED); y+=13
    y += 4

    # event log
    y = panel_section(ps, y, "EVENTS", pw)
    visible = log_msgs[max(0,len(log_msgs)-LOG_MAX-panel_scroll):
                       len(log_msgs)-panel_scroll if panel_scroll else None]
    for msg, col in visible[-LOG_MAX:]:
        txt(ps, msg[:40], 10, y, F_TINY, col); y+=13

    # controls hint
    y = SCR_H - 48
    pygame.draw.line(ps, BORDER, (6,y),(pw-6,y))
    y += 4
    for line in ["SPACE pause  +/- speed  ESC deselect",
                 "LClick select  RDrag pan  Scroll log"]:
        txt(ps, line, pw//2, y, F_TINY, MUTED, anchor='midtop'); y+=12

    surf.blit(ps, (0,0))

# ═══════════════════════════════════════════════════════════════════
#  TOP BAR
# ═══════════════════════════════════════════════════════════════════
def render_topbar(surf):
    pygame.draw.rect(surf, (*DARKER,210), (PANEL_W, 0, SCR_W-PANEL_W, 26))
    pygame.draw.line(surf, BORDER, (PANEL_W,26),(SCR_W,26))
    cx = PANEL_W + (SCR_W-PANEL_W)//2
    txt(surf, "SPACE=pause   +/-=speed   Click=select person   RMB drag=pan   ESC=deselect",
        cx, 6, F_TINY, MUTED, anchor='midtop')

# ═══════════════════════════════════════════════════════════════════
#  MINIMAP OVERLAY  (bottom-right)
# ═══════════════════════════════════════════════════════════════════
def render_minimap_overlay(surf):
    render_minimap()
    mx = SCR_W - MINI_W - 8
    my = SCR_H - MINI_H - 8
    pygame.draw.rect(surf, (*DARKER,210),(mx-3,my-3,MINI_W+6,MINI_H+6), border_radius=4)
    surf.blit(mini_surf, (mx,my))
    pygame.draw.rect(surf, BORDER,(mx-3,my-3,MINI_W+6,MINI_H+6),1, border_radius=4)
    txt(surf,"MAP",mx+3,my+2,F_TINY,MUTED)
    # camera viewport rect on minimap
    vx = int((cam_x / max(1,MAX_CAM_X)) * MINI_W)
    vy = int((cam_y / max(1,MAX_CAM_Y)) * MINI_H)
    vw = int(((SCR_W-PANEL_W) / max(1,MAX_CAM_X)) * MINI_W)
    vh = int((SCR_H / max(1,MAX_CAM_Y)) * MINI_H)
    pygame.draw.rect(surf, WHITE,(mx+vx,my+vy,max(4,vw),max(4,vh)),1)

# ═══════════════════════════════════════════════════════════════════
#  SIMULATION STEP
# ═══════════════════════════════════════════════════════════════════
def sim_step():
    global tick, prev_ids, prev_alive
    tick += 1
    ph = len(world.huts); ps2 = len(world.storehouses)

    for person in list(world.people):
        if person.isAlive: person.tick(world, tick)
    world.update_king(tick)

    for p in world.people:
        if id(p) not in prev_ids:
            pnames = getattr(p,'parent_names',
                     [x.name for x in world.people if x is not p and x.birth_cooldown>140])
            stats.register_birth(p, pnames, tick)
            add_log(f"T{tick}: {p.name} born", GREEN)

    for p in world.people:
        if p.name in prev_alive and not p.isAlive:
            stats.record_death(p, tick)
            add_log(f"T{tick}: {p.name} died ({p.cause_of_death or '?'})", RED)
            if selected is p: selected = None

    nh = len(world.huts)-ph; ns = len(world.storehouses)-ps2
    if nh: stats.huts_built+=nh;        add_log(f"T{tick}: Hut built!", ORANGE)
    if ns: stats.storehouses_built+=ns; add_log(f"T{tick}: Storehouse built!", TEAL)

    if world.succession_log:
        st,sn,sr = world.succession_log[-1]
        if st==tick: add_log(f"T{tick}: {sn} — {sr}", GOLD)

    world.grow_farms(); world.update_regrowth()
    world.update_animals(tick)
    if tick%50==0: world.respawn_animals()
    world.apply_hut_healing(); world.recompute_population_cap(); world.prune_dead()

    prev_ids   = {id(p):p for p in world.people}
    prev_alive = {p.name for p in world.people if p.isAlive}
    stats.peak_population = max(stats.peak_population,
                                sum(1 for p in world.people if p.isAlive))

# ═══════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════════
running = True
while running:
    dt = clock.tick(FPS) / 1000.0
    wave_tick += 1

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                sim_speed = min(60, sim_speed+1)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                sim_speed = max(1, sim_speed-1)
            elif event.key == pygame.K_ESCAPE:
                selected = None

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if event.button == 1 and mx > PANEL_W:
                gx, gy = screen_to_grid(mx, my)
                if gx is not None:
                    civ = world.grid[gy][gx].civilization
                    selected = civ if civ and getattr(civ,'symbol','') in ('P','K','O') else None
            elif event.button == 3:
                dragging=True; drag_start=event.pos; cam_start=(cam_x,cam_y)
            elif event.button == 4:
                panel_scroll = max(0, panel_scroll-1)
            elif event.button == 5:
                panel_scroll += 1

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3: dragging=False

        elif event.type == pygame.MOUSEMOTION:
            if dragging:
                dx = event.pos[0]-drag_start[0]
                dy = event.pos[1]-drag_start[1]
                cam_x = max(0, min(cam_start[0]-dx, MAX_CAM_X))
                cam_y = max(0, min(cam_start[1]-dy, MAX_CAM_Y))

        elif event.type == pygame.VIDEORESIZE:
            SCR_W=event.w; SCR_H=event.h
            screen=pygame.display.set_mode((SCR_W,SCR_H),pygame.RESIZABLE)

    if not paused and any(p.isAlive for p in world.people):
        sim_accum += dt * sim_speed
        while sim_accum >= 1.0:
            sim_accum -= 1.0
            sim_step()

    screen.fill(c(12,10,18))
    render_map(screen)
    render_topbar(screen)
    render_panel(screen)
    render_minimap_overlay(screen)
    pygame.display.flip()

pygame.quit()
sys.exit()