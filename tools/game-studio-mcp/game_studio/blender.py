"""Blender automation through the real Blender executable in background mode.

The runner never trusts the working directory and never interpolates arguments
into Python source. Paths and options are written to a JSON file that the job
script reads, which removes quoting/injection problems on every platform.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import config
from .detect import detect_blender
from .util import (
    ToolError,
    expand,
    now_iso,
    read_json,
    require_path,
    run_command,
    sha256_file,
    truncate,
)

DEFAULT_TIMEOUT = int(os.environ.get("BLENDER_MCP_TIMEOUT", "900"))


def resolve_blender(explicit: str | None = None, cfg: dict | None = None) -> str | None:
    cfg = cfg or config.load_config()
    for candidate in (explicit, os.environ.get("BLENDER_EXE"), cfg.get("blender_exe")):
        if candidate:
            resolved = expand(candidate)
            if resolved and os.path.isfile(resolved):
                return resolved
    detected = detect_blender(cfg)
    if detected.get("state") in ("verified", "detected") and detected.get("executables"):
        return detected["executables"][0]["path"]
    return None


def run_blender(script: str, *, args: dict | None = None, blend_file: str | None = None,
                timeout: int = DEFAULT_TIMEOUT, blender_exe: str | None = None,
                factory: bool = True) -> dict:
    exe = resolve_blender(blender_exe)
    if not exe:
        return {
            "ok": False,
            "error": "Blender executable not found",
            "remediation": "Set BLENDER_EXE, configure studio.blender_exe, or install Blender.",
        }
    if blend_file:
        blend_file = require_path(blend_file, label="blend_file")
    workdir = tempfile.mkdtemp(prefix="game-studio-blender-")
    result_path = os.path.join(workdir, "result.json")
    args_path = os.path.join(workdir, "args.json")
    script_path = os.path.join(workdir, "job.py")
    Path(args_path).write_text(json.dumps(args or {}, default=str), encoding="utf-8")

    prefix = (
        "import json, os, sys, traceback, math, random\n"
        f"RESULT_PATH = {result_path!r}\n"
        f"ARGS_PATH = {args_path!r}\n"
        "def __emit(payload):\n"
        "    with open(RESULT_PATH, 'w', encoding='utf-8') as fh:\n"
        "        json.dump(payload, fh, default=str)\n"
        "try:\n"
        "    with open(ARGS_PATH, 'r', encoding='utf-8') as fh:\n"
        "        ARGS = json.load(fh)\n"
    )
    body = "\n".join("    " + line for line in script.splitlines())
    wrapper = (
        prefix + body + "\n"
        "    try:\n"
        "        __mcp_result\n"
        "    except NameError:\n"
        "        __mcp_result = {'ran': True}\n"
        "    __emit({'ok': True, 'result': __mcp_result})\n"
        "except Exception:\n"
        "    __emit({'ok': False, 'error': traceback.format_exc()})\n"
    )
    Path(script_path).write_text(wrapper, encoding="utf-8")

    command = [exe, "--background"]
    if blend_file:
        command.append(os.path.abspath(blend_file))
    if factory:
        command.append("--factory-startup")
    command += ["--python", script_path, "--python-exit-code", "1"]

    started = time.time()
    proc = run_command(command, timeout=timeout)
    payload: dict
    if os.path.isfile(result_path):
        try:
            payload = read_json(result_path)
        except (OSError, json.JSONDecodeError) as exc:
            payload = {"ok": False, "error": f"unreadable Blender result: {exc}"}
    else:
        payload = {"ok": False, "error": "Blender produced no result file"}
    payload.update({
        "blender": exe,
        "exit_code": proc.get("exit_code"),
        "timed_out": proc.get("timed_out", False),
        "duration_ms": int((time.time() - started) * 1000),
        "stdout_tail": truncate(proc.get("stdout", ""), 4000),
        "stderr_tail": truncate(proc.get("stderr", ""), 4000),
    })
    if proc.get("timed_out"):
        payload["ok"] = False
        payload["error"] = f"Blender timed out after {timeout}s"
    return payload


# --------------------------------------------------------------------------
# scripts
# --------------------------------------------------------------------------
INFO_SCRIPT = """
import bpy, sys, platform, os
info = {
  'version': '.'.join(str(v) for v in bpy.app.version),
  'version_string': bpy.app.version_string,
  'python': sys.version.split()[0],
  'platform': platform.platform(),
  'file': bpy.data.filepath,
  'scenes': [s.name for s in bpy.data.scenes],
  'addons_enabled': sorted(a.module for a in bpy.context.preferences.addons)[:60],
  'unit_system': bpy.context.scene.unit_settings.system,
  'unit_scale': bpy.context.scene.unit_settings.scale_length,
  'engines': [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items],
  'exporter_gltf': hasattr(bpy.ops.export_scene, 'gltf'),
  'exporter_fbx': hasattr(bpy.ops.export_scene, 'fbx'),
}
__mcp_result = info
"""

INSPECT_SCRIPT = """
import bpy, os, math
scene = bpy.context.scene
max_objects = int(ARGS.get('max_objects', 500))
objects = []
for ob in list(bpy.data.objects)[:max_objects]:
    entry = {
        'name': ob.name, 'type': ob.type,
        'parent': ob.parent.name if ob.parent else None,
        'location': [round(v, 4) for v in ob.location],
        'rotation_euler_deg': [round(math.degrees(v), 2) for v in ob.rotation_euler],
        'scale': [round(v, 4) for v in ob.scale],
        'dimensions': [round(v, 4) for v in ob.dimensions],
        'modifiers': [m.type for m in ob.modifiers],
        'materials': [ms.material.name for ms in ob.material_slots if ms.material],
        'visible': bool(ob.visible_get()),
        'collections': [c.name for c in ob.users_collection],
        'custom_properties': {k: ob[k] for k in ob.keys() if k != '_RNA_UI'},
    }
    if ob.type == 'MESH':
        me = ob.data
        entry.update({
            'vertices': len(me.vertices),
            'polygons': len(me.polygons),
            'uv_layers': [uv.name for uv in me.uv_layers],
            'shape_keys': len(me.shape_keys.key_blocks) if me.shape_keys else 0,
        })
    if ob.type == 'ARMATURE':
        entry.update({'bones': len(ob.data.bones),
                      'bone_names': [b.name for b in ob.data.bones][:80]})
    objects.append(entry)

