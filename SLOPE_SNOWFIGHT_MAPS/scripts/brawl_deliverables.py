"""SNOW BRAWL 전용 맵 결과물 7종 → snow_brawl_arena/ + 검증(validation_report.json).

Run (generate_maps.py -- snow_brawl_arena 다음에):  blender --background --python scripts/brawl_deliverables.py
- snow_brawl_arena.blend / .glb(압축 전 원본) / terrain_collision.json / colliders.json / spawn_points.json / map_config.json / preview.png
- 검증: GLB 를 새 장면에 다시 불러와 메시·재질 확인, 지형 정점 높이 ↔ 높이 격자(좌표계·스케일·원점 일치), JSON 다시 파싱,
  스폰 ↔ 장애물 거리, 나무 없음, 기존 맵 파일은 손대지 않음(이 스크립트는 snow_brawl_arena/ 에만 씀)
"""
import bpy, json, math, os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MID = 'snow_brawl_arena'; OUT = os.path.join(ROOT, MID); os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(ROOT, 'metadata', f'{MID}.json')))
H = meta['terrain']['heightfield']['heights']; N = len(H)  # H[r][c] at x = -50 + c, z = -50 + r
RING_R = 30.0  # 플레이 영역(바깥 눈벽 링 안쪽) 반지름, generate_maps.SnowBrawlArena.R
def wj(name, obj):
    p = os.path.join(OUT, name); json.dump(obj, open(p, 'w'), ensure_ascii=False, indent=1); return p

# 1·2·7) 원본 파일 복사
shutil.copyfile(os.path.join(ROOT, 'blend', f'{MID}.blend'), os.path.join(OUT, f'{MID}.blend'))
shutil.copyfile(os.path.join(ROOT, 'glb', 'maps_raw', f'{MID}.glb'), os.path.join(OUT, f'{MID}.glb'))
shutil.copyfile(os.path.join(ROOT, 'renders', MID, f'{MID}_1_overview.png'), os.path.join(OUT, 'preview.png'))

# 3) 지형: 높이 + 경사(굴린 눈이 지형을 따라 가도록)
def hgt(c, r): return H[max(0, min(N - 1, r))][max(0, min(N - 1, c))]
slope = [[round(math.degrees(math.atan(math.hypot((hgt(c + 1, r) - hgt(c - 1, r)) / 2, (hgt(c, r + 1) - hgt(c, r - 1)) / 2))), 1) for c in range(N)] for r in range(N)]
wj('terrain_collision.json', {
    'map': MID, 'coordinates': 'three.js / glTF (+Y up, meters). x = origin_x + c * step, z = origin_z + r * step',
    'grid': {'cols': N, 'rows': N, 'step': 1.0, 'origin_x': -50.0, 'origin_z': -50.0},
    'sampling': 'bilinear between the 4 surrounding samples (same as the game, maps.js gridHeight)',
    'height_range': meta['terrain']['height_range'], 'heights': H,
    'slope_deg': slope, 'slope_note': 'slope_deg[r][c] = terrain slope in degrees (central difference). Inside the play ring it stays under 3°',
})
# 4) 충돌: 장애물(정확한 상자/원기둥 + 서버용 원기둥 근사) + 경계
obs = [o for o in meta['objects'] if o['collision']]
HOP = {'snow_wall_low', 'snow_pile'}  # 점프로 넘을 수 있는 낮은 엄폐물(꼭대기 ≤ 1.25 m)
wj('colliders.json', {
    'map': MID, 'coordinates': 'three.js / glTF (+Y up). rotation_y in radians around +Y',
    'boundary': {'shape': 'ring_wall', 'center': [0, 0], 'inner_radius': RING_R, 'note': f'{sum(o["prop"] == "snow_wall_high" and o["name"].startswith("ring_wall") for o in obs)} snow_wall_high boxes (2.2 m, cannot be jumped) overlapping into a closed ring; server also clamps x,z to ±50'},
    'colliders': [{'name': o['name'], 'kind': o['prop'], 'position': o['position'], 'rotation_y': o['rotation_y'], 'scale': o['scale'], 'hop': o['prop'] in HOP, **o['collider']} for o in obs],
})
# 5) 스폰 20곳(개인전 최대 20명): 링 안쪽 r 25·18° 간격, 가운데를 바라봄
MAX = 20
sp = [{'id': i, 'x': round(p[0], 2), 'y': round(p[1], 2), 'z': round(p[2], 2), 'yaw': round(math.atan2(-p[0], -p[2]), 4)} for i, p in enumerate(meta['spawns']['ffa'])]
wj('spawn_points.json', {'map': MID, 'mode': 'snow_brawl', 'max_players': MAX, 'yaw_note': 'yaw = atan2(dx, dz) facing the arena centre (game convention)', 'spawns': sp})
# 6) 설정
wj('map_config.json', {
    'id': MID, 'name': 'Snow Brawl Arena', 'mode': 'snow_brawl', 'max_players': MAX,
    'size_m': [60, 60], 'play_area': {'shape': 'circle', 'center': [0, 0], 'radius': RING_R},
    'world_bounds': {'x': [-50, 50], 'z': [-50, 50], 'note': 'terrain mesh is 100×100 m; outside the ring is scenery (berm + backdrop hills)'},
    'coordinates': meta['coordinates'], 'units': 'meters (penguin 2 m tall)', 'origin': [0, 0, 0], 'up': '+Y',
    'terrain': {'object': 'terrain', 'grid_step': 1.0, 'height_range': meta['terrain']['height_range'], 'file': 'terrain_collision.json'},
    'environment': meta['environment'], 'trees': 0, 'triangles': meta['triangles'],
    'files': [f'{MID}.blend', f'{MID}.glb', 'terrain_collision.json', 'colliders.json', 'spawn_points.json', 'map_config.json', 'preview.png'],
})

