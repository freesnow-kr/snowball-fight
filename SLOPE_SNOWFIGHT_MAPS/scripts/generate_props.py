"""SLOPE SNOWFIGHT maps — prop library (Blender, headless).

Run alone:  blender --background --python scripts/generate_props.py
  → builds every prop, exports glb/props/*.glb, renders renders/props/*.png
Imported by generate_maps.py: build_props() returns {name: prototype object}.

Every prop: origin at its ground centre, front = -Y (Blender) = +Z (glTF), meters.
Custom property 'collider' (local space) feeds the map metadata.
"""
import os, sys, math, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

PROTO = None  # collection holding prototypes (not exported with maps; maps use linked instances)

def finish(b, name, collider=None, decor=False, sharp=38):
    ob = b.build(name, sharp_deg=sharp, collection=PROTO)
    ob['collider'] = collider or {}
    ob['decor'] = decor
    return ob

# ══════════════════════ pine trees (4 distinct designs + a light background variant) ══════════════════════
def skirt(b, z_top, z_bot, R, S, K, sc, amp, droop, phase, rnd, material, p=.85, u_end=1., lift=0., grow=1., jit=.05, under=.35, under_mat=None):
    """One branch tier: apex → scalloped, drooping rim, closed underneath (no holes when seen from below)."""
    V, F = [(0, 0, z_top + lift)], []
    for k in range(1, K + 1):
        u = u_end * k / K
        for s in range(S):
            th = 2 * math.pi * s / S + phase; c = math.cos(sc * th)
            rad = R * grow * (u ** p) * (1 + amp * c * u * u) * (1 + jit * (rnd.random() - .5) * u)
            z = z_top - (z_top - z_bot) * u - droop * u * u * (.5 + .5 * c) + lift
            V.append((rad * math.cos(th), rad * math.sin(th), z))
    for s in range(S): F.append((0, 1 + s, 1 + (s + 1) % S))
    for k in range(K - 1):
        for s in range(S):
            a, c = 1 + k * S + s, 1 + k * S + (s + 1) % S
            F.append((a, a + S, c + S, c))
    rim = 1 + (K - 1) * S; zr = z_top - (z_top - z_bot) * u_end + lift
    inner = len(V)
    for s in range(S):
        x, y, z = V[rim + s]; V.append((x * .55, y * .55, zr + (z_top - zr) * under * .5))
    top_faces = len(F)
    for s in range(S):
        F.append((rim + s, inner + s, inner + (s + 1) % S, rim + (s + 1) % S))
    cen = len(V); V.append((0, 0, zr + (z_top - zr) * under))
    for s in range(S): F.append((inner + s, cen, inner + (s + 1) % S))
    if under_mat:  # shaded underside → reads as depth between tiers
        b.add(from_arrays(V, F[:top_faces]), material); b.add(from_arrays(V, F[top_faces:]), under_mat)
    else: b.add(from_arrays(V, F), material)

TREES = {  # height, tiers, base R, top R, first tier bottom, tier height, droop, scallops, scallop amp, snow share, trunk r, puff p
    'pine_tree_01': dict(H=8.6, n=6, R0=2.0, Rt=.55, zb=1.4, th=2.5, droop=.3, sc=9, amp=.10, snow=.45, trunk=.26, p=.85, pine='pine'),      # tall
    'pine_tree_02': dict(H=5.2, n=4, R0=2.3, Rt=.9, zb=.8, th=2.1, droop=.12, sc=7, amp=.07, snow=.55, trunk=.30, p=.55, pine='pine_light'),  # short & round
    'pine_tree_03': dict(H=6.6, n=4, R0=3.1, Rt=1.0, zb=1.3, th=2.0, droop=.55, sc=12, amp=.15, snow=.30, trunk=.38, p=.9, pine='pine_dark'), # wide branches
    'pine_tree_04': dict(H=7.2, n=5, R0=2.3, Rt=.6, zb=1.1, th=2.4, droop=.3, sc=8, amp=.10, snow=.85, trunk=.28, p=.8, pine='pine'),        # heavy snow
}
def pine(name, H, n, R0, Rt, zb, th, droop, sc, amp, snow, trunk, p, pine, S=20, K=3, seed=1):
    rnd = random.Random(seed); b = Builder()
    step = (H - th * .7 - zb) / max(1, n - 1)
    lowest = zb
    for i in range(n):
        t = i / max(1, n - 1); R = R0 * (1 - t) ** .85 + Rt * t; h = th * (1 - .3 * t)
        z_b = zb + i * step; z_t = min(z_b + h, H) if i < n - 1 else H
        ph = rnd.random() * 6.28
        skirt(b, z_t, z_b, R, S, K, sc, amp, droop * (1 - .3 * t), ph, rnd, pine, p=p, under_mat='pine_dark' if pine != 'pine_dark' else 'bark')
        skirt(b, z_t, z_b, R, S, max(2, K - 1), sc + 2, amp * 1.3, droop * .4, ph + .3, rnd, 'snow', p=p, u_end=snow + .1 * rnd.random(), lift=.05, grow=1.045, jit=.12)  # snow cap covers only the upper part → one ring fewer
    b.add(cyl(trunk, trunk * .7, lowest + 1.2, 10), 'bark', M((0, 0, (lowest + 1.2) / 2)))
    b.add(cyl(trunk * 1.5, trunk, .35, 10), 'bark', M((0, 0, .17)))  # root flare
    if snow > .7:  # extra snow clumps sitting on the tiers
        for i in range(n):
            t = i / max(1, n - 1); R = (R0 * (1 - t) ** .85 + Rt * t) * .55; z = zb + i * step + th * (1 - .3 * t) * .55
            for k in range(3):
                a = rnd.random() * 6.28; b.add(ico(.35 * (1 - .4 * t), 1), 'snow', M((R * math.cos(a), R * math.sin(a), z), scale=(1, 1, .6)))
    b.add(ico(.22, 1), 'snow', M((0, 0, H - .05), scale=(1, 1, 1.3)))
    return finish(b, name, {'shape': 'cylinder', 'body': round(trunk * 1.5, 2), 'ball': round(R0 * .55, 2), 'top': H}, sharp=89)  # soft foliage