images = [{
    'name': img.name, 'filepath': img.filepath, 'packed': bool(img.packed_file),
    'missing': (not img.packed_file) and bool(img.filepath) and not os.path.isfile(bpy.path.abspath(img.filepath)),
    'size': list(img.size),
} for img in bpy.data.images]

actions = [{
    'name': act.name, 'frame_range': [round(v, 2) for v in act.frame_range],
    'fcurves': len(act.fcurves),
} for act in bpy.data.actions]

materials = []
for mat in bpy.data.materials:
    node_types, textures = [], []
    if mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            node_types.append(n.type)
            if n.type == 'TEX_IMAGE' and n.image:
                textures.append(n.image.name)
    materials.append({'name': mat.name, 'use_nodes': mat.use_nodes,
                      'node_types': sorted(set(node_types)), 'textures': textures})

__mcp_result = {
    'file': bpy.data.filepath, 'scene': scene.name, 'frame': scene.frame_current,
    'frame_range': [scene.frame_start, scene.frame_end],
    'render_engine': scene.render.engine,
    'unit_system': scene.unit_settings.system,
    'unit_scale': scene.unit_settings.scale_length,
    'object_count': len(bpy.data.objects),
    'objects': objects, 'images': images, 'actions': actions,
    'materials': materials, 'collections': [{'name': c.name, 'objects': len(c.objects)} for c in bpy.data.collections],
}
"""

VALIDATE_SCRIPT = """
import bpy, os, math
from mathutils import Vector
issues, warnings, info = [], [], {}
scene = bpy.context.scene
max_tri = int(ARGS.get('max_triangles', 150000))
info['file'] = bpy.data.filepath
info['unit_scale'] = scene.unit_settings.scale_length
info['unit_system'] = scene.unit_settings.system
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
triangles = 0
for ob in meshes:
    me = ob.data
    me.calc_loop_triangles()
    tris = len(me.loop_triangles)
    triangles += tris
    if tris == 0:
        issues.append(f"{ob.name}: mesh has zero triangles")
    if not me.uv_layers:
        warnings.append(f"{ob.name}: no UV map")
    if any(abs(s - 1.0) > 1e-3 for s in ob.scale):
        warnings.append(f"{ob.name}: non-unit scale {[round(s, 3) for s in ob.scale]}")
    if ob.location.length > 1e-4 and ob.parent is None:
        warnings.append(f"{ob.name}: non-zero object location (pivot may be off)")
    for slot in ob.material_slots:
        if slot.material is None:
            warnings.append(f"{ob.name}: empty material slot")
    zero_area = sum(1 for p in me.polygons if p.area < 1e-9)
    if zero_area:
        warnings.append(f"{ob.name}: {zero_area} zero-area faces")
    if len(me.polygons) and all(len(p.vertices) > 4 for p in me.polygons):
        warnings.append(f"{ob.name}: n-gons only; triangulate before engine import")