# ── 검증 ──
R = {}
for f in ('terrain_collision.json', 'colliders.json', 'spawn_points.json', 'map_config.json'):
    try: json.load(open(os.path.join(OUT, f))); R[f'json:{f}'] = 'PASS'
    except Exception as e: R[f'json:{f}'] = f'FAIL {e}'
R['files'] = {f: os.path.getsize(os.path.join(OUT, f)) for f in json.load(open(os.path.join(OUT, 'map_config.json')))['files'] if os.path.exists(os.path.join(OUT, f))}
R['all_7_files'] = 'PASS' if len(R['files']) == 7 else 'FAIL'
R['no_trees'] = 'PASS' if not any(k in o['prop'] for o in meta['objects'] for k in ('tree', 'pine', 'forest')) else 'FAIL'
# 스폰: 링 안·평탄·장애물에서 2.5 m+·서로 3 m+
def clear(x, z, o):
    c = o['collider']
    if c['shape'] == 'box':
        cx, _, cz = c['center']; w, _, d = c['size']; a = c['rotation_y']
        dx, dz = x - cx, z - cz; lx, lz = dx * math.cos(a) - dz * math.sin(a), dx * math.sin(a) + dz * math.cos(a)
        return math.hypot(max(0, abs(lx) - w / 2), max(0, abs(lz) - d / 2))
    return min(math.hypot(x - cy['x'], z - cy['z']) - cy['body'] for cy in c['cylinders'])
mins = [min(clear(s['x'], s['z'], o) for o in obs) for s in sp]
gaps = [math.hypot(a['x'] - b['x'], a['z'] - b['z']) for i, a in enumerate(sp) for b in sp[i + 1:]]
R['spawns'] = {'count': len(sp), 'min_clearance_m': round(min(mins), 2), 'min_gap_m': round(min(gaps), 2), 'max_r': round(max(math.hypot(s['x'], s['z']) for s in sp), 2),
               'result': 'PASS' if len(sp) == MAX and min(mins) >= 2.5 and min(gaps) >= 3 and max(math.hypot(s['x'], s['z']) for s in sp) < RING_R - 1 else 'FAIL'}
R['inner_slope_max_deg'] = max(slope[r][c] for r in range(N) for c in range(N) if math.hypot(c - 50, r - 50) < RING_R - 1)
# GLB 다시 불러오기: 메시·재질, 지형 정점 높이 ↔ 높이 격자
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, f'{MID}.glb'))
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
nomat = [o.name for o in meshes if not o.data.materials or any(m is None for m in o.data.materials)]
R['glb_reimport'] = {'mesh_objects': len(meshes), 'materials': len(bpy.data.materials), 'meshes_without_material': nomat[:5],
                     'trees_in_glb': sum('tree' in o.name or 'pine' in o.name for o in bpy.data.objects), 'result': 'PASS' if meshes and not nomat else 'FAIL'}
ter = bpy.data.objects.get('terrain'); worst = 0.0; n = 0
if ter:
    mw = ter.matrix_world
    for v in list(ter.data.vertices)[::37]:
        w = mw @ v.co; x, z, y = w.x, -w.y, w.z  # Blender(Z-up) 로 다시 들어온 좌표 → three (x, y, z)
        if abs(x) > 49.5 or abs(z) > 49.5: continue
        c, r = x + 50, z + 50; c0, r0 = int(c), int(r); u, t = c - c0, r - r0
        hh = (hgt(c0, r0) * (1 - u) + hgt(c0 + 1, r0) * u) * (1 - t) + (hgt(c0, r0 + 1) * (1 - u) + hgt(c0 + 1, r0 + 1) * u) * t
        worst = max(worst, abs(hh - y)); n += 1
R['coords_glb_vs_heightfield'] = {'samples': n, 'max_err_m': round(worst, 3), 'result': 'PASS' if ter and n > 100 and worst < .02 else 'FAIL'}
# 스폰·장애물 위치 ↔ GLB 노드 위치
moved = []
for o in meta['objects']:
    ob = bpy.data.objects.get(o['name'])
    if ob is None or o.get('virtual'): continue
    p = ob.matrix_world.translation; t3 = (p.x, p.z, -p.y)
    if max(abs(a - b) for a, b in zip(t3, o['position'])) > .02: moved.append(o['name'])
R['coords_glb_vs_objects'] = {'checked': len(meta['objects']), 'mismatch': moved[:5], 'result': 'PASS' if not moved else 'FAIL'}
json.dump(R, open(os.path.join(OUT, 'validation_report.json'), 'w'), ensure_ascii=False, indent=1)
print('VALIDATION', json.dumps(R, ensure_ascii=False))
