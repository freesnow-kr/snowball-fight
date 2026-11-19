"""SLOPE SNOWFIGHT — Blue Penguin hero model (Blender, headless).

Run:  blender --background --python blender/build_penguin.py
Outputs: ../assets/penguin_blue.glb (game), penguin_blue.blend,
renders/*.png, report.json

Pipeline: analytic SDF shapes (numpy) -> surface nets -> Quadriflow quad retopology (symmetric)
-> exact iso-line cuts for colour regions -> hidden-face removal -> armature + procedural skin
weights -> 9 (+5 new: blender/add_actions.py) actions as NLA tracks -> penetration test -> EEVEE renders -> glTF (+Y up, +Z front).
Shape coordinates below are glTF/three space (x, y-up, z-front); B() converts to Blender (x, -z, y).
"""
import bpy, bmesh, math, json, os, sys, time
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
RENDERS = os.path.join(HERE, 'renders')
GAME_GLB = os.path.join(os.path.dirname(HERE), 'assets', 'penguin_blue.glb')  # the file the game loads
os.makedirs(os.path.dirname(GAME_GLB), exist_ok=True)
os.makedirs(RENDERS, exist_ok=True)
T0 = time.time()
def log(*a): print(f'[{time.time() - T0:6.1f}s]', *a, flush=True)

# ══════════════════════ SDF primitives (vectorised) ══════════════════════
L = lambda *a: np.sqrt(sum(v * v for v in a))
def sd_ell(x, y, z, rx, ry, rz):
    k0 = L(x / rx, y / ry, z / rz); k1 = np.maximum(L(x / rx**2, y / ry**2, z / rz**2), 1e-12)
    return np.where(k0 < 1e-9, -min(rx, ry, rz), k0 * (k0 - 1) / k1)
def smin(a, b, k): h = np.maximum(k - np.abs(a - b), 0) / k; return np.minimum(a, b) - h * h * k * .25
def smax(a, b, k): return -smin(-a, -b, k)
def sstep(a, b, x): t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def sd_torus_y(x, y, z, R, r): return L(L(x, z) - R, y) - r
def sd_round_cone(px, py, pz, a, b, r1, r2):  # iq
    bx, by, bz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    l2 = bx * bx + by * by + bz * bz; rr = r1 - r2; a2 = l2 - rr * rr; il2 = 1 / l2
    ax, ay, az = px - a[0], py - a[1], pz - a[2]
    y = ax * bx + ay * by + az * bz; z = y - l2
    x2 = (ax * l2 - bx * y)**2 + (ay * l2 - by * y)**2 + (az * l2 - bz * y)**2
    y2 = y * y * l2; z2 = z * z * l2; k = np.sign(rr) * rr * rr * x2
    return np.where(np.sign(z) * a2 * z2 > k, np.sqrt(x2 + z2) * il2 - r2,
           np.where(np.sign(y) * a2 * y2 < k, np.sqrt(x2 + y2) * il2 - r1,
                    (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1))
def sd_rect2(x, y, hw, hh, r):
    qx, qy = abs(x) - hw + r, abs(y) - hh + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
def scalar(f): return lambda x, y, z: float(f(np.array([x]), np.array([y]), np.array([z]))[0])
def grad(f, x, y, z, e=2e-4):
    g = np.stack([f(x + e, y, z) - f(x - e, y, z), f(x, y + e, z) - f(x, y - e, z), f(x, y, z + e) - f(x, y, z - e)], -1)
    return g / np.maximum(np.linalg.norm(g, axis=-1, keepdims=True), 1e-12)

# ══════════════════════ character shape (meters, feet Y=0, front +Z, L=+X) ══════════════════════
HEAD = (0, .98, 0, .46, .40, .42); BODY = (0, .34, 0, .35, .32, .31); HY = .98
def ell(x, y, z, e): return sd_ell(x - e[0], y - e[1], z - e[2], *e[3:])
def core(x, y, z): return smin(ell(x, y, z, HEAD), ell(x, y, z, BODY), .14)

TILT = math.atan(.25); cT, sT = math.cos(TILT), math.sin(TILT); EDGE = -.03
def to_hat(x, y, z): return x, (y - HY) * cT - z * sT, (y - HY) * sT + z * cT
def from_hat(x, yh, zh): return (x, HY + yh * cT + zh * sT, -yh * sT + zh * cT)
def beanie(x, y, z, detail=True):
    hx, hy, hz = to_hat(x, y, z); h = hy - EDGE
    cuff = sstep(.125, .095, h)
    d = sd_ell(hx, hy - .01, hz, .482, .44, .452) - .013 * cuff
    if detail: d = d + .004 * cuff * (1 + np.cos(18 * np.arctan2(hx, hz)))
    return smax(d, -h, .016)
def gbase(x, y, z): return beanie(x, y, z, False)
POM = from_hat(0, .48, 0); POM_R = .082
def pompom(x, y, z):
    return L(x - POM[0], y - POM[1], z - POM[2]) - POM_R - .007 * np.sin(41 * x) * np.sin(37 * y + 1) * np.sin(43 * z + 2)

SHOULDER = (.37, .49, 0.)
def wing_pts(s):
    P = (SHOULDER[0] * s, SHOULDER[1], SHOULDER[2])
    add = lambda v: (P[0] + v[0] * s, P[1] + v[1], P[2] + v[2])
    return {'P': P, 'elbow': add((.11, -.15, .035)), 'tip': add((.18, -.25, .065))}
def jacket_torso(x, y, z, detail=True):
    d = sd_ell(x, y - .36, z + .005, .42, .34, .385)
    d = smin(d, sd_ell(np.abs(x) - .28, y - .5, z, .15, .12, .15), .1)
    d = smin(d, sd_torus_y(x, y - .6, z + .01, .28, .06), .06)
    if detail: d = d + .008 * (.5 + .5 * np.cos(2 * np.pi * (y - .14) / .1))**3 * sstep(.52, .46, y) * sstep(.13, .18, y)
    d = smax(d, .1 - y, .035)
    return smax(d, y - .68, .02)
def sleeve(s, detail=True):
    w = wing_pts(s)
    def f(x, y, z):
        d = sd_round_cone(x, y, z, w['P'], w['elbow'], .105, .088)
        if detail:
            t = (y - w['P'][1]) / (w['elbow'][1] - w['P'][1])
            d = d + .006 * (1 - np.abs(np.sin(np.pi * t * 2.5)))**6 * sstep(.95, .8, t)
        return d
    return f
def jacket(x, y, z, detail=True):  # padded torso + both sleeves as ONE surface → shoulders deform with the arm
    return smin(smin(jacket_torso(x, y, z, detail), sleeve(1, detail)(x, y, z), .035), sleeve(-1, detail)(x, y, z), .035)
def flipper(s):
    w = wing_pts(s); e, t = w['elbow'], w['tip']
    tip = (e[0] + (t[0] - e[0]) / .58, t[1], t[2])
    return lambda x, y, z: sd_round_cone(e[0] + (x - e[0]) / .58, y, z, e, tip, .062, .034) * .58
def foot_c(s): return (.13 * s, .035, .1)
def foot(s):
    F = foot_c(s)
    def f(x, y, z):
        X, Y, Z = (x - F[0]) * s, y - F[1], z - F[2]
        d = sd_ell(X, Y, Z - .02, .085, .036, .105)
        for tx, tz in ((-.048, .1), (0, .118), (.048, .1)): d = smin(d, sd_ell(X - tx, Y, Z - tz, .036, .03, .042), .03)
        return smax(d, -Y - .035, .012)
    return f
def surf_z(f, x, y, z0=0., z1=.7):
    fs = scalar(f)
    for _ in range(40):
        m = (z0 + z1) / 2
        if fs(x, y, m) > 0: z1 = m
        else: z0 = m
    return np.array([x, y, (z0 + z1) / 2])
def face_white(x, y, z):
    return smin(sd_ell(x, y - .815, z - .33, .35, .26, .28),
                smin(sd_ell(x - .165, y - .965, z - .33, .195, .19, .22), sd_ell(x + .165, y - .965, z - .33, .195, .19, .22), .05), .09)
CHEEK = [surf_z(core, .265 * s, .86) for s in (1, -1)]
def cheek(x, y, z): return np.minimum(*[sd_ell(x - c[0], y - c[1], z - c[2], .072, .05, .075) for c in CHEEK])
def belly_white(x, y, z): return sd_ell(x, y - .26, z - .2, .26, .3, .2)

# ══════════════════════ meshing ══════════════════════
def surface_nets(f, lo, hi, h):
    xs, ys, zs = (np.arange(lo[i], hi[i] + h, h) for i in range(3))
    G = f(*np.meshgrid(xs, ys, zs, indexing='ij')); S = G < 0; n = G.shape
    offs = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    cs = [G[i:n[0] - 1 + i, j:n[1] - 1 + j, k:n[2] - 1 + k] for i, j, k in offs]
    acc = np.zeros(cs[0].shape + (3,)); cnt = np.zeros(cs[0].shape)
    for a in range(8):
        for b in range(a + 1, 8):
            if sum(abs(offs[a][i] - offs[b][i]) for i in range(3)) != 1: continue
            ga, gb = cs[a], cs[b]; m = (ga < 0) != (gb < 0)
            t = np.where(m, ga / np.where(m, ga - gb, 1), 0)
            pa, pb = np.array(offs[a], float), np.array(offs[b], float)
            acc += np.where(m[..., None], pa + (pb - pa) * t[..., None], 0); cnt += m
    act = cnt > 0
    idx = -np.ones(cnt.shape, int); idx[act] = np.arange(act.sum())
    I, J, K = np.nonzero(act)
    verts = np.stack([xs[I], ys[J], zs[K]], 1) + acc[act] / cnt[act][:, None] * h
    faces = []
    for a in range(3):
        u, v = [d for d in range(3) if d != a]
        s0 = [slice(None)] * 3; s1 = [slice(None)] * 3; s0[a] = slice(0, -1); s1[a] = slice(1, None)
        P = np.argwhere(S[tuple(s0)] != S[tuple(s1)])
        P = P[(P[:, u] >= 1) & (P[:, v] >= 1) & (P[:, u] <= n[u] - 2) & (P[:, v] <= n[v] - 2)]
        def cell(du, dv):
            c = P.copy(); c[:, u] += du; c[:, v] += dv; return idx[c[:, 0], c[:, 1], c[:, 2]]
        faces.append(np.stack([cell(-1, -1), cell(0, -1), cell(0, 0), cell(-1, 0)], 1))
    return verts, np.concatenate(faces)

def project(f, P, it=5):
    P = P.copy()
    for _ in range(it):
        d = f(P[:, 0], P[:, 1], P[:, 2]); g = grad(f, P[:, 0], P[:, 1], P[:, 2])
        P -= d[:, None] * g
    return P

to_b = lambda P: np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)
to_t = lambda P: np.stack([P[:, 0], P[:, 2], -P[:, 1]], 1)
B = lambda p: Vector((p[0], -p[2], p[1]))