info['mesh_objects'] = len(meshes)
info['triangles'] = triangles
info['armatures'] = len(armatures)
info['bones'] = sum(len(a.data.bones) for a in armatures)
info['actions'] = [a.name for a in bpy.data.actions]
info['materials'] = len(bpy.data.materials)
info['images'] = len(bpy.data.images)
if triangles > max_tri:
    warnings.append(f"triangle budget exceeded: {triangles} > {max_tri}")
missing = []
for img in bpy.data.images:
    if img.packed_file:
        continue
    if img.filepath and not os.path.isfile(bpy.path.abspath(img.filepath)):
        missing.append(img.filepath)
if missing:
    issues.append(f"missing texture files: {missing}")
for a in armatures:
    if not a.data.bones:
        issues.append(f"{a.name}: armature has no bones")
mins = [1e9] * 3
maxs = [-1e9] * 3
for ob in meshes:
    for corner in ob.bound_box:
        w = ob.matrix_world @ Vector(corner)
        for i in range(3):
            mins[i] = min(mins[i], w[i])
            maxs[i] = max(maxs[i], w[i])
if meshes:
    info['bounds_size'] = [round(maxs[i] - mins[i], 4) for i in range(3)]
    info['bounds_min'] = [round(mins[i], 4) for i in range(3)]
