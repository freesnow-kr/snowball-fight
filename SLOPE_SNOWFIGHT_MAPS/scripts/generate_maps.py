"""SLOPE SNOWFIGHT maps — 5 Blender maps → .blend / .glb / metadata / renders.

Run:  blender --background --python scripts/generate_maps.py -- base_camp [slope_field ...] [--no-render]
Play area: Blender X,Y ∈ [-50, 50] (= glTF/three x,z ∈ [-50, 50]); terrain height in Blender Z (= three y).
Everything outside the square (backdrop hills, far trees, mountains, aurora) is decoration.
"""
import os, sys, math, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import generate_props as GP
from export_glb import export_objects
import render_preview as RP

HALF = 50.
def nz(x, y, s, seed=0): return noise.noise(Vector((x * s + seed * 17.3, y * s - seed * 9.1, seed * .7)))
def fbm(x, y, s, seed=0, o=3):
    return sum(nz(x, y, s * 2**i, seed + i) / 2**i for i in range(o))
def sst(a, b, x): t = max(0., min(1., (x - a) / (b - a))); return t * t * (3 - 2 * t)
def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay; t = max(0., min(1., ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy + 1e-9)))
    return math.hypot(px - ax - dx * t, py - ay - dy * t)
def path_dist(x, y, paths):
    return min((seg_dist(x, y, *p[i], *p[i + 1]) for p in paths for i in range(len(p) - 1)), default=1e9)

# ══════════════════════ map definitions (heights in Blender Z; x,y Blender) ══════════════════════
class MapDef:
    id = name = ''; kind = 'day'; paths = []; plaza = None
    def height(self, x, y): return 0.
    def outside(self, x, y):  # backdrop height beyond the play square
        d = max(abs(x), abs(y)) - HALF
        return self.height(max(-HALF, min(HALF, x)), max(-HALF, min(HALF, y))) + sst(0, 45, d) * (10 + 9 * fbm(x, y, .025, 3)) + sst(30, 80, d) * 14 * max(0, fbm(x, y, .012, 5) + .6)
    def color(self, x, y, h, slope):
        n = fbm(x, y, .08, 11, 2)
        c = Vector((.93, .955, 1.0)) + Vector((-.03, -.02, 0)) * n
        if self.plaza: c = c.lerp(Vector((.9, .93, .98)), .5 * sst(self.plaza[2], self.plaza[2] - 3, math.hypot(x - self.plaza[0], y - self.plaza[1])))
        w = sst(1.8, .8, path_dist(x, y, self.paths)) if self.paths else 0
        c = c.lerp(Vector((.58, .66, .8)), w * .85)  # trodden snow path (linear colour)
        if slope > .7: c = c.lerp(Vector((.15, .18, .24)), sst(.7, 1.2, slope))  # exposed rock on steep cliffs (linear colour)
        return c
    def path_dip(self, x, y): return -.06 * sst(1.6, .7, path_dist(x, y, self.paths)) if self.paths else 0.
    def walk(self, x, y): return self.height(x, y)  # surface the game stands on (server heightfield)

class BaseCamp(MapDef):
    id, name = 'base_camp', 'Base Camp'
    paths = [[(0, 19), (0, 8), (-2, -4), (-14, -10), (-38, -6)], [(0, 8), (3, -4), (16, -9), (38, -6)], [(0, 8), (-10, 14), (-30, 22)], [(-2, -4), (0, -24), (2, -46)]]
    plaza = (0, -2, 15)
    def height(self, x, y):
        h = .45 * fbm(x, y, .045, 1)
        h *= 1 - .85 * sst(18, 6, math.hypot(x, y + 2))            # flat central plaza
        h += sst(30, 50, y) * 4.5 + sst(38, 50, abs(x)) * 2.6 + sst(40, 50, -y) * 2.0  # hill behind, banks on the sides
        for cx, cy, r, hh in ((-31, -30, 7, 1.8), (33, -31, 6, 1.5), (-36, 14, 6, 1.4), (35, 18, 7, 1.7), (-12, 38, 6, 1.2)):
            h += hh * math.exp(-((x - cx)**2 + (y - cy)**2) / r**2)
        return h + self.path_dip(x, y)

class SlopeField(MapDef):
    id, name = 'slope_field', 'Slope Field'
    paths = [[(0, -46), (0, -30)], [(38, -46), (38, 46)]]
    def slope_base(self, y): return 17 * max(0, (y + 28) / 78) ** 1.55
    def height(self, x, y):
        h = self.slope_base(y) + .35 * fbm(x, y, .06, 2) * sst(-30, -15, y) + .2 * fbm(x, y, .2, 7) * sst(-25, -10, y)
        h += sst(29, 47, abs(x)) * (3.5 + 1.5 * fbm(x, y, .05, 4))  # ridges along both sides of the piste
        h += .25 * fbm(x, y, .05, 9) * sst(-28, -40, y)               # gentle swells on the flat bottom
        pad = sst(10, 7, abs(x)) * sst(39, 42, y)                      # levelled pad for the top lodge
        h = h + (self.slope_base(42) - h) * pad
        return h + self.path_dip(x, y)

class IceLake(MapDef):
    id, name = 'ice_lake', 'Ice Lake'
    LAKE = (0, -2, 30, 22)
    paths = [[(-46, -4), (-33, -3)], [(46, -4), (33, -3)]]
    def lake_r(self, x, y):
        cx, cy, rx, ry = self.LAKE; return math.hypot((x - cx) / rx, (y - cy) / ry)
    def height(self, x, y):
        r = self.lake_r(x, y)
        h = -.7 * sst(1.05, .9, r) + sst(1.0, 1.35, r) * (1.1 + .5 * fbm(x, y, .07, 3))
        h += sst(29, 37, y + 2 * fbm(x, y, .08, 2)) * (10 + 3 * fbm(x, y, .06, 8)) * sst(.95, 1.4, r)   # steep rocky cliffs in the north
        h += sst(40, 50, abs(x)) * 2 + sst(40, 50, -y) * 2
        return h + self.path_dip(x, y)
    def color(self, x, y, h, slope):
        c = super().color(x, y, h, slope)
        if self.lake_r(x, y) < 1.02: c = Vector((.3, .5, .62))  # lake bed (seen through the ice edge)
        return c
    CAVE = (-2, 30.2)
    def cliff_mask(self, x, y, h):
        m = sst(25.5, 28.5, y) * sst(.8, 3.0, h)
        return m * (1 - .85 * sst(4.5, 2.5, math.hypot(x - self.CAVE[0], y - self.CAVE[1])))  # keep the cave mouth clear
    def cliff(self, x, y):
        """Stratified rock: terraces of 1.7 m (steep face, flat snowy ledge), phase-shifted and bumped by noise. Never below the terrain."""
        h = self.height(x, y); m = self.cliff_mask(x, y, h)
        if m <= 0: return h
        L = 2.4; hp = h + .35 * (fbm(x, 0, .03, 13) + 1) * .5 + .3  # strata run almost level along x (no staircase jaggies)
        k = math.floor(hp / L); f = hp / L - k
        S = L * (k + 1 - (1 - f) ** 6) + .3 * max(0, fbm(x, y, .16, 17)) * sst(.2, .8, f)  # steep face, flat ledge, knobbly rock (bump period > grid)
        return h + m * (S - h) + .04
    def walk(self, x, y):
        t = self.cliff(x, y)
        return max(t, -.35) if self.lake_r(x, y) < 1.02 else t  # on the ice (not the lake bed); rim = whichever surface is on top

