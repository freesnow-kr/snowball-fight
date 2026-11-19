"""SLOPE SNOWFIGHT maps — shared Blender modelling kit.

Coordinates: Blender world (X right, Y north/back, Z up, meters). glTF export converts to Y-up:
three (x, y, z) = (bx, bz, -by). Map play area = X,Y in [-50, 50].
"""
import bpy, bmesh, math, os, sys, time, random
import numpy as np
from mathutils import Vector, Matrix, Euler, noise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.time()
def log(*a): print(f'[{time.time() - T0:6.1f}s]', *a, flush=True)

def to_three(v):  # Blender → glTF/three
    return [round(v[0], 3), round(v[2], 3), round(-v[1], 3)]

# ══════════════════════ materials (one shared library for every prop and map) ══════════════════════
def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= .04045 else ((x + .055) / 1.055)**2.4 for x in c]

MAT_DEFS = {  # name: (hex, roughness, metallic, extra)
    'snow': ('#f4f8ff', .78, 0, {}), 'snow_blue': ('#dbe8f7', .8, 0, {}), 'snow_path': ('#e4ebf4', .85, 0, {}),
    'ice': ('#9fe3f0', .06, 0, {'alpha': .82, 'coat': .6}), 'ice_solid': ('#8fd6ea', .08, 0, {'coat': .6}),
    'ice_dark': ('#4fa9c9', .1, 0, {'coat': .5}), 'icicle': ('#c9f3ff', .05, 0, {'alpha': .9, 'coat': .5}), 'icicle_light': ('#eafaff', .08, 0, {'coat': .6}),
    'log': ('#9a6236', .7, 0, {}), 'log_end': ('#d9a66b', .75, 0, {}), 'wood': ('#b97a45', .7, 0, {}),
    'wood_dark': ('#6e4528', .75, 0, {}), 'roof': ('#7c3f2a', .7, 0, {}), 'bark': ('#6b4428', .9, 0, {}),
    'stone': ('#9aa3b2', .85, 0, {}), 'rock': ('#7f8a9c', .85, 0, {}), 'rock_dark': ('#5e6878', .9, 0, {}),
    'pine': ('#2f7d5b', .8, 0, {}), 'pine_dark': ('#22634a', .8, 0, {}), 'pine_light': ('#3f9a6c', .8, 0, {}),
    'window': ('#ffd36e', .3, 0, {'emit': ('#ffb547', 2.5)}), 'bulb': ('#fff2c4', .3, 0, {'emit': ('#ffd27a', 6.0)}),
    'lamp': ('#fff6dc', .3, 0, {'emit': ('#ffe2a8', 8.0)}),
    'red': ('#e5484d', .6, 0, {}), 'red_dark': ('#b9353a', .65, 0, {}), 'blue': ('#2f6fe0', .6, 0, {}),
    'orange': ('#ff9a3c', .55, 0, {}), 'yellow': ('#ffd24d', .55, 0, {}), 'white': ('#fbfcff', .55, 0, {}),
    'black': ('#1d1f29', .4, 0, {}), 'metal': ('#6e7b8f', .45, .5, {}), 'metal_dark': ('#3a4252', .5, .4, {}),
    'rope': ('#c9a27a', .9, 0, {}), 'purple': ('#8b6cf2', .55, 0, {}), 'pink': ('#ff7fb0', .6, 0, {}),
    'net': ('#ff7a2f', .7, 0, {}), 'terrain': ('#ffffff', .82, 0, {'vcol': True}),
    'aurora': ('#000000', 1, 0, {'vcol_emit': 3.0}),
}
_MATS = {}
def mat(name):
    if name in _MATS: return _MATS[name]
    hexcol, rough, metal, ex = MAT_DEFS[name]
    m = bpy.data.materials.new(name)
    try: m.use_nodes = True
    except Exception: pass
    nt = m.node_tree; b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (*srgb(hexcol), 1)
    b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    if 'emit' in ex:
        b.inputs['Emission Color'].default_value = (*srgb(ex['emit'][0]), 1); b.inputs['Emission Strength'].default_value = ex['emit'][1]
    if 'alpha' in ex:
        b.inputs['Alpha'].default_value = ex['alpha']
        for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
            try: setattr(m, attr, val)
            except Exception: pass
    if 'coat' in ex:
        try: b.inputs['Coat Weight'].default_value = ex['coat']; b.inputs['Coat Roughness'].default_value = .05
        except Exception: pass
    if ex.get('vcol') or ex.get('vcol_emit'):
        cn = nt.nodes.new('ShaderNodeVertexColor'); cn.layer_name = 'Col'
        if ex.get('vcol'): nt.links.new(cn.outputs['Color'], b.inputs['Base Color'])
        else:
            nt.links.new(cn.outputs['Color'], b.inputs['Emission Color']); b.inputs['Emission Strength'].default_value = ex['vcol_emit']
            b.inputs['Alpha'].default_value = .75
            for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
                try: setattr(m, attr, val)
                except Exception: pass
    m.diffuse_color = (*srgb(hexcol), 1)
    _MATS[name] = m
    return m