__mcp_result = {'issues': issues, 'warnings': warnings, 'info': info}
"""

EXPORT_SCRIPT = """
import bpy, os
out_path = ARGS['output']
fmt = ARGS['format']
selected_only = bool(ARGS.get('selected_only', False))
apply_transforms = bool(ARGS.get('apply_transforms', True))
scale = float(ARGS.get('scale', 1.0))
os.makedirs(os.path.dirname(out_path), exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
if selected_only:
    if not any(o.select_get() for o in bpy.context.scene.objects):
        raise RuntimeError('selected_only=true but nothing is selected')
else:
    for ob in bpy.context.scene.objects:
        if ob.type in ('MESH', 'ARMATURE', 'EMPTY'):
            ob.select_set(True)
if apply_transforms:
    for ob in [o for o in bpy.context.scene.objects if o.select_get() and o.type in ('MESH', 'ARMATURE')]:
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
if scale != 1.0:
    for ob in [o for o in bpy.context.scene.objects if o.select_get()]:
        ob.scale = [s * scale for s in ob.scale]
if fmt == 'glb':
    bpy.ops.export_scene.gltf(filepath=out_path, export_format='GLB', use_selection=selected_only, export_apply=True, export_yup=True)
elif fmt == 'gltf':
    bpy.ops.export_scene.gltf(filepath=out_path, export_format='GLTF_SEPARATE', use_selection=selected_only, export_apply=True, export_yup=True)
elif fmt == 'fbx':
    bpy.ops.export_scene.fbx(filepath=out_path, use_selection=selected_only, apply_scale_options='FBX_SCALE_ALL', bake_anim=True, axis_forward='-Z', axis_up='Y', path_mode='COPY', embed_textures=True)
elif fmt == 'obj':
    bpy.ops.wm.obj_export(filepath=out_path, export_selected_objects=selected_only)
elif fmt == 'stl':
    if hasattr(bpy.ops.wm, 'stl_export'):
        bpy.ops.wm.stl_export(filepath=out_path, export_selected_objects=selected_only)
    else:
        bpy.ops.export_mesh.stl(filepath=out_path, use_selection=selected_only)
elif fmt == 'usdz':
    bpy.ops.wm.usd_export(filepath=out_path, selected_objects_only=selected_only)
else:
    raise RuntimeError('unsupported format: ' + fmt)
size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
if size <= 0:
    raise RuntimeError('exporter produced no file: ' + out_path)
__mcp_result = {'output': out_path, 'format': fmt, 'bytes': size, 'exists': True}
"""

IMPORT_SCRIPT = """
import bpy, os
src = ARGS['source']
ext = os.path.splitext(src)[1].lower()
save_path = ARGS.get('save_blend')
before = set(o.name for o in bpy.data.objects)
if ext == '.fbx':
    bpy.ops.import_scene.fbx(filepath=src)
elif ext in ('.glb', '.gltf'):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == '.obj':
    bpy.ops.wm.obj_import(filepath=src)
elif ext == '.stl':
    if hasattr(bpy.ops.wm, 'stl_import'):
        bpy.ops.wm.stl_import(filepath=src)
    else:
        bpy.ops.import_mesh.stl(filepath=src)
elif ext == '.blend':
    with bpy.data.libraries.load(src, link=False) as (src_data, dst_data):
        dst_data.objects = src_data.objects
    for ob in dst_data.objects:
        if ob:
            bpy.context.scene.collection.objects.link(ob)
elif ext in ('.usd', '.usdz'):
    bpy.ops.wm.usd_import(filepath=src)
else:
    raise RuntimeError('unsupported import format: ' + ext)
new = [o.name for o in bpy.data.objects if o.name not in before]
if save_path:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)
__mcp_result = {'imported': new, 'count': len(new), 'saved': save_path or None}
"""

RENDER_SCRIPT = """
import bpy, os
scene = bpy.context.scene
scene.render.resolution_x = int(ARGS.get('width', 640))
scene.render.resolution_y = int(ARGS.get('height', 360))
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
out = ARGS['output_png']
os.makedirs(os.path.dirname(out), exist_ok=True)
scene.render.filepath = out
frame = ARGS.get('frame')
if frame is not None:
    scene.frame_set(int(frame))