class ForestVillage(MapDef):
    id, name = 'forest_village', 'Forest Village'
    paths = [[(0, -48), (0, -12)], [(0, 12), (0, 48)], [(-48, 0), (-13, 0)], [(13, 0), (48, 0)],
             [(0, -14), (-14, -18), (-22, -6), (-22, 10), (-12, 20), (0, 16)], [(0, -14), (14, -18), (22, -6), (22, 10), (12, 20), (0, 16)]]
    plaza = (0, 0, 13)
    def height(self, x, y):
        h = .9 * fbm(x, y, .04, 4) + .3 * fbm(x, y, .12, 6)
        h *= 1 - .8 * sst(16, 8, math.hypot(x, y))
        h += sst(40, 50, abs(x)) * 2.2 + sst(40, 50, abs(y)) * 2.2
        return h + self.path_dip(x, y)

class NightResort(MapDef):
    id, name, kind = 'night_resort', 'Night Resort', 'night'
    paths = [[(0, 24), (0, -46)], [(-40, -6), (40, -6)], [(-18, 24), (18, 24)]]
    plaza = (0, -6, 18)
    def height(self, x, y):
        h = .35 * fbm(x, y, .05, 5)
        h *= 1 - .85 * sst(20, 8, math.hypot(x, y + 6))
        h += sst(28, 50, y) * 3.5 + sst(40, 50, abs(x)) * 2.4 + sst(40, 50, -y) * 2
        return h + self.path_dip(x, y)

class SnowBrawlArena(MapDef):
    """개인전(SNOW BRAWL) 전용: 지름 60 m 원형 설원 + 높은 눈벽 링. 나무 없음, 안쪽은 거의 평탄(굴린 눈이 지형을 따라 감)."""
    id, name = 'snow_brawl_arena', 'Snow Brawl Arena'
    R = 30.  # 바깥 눈벽 링 반지름(안쪽 플레이 영역)
    plaza = (0, 0, 9)
    def height(self, x, y):
        r = math.hypot(x, y)
        h = .12 * fbm(x, y, .06, 21) * sst(26, 8, r)              # 안쪽: 10 cm 남짓 결만(평탄)
        h += sst(31, 44, r) * (3.2 + 1.2 * fbm(x, y, .05, 23))     # 링 바깥: 둔덕 → 배경 설산으로 이어짐
        return h

MAPS = {m.id: m for m in (BaseCamp(), SlopeField(), IceLake(), ForestVillage(), NightResort(), SnowBrawlArena())}