# ══════════════════════ snow props ══════════════════════
def snow_wall(name, rows, blocks, bh, seed=3):
    """Stacked snow bricks (reference: 눈 벽): rounded, slightly irregular, staggered courses."""
    rnd = random.Random(seed); b = Builder(); bl, bd = .8, .6
    for r in range(rows):
        n = blocks - (r % 2); off = (bl / 2) * (r % 2)
        for i in range(n):
            x = (i - (blocks - 1) / 2) * bl + off + (rnd.random() - .5) * .04
            sz = (bl * (.96 + .04 * rnd.random()), bd * (.94 + .08 * rnd.random()), bh * (.95 + .05 * rnd.random()))
            top_jit = (rnd.random() - .5) * .05 if r == rows - 1 else 0
            b.add(rbox(*sz, bevel=.11, seg=3), 'snow' if (r + i) % 3 else 'snow_blue',
                  M((x, (rnd.random() - .5) * .04, bh * r + sz[2] / 2 + top_jit), rot=(0, (rnd.random() - .5) * .04, (rnd.random() - .5) * .07)))
    L = blocks * bl
    for s in (-1, 1):  # drifts at the base
        f = lambda x, y, z, s=s: sd_ell(x - s * (L / 2 - .2), y + .32, z, .55, .35, .28) + .03 * vnoise(x, y, z, 4, seed)
        b.add(sdf_bm(f, (s * (L / 2 - .2) - .7, -.8, -.3), (s * (L / 2 - .2) + .7, .1, .35), .03, 160, key=f'drift{rows}{s}'), 'snow')
    return finish(b, name, {'shape': 'box', 'size': [round(L + .1, 2), .7, round(rows * bh, 2)]}, sharp=55)

def snow_pile(name='snow_pile', seed=5):
    def f(x, y, z):
        d = sd_ell(x, y, z, 1.25, 1.0, .85)
        d = smin(d, sd_ell(x - .7, y + .3, z, .7, .6, .55), .35); d = smin(d, sd_ell(x + .65, y - .25, z, .6, .55, .45), .35)
        return smax(d + .05 * vnoise(x, y, z, 2.5, seed), -z, .1)
    b = Builder().add(sdf_bm(f, (-1.8, -1.4, -.2), (1.8, 1.4, 1.0), .04, 520, key=name), 'snow')
    return finish(b, name, {'shape': 'cylinder', 'body': 1.1, 'ball': 1.2, 'top': .8}, sharp=89)

def snowman(name='snowman'):
    b = Builder()
    f = lambda x, y, z: smax(smin(smin(sd_ell(x, y, z - .5, .58, .55, .52), sd_ell(x, y, z - 1.12, .42, .4, .4), .1), sd_ell(x, y, z - 1.6, .32, .31, .32), .08)
                             + .008 * vnoise(x, y, z, 6, 2), -z - .02, .05)
    b.add(sdf_bm(f, (-.7, -.7, -.1), (.7, .7, 1.98), .025, 1300, key=name), 'snow')
    for s in (-1, 1):
        b.add(ico(.045, 2), 'black', M((s * .11, -.28, 1.68)))  # coal eyes
    for i in range(5):  # coal smile
        a = math.pi * (1.2 + .6 * i / 4); b.add(ico(.025, 1), 'black', M((math.cos(a) * .12, -.3 + .02 * abs(i - 2) * 0, 1.55 + math.sin(a) * .05 + .02)))
    for z in (1.25, 1.05, .78): b.add(ico(.045, 1), 'black', M((0, -math.sqrt(max(0, .42**2 - (z - 1.12)**2)) - .02 if z > .9 else -.53, z)))
    b.add(cyl(.05, .005, .32, 10), 'orange', M((0, -.45, 1.6), rot=(math.pi / 2 + .1, 0, 0)))  # carrot
    b.add(torus(.31, .07, 20, 8), 'red', M((0, 0, 1.36), scale=(1, 1, .8)))  # scarf
    b.add(rbox(.13, .05, .38, .025), 'red', M((.16, -.33, 1.18), rot=(.15, 0, -.25)))
    for s in (-1, 1):  # twig arms with a fork
        p0, p1 = Vector((s * .36, 0, 1.15)), Vector((s * .95, .05, 1.45))
        b.add(tube([p0, p0.lerp(p1, .5) + Vector((0, 0, .03)), p1], lambda t: .035 * (1 - .6 * t), 6), 'bark')
        b.add(tube([p0.lerp(p1, .7), p0.lerp(p1, .7) + Vector((s * .12, 0, .2))], .018, 5), 'bark')
    b.add(cyl(.33, .1, .36, 18, bevel=.03), 'red', M((0, 0, 1.97)))  # knit hat
    b.add(torus(.31, .06, 20, 8), 'white', M((0, 0, 1.82)))
    b.add(ico(.09, 2), 'white', M((0, 0, 2.18)))
    return finish(b, name, {'shape': 'cylinder', 'body': .55, 'ball': .6, 'top': 2.2}, sharp=70)

def rock(name, seed, size=(1.6, 1.2, 1.0)):
    sx, sy, sz = size
    def rf(x, y, z):
        d = sd_ell(x, y, z - sz * .35, sx, sy, sz) + .18 * vnoise(x, y, z, 1.4, seed) + .06 * vnoise(x, y, z, 4, seed + 1)
        return smax(d, -z, .05)
    def sf(x, y, z):  # snow cap: thin shell on the upper part, edge broken up by noise
        top = sz * .55 + .25 * vnoise(x, y, z, 1.6, seed + 2)
        return np.maximum(np.abs(rf(x, y, z) - .06) - .06, top - z)
    lo, hi = (-sx * 1.4, -sy * 1.4, -.1), (sx * 1.4, sy * 1.4, sz * 1.6)
    b = Builder().add(sdf_bm(rf, lo, hi, .05, 700, key=name), 'rock')
    b.add(sdf_bm(sf, lo, hi, .03, 600, key=name + 's'), 'snow')
    return finish(b, name, {'shape': 'cylinder', 'body': round(max(sx, sy) * .85, 2), 'ball': round(max(sx, sy), 2), 'top': round(sz * 1.3, 2)}, sharp=72)

def fence(name, material='wood', length=2.5):
    b = Builder()
    for x in (-length / 2, length / 2):
        b.add(rbox(.15, .15, 1.2, .03), material, M((x, 0, .6)))
        b.add(ico(.11, 1), 'snow', M((x, 0, 1.22), scale=(1, 1, .55)))
    for z in (.45, .95):
        b.add(rbox(length, .07, .13, .025), material, M((0, 0, z)))
        b.add(rbox(length - .1, .1, .05, .025), 'snow', M((0, 0, z + .085)))  # snow on the rail
    return finish(b, name, {'shape': 'box', 'size': [length + .15, .3, 1.2]})