COLL = None
def new_obj(name, me):
    ob = bpy.data.objects.new(name, me); COLL.objects.link(ob); return ob
def activate(ob):
    for o in bpy.context.view_layer.objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob

def mesh_verts_t(me):
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co); return to_t(co.reshape(-1, 3))
def set_verts_t(me, P):
    me.vertices.foreach_set('co', to_b(P).ravel()); me.update()

def sdf_object(name, f, lo, hi, h, faces):
    V, F = surface_nets(f, lo, hi, h)
    V = project(f, V)
    me = bpy.data.meshes.new(name); me.from_pydata(to_b(V).tolist(), [], F.tolist()); me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=h * .05)  # projection collapses quads on flat cuts
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    ob = new_obj(name, me); activate(ob)
    raw = len(me.polygons)
    if faces is None or (isinstance(faces, tuple) and faces[0] == 'cap'):
        cap = faces[1] if faces else raw
        if raw > cap:
            mod = ob.modifiers.new('cap', 'DECIMATE'); mod.ratio = cap / raw; bpy.ops.object.modifier_apply(modifier='cap')
        log(f'{name}: surface nets {raw} → {len(ob.data.polygons)} faces (decal)')
        return ob
    def qf(sym):
        try: bpy.ops.object.quadriflow_remesh(target_faces=faces, use_mesh_symmetry=sym, use_preserve_sharp=False)
        except Exception: pass
        return abs(len(ob.data.polygons) - faces) < faces * .6  # op reports FINISHED even when it bails out
    ok = qf(True) or qf(False)
    if not ok:  # surface nets can leave non-manifold edges → voxel remesh makes it watertight, then retry
        ob.data.remesh_voxel_size = h; bpy.ops.object.voxel_remesh()
        ok = qf(True) or qf(False)
    me = ob.data
    set_verts_t(me, project(f, mesh_verts_t(me)))  # Quadriflow resamples; snap back onto the exact surface
    log(f'{name}: surface nets {raw} quads → quadriflow {len(me.polygons)} ({"ok" if ok else "FAILED"})')
    return ob

def cut(ob, field, shape, refine=14):
    """Split edges where field changes sign, connect the new vertices inside each face → exact boundary curve."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    fv = lambda co: float(field(np.array([co.x]), np.array([co.z]), np.array([-co.y]))[0])
    vals = {v: fv(v.co) for v in bm.verts}
    new = set()
    for e in list(bm.edges):
        a, b = e.verts; fa, fb = vals[a], vals[b]
        if (fa < 0) == (fb < 0) or abs(fa - fb) < 1e-12: continue
        t0, t1 = 0., 1.; A, Bc = a.co.copy(), b.co.copy()
        for _ in range(refine):
            m = (t0 + t1) / 2
            if (fv(A.lerp(Bc, m)) < 0) == (fa < 0): t0 = m
            else: t1 = m
        t = (t0 + t1) / 2
        if t < .02 or t > .98:  # snap onto existing vertex instead of creating a sliver
            v = a if t < .5 else b; vals[v] = 0.; new.add(v); continue
        _, nv = bmesh.utils.edge_split(e, a, t)
        p = project(shape, to_t(np.array([nv.co[:]])))[0]; nv.co = B(p); vals[nv] = 0.; new.add(nv)
    for f in list(bm.faces):
        vs = [v for v in f.verts if v in new]
        if len(vs) == 2 and not any(set(vs) == set(e.verts) for e in f.edges):
            bmesh.ops.connect_verts(bm, verts=vs)
    bm.to_mesh(ob.data); bm.free()

def refine(ob, shape, region):
    """Subdivide faces inside `region` once and snap the new vertices back onto the SDF surface."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    C = to_t(np.array([f.calc_center_median()[:] for f in bm.faces])); inr = region(C)
    edges = {e for f, k in zip(bm.faces, inr) if k for e in f.edges}
    bmesh.ops.subdivide_edges(bm, edges=list(edges), cuts=1, use_grid_fill=True)
    P = project(shape, to_t(np.array([v.co[:] for v in bm.verts])))
    for v, p in zip(bm.verts, P): v.co = B(p)
    bm.to_mesh(ob.data); bm.free()

def snowflake(shape, cx, cy, r):
    """Thin emblem strips conformed to the padded jacket (follows every seam), offset 2.5mm along the normal."""
    V, F = [], []
    def bar(a, ln, w, ox=0., oy=0., K=10):
        c, s = math.cos(a), math.sin(a); base = len(V)
        for k in range(K + 1):
            for v in (-w, w):
                u = ln * k / K; q = surf_z(shape, cx + ox + u * c - v * s, cy + oy + u * s + v * c)
                V.append(q + grad(shape, *[np.array([t]) for t in q])[0] * .0025)
        for k in range(K): i = base + 2 * k; F.append((i, i + 2, i + 3, i + 1))
    for i in range(6):
        a = i * math.pi / 3 + math.pi / 2; bar(a, r, .0055)
        bx, by = math.cos(a) * r * .55, math.sin(a) * r * .55
        bar(a + .8, r * .32, .0045, bx, by, 4); bar(a - .8, r * .32, .0045, bx, by, 4)
    ob = from_arrays('jacket_snowflake', V, F)
    for p in ob.data.polygons:  # face +Z (front)
        if p.normal.y > 0: p.flip()
    return ob

def assign(ob, rules):
    """rules: [(field, material_index)] — first rule whose field < 0 at the face centre wins; default 0."""
    me = ob.data; idx = []
    for p in me.polygons:
        c = p.center; x, y, z = np.array([c.x]), np.array([c.z]), np.array([-c.y])
        idx.append(next((mi for f, mi in rules if f(x, y, z)[0] < 0), 0))
    me.polygons.foreach_set('material_index', idx)