# ══════════════════════ terrain + backdrop meshes ══════════════════════
def terrain(m, coll, step=1.):
    n = int(2 * HALF / step) + 1; V, C, F = [], [], []
    H = [[m.height(-HALF + i * step, -HALF + j * step) for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(n):
            x, y = -HALF + i * step, -HALF + j * step
            sx = (H[min(i + 1, n - 1)][j] - H[max(i - 1, 0)][j]) / (2 * step); sy = (H[i][min(j + 1, n - 1)] - H[i][max(j - 1, 0)]) / (2 * step)
            V.append((x, y, H[i][j])); C.append(tuple(m.color(x, y, H[i][j], math.hypot(sx, sy))))
    for i in range(n - 1):
        for j in range(n - 1): F.append((i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1))
    ob = Builder().add_arrays(V, F, 'terrain', colors=C).build('terrain', sharp_deg=89, collection=coll)
    return ob, H

def backdrop(m, coll, R=140., step=5.):
    """Snowy hills/mountains around the arena (decor). Seam matches the terrain edge."""
    n = int(2 * R / step) + 1; V, C, F, idx = [], [], [], {}
    for i in range(n):
        for j in range(n):
            x, y = -R + i * step, -R + j * step
            if max(abs(x), abs(y)) < HALF - step: continue
            h = m.outside(x, y) if max(abs(x), abs(y)) > HALF else m.height(max(-HALF, min(HALF, x)), max(-HALF, min(HALF, y))) - .3
            idx[(i, j)] = len(V); V.append((x, y, h))
            k = sst(4, 22, h - m.height(max(-HALF, min(HALF, x)), max(-HALF, min(HALF, y))))
            C.append(tuple(Vector((.94, .96, 1.0)).lerp(Vector((.78, .85, .95)), .6 * k)))
    for i in range(n - 1):
        for j in range(n - 1):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if all(k in idx for k in q): F.append(tuple(idx[k] for k in q))
    return Builder().add_arrays(V, F, 'terrain', colors=C).build('backdrop_hills', sharp_deg=89, collection=coll)

# ══════════════════════ placement + metadata ══════════════════════
class Scene:
    def __init__(self, m, props, coll):
        self.m, self.props, self.coll, self.objects, self.count = m, props, coll, [], {}
    def ground(self, x, y):
        if max(abs(x), abs(y)) <= HALF: return self.m.walk(x, y)
        return self.m.outside(x, y)
    def put(self, key, x, y, yaw=0., s=1., pitch=0., z=None, decor=None, sink=.05, name=None):
        proto = self.props[key]; self.count[key] = self.count.get(key, 0) + 1
        nm = name or f'{key}_{self.count[key]:02d}'
        col = proto['collider'].to_dict() if hasattr(proto['collider'], 'to_dict') else dict(proto['collider'])
        if z is None:
            fp = [(0, 0)]
            if col.get('shape') == 'box':
                w, d = col['size'][0] * s / 2, col['size'][1] * s / 2
                fp += [(ca * w * sx - sa * d * sy, sa * w * sx + ca * d * sy) for sx in (-1, 1) for sy in (-1, 1) for ca, sa in [(math.cos(yaw), math.sin(yaw))]]
            elif col.get('body'): fp += [(col['body'] * s * math.cos(a), col['body'] * s * math.sin(a)) for a in (0, 1.57, 3.14, 4.71)]
            z = min(self.ground(x + dx, y + dy) for dx, dy in fp) - sink
        ob = instance(proto, nm, (x, y, z), yaw, s, self.coll)
        if pitch: ob.rotation_mode = 'ZXY'; ob.rotation_euler = (pitch, 0, yaw)
        is_decor = bool(proto['decor']) if decor is None else decor
        self.objects.append({'name': nm, 'prop': key, 'blender': (x, y, z), 'yaw': yaw, 'pitch': pitch, 'scale': s, 'decor': is_decor, 'collider': col})
        return ob
    def free(self, x, y, r):
        """True if a circle of radius r at (x, y) touches no collider."""
        for o in self.objects:
            c = o['collider']
            if o['decor'] or not c: continue
            ox, oy = o['blender'][0], o['blender'][1]
            if c.get('shape') == 'box':
                ca, sa = math.cos(-o['yaw']), math.sin(-o['yaw']); dx, dy = x - ox, y - oy
                lx, ly = dx * ca - dy * sa, dx * sa + dy * ca
                if abs(lx) < c['size'][0] * o['scale'] / 2 + r and abs(ly) < c['size'][1] * o['scale'] / 2 + r: return False
            elif c.get('body') and math.hypot(x - ox, y - oy) < c['body'] * o['scale'] + r: return False
        return True

def collider_world(o):
    """Exact collider + server-compatible upright cylinders (maps.js body/ball/top format), three.js coordinates."""
    c, s = o['collider'], o['scale']; x, y, z = o['blender']; p = to_three((x, y, z))
    if not c or o['decor']: return None
    if c.get('shape') == 'box':
        w, d, h = (v * s for v in c['size']); yaw = o['yaw']
        if c.get('offset'):  # box centre shifted in prop space (e.g. cabin + porch)
            ox, oy = c['offset'][0] * s, c['offset'][1] * s
            x, y = x + ox * math.cos(yaw) - oy * math.sin(yaw), y + ox * math.sin(yaw) + oy * math.cos(yaw); p = to_three((x, y, z))
        n = max(1, math.ceil(max(w, d) / min(w, d))); r = min(w, d) / 2; along = w >= d
        cyl_list = []
        for i in range(n):
            t = (i + .5) / n - .5; lx, ly = (t * w, 0) if along else (0, t * d)
            wx, wy = x + lx * math.cos(yaw) - ly * math.sin(yaw), y + lx * math.sin(yaw) + ly * math.cos(yaw)
            tp = to_three((wx, wy, z)); cyl_list.append({'x': tp[0], 'z': tp[2], 'y': tp[1], 'body': round(r * 1.05, 2), 'ball': round(r * 1.1, 2), 'top': round(h, 2)})
        return {'shape': 'box', 'center': p, 'size': [round(w, 2), round(h, 2), round(d, 2)], 'rotation_y': round(yaw, 4), 'cylinders': cyl_list}
    if c.get('shape') == 'cylinders':
        out = []
        for lx, ly, rr in c['parts']:
            wx, wy = x + lx * math.cos(o['yaw']) - ly * math.sin(o['yaw']), y + lx * math.sin(o['yaw']) + ly * math.cos(o['yaw'])
            tp = to_three((wx, wy, z)); out.append({'x': tp[0], 'z': tp[2], 'y': tp[1], 'body': rr * s, 'ball': rr * s, 'top': c['top'] * s})
        return {'shape': 'cylinders', 'cylinders': out}
    cy = {'x': p[0], 'z': p[2], 'y': p[1], 'body': round(c['body'] * s, 2), 'ball': round(c['ball'] * s, 2), 'top': round(c['top'] * s, 2)}
    return {'shape': 'cylinder', **cy, 'cylinders': [cy]}

def scatter_trees(S, rnd, n, region, ok, kinds=('pine_tree_01', 'pine_tree_02', 'pine_tree_03', 'pine_tree_04'), gap=4.2, smin_=.8, smax_=1.25, tries=4000):
    placed = 0
    for _ in range(tries):
        if placed >= n: break
        x, y = rnd.uniform(*region[0]), rnd.uniform(*region[1])
        if not ok(x, y) or not S.free(x, y, gap * .5): continue
        if any(o['prop'].startswith('pine') and math.hypot(o['blender'][0] - x, o['blender'][1] - y) < gap for o in S.objects): continue
        k = rnd.choice(kinds); S.put(k, x, y, rnd.random() * 6.28, rnd.uniform(smin_, smax_), decor=max(abs(x), abs(y)) > HALF); placed += 1
    return placed

def lift_line(S, pts, yaw, cable_side=1.3, chairs_every=9.):
    """Towers along pts (Blender xy), cables with sag between tower heads, chairs hanging on both cables."""
    tops = []
    for i, (x, y) in enumerate(pts):
        ob = S.put('ski_lift_tower', x, y, yaw, decor=max(abs(x), abs(y)) > HALF - 1); tops.append(Vector((x, y, ob.location.z + 9.1)))
    b = Builder(); chair = S.props['ski_lift_chair']; side = Vector((math.cos(yaw), math.sin(yaw), 0))
    k = 0
    for s in (-1, 1):
        for a, c in zip(tops, tops[1:]):
            A, C = a + side * s * cable_side, c + side * s * cable_side; pts3 = catenary(A, C, .45, 14)
            b.add(tube(pts3, .035, 5, caps=False), 'metal_dark')
            ln = (C - A).length
            for t in [i / max(1, int(ln / chairs_every)) for i in range(1, int(ln / chairs_every))]:
                P = A.lerp(C, t) - Vector((0, 0, .45 * 4 * t * (1 - t))); k += 1
                inst = instance(chair, f'ski_lift_chair_{k:02d}', P, yaw + (math.pi if s > 0 else 0), 1, S.coll)
                S.objects.append({'name': inst.name, 'prop': 'ski_lift_chair', 'blender': tuple(P), 'yaw': yaw, 'pitch': 0, 'scale': 1, 'decor': True, 'collider': {}})
    cab = b.build(f'lift_cables_{len(S.objects)}', collection=S.coll)
    S.objects.append({'name': cab.name, 'prop': 'lift_cable', 'blender': (0, 0, 0), 'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': True, 'collider': {}})

def string_lights(S, a, b_, sag=.5, n=16, name='string_lights'):
    b = Builder(); pts = catenary(a, b_, sag, n)
    b.add(tube(pts, .012, 4, caps=False), 'black')
    for p in pts[1:-1]: b.add(ico(.07, 1), 'bulb', M(tuple(p - Vector((0, 0, .07)))))
    ob = b.build(f'{name}_{len(S.objects)}', collection=S.coll)
    S.objects.append({'name': ob.name, 'prop': 'string_lights', 'blender': (0, 0, 0), 'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': True, 'collider': {}})

# ══════════════════════ layouts (follow map.png concepts) ══════════════════════
def layout_base_camp(S):
    rnd = random.Random(101)
    S.put('wooden_cabin', 0, 27)                                                     # hero lodge facing the plaza
    S.put('bench', -7.2, 19.0, .25); S.put('bench', 7.2, 19.0, -.25); S.put('snowboard_rack', -6.6, 23.6, .35)
    for x, y in ((-2.4, 14), (2.4, 14), (-2.6, 6.5), (2.6, 6.5)): S.put('lantern_post', x, y)
    for x in (-10.4, -13, -15.6, 10.4, 13, 15.6): S.put('fence_wood', x, 20.5, 0)
    for x, y, yaw in ((-17.2, 22.2, 1.4), (17.2, 22.2, -1.4)): S.put('fence_wood', x, y, yaw)
    for x, y in ((-10.5, 9), (10.5, 9), (-15, -16), (15, -16)): S.put('banner_blue', x, y, 0)
    for x, y in ((-19, -1), (19, -1)): S.put('flag_red', x, y, 0)
    # cover in the plaza: symmetric low walls, high walls on the flanks, snow piles
    for x, y, yaw in ((-6.5, -1, .35), (6.5, -1, -.35), (0, -9.5, 0), (0, 4.5, 0), (-14, -7, 1.15), (14, -7, -1.15)): S.put('snow_wall_low', x, y, yaw)
    for x, y, yaw in ((-22, 6, 1.57), (22, 6, 1.57), (-8, -21, .3), (8, -21, -.3)): S.put('snow_wall_high', x, y, yaw)
    for x, y in ((-11, -13), (11, -13), (-25, -5), (25, -5), (-4, -30), (5, -29)): S.put('snow_pile', x, y, rnd.random() * 6, rnd.uniform(.85, 1.15))
    S.put('snowman', -10.5, 15.5, .5); S.put('snowman', 13.5, -25, -.4)
    for x, y, k in ((-27, -20, 'rock_01'), (29, 13, 'rock_02'), (-31, 9, 'rock_01'), (26, -35, 'rock_02'), (-9, 37, 'rock_01'), (14, 36, 'rock_01')): S.put(k, x, y, rnd.random() * 6, rnd.uniform(.8, 1.2))
    S.put('signpost', 3.6, 10.5, -.3); S.put('signpost', -3.5, -36, .2)
    spawn_zone = lambda x, y: 30 < abs(x) < 46 and -16 < y < 6
    scatter_trees(S, rnd, 46, ((-49, 49), (-49, 49)), lambda x, y: (math.hypot(x, y + 2) > 25 or y > 32) and not spawn_zone(x, y) and not (abs(x) < 12 and 15 < y < 38) and path_dist(x, y, S.m.paths) > 3)
    scatter_trees(S, rnd, 50, ((-120, 120), (-120, 120)), lambda x, y: max(abs(x), abs(y)) > 53 and max(abs(x), abs(y)) < 110, kinds=('pine_tree_far',), gap=6, smin_=.9, smax_=1.5)
    # background ski hill: lift climbing behind the lodge (concept image)
    S.put('ski_lift_station', -30, 44, 0, decor=True)
    lift_line(S, [(-28, 52), (-28, 66), (-28, 80), (-28, 94)], 0)
    S.put('small_cabin', -14, 92, 0, decor=True)
    string_lights(S, (-11.5, 20.5, S.ground(-11.5, 20.5) + 1.25), (-2.4, 14, S.ground(-2.4, 14) + 1.9), .4)
    string_lights(S, (11.5, 20.5, S.ground(11.5, 20.5) + 1.25), (2.4, 14, S.ground(2.4, 14) + 1.9), .4)
    return {'pink': ((-44, -32), (-16, 6)), 'blue': ((32, 44), (-16, 6))}

def layout_slope_field(S):
    rnd = random.Random(202); m = S.m
    pitch = lambda y: math.atan((m.slope_base(y + .5) - m.slope_base(y - .5)))
    for side in (-1, 1):
        y = -30.
        while y < 47:
            S.put('fence_red', side * 27, y + 1.25, math.pi / 2, pitch=pitch(y + 1.25) * side * 0 + pitch(y + 1.25), sink=.15); y += 2.5
    for i, (y, x) in enumerate(((-16, -6), (-3, 6), (10, -6), (23, 6), (36, -5))):
        S.put('gate_red' if i % 2 == 0 else 'gate_blue', x, y, 0, pitch=pitch(y))
    for x, y in ((-9, 4), (10, 17), (-1, 31)): S.put('jump_ramp', x, y, 0, pitch=pitch(y), sink=.1)
    S.put('arch_gate', 0, -29, 0)
    for x, y, yaw in ((-13, -37, .2), (13, -37, -.2), (0, -43, 0), (-6, -20, .4), (7, -22, -.4)): S.put('snow_wall_low', x, y, yaw)
    for x, y, yaw in ((-21, -24, 1.4), (21, -24, -1.4)): S.put('snow_wall_high', x, y, yaw)
    for x, y in ((-18, -42), (18, -42), (0, -35)): S.put('snow_pile', x, y, rnd.random() * 6)
    for x in (-24.5, -19.5): S.put('safety_net', x, -31, 0)
    for x in (19.5, 24.5): S.put('safety_net', x, -31, 0)
    for x, y in ((-24, -26), (24, -26)): S.put('banner_blue', x, y, 0)
    for x, y in ((-3, 43), (3, 43), (-24, -45), (24, -45)): S.put('flag_red', x, y, 0)
    S.put('signpost', -24, -38, .3); S.put('signpost', 24, -38, -.3)
    S.put('wooden_cabin', 0, 47.5, 0, decor=False)
    S.put('snowman', 8, -40, -.5)
    S.put('ski_lift_station', 38, -44, 0); S.put('ski_lift_station', 38, 46, math.pi, decor=True)
    lift_line(S, [(38, -36), (38, -20), (38, -4), (38, 12), (38, 28), (38, 41)], 0)
    scatter_trees(S, rnd, 40, ((-49, 49), (-49, 49)), lambda x, y: abs(x) > 31 and not (33 < x < 43) and not (abs(x) > 30 and y < -30 and abs(x) < 44), gap=4.5)
    scatter_trees(S, rnd, 50, ((-120, 120), (-120, 120)), lambda x, y: max(abs(x), abs(y)) > 53, kinds=('pine_tree_far',), gap=6, smin_=.9, smax_=1.5)
    return {'pink': ((-24, -10), (-46, -34)), 'blue': ((10, 24), (-46, -34))}

def ice_surface(S):
    """Lake ice: radial disk with depth colour (deep teal centre → bright rim) + raised crack lines."""
    m = S.m; cx, cy, rx, ry = m.LAKE; V, F, C = [], [], []; NR, NA = 14, 72
    V.append((cx, cy, -.35)); C.append((.04, .27, .4))
    for i in range(1, NR + 1):
        u = i / NR
        for a in range(NA):
            t = 2 * math.pi * a / NA; V.append((cx + rx * 1.02 * u * math.cos(t), cy + ry * 1.02 * u * math.sin(t), -.35))
            k = u ** 1.3; C.append((.04 + .66 * k, .27 + .62 * k, .4 + .55 * k))  # deep teal centre → bright rim (linear)
    for a in range(NA): F.append((0, 1 + a, 1 + (a + 1) % NA))
    for i in range(NR - 1):
        for a in range(NA): F.append((1 + i * NA + a, 1 + (i + 1) * NA + a, 1 + (i + 1) * NA + (a + 1) % NA, 1 + i * NA + (a + 1) % NA))
    b = Builder().add_arrays(V, F, 'terrain', colors=C)
    rnd = random.Random(9)
    for k in range(16):  # cracks
        x, y = cx + rnd.uniform(-.7, .7) * rx, cy + rnd.uniform(-.7, .7) * ry; ang = rnd.random() * 6.28; pts = []
        for i in range(8):
            pts.append((x, y, -.335)); ang += rnd.uniform(-.6, .6); x += math.cos(ang) * 1.6; y += math.sin(ang) * 1.6
            if m.lake_r(x, y) > .95: break
        if len(pts) > 2: b.add(tube(pts, .035, 4, caps=False), 'icicle', M(scale=(1, 1, .3)) if False else None)
    ob = b.build('ice_lake_surface', sharp_deg=89, collection=S.coll)
    S.objects.append({'name': ob.name, 'prop': 'ice_surface', 'blender': (cx, cy, -.35), 'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': False, 'collider': {}})

def ice_cliff(S):
    """Separate 0.5 m cliff mesh over the north slope: rock strata, snowy ledges, ice veins (vertex colour = glTF-safe)."""
    m = S.m; step, sy = .4, .3; xs = [-50 + i * step for i in range(251)]; ys = [24 + j * sy for j in range(88)]; NY = len(ys); NX = len(xs)  # y 24 → 50.1: covers everything the heightfield calls cliff
    Hc = [[m.cliff(x, y) for y in ys] for x in xs]; V, C, F = [], [], []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            gx = (Hc[min(i + 1, NX - 1)][j] - Hc[max(i - 1, 0)][j]) / (2 * step); gy = (Hc[i][min(j + 1, NY - 1)] - Hc[i][max(j - 1, 0)]) / (2 * sy)
            nz = 1 / math.sqrt(1 + gx * gx + gy * gy); h = Hc[i][j]
            rockv = .5 + .5 * fbm(x, y + h, .25, 21)
            c = Vector((.035, .045, .07)).lerp(Vector((.12, .135, .18)), rockv)      # cold grey rock, two tones (linear)
            frac = ((h - .3) / 2.4) % 1
            c = c.lerp(Vector((.02, .025, .04)), .6 * sst(.12, 0, frac) * (1 - nz))  # dark seams between strata
            vein = sst(.94, .995, abs(math.sin(x * .55 + 4 * fbm(x, y, .15, 23)))) * sst(.75, .4, nz) * sst(.1, .5, fbm(x, 0, .07, 29))
            c = c.lerp(Vector((.22, .5, .68)), .9 * vein)                            # pale blue ice in a few cracks
            c = c.lerp(Vector((.93, .955, 1.0)), sst(.55, .78, nz))                   # snow on ledges / flats
            V.append((x, y, h)); C.append(tuple(c))
    for i in range(NX - 1):
        for j in range(NY - 1): F.append((i * NY + j, (i + 1) * NY + j, (i + 1) * NY + j + 1, i * NY + j + 1))
    ob = Builder().add_arrays(V, F, 'terrain', colors=C).build('ice_cliff', sharp_deg=89, collection=S.coll)
    S.objects.append({'name': ob.name, 'prop': 'ice_cliff', 'blender': (0, 0, 0), 'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': False, 'collider': {}})
    # icicles under ledge lips
    rnd = random.Random(31); b = Builder()
    for x in [-48 + k * 1.15 for k in range(84)]:
        if min(abs(x - c) for c in (-15, 11, m.CAVE[0])) < 3: continue
        col = [m.cliff(x, 24 + t * .1) for t in range(220)]
        for t in range(2, 218):
            if col[t + 1] - col[t] < .02 and col[t] - col[t - 2] > .5 and rnd.random() < .7:  # top of a steep rise = ledge lip
                y, z = 24 + t * .1, col[t]
                for n in range(rnd.randint(2, 4)):
                    ln = rnd.uniform(.3, .85); dx = rnd.uniform(-.45, .45)
                    b.add(cyl(rnd.uniform(.05, .1), .004, ln, 5), 'icicle_light', M((x + dx, y - .3 - rnd.uniform(0, .15), z - ln / 2 - .05), rot=(math.pi, 0, 0)))
    ic = b.build('cliff_icicles', collection=S.coll)
    S.objects.append({'name': ic.name, 'prop': 'cliff_icicles', 'blender': (0, 0, 0), 'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': True, 'collider': {}})
    for x in (-44, -38, -29, -20, -8.5, 6, 16, 25, 35, 45):
        S.put('snow_pile', x + rnd.uniform(-1, 1), 27.3 + rnd.uniform(-.4, .4), rnd.random() * 6, rnd.uniform(.9, 1.4), decor=True)
    # the cliff is not climbable: one invisible box along its foot (one box → no ping-pong between neighbours)
    S.objects.append({'name': 'cliff_collider', 'prop': 'cliff_collider', 'virtual': True, 'blender': (0, 31.5, S.ground(0, 27.5)),
                      'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': False, 'collider': {'shape': 'box', 'size': [104, 6, 14]}})

def layout_ice_lake(S):
    rnd = random.Random(303); m = S.m
    ice_surface(S); ice_cliff(S)
    for x, y, s in ((-8, 4, 1.2), (-6.6, 4.3, .9), (7, -9, 1.3), (8.4, -8.6, .9), (-14, -12, 1.1), (15, 6, 1.2), (0, -14, 1.0), (2, 12, 1.1), (-20, 0, .95)):
        S.put('ice_block', x, y, rnd.random() * 1.5, s, z=-.36)
    for x, y in ((-3, -3), (11, 1), (-12, 11)): S.put('ice_pillar', x, y, rnd.random(), rnd.uniform(.9, 1.2), z=-.36)
    S.put('ice_arch', 18, -3, 1.57, 1.0, z=-.36)
    for x, y, yaw in ((-31, 12, 1.2), (31, 12, -1.2), (-28, -18, -1.0), (28, -18, 1.0)): S.put('snow_wall_low', x, y, yaw)
    for x, y, yaw in ((-35, -2, 1.57), (35, -2, 1.57)): S.put('snow_wall_high', x, y, yaw)
    for x, y, yaw in ((-15, 30.5, .1), (11, 30.8, -.1)): S.put('frozen_waterfall', x, y, yaw, 1.15, z=S.ground(x, y - 1.5) - .3, decor=False)
    S.put('ice_arch', -2, 30.2, 0, 1.45, z=S.ground(-2, 28.5) - .2)  # ice cave mouth set into the cliff
    for x, y, s in ((-34, 30, 2.4), (-25, 29, 1.8), (-8, 29.5, 1.6), (4, 29.5, 1.7), (20, 29, 2.2), (30, 30, 2.6), (40, 31, 2.0)):
        S.put('rock_02', x, y, rnd.random() * 6, s)  # boulders along the cliff foot
    for i in range(14):
        a = i / 14 * 6.28 + .2; x, y = m.LAKE[0] + math.cos(a) * m.LAKE[2] * 1.14, m.LAKE[1] + math.sin(a) * m.LAKE[3] * 1.14
        if y < 26 and abs(x) < 46: S.put('rock_01' if i % 2 else 'rock_02', x, y, rnd.random() * 6, rnd.uniform(.6, 1.0))
    for x, y in ((-24, -26), (25, -27), (-36, 20)): S.put('snow_pile', x, y, rnd.random() * 6)
    S.put('snowman', -38, -10, .8)
    scatter_trees(S, rnd, 32, ((-49, 49), (-49, 49)), lambda x, y: m.lake_r(x, y) > 1.3 and y < 28 and not (30 < abs(x) < 46 and -16 < y < 8), gap=4.5)
    scatter_trees(S, rnd, 20, ((-46, 46), (34, 49)), lambda x, y: True, kinds=('pine_tree_04', 'pine_tree_02'), gap=5)
    scatter_trees(S, rnd, 50, ((-120, 120), (-120, 120)), lambda x, y: max(abs(x), abs(y)) > 53, kinds=('pine_tree_far',), gap=6, smin_=.9, smax_=1.5)
    return {'pink': ((-46, -34), (-14, 6)), 'blue': ((34, 46), (-14, 6))}

def rope_bridge(S, a, b_, name='rope_bridge'):
    b = Builder(); A, B = Vector(a), Vector(b_); n = int((B - A).length / .45)
    deck = catenary(A, B, .8, n); d = (B - A).normalized(); side = Vector((-d.y, d.x, 0))
    for p in deck[1:-1]: b.add(rbox(.4, 1.2, .07, .02), 'wood', M(tuple(p), rot=(0, 0, math.atan2(d.y, d.x))))
    for s in (-1, 1):
        rail = [p + side * s * .62 + Vector((0, 0, .9)) for p in catenary(A, B, .5, n)]
        b.add(tube(rail, .035, 5, caps=False), 'rope')
        for i in range(0, len(deck), 2): b.add(tube([deck[i] + side * s * .6, rail[i]], .02, 4), 'rope')
    ob = b.build(name, collection=S.coll)
    S.objects.append({'name': ob.name, 'prop': 'rope_bridge', 'blender': tuple(A), 'yaw': 0, 'pitch': 0, 'scale': 1, 'decor': True, 'collider': {}})

def layout_forest_village(S):
    rnd = random.Random(404); m = S.m
    t1 = S.put('treehouse_tree', -11, 30, .3); t2 = S.put('treehouse_tree', 11, 31, -.4)
    z = 4.2 + .1
    rope_bridge(S, (-8.2, 30.4, t1.location.z + z), (8.2, 30.6, t2.location.z + z))
    string_lights(S, (-9, 28, t1.location.z + 5.3), (9, 29, t2.location.z + 5.3), .9, 18)
    for x, y, yaw in ((-27, 14, .55), (27, 13, -.55), (-25, -27, 2.5), (26, -28, -2.5)): S.put('small_cabin', x, y, yaw)
    for x, y, yaw in ((-21.5, 9, .55), (-23, 6.6, .55), (21.5, 8.4, -.55), (23, 6, -.55)): S.put('fence_wood', x, y, yaw)
    for x, y, yaw in ((-4, -12, .4), (4, -12, -.4), (-3, 15, 0)): S.put('signpost', x, y, yaw)
    for x, y, yaw in ((-6, 3, .3), (6, -3, -.3), (0, -7, 0), (-9, -6, 1.2), (9, 6, 1.2)): S.put('snow_wall_low', x, y, yaw)
    for x, y in ((-5, -2), (4, 4), (11, -9), (-11, 9), (0, 9.5)): S.put('tree_stump', x, y, rnd.random() * 6)
    for x, y in ((-12, -1), (12, 1)): S.put('banner_blue', x, y, 0)
    for x, y, k in ((-17, -20, 'rock_01'), (18, 19, 'rock_02'), (-33, -3, 'rock_01'), (32, -40, 'rock_02')): S.put(k, x, y, rnd.random() * 6, .9)
    for x, y in ((-16, 22), (15, -22), (-30, -36)): S.put('snow_pile', x, y, rnd.random() * 6)
    S.put('snowman', 7.5, 11, -.6)
    on_path = lambda x, y: path_dist(x, y, m.paths) < 3.6
    scatter_trees(S, rnd, 95, ((-49, 49), (-49, 49)), lambda x, y: math.hypot(x, y) > 16 and not on_path(x, y) and not (34 < abs(x) < 47 and -8 < y < 8), gap=3.8, smin_=.75, smax_=1.3)
    scatter_trees(S, rnd, 80, ((-120, 120), (-120, 120)), lambda x, y: max(abs(x), abs(y)) > 53, kinds=('pine_tree_far',), gap=5, smin_=.9, smax_=1.6)
    return {'pink': ((-46, -36), (-6, 6)), 'blue': ((36, 46), (-6, 6))}

def layout_night_resort(S):
    rnd = random.Random(505)
    for x, y, yaw in ((-19, 31, .12), (0, 35, 0), (19, 31, -.12)): S.put('night_lodge', x, y, yaw)
    for x, y in ((-34, -30), (34, -30), (-34, 20), (34, 20)): S.put('floodlight_tower', x, y, math.atan2(-x, -(y + 6)) + math.pi)
    for y in (16, 6, -6, -18, -30, -42):
        for x in (-3.4, 3.4): S.put('lamp_post', x, y, 0 if x < 0 else math.pi)
    for x, y, yaw in ((-8, -2, .3), (8, -2, -.3), (-8, -14, -.3), (8, -14, .3), (0, -24, 0), (-18, -8, 1.2), (18, -8, -1.2), (0, 8, 0)): S.put('snow_wall_low', x, y, yaw)
    for x, y, yaw in ((-25, 2, 1.57), (25, 2, 1.57), (-14, -32, .2), (14, -32, -.2)): S.put('snow_wall_high', x, y, yaw)
    for x, y in ((-12, 20), (12, 20)): S.put('snowman', x, y, rnd.random())
    for x, y in ((-28, -16), (28, -16), (0, -36)): S.put('snow_pile', x, y, rnd.random() * 6)
    for x, y in ((-6, 22), (6, 22)): S.put('banner_blue', x, y, 0)
    S.put('ski_lift_station', 42, 30, 0, decor=True)
    lift_line(S, [(42, 40), (42, 54), (42, 68), (42, 82)], 0)
    scatter_trees(S, rnd, 34, ((-49, 49), (-49, 49)), lambda x, y: (abs(x) > 38 or y > 42 or y < -44) and not (36 < abs(x) < 47 and -18 < y < 6), gap=4.5)
    scatter_trees(S, rnd, 50, ((-120, 120), (-120, 120)), lambda x, y: max(abs(x), abs(y)) > 53, kinds=('pine_tree_far',), gap=6, smin_=.9, smax_=1.5)
    S.put('aurora', 0, 150, 0, z=35, decor=True); S.put('aurora', -60, 135, .4, .8, z=30, decor=True)
    for x, y in ((-27, 33), (27, 33)): string_lights(S, (x * .6, y - 3, S.ground(x * .6, y - 3) + 4.5), (x * .2, y - 5, S.ground(x * .2, y - 5) + 4.5), .7)
    return {'pink': ((-46, -36), (-18, 4)), 'blue': ((36, 46), (-18, 4))}

def layout_snow_brawl_arena(S):
    """나무·건물·좁은 통로 없음. 바깥 링 = 높은 눈벽(경계), 안쪽 = 낮은 눈벽·눈더미·눈사람 엄폐물(8방 대칭, 사이 3 m+ 통로).
    스폰 20곳(개인전 최대 20명)은 링 안쪽 r=25·18° 간격(9° 비킴), 엄폐물과 2.5 m+ 떨어진 평탄한 자리(서로 7.8 m 간격, 모두 가운데를 봄)."""
    rnd = random.Random(707); R = S.m.R
    n = math.ceil(2 * math.pi * (R + .5) / 2.9)                 # 3.3 m 벽을 2.9 m 간격으로 → 겹쳐서 틈 없음
    for i in range(n):
        a = 2 * math.pi * i / n; S.put('snow_wall_high', (R + .5) * math.cos(a), (R + .5) * math.sin(a), a + math.pi / 2, name=f'ring_wall_{i:02d}')
    for k in range(4):                                         # 안쪽 링: 낮은 벽 4개(r 10, 대각선) — 넘어갈 수 있는 엄폐
        a = math.pi / 4 + k * math.pi / 2; S.put('snow_wall_low', 10 * math.cos(a), 10 * math.sin(a), a + math.pi / 2)
    for k in range(4):                                         # 축 방향 r 16: 눈더미
        a = k * math.pi / 2; S.put('snow_pile', 16 * math.cos(a), 16 * math.sin(a), rnd.random() * 6, rnd.uniform(.9, 1.1))
    for k in range(4):                                         # 대각선 r 19: 눈사람(작은 조형물)
        a = math.pi / 4 + k * math.pi / 2; S.put('snowman', 19 * math.cos(a), 19 * math.sin(a), a + math.pi)
    for k in range(4):                                         # 축 방향 r 22, 옆으로 비킨 낮은 벽(스폰 앞 엄폐, 스폰과는 안 겹침)
        a = k * math.pi / 2 + .26; S.put('snow_wall_low', 21.5 * math.cos(a), 21.5 * math.sin(a), a)
    for k in range(6):                                         # 링 밖 장식(설산 앞 눈더미·깃발) — 충돌 없음
        a = k * math.pi / 3 + .3; S.put('snow_pile', 36 * math.cos(a), 36 * math.sin(a), rnd.random() * 6, 1.4, decor=True)
    for k in range(8): a = k * math.pi / 4 + math.pi / 8; S.put('flag_red', (R + 2.2) * math.cos(a), (R + 2.2) * math.sin(a), 0, decor=True)
    return {'ffa': [(25 * math.cos(math.pi / 20 + k * math.pi / 10), 25 * math.sin(math.pi / 20 + k * math.pi / 10)) for k in range(20)]}

LAYOUTS = {'snow_brawl_arena': layout_snow_brawl_arena, 'base_camp': layout_base_camp, 'slope_field': layout_slope_field, 'ice_lake': layout_ice_lake,
           'forest_village': layout_forest_village, 'night_resort': layout_night_resort}

# ══════════════════════ night: baked light pools on the snow (emissive texture → works with zero real-time lights) ══════════════════════
def bake_night_glow(S, terrain_ob, res=512):
    """Warm pools under every lamp, in front of every lodge, and where the floodlights aim — computed analytically
    (soft round falloff) into a 512² emissive texture on the terrain only. glTF: emissiveTexture (+ planar UVs)."""
    src = []  # (x, y, radius, linear rgb * intensity)
    for o in S.objects:
        x, y, z = o['blender']; yaw = o['yaw']
        if o['prop'] == 'lamp_post': src.append((x + .55 * math.cos(yaw), y + .55 * math.sin(yaw), 6.5, (.55, .34, .15)))
        if o['prop'] == 'night_lodge': src.append((x + math.sin(yaw) * 4.8, y - math.cos(yaw) * 4.8, 9.0, (.6, .32, .12)))
        if o['prop'] == 'floodlight_tower':
            d = math.hypot(x, y + 6) or 1; src.append((x - x / d * 14, y - (y + 6) / d * 14, 15.0, (.26, .24, .2)))
    xs = (np.arange(res) + .5) / res * 100 - 50
    X, Y = np.meshgrid(xs, xs)  # rows = y (image v), cols = x (image u)
    img = np.zeros((res, res, 3), np.float32)
    for sx, sy, r, c in src:
        k = np.clip(1 - ((X - sx)**2 + (Y - sy)**2) / r**2, 0, 1) ** 2
        img += k[..., None] * np.array(c, np.float32)
    img = np.clip(img, 0, 1)
    im = bpy.data.images.new('night_glow', res, res, alpha=False, float_buffer=False)
    im.colorspace_settings.name = 'sRGB'
    srgb_px = np.where(img <= .0031308, img * 12.92, 1.055 * np.power(img, 1 / 2.4) - .055)  # store as sRGB (glTF emissive texture is sRGB)
    im.pixels.foreach_set(np.concatenate([srgb_px, np.ones((res, res, 1), np.float32)], -1).ravel())
    im.pack()
    me = terrain_ob.data; uv = me.uv_layers.new(name='UVMap')
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    li = np.zeros(len(me.loops), int); me.loops.foreach_get('vertex_index', li)
    uv.data.foreach_set('uv', np.stack([(co[li, 0] + 50) / 100, (co[li, 1] + 50) / 100], 1).ravel())
    mt = mat('terrain').copy(); mt.name = 'terrain_night'; nt = mt.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'); tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = im
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Emission Color']); bsdf.inputs['Emission Strength'].default_value = 1.0
    me.materials[0] = mt
    log(f'night glow baked: {len(src)} light pools → {res}² emissive texture')

# ══════════════════════ environment presets (Blender lighting is NOT in the GLB) ══════════════════════
def environment(m, S):
    if m.kind == 'night':
        lights = []
        for o in S.objects:
            x, y, z = o['blender']
            if o['prop'] == 'lamp_post': lights.append({'type': 'point', 'position': to_three((x + .55 * math.cos(o['yaw']), y + .55 * math.sin(o['yaw']), z + 3.9)), 'color': '#ffd9a0', 'intensity': 18, 'distance': 14, 'decay': 2})
            if o['prop'] == 'floodlight_tower': lights.append({'type': 'spot', 'position': to_three((x, y, z + 11)), 'target': to_three((0, -6, 0)), 'color': '#fff1d6', 'intensity': 400, 'angle': .55, 'penumbra': .5, 'distance': 80, 'castShadow': False})
            if o['prop'] == 'night_lodge': lights.append({'type': 'point', 'position': to_three((x, y - 4.5, z + 2.2)), 'color': '#ffb85c', 'intensity': 30, 'distance': 16, 'decay': 2})
        return {'preset': 'night', 'background_top': '#0b1030', 'background_horizon': '#3a3f7a', 'fog': {'color': '#2a2f63', 'near': 40, 'far': 140},
                'hemisphere': {'sky': '#7d8cff', 'ground': '#1d2252', 'intensity': .55}, 'moon': {'direction': to_three((-.4, .6, .7)), 'color': '#a9b8ff', 'intensity': .45},
                'toneMapping': 'ACESFilmic', 'exposure': 1.15, 'emissive_in_glb': ['window', 'bulb', 'lamp', 'aurora'],
                'lights': lights, 'note': 'GLB contains no light objects. Emissive materials (windows, bulbs, lamp heads, aurora) are in the GLB; create the listed lights in the game engine.'}
    return {'preset': 'day', 'background_top': '#7fb8ea', 'background_horizon': '#f2f8ff', 'fog': {'color': '#d6ecf8', 'near': 45, 'far': 140},
            'hemisphere': {'sky': '#ffffff', 'ground': '#8aa7c7', 'intensity': 1.3}, 'sun': {'direction': to_three((.55, -.45, .7)), 'color': '#fff4e0', 'intensity': 1.6, 'castShadow': True},
            'toneMapping': 'None', 'exposure': 1.0, 'emissive_in_glb': ['window', 'bulb', 'lamp'], 'lights': [],
            'note': 'GLB contains no light objects; values match the current game (index.html) lighting.'}

def spawns(S, zones):
    if 'ffa' in zones:  # 개인전: 정해 둔 자리 그대로(평탄·엄폐물 2.5 m+ 는 검증 스크립트가 확인)
        return {'ffa': [to_three((x, y, S.ground(x, y))) for x, y in zones['ffa']]}
    out = {}
    for team, ((x0, x1), (y0, y1)) in zones.items():
        pts = []
        for i in range(400):
            x = x0 + (x1 - x0) * ((i * .618) % 1); y = y0 + (y1 - y0) * ((i * .382 + .17) % 1)
            sl = math.hypot(S.ground(x + .5, y) - S.ground(x - .5, y), S.ground(x, y + .5) - S.ground(x, y - .5))
            if sl < .3 and S.free(x, y, 2.5) and all(math.hypot(x - a, y - b) > 3 for a, b in pts): pts.append((x, y))
            if len(pts) == 4: break
        out[team] = [to_three((x, y, S.ground(x, y))) for x, y in pts]
    return out

# ══════════════════════ renders: 4 shots per map, with real game penguins for scale ══════════════════════
PENGUIN_GLB = os.path.join(os.path.dirname(ROOT), 'assets', 'penguin_blue.glb')
PINK = {'jacket_blue': '#ff65a8', 'jacket_trim_blue': '#e44d8f', 'beanie_blue': '#ff6fae', 'goggle_strap_blue': '#e8579a'}
def add_penguin(rc, loc, yaw, team):  # team: 'blue' | 'pink' | '#rrggbb'(옷·모자·고글끈 한 색)
    if not os.path.exists(PENGUIN_GLB): return
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=PENGUIN_GLB)
    new = [o for o in bpy.data.objects if o not in before]
    for o in [o for o in new if o.name.startswith('Icosphere')]:  # importer's bone-display helper, not part of the GLB
        new.remove(o); bpy.data.objects.remove(o)
    for o in new:
        for c in list(o.users_collection): c.objects.unlink(o)
        rc.objects.link(o)
    root = next(o for o in new if o.type == 'ARMATURE')
    root.scale = (1.3115,) * 3; root.location = loc; root.rotation_mode = 'XYZ'; root.rotation_euler = (0, 0, yaw)
    show = set(root.get('expressions', {}).get('normal', [])); face = {n for v in root.get('expressions', {}).values() for n in v}
    for o in new:
        if o.type != 'MESH': continue
        if o.name.split('.')[0] in face and o.name.split('.')[0] not in show: o.hide_render = True
        if team != 'blue':
            for i, ms in enumerate(o.material_slots):
                base = ms.material.name.split('.')[0] if ms.material else ''
                if base in PINK:
                    hexc = PINK[base] if team == 'pink' else team
                    nm = base + '_' + (team if team == 'pink' else team[1:]) + 'R'; pm = bpy.data.materials.get(nm)
                    if not pm:
                        pm = ms.material.copy(); pm.name = nm
                        nd = next(n for n in pm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'); nd.inputs['Base Color'].default_value = (*srgb(hexc), 1)
                    o.material_slots[i].material = pm

def render_map(m, S, H):
    rc = RP.setup(m.kind); out = os.path.join(ROOT, 'renders', m.id)
    if m.kind == 'night':
        for o in S.objects:
            x, y, z = o['blender']
            if o['prop'] == 'lamp_post': RP.point_light(rc, (x + .55 * math.cos(o['yaw']), y + .55 * math.sin(o['yaw']), z + 3.7), 220)
            if o['prop'] == 'floodlight_tower': RP.point_light(rc, (x * .9, y * .9 - 1, z + 10), 4500, '#fff1d6', 1.5)
            if o['prop'] == 'night_lodge':
                for dx in (-3, 0, 3): RP.point_light(rc, (x + dx, y - 4.8, z + 2.2), 160, '#ffb85c')
    g = lambda x, y: S.ground(x, y)
    P = {'base_camp': [(-3, 1, 0, 'blue'), (3.5, -4, .6, 'pink'), (-8, -6, -.7, 'pink'), (9, 4, 2.5, 'blue')],
         'slope_field': [(-4, -34, .3, 'blue'), (5, -30, -.5, 'pink'), (-8, 2, .2, 'pink'), (2, -38, 3.0, 'blue')],
         'ice_lake': [(-5, 2, .4, 'blue'), (6, -6, -.5, 'pink'), (-12, -9, .8, 'pink'), (13, 3, 2.6, 'blue')],
         'forest_village': [(-3, 1, .3, 'blue'), (4, -4, -.6, 'pink'), (-7, 6, .9, 'pink'), (8, 3, 2.4, 'blue')],
         'night_resort': [(-3, -6, .3, 'blue'), (5, -10, -.6, 'pink'), (-7, -1, .9, 'pink'), (9, -4, 2.4, 'blue')],
         'snow_brawl_arena': [(7 * math.cos(k * .31416), 7 * math.sin(k * .31416), k * .31416 + 1.57, c) for k, c in enumerate(('#F44336', '#2455E8', '#17A64A', '#963FE0', '#FF8800', '#00B8D9', '#F12A9B', '#8BC900', '#263D8F', '#D99500', '#00A884', '#C13CE0', '#99603B', '#3B9DFF', '#D81B60', '#E6C200', '#008C9E', '#FF6B6B', '#424B59', '#6043C9'))]}[m.id]
    for x, y, yaw, team in P: add_penguin(rc, (x, y, g(x, y)), yaw, team)
    shots = {
        'base_camp': [((-58, -62, 46), (0, 6, 0), 32), ((-28, -13, g(-28, -13) + 1.7), (0, 4, 2), 30), ((-15, -24, 9), (0, -1, 0), 32), ((-16, 5, g(-16, 5) + 2.6), (0, 26, 3.2), 32)],
        'slope_field': [((-70, -78, 48), (0, 0, 6), 30), ((-6, -46, g(-6, -46) + 1.7), (0, 0, 6), 28), ((-18, -50, 12), (0, -30, 0), 32), ((-14, 30, g(-14, 30) + 3.2), (0, 47.5, g(0, 47.5) + 3.5), 30)],
        'ice_lake': [((-60, -66, 44), (0, 4, 0), 32), ((-36, -6, g(-36, -6) + 1.7), (0, 2, 0), 28), ((-16, -30, 10), (0, -2, 0), 32), ((-6, 8, 2.6), (-2, 31, 4.5), 30)],
        'forest_village': [((-56, -64, 50), (0, 6, 0), 32), ((-40, 0, g(-40, 0) + 1.7), (0, 0, 2), 28), ((-14, -22, 10), (0, 0, 0), 32), ((-4, 14, 2.5), (0, 31, 6), 26)],
        'snow_brawl_arena': [((-44, -48, 40), (0, 0, 0), 30), ((-24, -4, 1.7), (0, 0, 1), 28), ((-14, -20, 9), (0, 0, 0), 32), ((0, -13, 3.2), (0, 0, 1), 32)],
        'night_resort': [((-58, -64, 40), (0, 12, 2), 30), ((-40, -10, g(-40, -10) + 1.7), (0, 0, 2), 28), ((-16, -32, 10), (0, -8, 0), 32), ((-8, 14, g(-8, 14) + 2.6), (0, 34, 4), 30)],
    }[m.id]
    for (loc, tgt, lens), nm in zip(shots, ('1_overview', '2_player_eye', '3_combat_zone', '4_landmark_closeup')):
        RP.shot(os.path.join(out, f'{m.id}_{nm}.png'), loc, tgt, lens)

# ══════════════════════ build one map ══════════════════════
def build_map(mid, render=True):
    reset_scene(); m = MAPS[mid]
    props = GP.build_props(); coll = collection(mid.upper())
    t, H = terrain(m, coll); bd = backdrop(m, coll)
    S = Scene(m, props, coll)
    zones = LAYOUTS[mid](S)
    for o in S.objects:  # anything placed beyond the square is scenery
        if max(abs(o['blender'][0]), abs(o['blender'][1])) > HALF: o['decor'] = True
    sp = spawns(S, zones)
    for o in S.objects:  # metadata = the real object transform (generated meshes have their origin at 0,0,0)
        if o.get('virtual'): continue
        ob = bpy.data.objects[o['name']]; o['blender'] = tuple(ob.location)  # parentless → location is world
    if m.kind == 'night': bake_night_glow(S, t)
    tris = tri_count(t) + tri_count(bd) + sum(tri_count(bpy.data.objects[o['name']]) for o in S.objects if not o.get('virtual'))
    log(f'{mid}: {len(S.objects)} objects, {tris} triangles')
    bpy.context.preferences.filepaths.save_version = 0
    blend = os.path.join(ROOT, 'blend', f'{mid}.blend'); bpy.ops.wm.save_as_mainfile(filepath=blend)
    # 압축 전 원본. 게임이 받는 파일은 scripts/compress_maps.sh 가 glb/maps 에 만든다(Meshopt)
    glb = os.path.join(ROOT, 'glb', 'maps_raw', f'{mid}.glb'); size = export_objects(list(coll.objects), glb)
    n = len(H); hs = [[round(m.walk(-HALF + i, -HALF + j), 2) for i in range(n)] for j in range(n)]  # walkable surface (ice, cliff ledges)
    meta = {
        'id': mid, 'name': m.name, 'size': [100, 100], 'center': [0, 0, 0],
        'coordinates': 'three.js / glTF: +Y up, play area x,z ∈ [-50, 50] (Blender x, -y). GLB node positions are already in this space.',
        'terrain': {'object': 'terrain', 'height_range': [round(min(map(min, H)), 2), round(max(map(max, H)), 2)], 'grid_step': 1.0,
                    'heightfield': {'note': 'heights[r][c] = terrain height (three y) at three x = -50 + c, z = -50 + r (1 m grid, 101×101)', 'heights': hs[::-1]}},
        'spawns': sp, 'environment': environment(m, S), 'triangles': tris, 'glb_bytes': size,
        'objects': [{'name': o['name'], 'prop': o['prop'], 'virtual': bool(o.get('virtual')), 'position': to_three(o['blender']), 'rotation_y': round(o['yaw'], 4), 'pitch': round(o['pitch'], 4),
                     'scale': o['scale'], 'decor': o['decor'], 'collision': bool(collider_world(o)), 'collider': collider_world(o)} for o in S.objects],
    }
    if mid == 'ice_lake': meta['ice_zone'] = {'shape': 'ellipse', 'center': to_three((m.LAKE[0], m.LAKE[1], 0)), 'radius_x': m.LAKE[2], 'radius_z': m.LAKE[3], 'note': 'slippery area'}
    json.dump(meta, open(os.path.join(ROOT, 'metadata', f'{mid}.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    log(f'{mid}: glb {size / 1e6:.2f} MB, spawns {[len(v) for v in sp.values()]}')
    if render: render_map(m, S, H)

if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ids = [a for a in args if a in MAPS] or list(MAPS)
    for mid in ids: build_map(mid, '--no-render' not in args)
    log('maps done', ids)