# ══════════════════════ buildings ══════════════════════
def roof_snow_sdf(w, d_len, y0, zw, a, over, t=.38, seed=7):
    """Thick snow blanket on a gable roof (ridge along Y), rounded ridge and drips along both eaves."""
    ca, sa = math.cos(a), math.sin(a); zr = zw + (w / 2) * math.tan(a); L = (w / 2 + over) / ca + .05
    rnd = random.Random(seed); drips = []
    for s in (-1, 1):
        for i in range(int(d_len / .55)):
            yy = y0 - d_len / 2 + (i + .5) * d_len / int(d_len / .55)
            drips.append((s, yy + (rnd.random() - .5) * .2, .12 + .1 * rnd.random(), .18 + .12 * rnd.random()))
    def f(x, y, z):
        out = None
        for s in (-1, 1):
            px, pz = x, z - zr - .2 * ca  # ridge on top of the roof boards
            w_ = s * px * ca - pz * sa * 1  # along slope (down)
            n_ = s * px * sa + pz * ca       # out of roof
            d = sd_box(w_ - L / 2, y - y0, n_ - t / 2, L / 2, d_len / 2 + .08, t / 2, t * .45)
            out = d if out is None else smin(out, d, .25)
        for s, yy, rr, hh in drips:  # rounded lumps hanging over the eave
            ex = s * (L * ca) ; ez = zr + .2 * ca - L * sa
            out = smin(out, sd_ell(x - ex, y - yy, z - ez + .05, rr * 1.1, rr * 1.6, hh), .14)
        return out + .025 * vnoise(x, y, z, 2.2, seed)
    lo = (-w / 2 - over - .8, y0 - d_len / 2 - .5, zw - 1.2); hi = (w / 2 + over + .8, y0 + d_len / 2 + .5, zr + .9)
    return f, lo, hi