def delete_faces(ob, inside, margin):
    """Remove faces whose every vertex is deeper than `margin` inside another surface (hidden geometry)."""
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.verts.ensure_lookup_table()
    P = to_t(np.array([v.co[:] for v in bm.verts])); deep = inside(P[:, 0], P[:, 1], P[:, 2]) < -margin
    dead = [f for f in bm.faces if all(deep[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=dead, context='FACES'); bm.to_mesh(ob.data); bm.free()
    return len(dead)

def from_arrays(name, V, F, cols=None):
    me = bpy.data.meshes.new(name); me.from_pydata(to_b(np.asarray(V)).tolist(), [], [list(f) for f in F]); me.update()
    if cols is not None:
        ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
        ca.data.foreach_set('color', np.concatenate([cols, np.ones((len(cols), 1))], 1).ravel())
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    return new_obj(name, me)

# ══════════════════════ face expressions: swappable face-part meshes (all on the head bone) ══════════════════════
def face_frame(x, y):
    """Point on the face surface + local (side, up, normal) basis."""
    P = surf_z(core, x, y); nrm = grad(core, *[np.array([v]) for v in P])[0]
    up = np.cross(nrm, np.cross([0, 1, 0], nrm)); up /= np.linalg.norm(up)
    return P, (np.cross(up, nrm), up, nrm)
def ellip_at(name, ctr, axes, radii, seg):
    side, up, nrm = axes
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg * 3 // 4, radius=1)
    V = np.array([v.co[:] for v in bm.verts]) * radii  # local (side, up, normal)
    Vt = ctr + V[:, 0:1] * side + V[:, 1:2] * up + V[:, 2:3] * nrm
    Fc = [[v.index for v in f.verts] for f in bm.faces]; bm.free()
    return from_arrays(name, Vt, Fc)
def sd_arc2(x, y, cx, cy, R, a0, a1, w):
    px, py = x - cx, y - cy; a = np.arctan2(py, px)
    e = np.minimum(np.hypot(px - R * math.cos(a0), py - R * math.sin(a0)), np.hypot(px - R * math.cos(a1), py - R * math.sin(a1)))
    return np.where((a >= a0) & (a <= a1), np.abs(np.hypot(px, py) - R), e) - w
def sd_seg2(x, y, a, b, w):
    ax, ay = x - a[0], y - a[1]; bx, by = b[0] - a[0], b[1] - a[1]; h = np.clip((ax * bx + ay * by) / (bx * bx + by * by), 0, 1)
    return np.hypot(ax - bx * h, ay - by * h) - w
def sd_ell2(x, y, cx, cy, rx, ry): return (np.hypot((x - cx) / rx, (y - cy) / ry) - 1) * min(rx, ry)
def sd_heart2(x, y, cx, cy, s):  # iq heart, tip at (cx, cy), height ≈ s
    px, py = np.abs(x - cx) / s, (y - cy) / s; q = .5 * np.maximum(px + py, 0)
    d2 = np.sqrt(np.minimum(px**2 + (py - 1)**2, (px - q)**2 + (py - q)**2)) * np.sign(px - py)
    return np.where(px + py > 1, np.hypot(px - .25, py - .75) - math.sqrt(2) / 4, d2) * s

def expressions(parts, mats, _ellip):
    """Extra face parts. The game shows one set at a time (map stored as glTF extras on the root)."""
    def decal(name, f2d, box, mat, off=.0045, th=.0035, cap=220):
        x0, x1, y0, y1 = box
        zs = [surf_z(core, x, y)[2] for x in (x0, (x0 + x1) / 2, x1) for y in (y0, (y0 + y1) / 2, y1)]
        f = lambda x, y, z: np.maximum(np.abs(core(x, y, z) - off) - th, f2d(x, y))  # thin shell hugging the face
        ob = sdf_object(name, f, (x0 - .01, y0 - .01, min(zs) - .03), (x1 + .01, y1 + .01, max(zs) + .03), .0012, ('cap', cap))
        parts[name] = mats(ob, mat); return name
    E = .155
    happy = [decal(f'expr_eyearc_{n}', lambda x, y, s=s: sd_arc2(x, y, E * s, .925, .05, .35, 2.79, .012), (E * s - .07, E * s + .07, .9, .99), 'eye')
             for s, n in ((1, 'L'), (-1, 'R'))]
    mouth_open = decal('expr_mouth_open', lambda x, y: np.maximum(sd_ell2(x, y, 0, .85, .07, .052), y - .85), (-.08, .08, .79, .86), 'mouth')
    tongue = decal('expr_tongue', lambda x, y: np.maximum(sd_ell2(x, y, 0, .818, .036, .022), np.maximum(sd_ell2(x, y, 0, .85, .066, .048), y - .85)),
                   (-.045, .045, .79, .845), 'tongue', off=.008, th=.002)
    smile = decal('expr_mouth_smile', lambda x, y: sd_arc2(x, y, 0, .872, .045, -2.6, -.54, .008), (-.05, .05, .815, .86), 'mouth')
    mouth_o = decal('expr_mouth_o', lambda x, y: sd_ell2(x, y, 0, .81, .029, .036), (-.04, .04, .765, .85), 'mouth')
    hearts = [decal(f'expr_heart_{n}', lambda x, y, s=s: sd_heart2(x, y, E * s, .9, .088), (E * s - .07, E * s + .07, .89, 1.0), 'heart', th=.005)
              for s, n in ((1, 'L'), (-1, 'R'))]
    brows = [decal(f'expr_brow_{n}', lambda x, y, s=s: sd_seg2(x, y, (.095 * s, 1.0), (.215 * s, 1.034), .011), (min(.095 * s, .215 * s) - .02, max(.095 * s, .215 * s) + .02, .98, 1.05), 'eye')
             for s, n in ((1, 'L'), (-1, 'R'))]
    big, focus = [], []
    for s, n in ((1, 'L'), (-1, 'R')):
        P, ax = face_frame(.16 * s, .955); side, up, nrm = ax; C = P - nrm * .008
        at = lambda u, w, d, C=C, side=side, up=up, nrm=nrm: C + side * u + up * w + nrm * d
        ob = _ellip(f'expr_eyebig_{n}', C, ax, (.072, .092, .036), 20); delete_faces(ob, core, .001); parts[ob.name] = mats(ob, 'eye'); big.append(ob.name)
        for k, (c, r, seg) in enumerate(((at(.022, .038, .026), (.024, .026, .012), 12), (at(-.02, -.04, .024), (.011, .011, .007), 8))):
            hl = _ellip(f'expr_eyebig_shine_{n}{k}', c, ax, r, seg); parts[hl.name] = mats(hl, 'white'); big.append(hl.name)
        # focused: same eye, upper lid cut on a slant (inner corner lower) → determined look
        P, ax = face_frame(.155 * s, .95); side, up, nrm = ax; C = P - nrm * .007; Bm = np.stack([side, up, nrm])
        def fe(x, y, z, C=C, Bm=Bm, s=s):
            L = (np.stack([x - C[0], y - C[1], z - C[2]], -1) @ Bm.T)
            return np.maximum(sd_ell(L[..., 0], L[..., 1], L[..., 2], .062, .08, .034), y - (.968 + (np.abs(x) - .155) * .45))
        ob = sdf_object(f'expr_eyefocus_{n}', fe, tuple(C - .1), tuple(C + .1), .003, 300); delete_faces(ob, core, .001)
        parts[ob.name] = mats(ob, 'eye'); focus.append(ob.name)
        at = lambda u, w, d, C=C, side=side, up=up, nrm=nrm: C + side * u + up * w + nrm * d
        hl = _ellip(f'expr_eyefocus_shine_{n}', at(.02, -.005, .025), ax, (.016, .016, .009), 10); parts[hl.name] = mats(hl, 'white'); focus.append(hl.name)
    normal = ['eye_L', 'eye_R', 'eye_shine_L0', 'eye_shine_L1', 'eye_shine_R0', 'eye_shine_R1']
    EXPRESSIONS.update({
        'normal': normal,
        'excited': happy + [mouth_open, tongue],
        'wink': ['eye_L', 'eye_shine_L0', 'eye_shine_L1', happy[1], smile],
        'surprised': big + [mouth_o],
        'focused': focus + brows,
        'heart': hearts + [smile],
    })
EXPRESSIONS = {}

# ══════════════════════ goggles: swept frame, curved lens, wrap strap ══════════════════════
R0 = .5; G = dict(hc=.075, hw=.37, hh=.07, cr=.05)
gb = scalar(gbase)
def gsurf(s, h):
    phi = s / R0; yh = EDGE + h; a, b = 0., .75
    for _ in range(32):
        m = (a + b) / 2
        if gb(*from_hat(m * math.sin(phi), yh, m * math.cos(phi))) > 0: b = m
        else: a = m
    p = np.array(from_hat((a + b) / 2 * math.sin(phi), yh, (a + b) / 2 * math.cos(phi)))
    n = grad(gbase, *[np.array([v]) for v in p])[0]
    return p, n
def outline():
    hw, hh, cr = G['hw'], G['hh'], G['cr']; pts = []
    def arc(cx, cy, a0):
        for i in range(8): a = a0 + i / 7 * math.pi / 2; pts.append((cx + math.cos(a) * cr, cy + math.sin(a) * cr))
    def line(x0, y0, x1, y1, n):
        for i in range(1, n): pts.append((x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n))
    arc(hw - cr, hh - cr, 0); line(hw - cr, hh, -hw + cr, hh, 26)
    arc(-hw + cr, hh - cr, math.pi / 2); line(-hw, hh - cr, -hw, -hh + cr, 3)
    arc(-hw + cr, -hh + cr, math.pi); line(-hw + cr, -hh, hw - cr, -hh, 26)
    arc(hw - cr, -hh + cr, math.pi * 1.5); line(hw, -hh + cr, hw, hh - cr, 3)
    return pts
def sweep_on_surface(name, path, closed, offset, depth, width, M, square):
    S = [gsurf(s, G['hc'] + h) for s, h in path]; V = []; n_ = len(S)
    for i, (p, n) in enumerate(S):
        a = S[(i - 1) % n_][0] if (closed or i > 0) else p; b = S[(i + 1) % n_][0] if (closed or i < n_ - 1) else p
        T = (b - a) / np.linalg.norm(b - a); Bv = np.cross(n, T); Bv /= np.linalg.norm(Bv); C = p + n * offset
        for j in range(M):
            t = j / M * 2 * math.pi; c, s = math.cos(t), math.sin(t)
            V.append(C + n * depth * math.copysign(abs(c)**square, c) + Bv * width * math.copysign(abs(s)**square, s))
    F = []
    for i in range(n_ if closed else n_ - 1):
        for j in range(M):
            a, b = i * M + j, ((i + 1) % n_) * M + j
            F.append((a, b, ((i + 1) % n_) * M + (j + 1) % M, i * M + (j + 1) % M))
    if not closed:  # cap the strap ends
        F.append(tuple(range(M))[::-1]); F.append(tuple((n_ - 1) * M + j for j in range(M)))
    return from_arrays(name, V, F)
def lens():
    hw, hh, cr = G['hw'] - .014, G['hh'] - .014, G['cr'] - .014
    NX, NY = 40, 12; V = []; C = []
    top, bot, hi = np.array(srgb('#1746b8')), np.array(srgb('#6fd2ff')), np.ones(3)
    for j in range(NY + 1):
        for i in range(NX + 1):
            u, v = -1 + 2 * i / NX, -1 + 2 * j / NY; frac = max(abs(u), abs(v))
            if frac == 0: s, h = 0., 0.
            else:  # map square grid onto the rounded rect so the lens edge is exact (no clipping)
                d = np.array([u * hw, v * hh]); d /= np.linalg.norm(d); a, b = 0., 1.
                for _ in range(30):
                    m = (a + b) / 2
                    if sd_rect2(d[0] * m, d[1] * m, hw, hh, cr) > 0: b = m
                    else: a = m
                s, h = d * a * frac
            q, n = gsurf(s, G['hc'] + h)
            bulge = max(0, (1 - (s / G['hw'])**2) * (1 - (h / G['hh'])**2))
            V.append(q + n * (.036 + .018 * bulge))
            k = (h + hh) / (2 * hh); col = bot + (top - bot) * float(sstep(0, 1, np.array(k)))
            w = s + .9 * h; band = math.exp(-((w - .12) / .022)**2) * .75 + math.exp(-((w - .19) / .009)**2) * .6
            C.append(col + (hi - col) * min(band, .85))
    F = [(j * (NX + 1) + i, j * (NX + 1) + i + 1, (j + 1) * (NX + 1) + i + 1, (j + 1) * (NX + 1) + i) for j in range(NY) for i in range(NX)]
    return from_arrays('goggle_lens', V, F, np.array(C))

# ══════════════════════ materials ══════════════════════
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= .04045 else ((x + .055) / 1.055)**2.4 for x in c]
def material(name, hexcol, rough=.6, metal=0., vcol=False):
    m = bpy.data.materials.new(name)
    try: m.use_nodes = True
    except Exception: pass
    nt = m.node_tree; bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*srgb(hexcol), 1)
    bsdf.inputs['Roughness'].default_value = rough; bsdf.inputs['Metallic'].default_value = metal
    if vcol:
        cn = nt.nodes.new('ShaderNodeVertexColor'); cn.layer_name = 'Col'
        nt.links.new(cn.outputs['Color'], bsdf.inputs['Base Color'])
    m.diffuse_color = (*srgb(hexcol), 1)
    return m

