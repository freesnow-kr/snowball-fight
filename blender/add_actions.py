"""기존 펭귄 .blend 에 신규 동작(build_penguin.NEW_CLIPS)만 추가하고 GLB 를 다시 내보낸다. 메시·뼈·기존 9개 동작은 그대로.

Run:  blender -b blender/penguin_blue.blend --python blender/add_actions.py [-- --no-render]
- 원본을 blender/penguin_blue.backup.blend 로 먼저 복사(이미 있으면 덮지 않음)
- 같은 이름 동작이 있으면 지우고 다시 만듦 → 여러 번 돌려도 결과 같음
- 기존 동작의 키프레임이 한 개라도 바뀌면 중단
- 신규 동작: 날개 관통·목·발 + 몸 전체 최저 높이(땅 파묻힘)·자세 바운딩 박스(게임 충돌·명중 판정용) → report.json 'new_clips'
"""
import bpy, sys, os, json, shutil, hashlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.argv.append('--no-main')
import build_penguin as bp

def keyhash(act):
    h = hashlib.sha1()
    for fc in sorted(bp_fcurves(act), key=lambda f: (f.data_path, f.array_index)):
        h.update(f'{fc.data_path}{fc.array_index}'.encode())
        for k in fc.keyframe_points: h.update(np.array([*k.co, *k.handle_left, *k.handle_right], 'f8').tobytes())
    return h.hexdigest()
def bp_fcurves(act):  # Blender 4.4+ 슬롯 액션: 레이어 → 스트립 → 채널백
    if getattr(act, 'layers', None):
        return [fc for L in act.layers for s in L.strips for cb in s.channelbags for fc in cb.fcurves]
    return list(act.fcurves)

def main():
    src = bpy.data.filepath; bak = os.path.join(HERE, 'penguin_blue.backup.blend')
    if not os.path.exists(bak): shutil.copy2(src, bak); bp.log('backup →', bak)
    arm = bpy.data.objects['penguin_blue']
    parts = {o.name: o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm}
    old = {a.name: keyhash(a) for a in bpy.data.actions if a.name not in bp.NEW_CLIPS}
    assert len(old) == 9, f'기존 동작 {sorted(old)}'
    for name in bp.NEW_CLIPS:  # 다시 돌릴 때: 예전 신규 동작·NLA 트랙 지움
        for tr in [t for t in arm.animation_data.nla_tracks if t.name == name]: arm.animation_data.nla_tracks.remove(tr)
        if name in bpy.data.actions: bpy.data.actions.remove(bpy.data.actions[name])
    actions = bp.animate(arm, {n: bp.CLIPS[n] for n in bp.NEW_CLIPS})
    bp.log('added', ', '.join(actions))
    changed = [n for n, h in old.items() if keyhash(bpy.data.actions[n]) != h]
    assert not changed, f'기존 동작이 바뀜: {changed}'
    rep = json.load(open(os.path.join(HERE, 'report.json')))
    pen = bp.penetration(arm, parts, actions)
    # 몸 전체(모든 메시) 최저 높이·바운딩 박스. 게임 단위(2m 키)로도 기록
    bp.use_action(arm, None); bpy.context.scene.frame_set(0)
    rest = np.concatenate([bp.evaluated_t(o) for o in parts.values()]); k = 2.0 / (rest[:, 1].max() - rest[:, 1].min())
    for name, (act, dur) in actions.items():
        bp.use_action(arm, act); lo, hi = np.full(3, 9.), np.full(3, -9.)
        for f in range(int(round(dur * bp.FPS)) + 1):
            bpy.context.scene.frame_set(f)
            P = np.concatenate([bp.evaluated_t(o) for o in parts.values()]); lo = np.minimum(lo, P.min(0)); hi = np.maximum(hi, P.max(0))
        c = pen['clips'][name]; c['min_body_y'] = round(float(lo[1]), 4)
        c['bbox_game_m'] = {'min': [round(float(v * k), 2) for v in lo], 'max': [round(float(v * k), 2) for v in hi]}
        c['ok'] = bool(c['ok'] and lo[1] > -.02)
        bp.log(f'  {name:17s} body y {lo[1]:+.3f}  bbox(game m) {c["bbox_game_m"]}')
    bp.use_action(arm, None)
    for tr in arm.animation_data.nla_tracks: tr.mute = False
    rep['new_clips'] = pen['clips']
    if '--no-render' not in sys.argv:
        bp.COLL = arm.users_collection[0]; cam = bp.setup_render()
        for name, t in (('Slap', .2), ('Slap', .45), ('SlapHit', .14), ('BellySlide_Start', .45), ('BellySlide_Loop', .25), ('BellySlide_End', .3), ('BellySlide_End', .65)):
            act, dur = actions[name]; bp.use_action(arm, act); bpy.context.scene.frame_set(int(round(t * dur * bp.FPS)))
            bp.shoot(cam, os.path.join(bp.RENDERS, f'pose_{name}_{int(t * 100):02d}.png'), (.8, .25, 1), dist=5, res=(420, 520))
        act, dur = actions['BellySlide_Loop']; bp.use_action(arm, act); bpy.context.scene.frame_set(0)
        bp.shoot(cam, os.path.join(bp.RENDERS, 'pose_BellySlide_Loop_side.png'), (1, .05, 0), dist=5, target=(0, .5, 0), res=(560, 420))
        bp.shoot(cam, os.path.join(bp.RENDERS, 'pose_BellySlide_Loop_front.png'), (0, .15, 1), dist=5, target=(0, .5, 0), res=(560, 420))
        bp.use_action(arm, None)
        for tr in arm.animation_data.nla_tracks: tr.mute = False
        for o in [o for o in bpy.data.objects if o.name.startswith('render_') or o.type in ('LIGHT', 'CAMERA')]: bpy.data.objects.remove(o)
        bpy.context.scene.frame_set(0)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, 'penguin_blue.blend'))
    rep['glb_bytes'] = bp.export(bp.GAME_GLB)
    json.dump(rep, open(os.path.join(HERE, 'report.json'), 'w'), indent=2, ensure_ascii=False)
    bp.log('done', rep['glb_bytes'], 'bytes →', bp.GAME_GLB)

main()