def cabin(name, w=9., d=7., wall_h=3.2, pitch=38, porch=2.2, lights=True, front_over=1.6, wins=2, seed=7, night=False):
    """Stylized log cabin: interlocked logs, plank gables, thick snow roof with drips, porch, steps, rail, chimney, glowing windows."""
    b = Builder(); a = math.radians(pitch); r = .17; sp = r * 1.9; base = .45
    b.add(rbox(w + .5, d + .5, base, .06), 'stone', M((0, 0, base / 2)))
    n = int((wall_h - .05) / sp)
    for i in range(n):  # front/back logs at even heights, side logs half a log higher (interlocking corners)
        z = base + r + i * sp
        for y in (-d / 2, d / 2):
            b.add(cyl(r, r, w + .55, 10, bevel=.03, bseg=1), 'log', M((0, y, z), rot=(0, math.pi / 2, 0)))
            for x in (-(w + .55) / 2, (w + .55) / 2): b.add(cyl(r * .82, r * .82, .03, 10), 'log_end', M((x, y, z), rot=(0, math.pi / 2, 0)))
        for x in (-w / 2, w / 2):
            b.add(cyl(r, r, d + .55, 10, bevel=.03, bseg=1), 'log', M((x, 0, z + sp / 2), rot=(math.pi / 2, 0, 0)))
            for y in (-(d + .55) / 2, (d + .55) / 2): b.add(cyl(r * .82, r * .82, .03, 10), 'log_end', M((x, y, z + sp / 2), rot=(math.pi / 2, 0, 0)))
    zw = base + n * sp + r; hg = (w / 2) * math.tan(a); zr = zw + hg
    for y in (-d / 2, d / 2):  # vertical plank gables
        for i in range(int(w / .32)):
            x = -w / 2 + (i + .5) * w / int(w / .32); h = hg * (1 - abs(x) / (w / 2)) + .05
            if h > .1: b.add(rbox(w / int(w / .32) - .02, .1, h, .015), 'wood', M((x, y, zw + h / 2 - .02)))
        gz = zw + hg * .45  # round gable window
        b.add(torus(.42, .07, 20, 8), 'wood_dark', M((0, y - math.copysign(.1, -y) * 0 - (.08 if y < 0 else -.08), gz), rot=(math.pi / 2, 0, 0)))
        b.add(cyl(.42, .42, .04, 20), 'window', M((0, y - (.05 if y < 0 else -.05), gz), rot=(math.pi / 2, 0, 0)))
    # roof boards (ridge along Y; front overhang shelters the porch)
    over = .7; L = (w / 2 + over) / math.cos(a); d_len = d + front_over + .6; y0 = -(front_over - .6) / 2
    for s in (-1, 1):
        cx = s * (L / 2) * math.cos(a); cz = zr + .1 - (L / 2) * math.sin(a)
        b.add(rbox(L, d_len, .2, .05), 'roof', M((cx, y0, cz), rot=(0, s * a, 0)))
    b.add(rbox(.3, d_len + .05, .3, .1), 'roof', M((0, y0, zr + .22)))
    f, lo, hi = roof_snow_sdf(w, d_len + .1, y0, zw, a, over, seed=seed)
    b.add(sdf_bm(f, lo, hi, .055, int(max(700, 24 * w * d_len)), key=f'roofsnow_{name}'), 'snow')  # face budget scales with roof area
    # chimney
    cx, cy = w * .22, d * .2; ch = zr + 1.0
    b.add(rbox(.95, .95, ch - base, .05), 'stone', M((cx, cy, base + (ch - base) / 2)))
    b.add(rbox(1.15, 1.15, .18, .05), 'rock_dark', M((cx, cy, ch + .05)))
    b.add(ico(.55, 2), 'snow', M((cx, cy, ch + .17), scale=(1.05, 1.05, .35)))
    # windows (front, back, sides): frame, glowing glass, cross mullion, snow on the sill
    def window(x, y, z, face, ww=1.0, wh=1.1):
        rot = {'front': 0, 'back': math.pi, 'left': -math.pi / 2, 'right': math.pi / 2}[face]
        T = M((x, y, z), rot=(0, 0, rot))
        b.add(rbox(ww + .2, .14, wh + .2, .04), 'wood_dark', T @ M((0, -.02, 0)))
        b.add(rbox(ww, .06, wh, .01), 'window', T @ M((0, -.07, 0)))
        b.add(rbox(.06, .1, wh, .01), 'wood_dark', T @ M((0, -.1, 0))); b.add(rbox(ww, .1, .06, .01), 'wood_dark', T @ M((0, -.1, 0)))
        b.add(rbox(ww + .35, .3, .08, .03), 'wood_dark', T @ M((0, -.12, -wh / 2 - .12)))
        b.add(rbox(ww + .25, .26, .07, .035), 'snow', T @ M((0, -.13, -wh / 2 - .05)))
    zwin = base + wall_h * .55; fy = -d / 2 - r
    xs = [(-w / 2 + .9 + i * (w / 2 - 1.8) / max(1, wins - 1)) for i in range(wins)] if wins > 1 else [-w / 4]
    for x in xs: window(x, fy, zwin, 'front'); window(-x, fy, zwin, 'front')
    window(0, d / 2 + r, zwin, 'back')
    for x in (-w / 2 - r, w / 2 + r): window(x, 0, zwin, 'left' if x < 0 else 'right')
    # door
    b.add(rbox(1.35, .16, 2.35, .04), 'wood_dark', M((0, fy - .02, base + 1.15)))
    for i in range(4): b.add(rbox(.27, .08, 2.05, .02), 'wood', M((-.42 + i * .28, fy - .1, base + 1.05)))
    b.add(ico(.05, 1), 'metal', M((.38, fy - .17, base + 1.05)))
    b.add(rbox(.4, .06, .3, .02), 'window', M((0, fy - .15, base + 1.65)))
    if porch:
        pd = porch; py0 = -d / 2 - r - pd / 2; dz = base
        for i in range(int((w + .4) / .3)):
            b.add(rbox((w + .4) / int((w + .4) / .3) - .03, pd, .1, .02), 'wood', M((-(w + .4) / 2 + (i + .5) * (w + .4) / int((w + .4) / .3), py0, dz - .05)))
        b.add(rbox(w + .5, pd, .1, .02), 'snow_blue', M((0, py0, dz - .12)))
        px = w / 2 - .25; pyf = -d / 2 - r - pd + .15; post_top = zw + .25 * math.tan(a)
        for x in (-px, px):
            b.add(rbox(.22, .22, post_top - dz, .04), 'log', M((x, pyf, dz + (post_top - dz) / 2)))
        sw = 1.7  # stair opening
        for x0, x1 in ((-px, -sw / 2), (sw / 2, px)):
            cxr = (x0 + x1) / 2; ln = abs(x1 - x0)
            b.add(rbox(ln, .1, .1, .03), 'wood_dark', M((cxr, pyf, dz + .95)))
            b.add(rbox(ln, .13, .06, .03), 'snow', M((cxr, pyf, dz + 1.03)))
            for k in range(int(ln / .28) + 1): b.add(rbox(.06, .06, .9, .015), 'wood_dark', M((x0 + (x1 - x0) * k / max(1, int(ln / .28)), pyf, dz + .45)))
        for side, x in ((-1, -px), (1, px)):  # side rails
            b.add(rbox(.1, pd - .2, .1, .03), 'wood_dark', M((x, py0 + .05, dz + .95)))
        for k in range(3):  # steps
            b.add(rbox(sw, .36, dz / 3 * (3 - k), .03), 'wood', M((0, pyf - .3 - k * .36, dz / 3 * (3 - k) / 2)))
            b.add(rbox(sw - .1, .3, .04, .02), 'snow', M((0, pyf - .3 - k * .36, dz / 3 * (3 - k) + .01)))
        for x in (-1.0, 1.0):  # lanterns beside the door
            b.add(rbox(.2, .2, .3, .03), 'lamp', M((x, fy - .15, base + 1.75)))
            b.add(rbox(.26, .26, .05, .02), 'metal_dark', M((x, fy - .15, base + 1.93)))
        if lights:  # string lights: along the porch front and up both gable eaves
            runs = [catenary((-px, pyf, post_top - .15), (px, pyf, post_top - .15), .3, 14)]
            ey = -d / 2 - front_over + .1
            for s in (-1, 1):
                runs.append([Vector((s * (w / 2 + over - .2) * (1 - t), ey, zw - .15 + (hg + .1) * (1 - abs(1 - t) * 0) * t)) for t in [i / 10 for i in range(11)]])
            for pts in runs:
                b.add(tube(pts, .012, 4, caps=False), 'black')
                for i, p in enumerate(pts[1:-1]):
                    b.add(ico(.055, 1), 'bulb', M(tuple(p - Vector((0, 0, .06)))))
    depth = d + .6 + (porch + .3 if porch else 0)
    return finish(b, name, {'shape': 'box', 'size': [round(w + 1.6, 2), round(depth, 2), round(zr + .6, 2)], 'offset': [0, round(-(porch / 2 if porch else 0), 2), 0]}, sharp=45)

def bench(name='bench'):
    b = Builder()
    for i in range(3): b.add(rbox(1.8, .14, .06, .02), 'wood', M((0, -.16 + i * .16, .48)))
    for i in range(2): b.add(rbox(1.8, .07, .12, .02), 'wood', M((0, .22, .7 + i * .2), rot=(-.15, 0, 0)))
    for x in (-.75, .75):
        for y in (-.18, .2): b.add(rbox(.08, .08, .46, .02), 'wood_dark', M((x, y, .23)))
        b.add(rbox(.08, .08, .55, .02), 'wood_dark', M((x, .25, .75), rot=(-.15, 0, 0)))
    b.add(rbox(1.7, .38, .06, .03), 'snow', M((0, 0, .53)))
    return finish(b, name, {'shape': 'box', 'size': [1.9, .6, .9]})

def snowboard_rack(name='snowboard_rack'):
    b = Builder()
    b.add(rbox(1.8, .25, .1, .03), 'wood_dark', M((0, .25, .9))); b.add(rbox(1.8, .3, .08, .03), 'snow', M((0, .25, .99)))
    for x in (-.85, .85): b.add(rbox(.1, .1, 1.0, .02), 'wood_dark', M((x, .25, .5)))
    for i, c in enumerate(('purple', 'blue', 'pink')):
        x = -.5 + i * .5; T = M((x, .05, .72), rot=(-.18, 0, (i - 1) * .06))
        b.add(rbox(.32, .05, 1.45, .14, 4), c, T)
        for k in range(6):  # white snowflake on each board
            b.add(rbox(.025, .012, .2, .005), 'white', T @ M((0, -.03, .2), rot=(0, k * math.pi / 3, 0)))
    return finish(b, name, {'shape': 'box', 'size': [1.9, .6, 1.5]})