# ══════════════════════ mesh builder: collect parts → one object per prop ══════════════════════
class Builder:
    """Accumulates bmesh parts (with transform + material) and emits one mesh object.
    Sharp edges are marked by face angle so bevelled wood stays crisp while snow stays soft."""
    def __init__(self): self.V, self.F, self.M, self.S, self.C = [], [], [], [], []
    def add(self, bm, material, mtx=None, smooth=True, color=None):
        mtx = mtx or Matrix(); bm.verts.index_update(); bm.verts.ensure_lookup_table(); base = len(self.V)  # indices go stale after bevel/ops
        for v in bm.verts: self.V.append(tuple(mtx @ v.co))
        for f in bm.faces:
            self.F.append([base + v.index for v in f.verts]); self.M.append(material); self.S.append(smooth)
        self.C += [color] * len(bm.verts)
        bm.free(); return self
    def add_arrays(self, V, F, material, smooth=True, colors=None):
        base = len(self.V); self.V += [tuple(v) for v in V]
        for f in F: self.F.append([base + i for i in f]); self.M.append(material); self.S.append(smooth)
        self.C += list(colors) if colors is not None else [None] * len(V)
        return self
    def build(self, name, sharp_deg=38, collection=None):
        me = bpy.data.meshes.new(name); me.from_pydata(self.V, [], self.F); me.validate(clean_customdata=False); me.update()
        names = list(dict.fromkeys(self.M))
        for n in names: me.materials.append(mat(n))
        me.polygons.foreach_set('material_index', [names.index(n) for n in self.M])
        me.polygons.foreach_set('use_smooth', self.S)
        if any(c is not None for c in self.C):
            ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
            ca.data.foreach_set('color', np.array([(*(c or (1, 1, 1)), 1) for c in self.C], dtype=np.float32).ravel())
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        lim = math.radians(sharp_deg)
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0) > lim: e.smooth = False
        bm.to_mesh(me); bm.free(); me.update()
        ob = bpy.data.objects.new(name, me); (collection or bpy.context.scene.collection).objects.link(ob)
        return ob

def M(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    s = scale if isinstance(scale, (tuple, list)) else (scale,) * 3
    return Matrix.Translation(loc) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Diagonal((*s, 1))

# ── primitives (bmesh) ──
def rbox(sx, sy, sz, bevel=.04, seg=1):  # 1 = chamfer (cheap); pass 2-4 for hero/soft pieces
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    b = min(bevel, sx / 2.05, sy / 2.05, sz / 2.05)
    if b > 1e-4: bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=b, segments=seg, profile=.5, affect='EDGES', clamp_overlap=True)
    return bm
def cyl(r1, r2, h, seg=12, bevel=0., bseg=2):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=h)
    if bevel > 0:
        rim = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6 and abs(abs(e.verts[0].co.z) - h / 2) < 1e-6]
        bmesh.ops.bevel(bm, geom=rim, offset=bevel, segments=bseg, profile=.5, affect='EDGES', clamp_overlap=True)
    return bm
def sphere(r, u=16, v=10):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r); return bm
def ico(r, sub=2):
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r); return bm
def torus(R, r, seg=24, rseg=8, arc=2 * math.pi):
    V, F = [], []
    closed = abs(arc - 2 * math.pi) < 1e-6; n = seg if closed else seg + 1
    for i in range(n):
        a = arc * i / seg
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            V.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(seg):
        for j in range(rseg):
            a, b = i * rseg + j, ((i + 1) % n) * rseg + j
            F.append((a, b, ((i + 1) % n) * rseg + (j + 1) % rseg, i * rseg + (j + 1) % rseg))
    return from_arrays(V, F)
def from_arrays(V, F):
    bm = bmesh.new(); vs = [bm.verts.new(v) for v in V]
    for f in F:
        try: bm.faces.new([vs[i] for i in f])
        except ValueError: pass
    return bm
def tube(points, r, seg=6, caps=True):
    """Polyline tube (ropes, cables, string lights, twigs)."""
    P = [Vector(p) for p in points]; V, F = [], []
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        a = t.orthogonal().normalized(); b = t.cross(a)
        rr = r(i / (len(P) - 1)) if callable(r) else r
        for j in range(seg):
            ang = 2 * math.pi * j / seg; V.append(tuple(p + (a * math.cos(ang) + b * math.sin(ang)) * rr))
    for i in range(len(P) - 1):
        for j in range(seg): F.append((i * seg + j, (i + 1) * seg + j, (i + 1) * seg + (j + 1) % seg, i * seg + (j + 1) % seg))
    if caps: F.append(tuple(range(seg))[::-1]); F.append(tuple((len(P) - 1) * seg + j for j in range(seg)))
    return from_arrays(V, F)
def catenary(a, b, sag, n=12):
    a, b = Vector(a), Vector(b)
    return [a.lerp(b, i / n) - Vector((0, 0, sag * 4 * (i / n) * (1 - i / n))) for i in range(n + 1)]