# ══════════════════════ build ══════════════════════
def build():
    global COLL
    bpy.ops.wm.read_factory_settings(use_empty=True)
    COLL = bpy.context.scene.collection
    M = {k: material(*v) for k, v in {
        'navy': ('penguin_navy', '#232a48', .55), 'white': ('penguin_white', '#fbfcff', .6), 'cheek': ('cheek_pink', '#ff9fb6', .7),
        'eye': ('eye_black', '#121218', .12), 'orange': ('beak_feet_orange', '#ffab2a', .5),
        'jacket': ('jacket_blue', '#2f6fe0', .62), 'trim': ('jacket_trim_blue', '#2457c4', .75), 'zip': ('zip_white', '#eef3fb', .4),
        'hat': ('beanie_blue', '#3274e6', .85), 'hatW': ('beanie_white', '#f6f8fc', .85), 'frame': ('goggle_frame_white', '#f2f5fa', .3),
        'strap': ('goggle_strap_blue', '#2a5fd0', .7)}.items()}
    M['lens'] = material('goggle_lens', '#ffffff', .08, .25, vcol=True)
    M['mouth'] = material('mouth_dark', '#6b1f2e', .5); M['tongue'] = material('mouth_tongue', '#ff8fa3', .5); M['heart'] = material('heart_pink', '#ff4d7d', .3)
    parts = {}

    def mats(ob, *keys):
        for k in keys: ob.data.materials.append(M[k])
        return ob

    # head + body: one continuous SDF surface
    ob = sdf_object('body', core, (-.52, -.05, -.5), (.52, 1.42, .5), .009, 2400)
    n1 = delete_faces(ob, lambda x, y, z: jacket(x, y, z, False), .035)
    n2 = delete_faces(ob, lambda x, y, z: gbase(x, y, z), .004)
    log(f'body: removed {n1} faces hidden under the jacket, {n2} under the beanie')
    refine(ob, core, lambda P: (P[:, 2] > .12) & (P[:, 1] > .7) & (P[:, 1] < 1.12))  # denser face → smooth cheek/mask curves
    for fld in (face_white, cheek, belly_white): cut(ob, fld, core)
    assign(ob, [(lambda x, y, z: np.where(y > .45, cheek(x, y, z), 1), 2),
                (lambda x, y, z: np.where(y > .45, face_white(x, y, z), belly_white(x, y, z)), 1)])
    parts['body'] = mats(ob, 'navy', 'white', 'cheek')

    # padded jacket + sleeves: one surface so the shoulders bend with the arms
    ob = sdf_object('jacket', jacket, (-.72, 0, -.5), (.72, .74, .5), .009, 2800)
    log(f'jacket: removed {delete_faces(ob, core, .03)} faces inside the body')
    zipf = lambda x, y, z: np.maximum.reduce([np.abs(x) - .011, .1 - z, y - .56, .16 - y])
    def cuff(x, y, z):
        out = np.ones_like(x)
        for s in (1, -1):
            w = wing_pts(s); a, e = np.array(w['P']), np.array(w['elbow']); d = (e - a) / np.linalg.norm(e - a)
            out = np.minimum(out, np.maximum(-(((x - e[0]) * d[0] + (y - e[1]) * d[1] + (z - e[2]) * d[2]) + .045), sleeve(s, False)(x, y, z) - .03))
        return out
    trimf = lambda x, y, z: np.minimum(np.minimum(y - .15, np.maximum(.545 - y, L(x, z) - .37)), cuff(x, y, z))
    for fld in (zipf, trimf): cut(ob, fld, jacket)
    assign(ob, [(zipf, 2), (trimf, 1)])
    parts['jacket'] = mats(ob, 'jacket', 'trim', 'zip')
    parts['snowflake'] = mats(snowflake(jacket, .16, .27, .065), 'zip')

    ob = sdf_object('beanie', beanie, (-.56, .74, -.56), (.56, 1.47, .56), .009, 1600)
    log(f'beanie: removed {delete_faces(ob, core, .002)} faces inside the head')
    stripe = lambda x, y, z: np.abs(to_hat(x, y, z)[1] - EDGE - .225) - .03
    cut(ob, stripe, beanie); assign(ob, [(stripe, 1)])
    parts['beanie'] = mats(ob, 'hat', 'hatW')
    ob = sdf_object('beanie_pompom', pompom, tuple(c - .11 for c in POM), tuple(c + .11 for c in POM), .005, 360)
    delete_faces(ob, gbase, .002); parts['pompom'] = mats(ob, 'hatW')

    for s, n in ((1, 'L'), (-1, 'R')):
        w = wing_pts(s); c = np.array(w['elbow']); t = np.array(w['tip'])
        lo, hi = np.minimum(c, t) - .1, np.maximum(c, t) + .1
        ob = sdf_object('flipper_' + n, flipper(s), lo, hi, .004, 320)
        delete_faces(ob, sleeve(s, False), .004); parts['flipper_' + n] = mats(ob, 'navy')
        F = foot_c(s)
        ob = sdf_object('foot_' + n, foot(s), (F[0] - .12, -.01, F[2] - .13), (F[0] + .12, .09, F[2] + .2), .004, 360)
        parts['foot_' + n] = mats(ob, 'orange')

    bp = surf_z(core, 0, .875); ba = (0, .88, bp[2] - .015); bb = (0, .862, bp[2] + .085)
    beak = lambda x, y, z: sd_round_cone(x, ba[1] + (y - ba[1]) / .7, z, ba, bb, .052, .014) * .7
    ob = sdf_object('beak', beak, (-.08, .8, bp[2] - .06), (.08, .95, bp[2] + .14), .003, 240)
    delete_faces(ob, core, .002); parts['beak'] = mats(ob, 'orange')

    # eyes: glossy ellipsoids oriented to the face normal; parts inside the head removed
    for s, n in ((1, 'L'), (-1, 'R')):
        P = surf_z(core, .155 * s, .95); nrm = grad(core, *[np.array([v]) for v in P])[0]
        up = np.cross(nrm, np.cross([0, 1, 0], nrm)); up /= np.linalg.norm(up); side = np.cross(up, nrm)
        C = P - nrm * .007
        ellip = lambda name, ctr, radii, seg: ellip_at(name, ctr, (side, up, nrm), radii, seg)
        eye = ellip('eye_' + n, C, (.062, .082, .034), 18); delete_faces(eye, core, .001)
        parts['eye_' + n] = mats(eye, 'eye')
        at = lambda u, w, d: C + side * u + up * w + nrm * d
        for k, (ctr, rad, seg) in enumerate(((at(.019, .032, .023), (.02, .022, .011), 12), (at(-.017, -.035, .021), (.009, .009, .006), 8))):
            hl = ellip(f'eye_shine_{n}{k}', ctr, rad, seg); parts[hl.name] = mats(hl, 'white')
    expressions(parts, mats, ellip_at)

    parts['goggle_frame'] = mats(sweep_on_surface('goggle_frame', outline(), True, .026, .026, .022, 10, .55), 'frame')
    a0 = (G['hw'] + .005) / R0
    strap = [((a0 + (2 * math.pi - 2 * a0) * i / 56) * R0, 0.) for i in range(57)]
    parts['goggle_strap'] = mats(sweep_on_surface('goggle_strap', strap, False, .0075, .0075, .034, 8, .3), 'strap')
    parts['goggle_lens'] = mats(lens(), 'lens')

    for ob in parts.values():
        ob.data.shade_smooth() if hasattr(ob.data, 'shade_smooth') else None
        for p in ob.data.polygons: p.use_smooth = True
    return parts