def lantern_post(name='lantern_post'):
    b = Builder()
    b.add(rbox(.14, .14, 1.5, .03), 'wood_dark', M((0, 0, .75)))
    b.add(rbox(.3, .3, .38, .04), 'lamp', M((0, 0, 1.68))); b.add(rbox(.36, .36, .06, .02), 'metal_dark', M((0, 0, 1.9)))
    b.add(cyl(.22, .05, .18, 4), 'metal_dark', M((0, 0, 2.0), rot=(0, 0, math.pi / 4))); b.add(ico(.12, 1), 'snow', M((0, 0, 2.06), scale=(1, 1, .5)))
    return finish(b, name, {'shape': 'cylinder', 'body': .15, 'ball': .2, 'top': 2.1})

def banner(name, color='blue', h=3.4):
    """Tall vertical banner with a snowflake (reference: blue 눈꽃 배너)."""
    b = Builder()
    b.add(cyl(.05, .05, h, 8), 'metal', M((0, 0, h / 2))); b.add(ico(.08, 1), 'yellow', M((0, 0, h + .05)))
    b.add(cyl(.03, .03, 1.1, 6), 'metal', M((.55, 0, h - .15), rot=(0, math.pi / 2, 0)))
    V, F, nx, nz = [], [], 8, 12
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz; V.append((.08 + u * .95, -.08 * math.sin(u * 3.1 + v * 1.5) * u, h - .2 - v * 1.7 + (.15 * u * u if j == nz else 0)))
    for j in range(nz):
        for i in range(nx): F.append((j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i))
    cloth = from_arrays(V, F); bmesh.ops.solidify(cloth, geom=cloth.faces[:], thickness=.025); b.add(cloth, color)
    for k in range(3):  # snowflake
        b.add(rbox(.06, .02, .62, .005), 'white', M((.55, -.11, h - 1.0), rot=(0, k * math.pi / 3, 0)))
    b.add(ico(.3, 2), 'snow', M((0, 0, 0), scale=(1, 1, .4)))
    return finish(b, name, {'shape': 'cylinder', 'body': .12, 'ball': .15, 'top': h})

def flag_red(name='flag_red'):
    """Small marker flag with a white mountain emblem (reference: 거점/깃발)."""
    b = Builder()
    b.add(cyl(.04, .04, 2.2, 8), 'metal_dark', M((0, 0, 1.1))); b.add(ico(.07, 1), 'yellow', M((0, 0, 2.24)))
    V, F, nx, nz = [], [], 8, 4
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz; V.append((.05 + u * .85, -.07 * math.sin(u * 3.5), 2.15 - v * .6))
    for j in range(nz):
        for i in range(nx): F.append((j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i))
    cloth = from_arrays(V, F); bmesh.ops.solidify(cloth, geom=cloth.faces[:], thickness=.02); b.add(cloth, 'red')
    b.add(from_arrays([(.2, -.09, 1.62), (.76, -.09, 1.62), (.48, -.09, 2.02), (.2, -.05, 1.62), (.76, -.05, 1.62), (.48, -.05, 2.02)], [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)]), 'white')  # mountain emblem
    b.add(from_arrays([(.39, -.1, 1.88), (.57, -.1, 1.88), (.48, -.1, 2.02)], [(0, 1, 2)]), 'snow_blue')
    b.add(ico(.25, 2), 'snow', M((0, 0, 0), scale=(1, 1, .45)))
    return finish(b, name, {'shape': 'cylinder', 'body': .1, 'ball': .12, 'top': 2.3})

def signpost(name='signpost'):
    b = Builder()
    b.add(rbox(.14, .14, 2.2, .03), 'wood_dark', M((0, 0, 1.1)))
    for z, s, c in ((1.85, 1, 'blue'), (1.45, -1, 'red')):
        b.add(rbox(1.1, .08, .3, .05), 'wood', M((s * .45, 0, z)))
        b.add(cyl(.12, .12, .1, 3), 'wood', M((s * 1.02, 0, z), rot=(math.pi / 2, 0, s * math.pi / 2), scale=(1.3, 1, 1)))
        b.add(rbox(.5, .02, .1, .02), c, M((s * .4, -.05, z)))
        b.add(rbox(1.05, .1, .05, .02), 'snow', M((s * .45, 0, z + .17)))
    b.add(ico(.1, 1), 'snow', M((0, 0, 2.22), scale=(1, 1, .5)))
    return finish(b, name, {'shape': 'cylinder', 'body': .15, 'ball': .2, 'top': 2.2})

def jump_ramp(name='jump_ramp'):
    """Snow kicker built from blocks (reference: 점프대): rounded wedge with course seams, lip at the front (-Y)."""
    Lr, W, H = 4.0, 3.0, 1.4
    def f(x, y, z):
        d = sd_box(x, y, z - H / 2, W / 2, Lr / 2, H / 2, .12)
        slope = (z - H * (y + Lr / 2) / Lr * -1 - H) if False else (z - H * (Lr / 2 - y) / Lr)  # high at -Y
        d = smax(d, slope * .93, .12)
        seam = .02 * np.clip(1 - np.abs(np.sin(np.pi * z / .35)) * 6, 0, 1)
        return d + seam + .015 * vnoise(x, y, z, 3, 4)
    b = Builder().add(sdf_bm(f, (-W / 2 - .2, -Lr / 2 - .2, -.2), (W / 2 + .2, Lr / 2 + .2, H + .2), .04, 900, key=name), 'snow')
    b.add(rbox(W - .1, .14, .06, .02), 'blue', M((0, -Lr / 2 + .14, H - .02)))
    return finish(b, name, {'shape': 'box', 'size': [W, Lr, H]}, sharp=60)

def ice_block(name='ice_block', s=1.2):
    b = Builder().add(rbox(s, s, s, .12, 3), 'ice', M((0, 0, s / 2)))
    b.add(rbox(s * .55, s * .55, s * .55, .1, 2), 'ice_dark', M((0, 0, s / 2)))  # deeper colour inside (reads as depth)
    b.add(rbox(s * .9, s * .9, .1, .05), 'snow', M((0, 0, s + .02)))
    return finish(b, name, {'shape': 'box', 'size': [s, s, s]}, sharp=55)

