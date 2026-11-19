"""Blender preview renders (EEVEE, 1920×1080). Render-only lights/sky never go into the GLB."""
import bpy, math, os
from mathutils import Vector
from common import ROOT, srgb, collection, instance, Builder, rbox, M, log

def setup(kind='day', res=(1920, 1080)):
    sc = bpy.context.scene; sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    ee = sc.eevee
    for attr, val in (('use_shadows', True), ('use_raytracing', True), ('shadow_ray_count', 2), ('shadow_step_count', 8), ('taa_render_samples', 32), ('shadow_pool_size', '1024')):
        try: setattr(ee, attr, val)
        except Exception: pass
    sc.view_settings.view_transform = 'AgX'
    try: sc.view_settings.look = 'AgX - Punchy'
    except Exception: pass
    sc.view_settings.exposure = .75 if kind == 'day' else .35
    rc = collection('RENDER_ONLY')
    if bpy.data.collections.get('PROTOTYPES'): bpy.data.collections['PROTOTYPES'].hide_render = True  # originals sit at the origin
    for o in list(rc.objects): bpy.data.objects.remove(o)
    w = bpy.data.worlds.get('sky') or bpy.data.worlds.new('sky'); sc.world = w
    try: w.use_nodes = True
    except Exception: pass
    nt = w.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld'); bg = nt.nodes.new('ShaderNodeBackground')
    tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ'); ramp = nt.nodes.new('ShaderNodeValToRGB')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0]); nt.links.new(sep.outputs['Z'], ramp.inputs[0])
    e = ramp.color_ramp.elements
    if kind == 'day':
        e[0].position, e[1].position = .0, .32  # Z of the view direction: 0 = horizon
        e[0].color = (*srgb('#e6f2ff'), 1); e[1].color = (*srgb('#5aa2e6'), 1); strength = 1.0
    else:
        e[0].position, e[1].position = .0, .4
        e[0].color = (*srgb('#3a3f7a'), 1); e[1].color = (*srgb('#0b1030'), 1); strength = .55
        stars = nt.nodes.new('ShaderNodeTexVoronoi'); stars.inputs['Scale'].default_value = 420
        cmp = nt.nodes.new('ShaderNodeMath'); cmp.operation = 'LESS_THAN'; cmp.inputs[1].default_value = .035
        nt.links.new(tc.outputs['Generated'], stars.inputs['Vector']); nt.links.new(stars.outputs['Distance'], cmp.inputs[0])
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
        nt.links.new(cmp.outputs[0], mix.inputs['Factor']); nt.links.new(ramp.outputs['Color'], mix.inputs['A'])
        mix.inputs['B'].default_value = (3, 3, 3.5, 1); nt.links.new(mix.outputs['Result'], bg.inputs['Color'])
    if kind == 'day': nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = strength; nt.links.new(bg.outputs[0], out.inputs[0])
    sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 3.6 if kind == 'day' else .5; sun.angle = math.radians(6)
    sun.color = srgb('#fff1dc') if kind == 'day' else srgb('#9fb3ff')
    so = bpy.data.objects.new('sun', sun); rc.objects.link(so); so.rotation_euler = (math.radians(50), 0, math.radians(35))
    fill = bpy.data.lights.new('fill', 'SUN'); fill.energy = .8 if kind == 'day' else .25; fill.color = srgb('#cfe2ff'); fill.angle = math.radians(30)
    fo = bpy.data.objects.new('fill', fill); rc.objects.link(fo); fo.rotation_euler = (math.radians(60), 0, math.radians(215))
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); rc.objects.link(cam); sc.camera = cam
    cam.data.clip_end = 600
    return rc

def point_light(rc, loc, energy=300, color='#ffc46b', radius=.3):
    ld = bpy.data.lights.new('pt', 'POINT'); ld.energy = energy; ld.color = srgb(color); ld.shadow_soft_size = radius
    o = bpy.data.objects.new('pt', ld); rc.objects.link(o); o.location = loc
    return o

def shot(path, loc, target, lens=35):
    sc = bpy.context.scene; cam = sc.camera
    cam.location = Vector(loc); cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); cam.data.lens = lens
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); log('render', os.path.relpath(path, ROOT))

def props_sheet(props):
    """Lay every prop out on a snow field and render overview + close-ups."""
    rc = setup('day')
    g = Builder().add(rbox(80, 60, .2, .1), 'snow', M((0, 8, -.1))).build('ground', collection=rc)
    order = [k for k in props if k not in ('aurora',)]
    rows = [['wooden_cabin', 'small_cabin', 'night_lodge', 'ski_lift_station', 'treehouse_tree'],
            ['pine_tree_01', 'pine_tree_02', 'pine_tree_03', 'pine_tree_04', 'pine_tree_far', 'ski_lift_tower', 'floodlight_tower', 'frozen_waterfall'],
            ['snow_wall_low', 'snow_wall_high', 'snow_pile', 'snowman', 'rock_01', 'rock_02', 'jump_ramp', 'ice_arch', 'ice_pillar', 'ice_block'],
            ['fence_wood', 'fence_red', 'bench', 'snowboard_rack', 'lantern_post', 'signpost', 'banner_blue', 'flag_red', 'gate_red', 'gate_blue', 'arch_gate', 'safety_net', 'lamp_post', 'tree_stump']]
    spacing = [11, 7, 4.6, 3.4]; ys = [22, 10, 1, -6]
    for r, row in enumerate(rows):
        for i, k in enumerate(row):
            if k in props: instance(props[k], 'sheet_' + k, ((i - (len(row) - 1) / 2) * spacing[r], ys[r], 0), 0, 1, rc)
    ch = props.get('ski_lift_chair')
    if ch: instance(ch, 'sheet_chair', ((-3.5 + 4) * 7, 10, 3.0), 0, 1, rc)
    out = os.path.join(ROOT, 'renders', 'props')
    shot(os.path.join(out, 'props_overview.png'), (0, -38, 26), (0, 8, 2), 30)
    shot(os.path.join(out, 'props_cabin_closeup.png'), (-13, 7, 4.5), (-22, 22, 3.2), 40)
    shot(os.path.join(out, 'props_trees.png'), (0, -8, 4.5), (0, 10, 3.6), 32)
    shot(os.path.join(out, 'props_small.png'), (0, -16, 3.2), (0, -6, .9), 40)