if scene.camera is None:
    cams = [o for o in bpy.data.objects if o.type == 'CAMERA']
    if cams:
        scene.camera = cams[0]
    else:
        raise RuntimeError('No camera in scene')
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
preferred = [e for e in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES', 'BLENDER_WORKBENCH') if e in engines]
if preferred:
    scene.render.engine = preferred[0]
bpy.ops.render.render(write_still=True)
if not os.path.isfile(out):
    raise RuntimeError('render produced no file')
__mcp_result = {'output': out, 'bytes': os.path.getsize(out), 'engine': scene.render.engine}
"""

BUILDOUT_SCRIPT = """
import bpy, os, math, random
from mathutils import Vector

preset = ARGS.get('preset', 'jungle')
seed = int(ARGS.get('seed', 1337))
size = float(ARGS.get('size', 100.0))
segments = int(ARGS.get('segments', 64))
tree_count = int(ARGS.get('tree_count', 60))
rock_count = int(ARGS.get('rock_count', 25))
water_level = float(ARGS.get('water_level', 0.0))
save_path = ARGS.get('save_blend')
export_glb = ARGS.get('export_glb')
render_png = ARGS.get('render_png')
random.seed(seed)

PRESETS = {
    'jungle': dict(ground=(0.10, 0.30, 0.10, 1), water=(0.05, 0.30, 0.32, 1),
                   foliage=(0.06, 0.42, 0.12, 1), trunk=(0.25, 0.16, 0.07, 1),
                   rock=(0.30, 0.29, 0.26, 1), sky=(0.55, 0.75, 0.65, 1),
                   height=9.0, fog=True),
    'forest': dict(ground=(0.16, 0.28, 0.13, 1), water=(0.10, 0.28, 0.35, 1),
                   foliage=(0.14, 0.36, 0.16, 1), trunk=(0.28, 0.20, 0.12, 1),
                   rock=(0.34, 0.32, 0.29, 1), sky=(0.62, 0.74, 0.82, 1),
                   height=6.0, fog=True),
    'desert': dict(ground=(0.70, 0.55, 0.32, 1), water=(0.25, 0.45, 0.55, 1),
                   foliage=(0.35, 0.42, 0.20, 1), trunk=(0.45, 0.34, 0.20, 1),
                   rock=(0.55, 0.40, 0.28, 1), sky=(0.80, 0.72, 0.55, 1),
                   height=5.0, fog=False),
    'alpine': dict(ground=(0.55, 0.58, 0.55, 1), water=(0.15, 0.38, 0.50, 1),
                   foliage=(0.12, 0.28, 0.18, 1), trunk=(0.26, 0.20, 0.14, 1),
                   rock=(0.40, 0.41, 0.42, 1), sky=(0.55, 0.70, 0.88, 1),
                   height=14.0, fog=True),
}
if preset not in PRESETS:
    raise RuntimeError('unknown preset: ' + preset + ' (choose ' + ', '.join(PRESETS) + ')')
palette = PRESETS[preset]

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)

clear_scene()

def material(name, rgba, roughness=0.8, metallic=0.0):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = rgba
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
    mat.diffuse_color = rgba
    return mat

def value_noise(x, y, octaves=4):
    total, amplitude, frequency, norm = 0.0, 1.0, 0.08, 0.0
    for _ in range(octaves):
        xi, yi = int(math.floor(x * frequency)), int(math.floor(y * frequency))
        xf, yf = x * frequency - xi, y * frequency - yi
        def h(ix, iy):
            n = (ix * 374761393 + iy * 668265263 + seed * 144665) & 0xFFFFFFFF
            n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
            return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0
        v00, v10 = h(xi, yi), h(xi + 1, yi)
        v01, v11 = h(xi, yi + 1), h(xi + 1, yi + 1)
        sx = xf * xf * (3 - 2 * xf)
        sy = yf * yf * (3 - 2 * yf)
        value = (v00 * (1 - sx) + v10 * sx) * (1 - sy) + (v01 * (1 - sx) + v11 * sx) * sy
        total += value * amplitude
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm

# terrain
step = size / segments
verts, faces, heights = [], [], []
for iy in range(segments + 1):
    for ix in range(segments + 1):
        x = -size / 2 + ix * step
        y = -size / 2 + iy * step
        h = value_noise(x, y) * palette['height'] - palette['height'] * 0.35
        verts.append((x, y, h))
        heights.append(h)
for iy in range(segments):
    for ix in range(segments):
        a = iy * (segments + 1) + ix
        b = a + 1
        c = a + segments + 1
        d = c + 1
        faces.append((a, b, d, c))
terrain_mesh = bpy.data.meshes.new('TerrainMesh')
terrain_mesh.from_pydata(verts, [], faces)
terrain_mesh.update()
terrain = bpy.data.objects.new('Terrain', terrain_mesh)
bpy.context.scene.collection.objects.link(terrain)
terrain.data.materials.append(material('M_Terrain', palette['ground'], 0.95))
for poly in terrain.data.polygons:
    poly.use_smooth = True
terrain['game_studio_role'] = 'terrain'
terrain['game_studio_collision'] = 'mesh'
terrain['game_studio_seed'] = seed
terrain['game_studio_preset'] = preset