def ice_pillar(name='ice_pillar', h=3.2):
    b = Builder()
    b.add(cyl(.55, .35, h, 6, bevel=.06), 'ice_solid', M((0, 0, h / 2)))
    b.add(cyl(.4, .1, .9, 6), 'icicle', M((.05, 0, h + .4)))
    for k in range(5):  # icicles around the top
        a = k * 1.256; b.add(cyl(.08, .005, .55, 5), 'icicle', M((math.cos(a) * .42, math.sin(a) * .42, h - .45), rot=(math.pi, 0, 0)))
    b.add(ico(.65, 2), 'snow', M((0, 0, 0), scale=(1, 1, .3)))
    return finish(b, name, {'shape': 'cylinder', 'body': .55, 'ball': .6, 'top': h})

def ice_arch(name='ice_arch'):
    """Igloo-style tunnel arch of ice bricks (reference: 아이스 레이크 아치)."""
    R, r_in, Wd = 2.2, 1.35, 2.4
    def f(x, y, z):
        ring = np.maximum(np.sqrt(x * x + z * z) - R, r_in - np.sqrt(x * x + z * z))
        d = smax(np.maximum(ring, np.abs(y) - Wd / 2), -z, .05)
        ang = np.arctan2(z, x); seam = .025 * np.clip(1 - np.abs(np.sin(ang * 7)) * 5, 0, 1) + .02 * np.clip(1 - np.abs(np.sin(y * np.pi / .6)) * 5, 0, 1)
        return d + seam
    b = Builder().add(sdf_bm(f, (-R - .2, -Wd / 2 - .2, -.1), (R + .2, Wd / 2 + .2, R + .2), .04, 1400, key=name), 'ice_solid')
    sf = lambda x, y, z: np.maximum(np.maximum(np.abs(np.sqrt(x * x + z * z) - R - .05) - .07, np.abs(y) - Wd / 2 - .05), 1.55 - z + .2 * vnoise(x, y, z, 2, 9))
    b.add(sdf_bm(sf, (-R - .3, -Wd / 2 - .3, 1), (R + .3, Wd / 2 + .3, R + .3), .035, 500, key=name + 's'), 'snow')
    return finish(b, name, {'shape': 'cylinders', 'parts': [[-1.78, 0, .5], [1.78, 0, .5]], 'top': R}, sharp=60)  # tunnel: only the two legs block

def frozen_waterfall(name='frozen_waterfall', h=7.):
    rnd = random.Random(11); b = Builder()
    for k in range(9):
        x = (k - 4) * .45 + (rnd.random() - .5) * .2; hh = h * (.55 + .45 * rnd.random()); r0 = .35 + .2 * rnd.random()
        pts = [Vector((x + .08 * math.sin(i), -.1 * i / 6, h - hh * i / 6)) for i in range(7)]
        b.add(tube(pts, lambda t, r0=r0: r0 * (1 - .75 * t) + .05, 7), 'icicle' if k % 2 else 'ice_solid')
    b.add(rbox(4.6, 1.2, .9, .3), 'ice_solid', M((0, -.3, .45)))
    b.add(rbox(4.4, 1.0, .25, .12), 'snow', M((0, -.3, .95)))
    return finish(b, name, {'shape': 'box', 'size': [4.6, 1.4, h]})

def tree_stump(name='tree_stump'):
    b = Builder()
    b.add(cyl(.62, .55, .7, 14, bevel=.04), 'bark', M((0, 0, .35)))
    b.add(cyl(.56, .56, .03, 14), 'log_end', M((0, 0, .71)))
    b.add(ico(.5, 2), 'snow', M((0, 0, .72), scale=(1, 1, .28)))
    for k in range(4): a = k * 1.57 + .4; b.add(cyl(.18, .1, .5, 6), 'bark', M((math.cos(a) * .6, math.sin(a) * .6, .12), rot=(math.sin(a) * 1.2, -math.cos(a) * 1.2, 0)))
    return finish(b, name, {'shape': 'cylinder', 'body': .65, 'ball': .7, 'top': .8})

# ══════════════════════ ski lift ══════════════════════
def lift_tower(name='ski_lift_tower', h=9.):
    b = Builder()
    b.add(rbox(1.2, 1.2, .5, .08), 'stone', M((0, 0, .25)))
    b.add(cyl(.32, .2, h, 12), 'metal', M((0, 0, h / 2 + .4)))
    b.add(rbox(3.2, .3, .35, .06), 'metal_dark', M((0, 0, h + .3)))
    for x in (-1.3, 1.3):
        for y in (-.35, .35): b.add(cyl(.22, .22, .08, 14), 'black', M((x, y, h + .1), rot=(0, math.pi / 2, 0)))
        b.add(rbox(.12, 1.0, .1, .02), 'metal_dark', M((x, 0, h + .1)))
    for i in range(10): b.add(rbox(.4, .04, .04, .01), 'metal_dark', M((0, -.24, 1.5 + i * .7)))  # ladder rungs
    b.add(ico(.4, 2), 'snow', M((0, 0, h + .45), scale=(4, .5, .35)))
    return finish(b, name, {'shape': 'cylinder', 'body': .45, 'ball': .5, 'top': h + .5})

def lift_chair(name='ski_lift_chair'):
    """Origin = cable grip; hangs along -Z."""
    b = Builder()
    b.add(rbox(.2, .3, .15, .04), 'metal_dark', M((0, 0, -.05)))
    b.add(tube([(0, 0, -.1), (0, 0, -1.4), (0, .25, -1.75)], .045, 6), 'metal')
    b.add(rbox(1.5, .55, .1, .05), 'red', M((0, -.1, -1.8))); b.add(rbox(1.5, .1, .6, .05), 'red', M((0, .2, -1.5), rot=(-.15, 0, 0)))
    for x in (-.78, .78): b.add(tube([(x, .2, -1.25), (x, -.3, -1.25), (x, -.35, -1.75)], .025, 5), 'metal')
    b.add(tube([(-.78, -.45, -1.25), (.78, -.45, -1.25)], .025, 5), 'metal')
    b.add(rbox(1.3, .5, .05, .025), 'snow', M((0, -.1, -1.73)))
    return finish(b, name, {}, decor=True)

