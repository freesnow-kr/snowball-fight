"""metadata/*.json → ../../maps_glb.js (game data module shared by server.ts and index.html through maps.js).

Run (plain python, no Blender):  python3 SLOPE_SNOWFIGHT_MAPS/scripts/export_game_data.py
Per map: walkable heightfield (101×101, cm, Int16 base64), obstacles in the maps.js format
(cylinders: x,z,y,body,ball,top · rotated boxes: x,z,y,hw,hd,rot,top), team spawns, sky/env, ice zone.
"""
import base64, json, os, struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(ROOT), 'maps_glb.js')
MAPS = [('base_camp', '베이스 캠프', '🏕️'), ('slope_field', '슬로프 필드', '🎿'), ('ice_lake', '아이스 레이크', '❄️'),
        ('forest_village', '포레스트 빌리지', '🏡'), ('night_resort', '나이트 리조트', '🌙')]
r2 = lambda v: round(v, 2)
# 점프로 넘을 수 있는 낮은 장애물(발이 꼭대기보다 높으면 통과). 울타리는 경계라서, 높은 벽·오두막·나무·절벽·점프대는 늘 막음
HOP = {'snow_wall_low', 'snow_pile', 'bench', 'tree_stump'}
HOP_MAX = 1.25  # 점프 최고 높이 1.33m 보다 낮아야 넘을 수 있음

def obstacles(meta):
    out = []
    for o in meta['objects']:
        c = o.get('collider')
        if not o.get('collision') or not c: continue
        kind = o['prop']
        if c['shape'] == 'box':
            x, y, z = c['center']; w, h, d = c['size']
            out.append({'kind': kind, 'x': r2(x), 'z': r2(z), 'y': r2(y), 'hw': r2(w / 2), 'hd': r2(d / 2), 'rot': round(c['rotation_y'], 4), 'top': r2(h), 'ball': .1, **({'hop': 1} if kind in HOP and h <= HOP_MAX else {})})
        else:
            for cy in c['cylinders']:
                out.append({'kind': kind, 'x': r2(cy['x']), 'z': r2(cy['z']), 'y': r2(cy['y']), 'body': r2(cy['body']), 'ball': r2(cy['ball']), 'top': r2(cy['top']), **({'hop': 1} if kind in HOP and cy['top'] <= HOP_MAX else {})})
    return out

def main():
    maps = []
    for mid, name, emoji in MAPS:
        meta = json.load(open(os.path.join(ROOT, 'metadata', f'{mid}.json')))
        H = meta['terrain']['heightfield']['heights']  # H[r][c] at x = -50 + c, z = -50 + r
        raw = b''.join(struct.pack('<h', max(-32768, min(32767, round(v * 100)))) for row in H for v in row)
        env = meta['environment']
        lights = env.get('lights', [])  # 화면이 고정(조명탑 스포트)·순환(가로등·산장 중 가까운 곳) 조명으로 나눠 씀
        m = {'id': mid, 'name': name, 'emoji': emoji, 'glb': f'/assets/maps/{mid}.glb', 'n': len(H),
             'heights': base64.b64encode(raw).decode(), 'spawns': [[[r2(p[0]), r2(p[2])] for p in meta['spawns'][t]] for t in ('pink', 'blue')],
             'sky': [env['background_horizon'] if env['preset'] == 'night' else env['background_top'], env['fog']['color']], 'fog': [env['fog']['near'], env['fog']['far']],
             'env': {'preset': env['preset'], 'hemisphere': env['hemisphere'], 'sun': env.get('sun') or env.get('moon'), 'lights': lights},
             'obstacles': obstacles(meta)}
        if 'ice_zone' in meta:
            z = meta['ice_zone']; m['ice'] = {'x': z['center'][0], 'z': z['center'][2], 'rx': z['radius_x'], 'rz': z['radius_z']}
        maps.append(m)
        print(f'{mid:15s} obstacles {len(m["obstacles"]):3d}  spawns {[len(s) for s in m["spawns"]]}  heights {len(raw)} B')
    with open(OUT, 'w') as f:
        f.write('// 생성 파일 — SLOPE_SNOWFIGHT_MAPS/scripts/export_game_data.py 가 Blender 맵 메타데이터로 만든다. 손으로 고치지 말 것.\n')
        f.write('// 맵마다: 걸을 수 있는 높이(101×101, cm Int16 base64), 장애물(maps.js 형식), 팀별 스폰, 하늘·조명\n')
        f.write('export const GLB_MAPS = ' + json.dumps(maps, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')

main()