# optional water
if ARGS.get('include_water', True):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, water_level))
    water = bpy.context.active_object
    water.name = 'Water'
    water.data.materials.append(material('M_Water', palette['water'], 0.12, 0.0))
    water['game_studio_role'] = 'water'
    water['game_studio_collision'] = 'trigger'
    water['game_studio_note'] = 'Add engine-specific water volume/collision behavior.'

def height_at(x, y):
    gx = int((x + size / 2) / step)
    gy = int((y + size / 2) / step)
    gx = max(0, min(segments, gx))
    gy = max(0, min(segments, gy))
    return heights[gy * (segments + 1) + gx]

foliage_mat = material('M_Foliage', palette['foliage'], 0.75)
trunk_mat = material('M_Trunk', palette['trunk'], 0.9)
rock_mat = material('M_Rock', palette['rock'], 0.85)

placed = 0
attempts = 0
while placed < tree_count and attempts < tree_count * 30:
    attempts += 1
    x = random.uniform(-size * 0.45, size * 0.45)
    y = random.uniform(-size * 0.45, size * 0.45)
    z = height_at(x, y)
    if z <= water_level + 0.4:
        continue
    scale = random.uniform(0.7, 1.35)
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.22 * scale, depth=2.4 * scale,
                                        location=(x, y, z + 1.2 * scale))
    trunk = bpy.context.active_object
    trunk.name = f'Tree_{placed:03d}_Trunk'
    trunk.data.materials.append(trunk_mat)
    bpy.ops.mesh.primitive_cone_add(vertices=7, radius1=1.5 * scale, radius2=0.15 * scale,
                                    depth=3.4 * scale, location=(x, y, z + 3.3 * scale))
    crown = bpy.context.active_object
    crown.name = f'Tree_{placed:03d}_Crown'
    crown.data.materials.append(foliage_mat)
    bpy.ops.object.select_all(action='DESELECT')
    trunk.select_set(True)
    crown.select_set(True)
    bpy.context.view_layer.objects.active = trunk
    bpy.ops.object.join()
    tree = bpy.context.active_object
    tree.name = f'Tree_{placed:03d}'
    tree['game_studio_role'] = 'tree'
    tree['game_studio_collision'] = 'capsule'
    tree['game_studio_collision_radius'] = round(0.35 * scale, 3)
    tree['game_studio_collision_height'] = round(4.5 * scale, 3)
    placed += 1

rocks = 0
attempts = 0
while rocks < rock_count and attempts < rock_count * 30:
    attempts += 1
    x = random.uniform(-size * 0.45, size * 0.45)
    y = random.uniform(-size * 0.45, size * 0.45)
    z = height_at(x, y)
    if z <= water_level + 0.2:
        continue
    scale = random.uniform(0.4, 1.8)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=scale, location=(x, y, z + scale * 0.55))
    rock = bpy.context.active_object
    rock.name = f'Rock_{rocks:03d}'
    rock.scale = (random.uniform(0.8, 1.6), random.uniform(0.8, 1.6), random.uniform(0.5, 1.0))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    rock.data.materials.append(rock_mat)
    rock['game_studio_role'] = 'rock'
    rock['game_studio_collision'] = 'mesh'
    rocks += 1

# lighting and camera
bpy.ops.object.light_add(type='SUN', location=(size * 0.3, -size * 0.4, size * 0.5))
sun = bpy.context.active_object
sun.name = 'Sun'
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(52), 0, math.radians(35))

world = bpy.data.worlds.new('World') if not bpy.data.worlds else bpy.data.worlds[0]
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = palette['sky']
    bg.inputs['Strength'].default_value = 1.0

bpy.ops.object.camera_add(location=(size * 0.55, -size * 0.62, size * 0.34))
cam = bpy.context.active_object
cam.name = 'PreviewCamera'
target = Vector((0, 0, palette['height'] * 0.15))
direction = target - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam
cam.data.lens = 35

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
if palette['fog']:
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8

if save_path:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)