def lift_station(name='ski_lift_station'):
    b = Builder()
    b.add(rbox(5, 4, .4, .06), 'stone', M((0, 0, .2)))
    b.add(rbox(3.4, 2.6, 2.6, .08), 'wood', M((-.6, .4, 1.7)))
    for i in range(3): b.add(rbox(.9, .1, .8, .03), 'window', M((-1.6 + i * 1.0, -.92, 2.0)))
    for s in (-1, 1):  # pitched roof with snow
        b.add(rbox(2.5, 3.6, .2, .05), 'roof', M((-.6 + s * 1.05, .4, 3.4), rot=(0, s * .5, 0)))
        b.add(rbox(2.5, 3.7, .26, .12), 'snow', M((-.6 + s * 1.08, .4, 3.6), rot=(0, s * .5, 0)))
    b.add(cyl(.3, .3, 3.2, 10), 'metal', M((1.6, 0, 2.0)))
    b.add(torus(1.3, .12, 28, 8), 'metal_dark', M((1.6, 0, 3.7)))
    b.add(cyl(.2, .2, .3, 10), 'black', M((1.6, 0, 3.7)))
    return finish(b, name, {'shape': 'box', 'size': [5, 4, 4]})

# ══════════════════════ slope / night / forest extras ══════════════════════
def gate_flag(name, color):
    """Slalom gate: two poles with a rectangular panel (reference: 빨강·파랑 게이트)."""
    b = Builder()
    for x in (-.7, .7): b.add(cyl(.035, .035, 1.8, 8), 'white', M((x, 0, .9))); b.add(ico(.2, 1), 'snow', M((x, 0, 0), scale=(1, 1, .4)))
    V, F = [], []
    for j in range(3):
        for i in range(7): u = i / 6; V.append((-.68 + 1.36 * u, -.05 * math.sin(u * math.pi), 1.7 - j * .3))
    for j in range(2):
        for i in range(6): F.append((j * 7 + i, j * 7 + i + 1, (j + 1) * 7 + i + 1, (j + 1) * 7 + i))
    panel = from_arrays(V, F); bmesh.ops.solidify(panel, geom=panel.faces[:], thickness=.02); b.add(panel, color)
    b.add(cyl(.18, 0, .22, 3), 'white', M((0, -.07, 1.4), rot=(math.pi / 2, 0, 0), scale=(1, .3, 1)))
    return finish(b, name, {'shape': 'box', 'size': [1.6, .2, 1.8]})

def arch_gate(name='arch_gate'):
    b = Builder()
    b.add(torus(3.0, .28, 32, 10, arc=math.pi), 'red', M((0, 0, 0), rot=(math.pi / 2, 0, 0)))
    b.add(rbox(3.2, .12, .8, .1), 'white', M((0, -.3, 2.6)))
    b.add(rbox(2.6, .14, .5, .06), 'red_dark', M((0, -.35, 2.6)))
    for x in (-3, 3): b.add(rbox(.8, .8, .3, .1), 'red_dark', M((x, 0, .15)))
    return finish(b, name, {'shape': 'cylinders', 'parts': [[-3, 0, .45], [3, 0, .45]], 'top': 3.3})

def safety_net(name='safety_net', length=5.):
    b = Builder()
    for x in (-length / 2, 0, length / 2): b.add(cyl(.05, .05, 1.6, 8), 'metal', M((x, 0, .8)))
    for i in range(int(length / .25) + 1):
        x = -length / 2 + i * .25; b.add(rbox(.025, .025, 1.25, .005), 'net', M((x, 0, .85), rot=(0, .5, 0)))
        b.add(rbox(.025, .025, 1.25, .005), 'net', M((x, 0, .85), rot=(0, -.5, 0)))
    for z in (.25, 1.45): b.add(rbox(length, .04, .05, .01), 'net', M((0, 0, z)))
    return finish(b, name, {'shape': 'box', 'size': [length, .2, 1.6]})

def lamp_post(name='lamp_post'):
    b = Builder()
    b.add(cyl(.22, .16, .4, 10), 'metal_dark', M((0, 0, .2))); b.add(cyl(.07, .06, 3.8, 10), 'metal_dark', M((0, 0, 2.2)))
    b.add(tube([(0, 0, 4.0), (.2, 0, 4.25), (.55, 0, 4.2)], .045, 6), 'metal_dark')
    b.add(cyl(.28, .1, .25, 10), 'metal_dark', M((.55, 0, 4.15))); b.add(ico(.14, 2), 'lamp', M((.55, 0, 3.97)))
    b.add(ico(.2, 1), 'snow', M((.55, 0, 4.3), scale=(1.3, 1.3, .4)))
    return finish(b, name, {'shape': 'cylinder', 'body': .2, 'ball': .25, 'top': 4.3})

def floodlight(name='floodlight_tower', h=10.):
    """Stadium light (reference: 나이트 리조트 조명탑)."""
    b = Builder()
    b.add(rbox(1.2, 1.2, .5, .08), 'stone', M((0, 0, .25)))
    b.add(cyl(.28, .18, h, 10), 'metal_dark', M((0, 0, h / 2 + .4)))
    b.add(rbox(2.3, .5, 1.5, .08), 'metal_dark', M((0, -.2, h + .9), rot=(-.25, 0, 0)))
    for i in range(3):
        for j in range(2): b.add(rbox(.6, .1, .55, .05), 'lamp', M((-.72 + i * .72, -.48, h + .55 + j * .65), rot=(-.25, 0, 0)))
    b.add(rbox(2.3, .5, .2, .1), 'snow', M((0, -.05, h + 1.68), rot=(-.25, 0, 0)))
    return finish(b, name, {'shape': 'cylinder', 'body': .5, 'ball': .55, 'top': h + 1.6})