# ══════════════════════ armature + weights ══════════════════════
BONES = {  # name: (head, tail, parent) in three coords
    'root': ((0, 0, 0), (0, .15, 0), None), 'hips': ((0, .2, 0), (0, .45, 0), 'root'), 'chest': ((0, .45, 0), (0, .6, 0), 'hips'),
    'head': ((0, .6, 0), (0, 1.25, 0), 'chest'),
}
for s, n in ((1, 'L'), (-1, 'R')):
    w = wing_pts(s)
    BONES['upperarm_' + n] = (w['P'], w['elbow'], 'chest'); BONES['hand_' + n] = (w['elbow'], w['tip'], 'upperarm_' + n)
    BONES['foot_' + n] = ((.13 * s, 0, .015), (.13 * s, 0, .2), 'root')

def rig(parts):
    arm_d = bpy.data.armatures.new('penguin_rig'); arm = new_obj('penguin_blue', arm_d)
    activate(arm); bpy.ops.object.mode_set(mode='EDIT')
    for name, (h, t, par) in BONES.items():
        eb = arm_d.edit_bones.new(name); eb.head = B(h); eb.tail = B(t)
        if par: eb.parent = arm_d.edit_bones[par]; eb.use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')

    def seg_dist(P, a, b):
        a, b = np.array(a), np.array(b); d = b - a; u = np.clip(((P - a) @ d) / (d @ d), 0, 1)
        return np.linalg.norm(P - (a + u[:, None] * d), axis=1), ((P - a) @ d) / (d @ d)
    def weights(ob, P):
        if ob.name == 'jacket':
            W = {}
            arm_w = {}
            for s, n in ((1, 'L'), (-1, 'R')):
                w = wing_pts(s); dist, u = seg_dist(P, w['P'], w['tip'])
                arm_w[n] = sstep(-.3, .2, u) * sstep(.17, .1, dist) * sstep(.12, .3, s * P[:, 0])
            torso = 1 - np.clip(arm_w['L'] + arm_w['R'], 0, 1)
            chest = sstep(.3, .5, P[:, 1])
            W['chest'] = torso * chest; W['hips'] = torso * (1 - chest)
            W['upperarm_L'], W['upperarm_R'] = arm_w['L'], arm_w['R']
            return W
        if ob.name == 'jacket_snowflake': return {'hips': 1 - sstep(.3, .5, P[:, 1]), 'chest': sstep(.3, .5, P[:, 1])}
        if ob.name == 'body': return {'head': (P[:, 1] > .45) * 1., 'hips': (P[:, 1] <= .45) * 1.}
        for key, bone in (('flipper_L', 'hand_L'), ('flipper_R', 'hand_R'), ('foot_L', 'foot_L'), ('foot_R', 'foot_R')):
            if ob.name == key: return {bone: np.ones(len(P))}
        return {'head': np.ones(len(P))}
    for ob in parts.values():
        P = mesh_verts_t(ob.data); W = weights(ob, P)
        tot = np.maximum(sum(W.values()), 1e-9)
        for bone, w in W.items():
            vg = ob.vertex_groups.new(name=bone)
            for i, val in enumerate(w / tot):
                if val > 1e-4: vg.add([i], float(val), 'REPLACE')
        ob.parent = arm; mod = ob.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
    return arm