triangles = 0
for ob in [o for o in bpy.data.objects if o.type == 'MESH']:
    ob.data.calc_loop_triangles()
    triangles += len(ob.data.loop_triangles)
bounds_min = [1e9, 1e9, 1e9]
bounds_max = [-1e9, -1e9, -1e9]
for ob in [o for o in bpy.data.objects if o.type == 'MESH']:
    for corner in ob.bound_box:
        w = ob.matrix_world @ Vector(corner)
        for i in range(3):
            bounds_min[i] = min(bounds_min[i], w[i])
            bounds_max[i] = max(bounds_max[i], w[i])
__mcp_result = {
    'preset': preset, 'seed': seed, 'size_m': size, 'trees': placed, 'rocks': rocks,
    'triangles': triangles, 'objects': len(bpy.data.objects),
    'bounds_min': [round(v, 2) for v in bounds_min],
    'bounds_max': [round(v, 2) for v in bounds_max],
    'saved': save_path, 'water_level': water_level,
    'note': 'Procedural blockout. Replace with production art and verify engine collision before shipping.',
}
"""


# --------------------------------------------------------------------------
# tool functions
# --------------------------------------------------------------------------
def blender_info(blender_exe: str | None = None) -> dict:
    result = run_blender(INFO_SCRIPT, blender_exe=blender_exe, timeout=120)
    if result.get("ok"):
        result["result"]["configured_exe"] = result.get("blender")
    return result


def inspect_blend(blend_file: str, max_objects: int = 500) -> dict:
    return run_blender(INSPECT_SCRIPT, args={"max_objects": max_objects},
                       blend_file=blend_file, timeout=300)


def validate_blend(blend_file: str, max_triangles: int = 150_000) -> dict:
    out = run_blender(VALIDATE_SCRIPT, args={"max_triangles": max_triangles},
                      blend_file=blend_file, timeout=300)
    if out.get("ok") and isinstance(out.get("result"), dict):
        validation = out["result"]
        out["ok"] = not validation.get("issues")
        out["validation"] = validation
    return out


def export_blend(blend_file: str, output: str, fmt: str = "glb", *,
                 selected_only: bool = False, apply_transforms: bool = True,
                 scale: float = 1.0, confirm_overwrite: bool = False) -> dict:
    fmt = (fmt or "glb").lower().lstrip(".")
    if fmt not in ("glb", "gltf", "fbx", "obj", "stl", "usdz"):
        raise ToolError(f"unsupported format: {fmt}")
    target = os.path.abspath(expand(output))
    if os.path.exists(target) and not confirm_overwrite:
        raise ToolError(f"output already exists (pass confirm_overwrite=true): {target}")
    out = run_blender(EXPORT_SCRIPT, args={
        "output": target, "format": fmt, "selected_only": selected_only,
        "apply_transforms": apply_transforms, "scale": scale,
    }, blend_file=blend_file, timeout=600)
    if out.get("ok") and isinstance(out.get("result"), dict) and os.path.isfile(target):
        out["result"]["sha256"] = sha256_file(target)
    return out


def import_to_blend(source: str, save_blend: str | None = None,
                    confirm_overwrite: bool = False) -> dict:
    source = require_path(source, label="source")
    destination = os.path.abspath(expand(save_blend)) if save_blend else None
    if destination and os.path.exists(destination) and not confirm_overwrite:
        raise ToolError(f"save_blend already exists (pass confirm_overwrite=true): {destination}")
    return run_blender(IMPORT_SCRIPT, args={"source": source, "save_blend": destination},
                       timeout=600)


def render_preview(blend_file: str, output_png: str, width: int = 640,
                   height: int = 360, frame: int | None = None,
                   confirm_overwrite: bool = False) -> dict:
    target = os.path.abspath(expand(output_png))
    if os.path.exists(target) and not confirm_overwrite:
        raise ToolError(f"output_png already exists (pass confirm_overwrite=true): {target}")
    return run_blender(RENDER_SCRIPT, args={
        "output_png": target, "width": width, "height": height, "frame": frame,
    }, blend_file=blend_file, timeout=900)


def create_environment_blockout(preset: str = "jungle", seed: int = 1337,
                                size: float = 100.0, segments: int = 64,
                                tree_count: int = 60, rock_count: int = 25,
                                water_level: float = 0.0,
                                include_water: bool = True,
                                save_blend: str | None = None,
                                export_glb: str | None = None,
                                render_png: str | None = None,
                                confirm_overwrite: bool = False) -> dict:
    if preset not in ("jungle", "forest", "desert", "alpine"):
        raise ToolError("preset must be one of: jungle, forest, desert, alpine")
    if not (16 <= segments <= 256):
        raise ToolError("segments must be between 16 and 256")
    if not (5.0 <= size <= 2000.0):
        raise ToolError("size must be between 5 and 2000 metres")
    if tree_count < 0 or rock_count < 0 or tree_count > 5000 or rock_count > 5000:
        raise ToolError("tree_count/rock_count must be between 0 and 5000")
    save = os.path.abspath(expand(save_blend)) if save_blend else None
    glb = os.path.abspath(expand(export_glb)) if export_glb else None
    png = os.path.abspath(expand(render_png)) if render_png else None
    for target in (save, glb, png):
        if target and os.path.exists(target) and not confirm_overwrite:
            raise ToolError(f"output exists (pass confirm_overwrite=true): {target}")
    if not save and not glb and not png:
        raise ToolError("provide at least one of save_blend, export_glb or render_png")

    # Rendering reopens a saved .blend. When the caller only asked for an image,
    # stage a temporary file so the render still happens, then remove it.
    temp_dir = None
    render_source = save
    if png and not save:
        temp_dir = tempfile.mkdtemp(prefix="game-studio-render-")
        render_source = os.path.join(temp_dir, "blockout.blend")

    out = run_blender(BUILDOUT_SCRIPT, args={
        "preset": preset, "seed": seed, "size": size, "segments": segments,
        "tree_count": tree_count, "rock_count": rock_count,
        "water_level": water_level, "include_water": include_water,
        "save_blend": render_source, "export_glb": glb, "render_png": png,
    }, timeout=1200)
    # Exporting and rendering are separate Blender invocations from the saved file,
    # so each artifact is produced by the documented exporter/renderer.
    artifacts = {}
    try:
        if out.get("ok") and render_source and os.path.isfile(render_source):
            if save:
                artifacts["blend"] = {"path": save, "bytes": os.path.getsize(save)}
            if glb:
                exported = export_blend(render_source, glb, "glb", confirm_overwrite=confirm_overwrite)
                artifacts["glb"] = exported.get("result") if exported.get("ok") else exported
                out["ok"] = out.get("ok") and bool(exported.get("ok"))
            if png:
                rendered = render_preview(render_source, png, confirm_overwrite=confirm_overwrite)
                artifacts["render"] = rendered.get("result") if rendered.get("ok") else rendered
                out["ok"] = out.get("ok") and bool(rendered.get("ok"))
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
    out["artifacts"] = artifacts
    missing = [name for name, target in
               (("blend", save), ("glb", glb), ("render", png))
               if target and not os.path.isfile(target)]
    if missing:
        out["ok"] = False
        out["error"] = "expected artifacts were not produced: " + ", ".join(missing)
    if out.get("ok"):
        out["generated_at"] = now_iso()
    return out


def run_python(code: str, blend_file: str | None = None, save: bool = False,
               confirm: bool = False, timeout: int = 900) -> dict:
    if not code or not isinstance(code, str):
        raise ToolError("code is required")
    if not confirm:
        raise ToolError("run_python executes arbitrary code; pass confirm=true to proceed")
    script = code + "\n"
    if save:
        script += (
            "\nimport bpy\n"
            "if not bpy.data.filepath:\n"
            "    raise RuntimeError('save=true requires blend_file')\n"
            "bpy.ops.wm.save_mainfile()\n"
        )
    return run_blender(script, blend_file=blend_file, timeout=timeout)