# ══════════════════════ SDF → mesh (organic snow, rocks, snowmen) ══════════════════════
L = lambda *a: np.sqrt(sum(v * v for v in a))
def sd_ell(x, y, z, rx, ry, rz):
    k0 = L(x / rx, y / ry, z / rz); k1 = np.maximum(L(x / rx**2, y / ry**2, z / rz**2), 1e-12)
    return np.where(k0 < 1e-9, -min(rx, ry, rz), k0 * (k0 - 1) / k1)
def sd_box(x, y, z, bx, by, bz, r=0.):
    qx, qy, qz = np.abs(x) - bx + r, np.abs(y) - by + r, np.abs(z) - bz + r
    return L(np.maximum(qx, 0), np.maximum(qy, 0), np.maximum(qz, 0)) + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0) - r
def smin(a, b, k): h = np.maximum(k - np.abs(a - b), 0) / k; return np.minimum(a, b) - h * h * k * .25
def smax(a, b, k): return -smin(-a, -b, k)
def sstep(a, b, x): t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def vnoise(x, y, z, scale=1., seed=0):
    """Smooth value noise (numpy, deterministic) for organic bumps."""
    rng = np.random.default_rng(seed); g = rng.random((17, 17, 17))
    p = np.stack([x, y, z], -1) * scale; i = np.floor(p).astype(int); f = p - i; f = f * f * (3 - 2 * f)
    def G(dx, dy, dz): return g[(i[..., 0] + dx) % 17, (i[..., 1] + dy) % 17, (i[..., 2] + dz) % 17]
    lx = lambda a, b: a + (b - a) * f[..., 0]
    return 2 * (lx(G(0, 0, 0), G(1, 0, 0)) * (1 - f[..., 1]) * (1 - f[..., 2]) + lx(G(0, 1, 0), G(1, 1, 0)) * f[..., 1] * (1 - f[..., 2])
                + lx(G(0, 0, 1), G(1, 0, 1)) * (1 - f[..., 1]) * f[..., 2] + lx(G(0, 1, 1), G(1, 1, 1)) * f[..., 1] * f[..., 2]) - 1

def grad(f, x, y, z, e=1e-3):
    g = np.stack([f(x + e, y, z) - f(x - e, y, z), f(x, y + e, z) - f(x, y - e, z), f(x, y, z + e) - f(x, y, z - e)], -1)
    return g / np.maximum(np.linalg.norm(g, axis=-1, keepdims=True), 1e-12)
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
    act = cnt > 0; idx = -np.ones(cnt.shape, int); idx[act] = np.arange(act.sum())
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
def project(f, P, it=4):
    P = P.copy()
    for _ in range(it):
        d = f(P[:, 0], P[:, 1], P[:, 2]); P -= d[:, None] * grad(f, P[:, 0], P[:, 1], P[:, 2])
    return P
_SDF_CACHE = {}
def sdf_bm(f, lo, hi, h, faces, key=None):
    """SDF → surface nets → Quadriflow quads (symmetric when possible) → bmesh. Cached per key."""
    if key and key in _SDF_CACHE:
        bm = bmesh.new(); bm.from_mesh(_SDF_CACHE[key]); return bm
    V, F = surface_nets(f, lo, hi, h); V = project(f, V)
    me = bpy.data.meshes.new('sdf_tmp'); me.from_pydata(V.tolist(), [], F.tolist()); me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=h * .05)
    bmesh.ops.triangulate(bm, faces=[x for x in bm.faces if len(x.verts) > 4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('sdf_tmp', me); bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.view_layer.objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    def qf(sym):
        try: bpy.ops.object.quadriflow_remesh(target_faces=faces, use_mesh_symmetry=sym, use_preserve_sharp=False)
        except Exception: pass
        return abs(len(ob.data.polygons) - faces) < faces * .6
    ok = not faces or qf(False)
    if not ok:  # non-manifold input → voxel remesh makes it watertight, then retry
        ob.data.remesh_voxel_size = h; bpy.ops.object.voxel_remesh(); ok = qf(False)
    if not ok:  # last resort: plain collapse decimation to the face budget
        mod = ob.modifiers.new('d', 'DECIMATE'); mod.ratio = min(1, faces / max(1, len(ob.data.polygons))); bpy.ops.object.modifier_apply(modifier='d')
    me = ob.data
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    me.vertices.foreach_set('co', project(f, co.reshape(-1, 3)).ravel()); me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bpy.data.objects.remove(ob)
    if key: _SDF_CACHE[key] = me
    else: bpy.data.meshes.remove(me)
    return bm

# ══════════════════════ scene helpers ══════════════════════
def collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in (parent or bpy.context.scene.collection).children: (parent or bpy.context.scene.collection).children.link(c)
    return c
def instance(proto, name, loc, rot_z=0., scale=1., coll=None):
    """Linked duplicate: shares mesh data → the GLB stores the geometry once."""
    ob = bpy.data.objects.new(name, proto.data)
    ob.location = loc; ob.rotation_euler = (0, 0, rot_z); ob.scale = (scale,) * 3 if not isinstance(scale, tuple) else scale
    for k in proto.keys(): ob[k] = proto[k]
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob
def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True); _MATS.clear(); _SDF_CACHE.clear()