# ══════════════════════ animation ══════════════════════
def mir(keys): return [(t, x, -y, -z) for t, x, y, z in keys]
def wings(l, r=None): return {'wing_L': {'rot': l}, 'wing_R': {'rot': r or mir(l)}}
def feet(keys, alt=True): return {'foot_L': {'rot': keys}, 'foot_R': {'rot': [(t, -x, y, z) for t, x, y, z in keys] if alt else keys}}
CLIPS = {  # (duration s, {node: {rot|pos|scl: [(normalized t, x, y, z)]}}) — three-space eulers (XYZ), same data as penguin.html
    'Idle': (2.4, {'torso': {'rot': [(0, 0, 0, .025), (.5, .02, 0, -.025), (1, 0, 0, .025)], 'scl': [(0, 1, 1, 1), (.5, 1.015, .985, 1.015), (1, 1, 1, 1)]},
                   'head': {'rot': [(0, 0, 0, -.04), (.5, -.03, 0, .04), (1, 0, 0, -.04)]}, **wings([(0, 0, 0, .04), (.5, 0, 0, .12), (1, 0, 0, .04)])}),
    'Walk': (.8, {'rig': {'pos': [(0, 0, 0, 0), (.25, 0, .035, 0), (.5, 0, 0, 0), (.75, 0, .035, 0), (1, 0, 0, 0)]},
                  'torso': {'rot': [(0, .04, 0, .1), (.5, .04, 0, -.1), (1, .04, 0, .1)]}, 'head': {'rot': [(0, -.03, 0, -.05), (.5, -.03, 0, .05), (1, -.03, 0, -.05)]},
                  'foot_L': {'rot': [(0, -.4, 0, 0), (.25, -.15, 0, 0), (.5, 0, 0, 0), (.75, 0, 0, 0), (1, -.4, 0, 0)]},
                  'foot_R': {'rot': [(0, 0, 0, 0), (.25, 0, 0, 0), (.5, -.4, 0, 0), (.75, -.15, 0, 0), (1, 0, 0, 0)]},
                  **wings([(0, .15, 0, .28), (.5, -.15, 0, .12), (1, .15, 0, .28)], mir([(0, -.15, 0, .12), (.5, .15, 0, .28), (1, -.15, 0, .12)]))}),
    'Run': (.5, {'rig': {'pos': [(0, 0, 0, 0), (.25, 0, .07, 0), (.5, 0, 0, 0), (.75, 0, .07, 0), (1, 0, 0, 0)]},
                 'torso': {'rot': [(0, .22, 0, .1), (.5, .22, 0, -.1), (1, .22, 0, .1)]}, 'head': {'rot': [(0, -.16, 0, 0), (1, -.16, 0, 0)]},
                 'foot_L': {'rot': [(0, -.6, 0, 0), (.25, -.2, 0, 0), (.5, 0, 0, 0), (1, -.6, 0, 0)]}, 'foot_R': {'rot': [(0, 0, 0, 0), (.5, -.6, 0, 0), (.75, -.2, 0, 0), (1, 0, 0, 0)]},
                 **wings([(0, .55, 0, .75), (.5, .3, 0, .55), (1, .55, 0, .75)])}),
    'Jump': (1., {'rig': {'pos': [(0, 0, 0, 0), (.18, 0, 0, 0), (.45, 0, .6, 0), (.72, 0, 0, 0), (1, 0, 0, 0)],
                          'scl': [(0, 1, 1, 1), (.18, 1.08, .88, 1.08), (.3, .95, 1.07, .95), (.45, 1, 1, 1), (.72, 1.08, .9, 1.08), (.85, 1, 1, 1), (1, 1, 1, 1)]},
                  'head': {'rot': [(0, 0, 0, 0), (.18, .1, 0, 0), (.45, -.12, 0, 0), (.72, .08, 0, 0), (1, 0, 0, 0)]},
                  **wings([(0, 0, 0, .04), (.18, .3, 0, .25), (.35, 0, 0, 1.25), (.6, 0, 0, 1.05), (.75, 0, 0, .2), (1, 0, 0, .04)]),
                  **feet([(0, 0, 0, 0), (.3, 0, 0, 0), (.4, .35, 0, 0), (.6, .35, 0, 0), (.66, 0, 0, 0), (1, 0, 0, 0)], False)}),
    'Gather': (1.4, {'torso': {'rot': [(0, 0, 0, 0), (.25, .45, 0, 0), (.75, .45, 0, 0), (1, 0, 0, 0)]}, 'head': {'rot': [(0, 0, 0, 0), (.25, -.1, 0, 0), (.75, -.1, 0, 0), (1, 0, 0, 0)]},
                     **wings([(0, 0, 0, .04), (.25, -.7, 0, .35), (.4, -1.15, 0, .12), (.55, -.7, 0, .35), (.7, -1.15, 0, .12), (1, 0, 0, .04)])}),
    'Roll': (1.2, {'rig': {'pos': [(0, 0, 0, 0), (.5, 0, 0, .06), (1, 0, 0, 0)]}, 'torso': {'rot': [(0, .3, 0, .05), (.5, .3, 0, -.05), (1, .3, 0, .05)]},
                   'head': {'rot': [(0, -.2, 0, 0), (1, -.2, 0, 0)]},
                   **wings([(0, -1.25, 0, .18), (.5, -.95, 0, .22), (1, -1.25, 0, .18)], mir([(0, -.95, 0, .22), (.5, -1.25, 0, .18), (1, -.95, 0, .22)])),
                   'foot_L': {'rot': [(0, -.35, 0, 0), (.5, 0, 0, 0), (1, -.35, 0, 0)]}, 'foot_R': {'rot': [(0, 0, 0, 0), (.5, -.35, 0, 0), (1, 0, 0, 0)]}}),
    'Throw': (.9, {'torso': {'rot': [(0, 0, 0, 0), (.35, -.1, -.45, 0), (.55, .18, .35, 0), (1, 0, 0, 0)]}, 'head': {'rot': [(0, 0, 0, 0), (.35, 0, .25, 0), (.55, 0, -.2, 0), (1, 0, 0, 0)]},
                   'wing_R': {'rot': [(0, 0, 0, 0), (.15, 1.0, 0, -1.0), (.35, 2.7, 0, -.15), (.45, -2.65, .05, .2), (.55, -1.89, -.05, .05), (.72, -1.31, 0, -.1), (1, 0, 0, 0)]},  # 뒤로 젖힘 → 머리 위 → 앞으로 휘두름 (오버핸드)
                   'wing_L': {'rot': [(0, 0, 0, .04), (.35, -.55, 0, .45), (.55, 0, 0, .25), (1, 0, 0, .04)]}}),
    'Hit': (.7, {'torso': {'rot': [(0, 0, 0, 0), (.15, -.3, 0, .1), (.5, -.12, 0, -.05), (1, 0, 0, 0)], 'scl': [(0, 1, 1, 1), (.15, 1.07, .9, 1.07), (.4, .97, 1.04, .97), (1, 1, 1, 1)]},
                 'head': {'rot': [(0, 0, 0, 0), (.15, -.22, 0, -.15), (.5, .06, 0, .08), (1, 0, 0, 0)]}, 'rig': {'pos': [(0, 0, 0, 0), (.15, 0, 0, -.08), (1, 0, 0, 0)]},
                 **wings([(0, 0, 0, .04), (.15, -.4, 0, 1.15), (.5, 0, 0, .5), (1, 0, 0, .04)])}),
    'Victory': (1.6, {'rig': {'pos': [(0, 0, 0, 0), (.2, 0, .25, 0), (.4, 0, 0, 0), (.6, 0, .25, 0), (.8, 0, 0, 0), (1, 0, 0, 0)]},
                      'torso': {'rot': [(0, 0, 0, 0), (.2, 0, .3, 0), (.6, 0, -.3, 0), (1, 0, 0, 0)]}, 'head': {'rot': [(0, 0, 0, 0), (.2, -.18, 0, 0), (.8, -.18, 0, 0), (1, 0, 0, 0)]},
                      **wings([(0, 0, 0, .04), (.1, 0, 0, 1.2), (.2, .1, 0, 1.75), (.4, .05, 0, 1.45), (.6, .1, 0, 1.75), (.8, .05, 0, 1.45), (1, 0, 0, .04)])}),
}
# ── 신규 동작(2026-11): 싸다구 + 배 슬라이딩. 기존 9개 클립은 건드리지 않음(blender/add_actions.py 가 기존 .blend 에 이 클립만 추가)
# 누운 자세: 루트를 발 기준으로 앞으로 83° 눕히고 배가 땅에 닿게 들어 올림, 몸 가운데가 루트 위에 오게 뒤로 당김 → 게임 충돌·명중 판정 중심 = 캐릭터 위치
# 허리를 뒤로 젖히고 머리를 들어 진행 방향을 봄. 발은 뒤로 쭉, 날개는 몸 옆으로 살짝 벌림
LIE = {'rig': ((1.5, 0, 0), (0, .292, -.6)), 'torso': (-.35, 0, 0), 'head': (-.7, 0, 0), 'wing': (.25, 0, .42), 'foot': (1.25, 0, 0)}
def lie_clip(frames):  # frames: [(t, wob, sway, wing_extra(x, z), foot_kick)] → CLIPS 형식
    out = {'rig': {'rot': [], 'pos': []}, 'torso': {'rot': []}, 'head': {'rot': []}, 'wing_L': {'rot': []}, 'wing_R': {'rot': []}, 'foot_L': {'rot': []}, 'foot_R': {'rot': []}}
    (rr, rp), w, f = LIE['rig'], LIE['wing'], LIE['foot']
    for t, wob, sway, (wx, wz), kick in frames:
        out['rig']['rot'].append((t, rr[0], rr[1], rr[2] + wob)); out['rig']['pos'].append((t, *rp))
        out['torso']['rot'].append((t, LIE['torso'][0], sway, 0)); out['head']['rot'].append((t, LIE['head'][0], -sway * .7, 0))
        out['wing_L']['rot'].append((t, w[0] + wx, 0, w[2] + wz)); out['wing_R']['rot'].append((t, w[0] + wx, 0, -(w[2] + wz)))
        out['foot_L']['rot'].append((t, f[0] + kick, 0, 0)); out['foot_R']['rot'].append((t, f[0] - kick, 0, 0))
    return out
def lie_at(t): return lie_clip([(t, 0, 0, (0, 0), 0)])
def merge(*specs):  # 같은 노드·채널의 키를 시간 순으로 이어 붙임
    out = {}
    for sp in specs:
        for node, ch in sp.items():
            for k, keys in ch.items(): out.setdefault(node, {}).setdefault(k, []).extend(keys)
    for ch in out.values():
        for k in ch: ch[k].sort(key=lambda q: q[0])
    return out