def treehouse_tree(name='treehouse_tree'):
    """Giant pine with a platform cabin and ladder (reference: 포레스트 빌리지 트리하우스)."""
    b = Builder(); rnd = random.Random(21)
    b.add(cyl(1.0, .55, 14, 14), 'bark', M((0, 0, 7))); b.add(cyl(1.6, 1.0, .8, 14), 'bark', M((0, 0, .4)))
    for i in range(4):
        t = i / 3; R = 4.2 * (1 - t) ** .85 + 1.2 * t; zt = 9 + i * 2.2; zb = zt - 3.2 * (1 - .3 * t)
        ph = rnd.random() * 6; skirt(b, zt + (2 if i == 3 else 0), zb, R, 18, 3, 11, .12, .5, ph, rnd, 'pine_dark', p=.9)
        skirt(b, zt + (2 if i == 3 else 0), zb, R, 18, 3, 13, .15, .2, ph + .3, rnd, 'snow', u_end=.5, lift=.06, grow=1.04, jit=.12)
    z = 4.2  # platform
    b.add(cyl(3.0, 3.0, .25, 18, bevel=.05), 'wood', M((0, 0, z)))
    b.add(cyl(3.0, 3.0, .08, 18), 'snow', M((0, 0, z + .16)))
    for k in range(4):
        a = k * 1.57 + .78; b.add(tube([(math.cos(a) * 1.0, math.sin(a) * 1.0, z - 2.2), (math.cos(a) * 2.6, math.sin(a) * 2.6, z - .1)], .12, 6), 'wood_dark')
    for k in range(18):
        a = k * 2 * math.pi / 18
        if abs(math.sin(a / 2 - .4)) < .1: continue
        b.add(rbox(.07, .07, .9, .02), 'wood_dark', M((math.cos(a) * 2.9, math.sin(a) * 2.9, z + .55)))
    b.add(torus(2.9, .06, 36, 6), 'wood_dark', M((0, 0, z + 1.0)))
    hx, hy = 1.6, -1.2  # mini cabin on the platform
    b.add(rbox(2.2, 1.8, 1.8, .05), 'wood', M((hx, hy, z + 1.05)))
    b.add(rbox(.7, .06, .6, .02), 'window', M((hx, hy - .92, z + 1.3)))
    for s in (-1, 1): b.add(rbox(1.5, 2.2, .14, .05), 'roof', M((hx + s * .58, hy, z + 2.25), rot=(0, s * .7, 0))); b.add(rbox(1.5, 2.2, .14, .07), 'snow', M((hx + s * .62, hy, z + 2.35), rot=(0, s * .7, 0)))
    for i in range(int(z / .35)): b.add(rbox(.6, .06, .06, .015), 'wood', M((0, -1.15, .3 + i * .35)))  # ladder
    for x in (-.32, .32): b.add(rbox(.07, .07, z + .9, .02), 'wood_dark', M((x, -1.15, (z + .9) / 2)))
    lights = catenary((-2.9, -.1, z + 1.0), (2.9, -.1, z + 1.0), .0, 16)
    for p in [Vector((math.cos(a) * 3.0, math.sin(a) * 3.0, z + 1.15 - .1 * math.sin(a * 6) ** 2)) for a in [k * 2 * math.pi / 22 for k in range(22)]]:
        b.add(ico(.06, 1), 'bulb', M(tuple(p)))
    return finish(b, name, {'shape': 'cylinder', 'body': 1.3, 'ball': 1.5, 'top': 22, 'platform_z': z}, sharp=45)

def aurora(name='aurora', length=120., h=18.):
    V, F, C, nx, nz = [], [], [], 48, 6
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz; x = (u - .5) * length
            V.append((x, 6 * math.sin(u * 7.0) + 3 * math.sin(u * 17), v * h + 2 * math.sin(u * 5)))
            g = math.sin(math.pi * v) ** 1.3 * math.sin(math.pi * u) ** .7 * (.6 + .4 * math.sin(u * 23) ** 2)  # fades out on every edge
            C.append((g * (.15 + .5 * v * v), g * (.95 - .5 * v), g * (.55 + .3 * v)))
    for j in range(nz):
        for i in range(nx): F.append((j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i))
    b = Builder().add_arrays(V, F, 'aurora', colors=C)
    return finish(b, name, {}, decor=True)

# ══════════════════════ library ══════════════════════
def build_props(only=None):
    global PROTO
    PROTO = collection('PROTOTYPES')
    jobs = {
        **{k: (lambda k=k: pine(k, **TREES[k], seed=hash(k) % 97)) for k in TREES},
        'pine_tree_far': lambda: pine('pine_tree_far', **{**TREES['pine_tree_01'], 'H': 7.5}, S=9, K=2, seed=5),
        'snow_wall_low': lambda: snow_wall('snow_wall_low', 2, 4, .5),
        'snow_wall_high': lambda: snow_wall('snow_wall_high', 4, 4, .55, seed=9),
        'snow_pile': snow_pile, 'snowman': snowman,
        'rock_01': lambda: rock('rock_01', 3), 'rock_02': lambda: rock('rock_02', 8, (2.6, 1.8, 1.6)),
        'fence_wood': lambda: fence('fence_wood', 'wood'), 'fence_red': lambda: fence('fence_red', 'red'),
        'wooden_cabin': lambda: cabin('wooden_cabin'),
        'small_cabin': lambda: cabin('small_cabin', w=5.2, d=4.4, wall_h=2.6, pitch=42, porch=1.4, lights=False, front_over=1.0, wins=1, seed=3),
        'night_lodge': lambda: cabin('night_lodge', w=8.0, d=6.0, wall_h=3.0, pitch=40, porch=1.8, lights=True, front_over=1.3, wins=2, seed=13),
        'bench': bench, 'snowboard_rack': snowboard_rack, 'lantern_post': lantern_post, 'signpost': signpost,
        'banner_blue': lambda: banner('banner_blue', 'blue'), 'flag_red': flag_red,
        'jump_ramp': jump_ramp, 'ice_block': ice_block, 'ice_pillar': ice_pillar, 'ice_arch': ice_arch,
        'frozen_waterfall': frozen_waterfall, 'tree_stump': tree_stump,
        'ski_lift_tower': lift_tower, 'ski_lift_chair': lift_chair, 'ski_lift_station': lift_station,
        'gate_red': lambda: gate_flag('gate_red', 'red'), 'gate_blue': lambda: gate_flag('gate_blue', 'blue'),
        'arch_gate': arch_gate, 'safety_net': safety_net, 'lamp_post': lamp_post, 'floodlight_tower': floodlight,
        'treehouse_tree': treehouse_tree, 'aurora': aurora,
    }
    out = {}
    for k, fn in jobs.items():
        if only and k not in only: continue
        ob = fn(); out[k] = ob
        log(f'prop {k:18s} {tri_count(ob):6d} tris  mats {len(ob.data.materials)}')
    return out

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from export_glb import export_objects
    from render_preview import props_sheet
    reset_scene()
    props = build_props()
    sizes = {}
    for k, ob in props.items():
        p = os.path.join(ROOT, 'glb', 'props', f'{k}.glb'); export_objects([ob], p); sizes[k] = os.path.getsize(p)
    props_sheet(props)
    json.dump({k: {'triangles': tri_count(o), 'bytes': sizes[k], 'collider': dict(o['collider']), 'decor': bool(o['decor'])} for k, o in props.items()},
              open(os.path.join(ROOT, 'metadata', 'props.json'), 'w'), indent=1, default=lambda v: v.to_dict() if hasattr(v, 'to_dict') else list(v))
    log('props done', len(props))
