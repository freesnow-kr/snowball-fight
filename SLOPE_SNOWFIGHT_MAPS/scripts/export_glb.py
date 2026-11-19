"""glTF 2.0 (GLB) export helpers. Blender Z-up → glTF Y-up is done by the exporter (export_yup)."""
import bpy, os

def _opts(path):
    return dict(filepath=path, export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                export_cameras=False, export_lights=False, export_extras=True, export_animations=False,
                export_materials='EXPORT', export_vertex_color='MATERIAL')

def export_objects(objects, path):
    """Export exactly these objects (and their children). Lights/cameras never included:
    the game sets its own lighting (see metadata environment presets)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keep = set()
    def walk(o):
        keep.add(o)
        for c in o.children: walk(c)
    for o in objects: walk(o)
    for o in bpy.context.view_layer.objects:
        try: o.select_set(o in keep)
        except RuntimeError: pass  # object hidden from this view layer
    opts = _opts(path)
    try: bpy.ops.export_scene.gltf(**opts)
    except TypeError:  # option not supported by this Blender version → drop the optional ones
        for k in ('export_vertex_color', 'export_materials'): opts.pop(k, None)
        bpy.ops.export_scene.gltf(**opts)
    return os.path.getsize(path)