CLIPS.update({
    # 싸다구 0.6초: 0~.2 뒤로 젖히며 오른 날개를 옆·뒤로 당김 → .2~.42 몸통을 돌리며 휘두름 → .42~.53 임팩트(살짝 멈칫) → 복귀. 머리는 몸과 반대로 흔들림
    'Slap': (.6, {'rig': {'pos': [(0, 0, 0, 0), (.2, 0, 0, -.03), (.42, 0, 0, .07), (.53, 0, 0, .08), (1, 0, 0, 0)]},
                  'torso': {'rot': [(0, 0, 0, 0), (.2, -.1, -.42, .04), (.42, .08, .3, -.03), (.53, .08, .36, -.03), (.78, .02, .08, 0), (1, 0, 0, 0)],
                            'scl': [(0, 1, 1, 1), (.2, 1.03, .97, 1.03), (.42, .98, 1.03, .98), (.53, 1.02, .98, 1.02), (1, 1, 1, 1)]},
                  'head': {'rot': [(0, 0, 0, 0), (.2, .05, .2, -.05), (.42, -.05, -.18, .06), (.53, -.04, -.24, .07), (.78, 0, -.05, 0), (1, 0, 0, 0)]},
                  'wing_R': {'rot': [(0, 0, 0, 0), (.2, .55, -.75, -1.3), (.34, .15, .35, -1.5), (.42, -.1, .55, -1.5), (.53, -.1, .6, -1.45), (.68, -.05, .4, -1.15), (.85, 0, .1, -.5), (1, 0, 0, 0)]},
                  'wing_L': {'rot': [(0, 0, 0, .04), (.2, -.25, 0, .4), (.42, .3, 0, .55), (.53, .3, 0, .5), (1, 0, 0, .04)]},
                  'foot_L': {'rot': [(0, 0, 0, 0), (.2, -.12, 0, 0), (.42, 0, 0, 0), (1, 0, 0, 0)]}}),
    # 싸다구 맞음 0.5초: 얼굴이 옆으로 홱 돌아가고(목 한계 안), 몸이 반대로 휘청 → 제자리. 눈 깜빡임·놀란 얼굴은 penguin.js 표정으로
    'SlapHit': (.5, {'torso': {'rot': [(0, 0, 0, 0), (.14, -.06, .22, .14), (.4, .02, -.06, -.07), (.7, 0, .02, .03), (1, 0, 0, 0)],
                               'scl': [(0, 1, 1, 1), (.14, 1.05, .93, 1.05), (.4, .98, 1.03, .98), (1, 1, 1, 1)]},
                     'head': {'rot': [(0, 0, 0, 0), (.12, .04, .3, .08), (.4, 0, .1, .04), (.7, 0, -.04, 0), (1, 0, 0, 0)]},
                     'rig': {'pos': [(0, 0, 0, 0), (.14, -.04, 0, -.05), (1, 0, 0, 0)]},
                     **wings([(0, 0, 0, .04), (.14, -.2, 0, .9), (.45, 0, 0, .35), (1, 0, 0, .04)])}),
    # 배 슬라이딩 시작 0.25초: 숙이며 날개를 펼치고(.45) 앞으로 몸을 던져 배가 눈에 닿음(1 = Loop 첫 자세)
    'BellySlide_Start': (.25, merge(
        {'rig': {'rot': [(0, 0, 0, 0), (.45, .55, 0, 0)], 'pos': [(0, 0, 0, 0), (.45, 0, .24, .02)]},
         'torso': {'rot': [(0, 0, 0, 0), (.45, .35, 0, 0)]}, 'head': {'rot': [(0, 0, 0, 0), (.45, -.25, 0, 0)]},
         'wing_L': {'rot': [(0, 0, 0, .04), (.45, .3, 0, 1.15)]}, 'wing_R': {'rot': [(0, 0, 0, -.04), (.45, .3, 0, -1.15)]},
         'foot_L': {'rot': [(0, 0, 0, 0), (.45, .5, 0, 0)]}, 'foot_R': {'rot': [(0, 0, 0, 0), (.45, .5, 0, 0)]}},
        lie_at(1))),
    # 배 슬라이딩 반복 0.6초: 누운 자세에서 몸이 좌우로 살짝 흔들리고 날개·발이 조금씩 파닥 (처음 = 끝)
    'BellySlide_Loop': (.6, lie_clip([(0, 0, 0, (0, 0), 0), (.25, .05, .06, (-.08, .08), .12), (.5, 0, 0, (0, 0), 0), (.75, -.05, -.06, (-.08, .08), -.12), (1, 0, 0, (0, 0), 0)])),
    # 배 슬라이딩 끝 0.35초: 날개로 땅을 짚고(.3) 상체를 일으켜(.65) 두 발로 섬 → Idle·Run 으로 이어짐
    'BellySlide_End': (.35, merge(lie_at(0),
        {'rig': {'rot': [(.3, 1.2, 0, 0), (.65, .35, 0, 0), (1, 0, 0, 0)], 'pos': [(.3, 0, .36, -.45), (.48, 0, .3, -.3), (.65, 0, .12, -.12), (1, 0, 0, 0)]},
         'torso': {'rot': [(.3, -.35, 0, 0), (.65, .1, 0, 0), (1, 0, 0, 0)]}, 'head': {'rot': [(.3, -.5, 0, 0), (.65, -.1, 0, 0), (1, 0, 0, 0)]},
         'wing_L': {'rot': [(.3, -1.1, 0, .5), (.65, -.3, 0, .35), (1, 0, 0, .04)]}, 'wing_R': {'rot': [(.3, -1.1, 0, -.5), (.65, -.3, 0, -.35), (1, 0, 0, -.04)]},
         'foot_L': {'rot': [(.3, .9, 0, 0), (.65, .1, 0, 0), (1, 0, 0, 0)]}, 'foot_R': {'rot': [(.3, .9, 0, 0), (.65, .1, 0, 0), (1, 0, 0, 0)]}})),
})
NEW_CLIPS = ('Slap', 'SlapHit', 'BellySlide_Start', 'BellySlide_Loop', 'BellySlide_End')
NECK_MAX = {'BellySlide_Start': .75, 'BellySlide_Loop': .75, 'BellySlide_End': .75}  # 누워서 고개를 드는 동작만 목 한계를 조금 넓게(나머지 .35)
NODE2BONE = {'rig': 'root', 'torso': 'hips', 'head': 'head', 'wing_L': 'upperarm_L', 'wing_R': 'upperarm_R', 'foot_L': 'foot_L', 'foot_R': 'foot_R'}
FPS = 30
P3 = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
def rot3(x, y, z):  # three.js Euler 'XYZ' = Rx·Ry·Rz
    return Matrix.Rotation(x, 3, 'X') @ Matrix.Rotation(y, 3, 'Y') @ Matrix.Rotation(z, 3, 'Z')
def sample(keys, t):
    ts = [k[0] for k in keys]; return [float(np.interp(t, ts, [k[i] for k in keys])) for i in (1, 2, 3)]

def animate(arm, clips=None):
    if not arm.animation_data: arm.animation_data_create()
    scn = bpy.context.scene; scn.render.fps = FPS
    actions = {}
    for name, (dur, spec) in (clips or CLIPS).items():
        act = bpy.data.actions.new(name); arm.animation_data.action = act
        for pb in arm.pose.bones: pb.matrix_basis = Matrix()
        prev_q = {}
        for node, ch in spec.items():
            pb = arm.pose.bones[NODE2BONE[node]]; Bm = pb.bone.matrix_local
            times = sorted({k[0] for keys in ch.values() for k in keys})
            for t in times:
                pos = sample(ch['pos'], t) if 'pos' in ch else [0, 0, 0]
                rot = sample(ch['rot'], t) if 'rot' in ch else [0, 0, 0]
                scl = sample(ch['scl'], t) if 'scl' in ch else [1, 1, 1]
                R = (P3 @ rot3(*rot) @ P3.inverted()).to_4x4()
                S = (P3 @ Matrix.Diagonal(scl) @ P3.inverted()).to_4x4()
                h = Bm.translation
                D = Matrix.Translation(B(pos)) @ Matrix.Translation(h) @ R @ S @ Matrix.Translation(-h)
                pb.matrix_basis = Bm.inverted() @ D @ Bm
                q = pb.rotation_quaternion.copy()
                if pb.name in prev_q and prev_q[pb.name].dot(q) < 0: pb.rotation_quaternion = -q  # keep quaternion keys in one hemisphere
                prev_q[pb.name] = pb.rotation_quaternion.copy()
                f = t * dur * FPS  # frame 0 = glTF time 0 (no 1-frame hold at the loop seam)
                pb.keyframe_insert('location', frame=f); pb.keyframe_insert('rotation_quaternion', frame=f); pb.keyframe_insert('scale', frame=f)
        act.use_fake_user = True
        tr = arm.animation_data.nla_tracks.new(); tr.name = name
        st = tr.strips.new(name, 0, act)
        if hasattr(st, 'action_slot') and getattr(act, 'slots', None): st.action_slot = act.slots[0]
        arm.animation_data.action = None
        actions[name] = (act, dur)
    for pb in arm.pose.bones: pb.matrix_basis = Matrix()
    return actions

def use_action(arm, act):
    for tr in arm.animation_data.nla_tracks: tr.mute = True
    arm.animation_data.action = act
    if hasattr(arm.animation_data, 'action_slot') and getattr(act, 'slots', None): arm.animation_data.action_slot = act.slots[0]

# ══════════════════════ penetration / ground test on the skinned, deformed meshes ══════════════════════
def evaluated_t(ob):
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co); ev.to_mesh_clear()
    co = co.reshape(-1, 3); mw = np.array(ob.matrix_world)
    return to_t(co @ mw[:3, :3].T + mw[:3, 3])
def penetration(arm, parts, actions):
    jac = parts['jacket']; P0 = mesh_verts_t(jac.data)
    vg = {g.name: g.index for g in jac.vertex_groups}; arm_w = np.zeros(len(P0)); side = np.zeros(len(P0))
    for v in jac.data.vertices:
        for g in v.groups:
            if g.group in (vg.get('upperarm_L'), vg.get('upperarm_R')) and g.weight > arm_w[v.index]:
                arm_w[v.index] = g.weight; side[v.index] = 1 if g.group == vg.get('upperarm_L') else -1
    sel = np.nonzero(arm_w > .6)[0]
    limbs = [('sleeve', jac, sel)] + [(f'flipper_{n}', parts['flipper_' + n], None) for n in 'LR']
    def frames(name):
        pb = arm.pose.bones[name]; return np.array(pb.bone.matrix_local @ pb.matrix.inverted())
    def into(Pt, M):  # world(three) → rest frame of a bone (via Blender space)
        Pb = to_b(Pt); return to_t(Pb @ M[:3, :3].T + M[:3, 3])
    shoulders = {s: np.array(wing_pts(s)['P']) for s in (1, -1)}
    def depth(Pt, Mc, Mh):
        pc, ph = into(Pt, Mc), into(Pt, Mh)
        near = np.min([np.linalg.norm(pc - shoulders[s], axis=1) for s in (1, -1)], 0) < .14
        db = np.where(near, 1., jacket_torso(pc[:, 0], pc[:, 1], pc[:, 2], False))
        dh = np.minimum(ell(ph[:, 0], ph[:, 1], ph[:, 2], HEAD) - .02, gbase(ph[:, 0], ph[:, 1], ph[:, 2]))
        return -np.minimum(db, dh)
    use_action(arm, None); bpy.context.scene.frame_set(0)
    rest = {}
    for n, ob, idx in limbs:
        Pt = evaluated_t(ob); Pt = Pt if idx is None else Pt[idx]
        rest[n] = np.maximum(depth(Pt, frames('chest'), frames('head')), 0)
    rep = {'rest_joint_overlap_cm': round(float(max(r.max() for r in rest.values())) * 100, 1), 'clips': {}}
    for name, (act, dur) in actions.items():
        use_action(arm, act); worst, where, ground, neck = 0., '', 0., 0.
        n_frames = int(round(dur * FPS)) + 1
        for f in range(0, n_frames):
            bpy.context.scene.frame_set(f)
            Mc, Mh = frames('chest'), frames('head')
            for n, ob, idx in limbs:
                Pt = evaluated_t(ob); Pt = Pt if idx is None else Pt[idx]
                d = depth(Pt, Mc, Mh) - rest[n]
                if d.max() > worst:
                    pc = into(Pt[[int(d.argmax())]], Mc)[0]
                    sd = min(np.linalg.norm(pc - shoulders[s]) for s in (1, -1))
                    worst, where = float(d.max()), f'{n} @{f / FPS:.2f}s, {sd * 100:.0f}cm from shoulder'
            for n in 'LR': ground = min(ground, float(evaluated_t(parts['foot_' + n])[:, 1].min()))
            qh = arm.pose.bones['head'].matrix.to_quaternion(); qc = arm.pose.bones['chest'].matrix.to_quaternion()
            neck = max(neck, qh.rotation_difference(qc).angle)
        ok = worst < .015 and ground > -.01 and neck < NECK_MAX.get(name, .35)
        rep['clips'][name] = {'ok': ok, 'frames': n_frames, 'max_extra_penetration_cm': round(worst * 100, 2), 'where': where,
                              'min_foot_y': round(ground, 4), 'neck_deg': round(math.degrees(neck), 1)}
        log(f'  {"OK " if ok else "XX "}{name:8s} penetration {worst * 100:4.1f}cm {where:18s} feet {ground:+.3f} neck {math.degrees(neck):4.1f}°')
    use_action(arm, None)
    for tr in arm.animation_data.nla_tracks: tr.mute = False
    return rep

# ══════════════════════ renders ══════════════════════
VIEWS = {'front': (0, .1, 1), 'front34': (.75, .2, 1), 'right': (-1, .1, 0), 'back34': (-.75, .2, -1), 'back': (0, .1, -1), 'left': (1, .1, 0)}
def setup_render():
    scn = bpy.context.scene; scn.render.engine = 'BLENDER_EEVEE'
    scn.view_settings.view_transform = 'Standard'; scn.render.film_transparent = False
    w = bpy.data.worlds.new('w'); scn.world = w
    try:
        w.use_nodes = True
    except Exception: pass
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND'); bg.inputs[0].default_value = (*srgb('#e3f0fd'), 1); bg.inputs[1].default_value = .9
    for name, loc, energy, typ, size in (('key', (2.5, -3.5, 4), 4., 'SUN', 0), ('fill', (-3, -2, 2), 1.2, 'SUN', 0)):
        ld = bpy.data.lights.new(name, typ); ld.energy = energy; lo = new_obj(name, ld); lo.location = loc
        lo.rotation_euler = (Vector((0, 0, .7)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    pl = bpy.data.meshes.new('ground'); pl.from_pydata([(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)], [], [(0, 1, 2, 3)])
    g = new_obj('render_ground', pl); g.data.materials.append(material('ground', '#eef5fd', .9)); g.is_shadow_catcher = True
    cam = new_obj('render_cam', bpy.data.cameras.new('render_cam')); cam.data.lens = 70; scn.camera = cam
    return cam
def shoot(cam, path, d, dist=4.6, target=(0, .72, 0), res=(560, 700)):
    scn = bpy.context.scene; scn.render.resolution_x, scn.render.resolution_y = res
    tgt = B(target); dv = Vector(B(np.array(d) / np.linalg.norm(d)))
    cam.location = tgt + dv * dist; cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scn.render.filepath = path; bpy.ops.render.render(write_still=True)

# ══════════════════════ export ══════════════════════
def export(path):
    kw = dict(filepath=path, export_format='GLB', use_selection=False, export_yup=True, export_apply=True, export_animations=True,
              export_animation_mode='NLA_TRACKS', export_skins=True, export_cameras=False, export_lights=False, export_extras=True)
    for o in bpy.context.scene.objects: o.hide_set(o.name.startswith('render_') or o.type in ('LIGHT', 'CAMERA'))
    sel_objs = [o for o in bpy.context.scene.objects if not o.hide_get()]
    for o in bpy.context.view_layer.objects: o.select_set(o in sel_objs)
    kw['use_selection'] = True
    try: bpy.ops.export_scene.gltf(**kw, export_vertex_color='MATERIAL')
    except TypeError: bpy.ops.export_scene.gltf(**kw)
    for o in bpy.context.scene.objects: o.hide_set(False)
    return os.path.getsize(path)

def main():
    parts = build()
    tris = sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in parts.values())
    log(f'mesh done: {len(parts)} objects, {tris} triangles')
    arm = rig(parts); arm['collider'] = {'type': 'capsule', 'center': [0, .75, 0], 'radius': .46, 'height': 1.5}; arm['expressions'] = EXPRESSIONS
    actions = animate(arm); log(f'animations: {", ".join(actions)}')
    rep = {'triangles': tris, 'objects': len(parts)}
    rep['penetration'] = penetration(arm, parts, actions)
    if '--no-render' not in sys.argv:
        cam = setup_render()
        for k, d in VIEWS.items(): shoot(cam, os.path.join(RENDERS, f'view_{k}.png'), d)
        shoot(cam, os.path.join(RENDERS, 'closeup.png'), (0, .05, 1), dist=2.6, target=(0, .8, 0), res=(700, 700))
        for name, t in (('Idle', .5), ('Walk', .15), ('Run', .1), ('Jump', .45), ('Gather', .55), ('Roll', .3), ('Throw', .32), ('Hit', .1), ('Victory', .32)):
            act, dur = actions[name]; use_action(arm, act); bpy.context.scene.frame_set(int(t * dur * FPS))
            shoot(cam, os.path.join(RENDERS, f'pose_{name}.png'), (.8, .25, 1), dist=5, res=(420, 520))
        use_action(arm, None)
        for tr in arm.animation_data.nla_tracks: tr.mute = False
        bpy.context.scene.frame_set(0)
        log('renders done')
    bpy.context.preferences.filepaths.save_version = 0  # no automatic .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, 'penguin_blue.blend'))
    rep['glb_bytes'] = export(GAME_GLB)
    if '--lod1' not in sys.argv:  # LOD1 is retired (zipper/stripe broke up); kept only as an opt-in experiment
        json.dump(rep, open(os.path.join(HERE, 'report.json'), 'w'), indent=2, ensure_ascii=False)
        return log('done', json.dumps({k: v for k, v in rep.items() if k != 'penetration'}))
    for ob in parts.values():
        ob.data = ob.data.copy(); activate(ob); mod = ob.modifiers.new('lod', 'DECIMATE'); mod.ratio = .38
        bpy.ops.object.modifier_move_to_index(modifier='lod', index=0); bpy.ops.object.modifier_apply(modifier='lod')
    rep['lod1_triangles'] = sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in parts.values())
    rep['lod1_glb_bytes'] = export(os.path.join(HERE, 'unused', 'penguin_blue_lod1.glb'))
    json.dump(rep, open(os.path.join(HERE, 'report.json'), 'w'), indent=2, ensure_ascii=False)
    log('done', json.dumps({k: v for k, v in rep.items() if k != 'penetration'}))

if "--no-main" not in sys.argv: main()
