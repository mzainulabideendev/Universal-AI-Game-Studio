#!/usr/bin/env python3
"""Minimal, dependency-free MCP stdio server that drives Blender.

Design notes
------------
* Every tool call launches the real Blender executable in background mode and
  runs a generated Python script. Nothing is simulated.
* Results are exchanged through a temporary JSON file instead of stdout, so
  Blender's own logging cannot corrupt the MCP response.
* Uses newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio transport).

Environment variables
---------------------
BLENDER_EXE   Optional path to Blender; otherwise "blender" is resolved from PATH
BLENDER_MCP_TIMEOUT  Per-call timeout in seconds (default: 600)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

SERVER_NAME = "blender-mcp"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT = int(os.environ.get("BLENDER_MCP_TIMEOUT", "600"))
MAX_TEXT = 200_000


def log(msg: str) -> None:
    print(f"[blender-mcp] {msg}", file=sys.stderr, flush=True)


def blender_exe() -> str | None:
    configured = os.environ.get("BLENDER_EXE")
    return configured if configured else shutil.which("blender")


# --------------------------------------------------------------------------
# Blender execution helpers
# --------------------------------------------------------------------------
def run_blender(script: str, blend_file: str | None = None,
                timeout: int | None = None, factory: bool = True) -> dict:
    exe = blender_exe()
    if not exe:
        return {
            "ok": False,
            "error": "Blender executable not found. Set BLENDER_EXE or add blender to PATH.",
        }
    if not os.path.isfile(exe):
        return {"ok": False, "error": f"Blender executable does not exist: {exe}"}
    if blend_file and not os.path.isfile(blend_file):
        return {"ok": False, "error": f".blend file not found: {blend_file}"}

    tmp_dir = tempfile.mkdtemp(prefix="blender-mcp-")
    script_path = os.path.join(tmp_dir, "job.py")
    result_path = os.path.join(tmp_dir, "result.json")

    payload = {"result_path": result_path.replace("\\", "\\\\")}
    wrapped = (
        "import json, sys, traceback\n"
        f"RESULT_PATH = r'''{result_path}'''\n"
        "def __mcp_emit(payload):\n"
        "    with open(RESULT_PATH, 'w', encoding='utf-8') as fh:\n"
        "        json.dump(payload, fh, default=str)\n"
        "try:\n"
        + "\n".join("    " + line for line in script.splitlines())
        + "\n    __mcp_emit({'ok': True, 'result': __mcp_result})\n"
        "except Exception:\n"
        "    __mcp_emit({'ok': False, 'error': traceback.format_exc()})\n"
    )
    Path(script_path).write_text(wrapped, encoding="utf-8")

    args = [exe, "--background"]
    if blend_file:
        args.append(os.path.abspath(blend_file))
    if factory:
        args.append("--factory-startup")
    args += ["--python", script_path, "--python-exit-code", "1"]

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Blender timed out after {timeout or DEFAULT_TIMEOUT}s"}
    except OSError as exc:
        return {"ok": False, "error": f"Failed to launch Blender: {exc}"}

    payload: dict = {}
    if os.path.isfile(result_path):
        try:
            payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - corrupt result guard
            payload = {"ok": False, "error": f"Unreadable Blender result: {exc}"}
    else:
        payload = {
            "ok": False,
            "error": "Blender produced no result file. See stderr/stdout.",
        }

    stdout = (proc.stdout or "")[-MAX_TEXT:]
    stderr = (proc.stderr or "")[-MAX_TEXT:]
    payload["exit_code"] = proc.returncode
    payload["stdout"] = stdout
    payload["stderr"] = stderr
    payload["blender"] = exe
    payload["script"] = script_path
    return payload


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------
def tool_blender_info(args: dict) -> dict:
    script = """
import bpy, sys, platform
info = {
  'version': '.'.join(str(v) for v in bpy.app.version),
  'version_string': bpy.app.version_string,
  'python': sys.version.split()[0],
  'platform': platform.platform(),
  'file': bpy.data.filepath,
  'scenes': [s.name for s in bpy.data.scenes],
  'engines': [getattr(e, 'bl_idname', e.__name__) for e in bpy.types.RenderEngine.__subclasses__()][:8],
  'addons_enabled': sorted(a.module for a in bpy.context.preferences.addons)[:40],
  'unit_system': bpy.context.scene.unit_settings.system,
  'unit_scale': bpy.context.scene.unit_settings.scale_length,
}
__mcp_result = info
"""
    return run_blender(script)


def _inspect_script(max_objects: int) -> str:
    return f"""
import bpy, os, math
scene = bpy.context.scene
objects = []
for ob in bpy.data.objects[:{max_objects}]:
    entry = {{
        'name': ob.name,
        'type': ob.type,
        'parent': ob.parent.name if ob.parent else None,
        'location': [round(v, 4) for v in ob.location],
        'rotation_euler': [round(math.degrees(v), 2) for v in ob.rotation_euler],
        'scale': [round(v, 4) for v in ob.scale],
        'dimensions': [round(v, 4) for v in ob.dimensions],
        'modifiers': [m.type for m in ob.modifiers],
        'materials': [ms.material.name for ms in ob.material_slots if ms.material],
        'visible': bool(ob.visible_get()),
    }}
    if ob.type == 'MESH':
        me = ob.data
        entry['vertices'] = len(me.vertices)
        entry['polygons'] = len(me.polygons)
        entry['uv_layers'] = [uv.name for uv in me.uv_layers]
        entry['has_normals'] = bool(me.has_custom_normals) or len(me.polygons) > 0
        entry['shape_keys'] = len(me.shape_keys.key_blocks) if me.shape_keys else 0
        entry['loose_edges'] = sum(1 for e in me.edges if not e.is_loose)
        entry['bounds_world'] = [
            [round(min((ob.matrix_world @ v.co)[i] for v in me.vertices), 4),
             round(max((ob.matrix_world @ v.co)[i] for v in me.vertices), 4)]
            for i in range(3)
        ] if len(me.vertices) else None
    if ob.type == 'ARMATURE':
        entry['bones'] = len(ob.data.bones)
        entry['bone_names'] = [b.name for b in ob.data.bones][:40]
    if ob.type == 'CAMERA':
        entry['camera_type'] = ob.data.type
    if ob.type == 'LIGHT':
        entry['light_type'] = ob.data.type
        entry['energy'] = ob.data.energy
    objects.append(entry)

images = []
for img in bpy.data.images:
    images.append({{
        'name': img.name,
        'filepath': img.filepath,
        'packed': bool(img.packed_file),
        'missing': (not img.packed_file) and bool(img.filepath) and not os.path.isfile(bpy.path.abspath(img.filepath)),
        'size': list(img.size),
    }})

actions = []
for act in bpy.data.actions:
    actions.append({{
        'name': act.name,
        'frame_range': [round(v, 2) for v in act.frame_range],
        'fcurves': len(act.fcurves),
    }})

materials = []
for mat in bpy.data.materials:
    node_types = []
    textures = []
    if mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            node_types.append(n.type)
            if n.type == 'TEX_IMAGE' and n.image:
                textures.append(n.image.name)
    materials.append({{
        'name': mat.name,
        'use_nodes': mat.use_nodes,
        'node_types': sorted(set(node_types)),
        'textures': textures,
        'blend_method': getattr(mat, 'blend_method', None),
    }})

collections = [{{'name': c.name, 'objects': len(c.objects)}} for c in bpy.data.collections]
__mcp_result = {{
    'file': bpy.data.filepath,
    'scene': scene.name,
    'frame': scene.frame_current,
    'frame_range': [scene.frame_start, scene.frame_end],
    'render_engine': scene.render.engine,
    'unit_system': scene.unit_settings.system,
    'unit_scale': scene.unit_settings.scale_length,
    'object_count': len(bpy.data.objects),
    'objects': objects,
    'images': images,
    'actions': actions,
    'materials': materials,
    'collections': collections,
}}
"""


def tool_inspect_blend(args: dict) -> dict:
    blend = args.get("blend_file")
    if not blend:
        return {"ok": False, "error": "blend_file is required"}
    return run_blender(_inspect_script(int(args.get("max_objects", 500))), blend)


def tool_validate_asset(args: dict) -> dict:
    blend = args.get("blend_file")
    if not blend:
        return {"ok": False, "error": "blend_file is required"}
    max_tri = int(args.get("max_triangles", 150000))
    script = f"""
import bpy, os, math
issues, warnings, info = [], [], {{}}
scene = bpy.context.scene
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
        issues.append(f"{{ob.name}}: mesh has zero triangles")
    if not me.uv_layers:
        warnings.append(f"{{ob.name}}: no UV map (untextured/PBR materials may fail)")
    if any(abs(s - 1.0) > 1e-3 for s in ob.scale):
        warnings.append(f"{{ob.name}}: non-unit scale {{[round(s,3) for s in ob.scale]}} (bake transforms before export)")
    if ob.location.length > 1e-4 and ob.parent is None:
        warnings.append(f"{{ob.name}}: non-zero world location {{[round(v,3) for v in ob.location]}} (pivot may be off)")
    for slot in ob.material_slots:
        if slot.material is None:
            warnings.append(f"{{ob.name}}: empty material slot")
    if len(me.vertices) and min(len(me.vertices), 3) == 3:
        pass
    # normals / degenerate geometry
    zero_area = sum(1 for p in me.polygons if p.area < 1e-9)
    if zero_area:
        warnings.append(f"{{ob.name}}: {{zero_area}} zero-area faces")

info['mesh_objects'] = len(meshes)
info['triangles'] = triangles
info['armatures'] = len(armatures)
info['bones'] = sum(len(a.data.bones) for a in armatures)
info['actions'] = [a.name for a in bpy.data.actions]
info['materials'] = len(bpy.data.materials)
info['images'] = len(bpy.data.images)

if triangles > {max_tri}:
    warnings.append(f"triangle budget exceeded: {{triangles}} > {max_tri}")

missing = []
for img in bpy.data.images:
    if img.packed_file:
        continue
    if img.filepath and not os.path.isfile(bpy.path.abspath(img.filepath)):
        missing.append(img.filepath)
if missing:
    issues.append(f"missing texture files: {{missing}}")

for a in armatures:
    if not a.data.bones:
        issues.append(f"{{a.name}}: armature has no bones")

# root motion hint: armature object animated on X/Y
root_motion = False
for a in armatures:
    ad = a.animation_data
    if ad and ad.action:
        paths = [fc.data_path for fc in ad.action.fcurves]
        root_motion = any(p in ('location', 'delta_location') for p in paths)
info['armature_object_animated'] = root_motion

# bounds across all meshes
mins = [1e9]*3; maxs = [-1e9]*3
for ob in meshes:
    for corner in ob.bound_box:
        w = ob.matrix_world @ __import__('mathutils').Vector(corner)
        for i in range(3):
            mins[i] = min(mins[i], w[i]); maxs[i] = max(maxs[i], w[i])
if meshes:
    info['bounds_size'] = [round(maxs[i]-mins[i], 4) for i in range(3)]

__mcp_result = {{'ok': not issues, 'issues': issues, 'warnings': warnings, 'info': info}}
"""
    out = run_blender(script, blend)
    if out.get("ok") and isinstance(out.get("result"), dict):
        out["validation"] = out["result"]
    return out


def tool_export_asset(args: dict) -> dict:
    blend = args.get("blend_file")
    output = args.get("output")
    fmt = (args.get("format") or "glb").lower().lstrip(".")
    if not blend or not output:
        return {"ok": False, "error": "blend_file and output are required"}
    if fmt not in ("glb", "gltf", "fbx", "obj", "usdz"):
        return {"ok": False, "error": f"Unsupported format: {fmt}"}
    selected_only = bool(args.get("selected_only", False))
    apply_transforms = bool(args.get("apply_transforms", True))
    scale = float(args.get("scale", 1.0))
    out_path = os.path.abspath(output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    script = f"""
import bpy, os
out_path = r'''{out_path}'''
fmt = r'''{fmt}'''
selected_only = {selected_only}
apply_transforms = {apply_transforms}
scale = {scale}

bpy.ops.object.select_all(action='DESELECT')
if selected_only:
    for ob in bpy.context.scene.objects:
        if ob.select_get() and ob.type in ('MESH','ARMATURE','EMPTY'):
            pass
else:
    for ob in bpy.context.scene.objects:
        if ob.type in ('MESH','ARMATURE','EMPTY'):
            ob.select_set(True)

if apply_transforms:
    for ob in [o for o in bpy.context.scene.objects if o.select_get() and o.type in ('MESH','ARMATURE')]:
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
elif fmt == 'usdz':
    bpy.ops.wm.usd_export(filepath=out_path, selected_objects_only=selected_only)

size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
if size <= 0:
    raise RuntimeError('Exporter produced no file: ' + out_path)
__mcp_result = {{'output': out_path, 'format': fmt, 'bytes': size, 'exists': os.path.isfile(out_path)}}
"""
    return run_blender(script, blend)


def tool_import_asset(args: dict) -> dict:
    source = args.get("source")
    save_path = args.get("save_blend")
    if not source or not os.path.isfile(source):
        return {"ok": False, "error": f"source file not found: {source}"}
    ext = os.path.splitext(source)[1].lower()
    script = f"""
import bpy, os
src = r'''{os.path.abspath(source)}'''
ext = r'''{ext}'''
before = set(o.name for o in bpy.data.objects)
if ext == '.fbx':
    bpy.ops.import_scene.fbx(filepath=src)
elif ext in ('.glb', '.gltf'):
    bpy.ops.import_scene.gltf(filepath=src)
elif ext == '.obj':
    bpy.ops.wm.obj_import(filepath=src)
elif ext == '.blend':
    with bpy.data.libraries.load(src, link=False) as (src_data, dst_data):
        dst_data.objects = src_data.objects
    for ob in dst_data.objects:
        if ob: bpy.context.scene.collection.objects.link(ob)
elif ext in ('.usd', '.usdz'):
    bpy.ops.wm.usd_import(filepath=src)
else:
    raise RuntimeError('Unsupported import format: ' + ext)
new = [o.name for o in bpy.data.objects if o.name not in before]
save_path = r'''{os.path.abspath(save_path) if save_path else ""}'''
if save_path:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)
__mcp_result = {{'imported': new, 'count': len(new), 'saved': save_path or None}}
"""
    return run_blender(script, None)


def tool_render_preview(args: dict) -> dict:
    blend = args.get("blend_file")
    output = args.get("output_png")
    if not blend or not output:
        return {"ok": False, "error": "blend_file and output_png are required"}
    width = int(args.get("width", 640))
    height = int(args.get("height", 360))
    frame = args.get("frame")
    out = os.path.abspath(output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    script = f"""
import bpy, os
scene = bpy.context.scene
scene.render.resolution_x = {width}
scene.render.resolution_y = {height}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = r'''{out}'''
f = {frame if frame is not None else "None"}
if f is not None:
    scene.frame_set(int(f))
if scene.camera is None:
    cams = [o for o in bpy.data.objects if o.type == 'CAMERA']
    if cams:
        scene.camera = cams[0]
    else:
        raise RuntimeError('No camera in scene')
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
preferred = [e for e in ('BLENDER_EEVEE_NEXT','BLENDER_EEVEE','CYCLES','BLENDER_WORKBENCH') if e in engines]
if preferred:
    scene.render.engine = preferred[0]
bpy.ops.render.render(write_still=True)
if not os.path.isfile(r'''{out}'''):
    raise RuntimeError('Render produced no file')
__mcp_result = {{'output': r'''{out}''', 'bytes': os.path.getsize(r'''{out}'''), 'engine': scene.render.engine}}
"""
    return run_blender(script, blend)


def tool_run_python(args: dict) -> dict:
    code = args.get("code")
    if not code:
        return {"ok": False, "error": "code is required"}
    blend = args.get("blend_file")
    save = bool(args.get("save", False))
    script = code + "\n"
    if save:
        script += (
            "\nimport bpy\n"
            "if not bpy.data.filepath:\n"
            "    raise RuntimeError('save=true requires blend_file')\n"
            "bpy.ops.wm.save_mainfile()\n"
            "__mcp_saved = bpy.data.filepath\n"
        )
    # Allow scripts to set __mcp_result; otherwise capture common conventions.
    script += (
        "\ntry:\n"
        "    __mcp_result\n"
        "except NameError:\n"
        "    __mcp_result = {'ran': True, 'stdout': 'script completed without __mcp_result'}\n"
    )
    return run_blender(script, blend)


TOOLS = [
    {
        "name": "blender_info",
        "description": "Report the installed Blender version, Python version, active file and enabled addons.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_blend",
        "description": "Open a .blend file and return objects, transforms, meshes, UVs, materials, textures, armatures, actions and missing image references.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blend_file": {"type": "string", "description": "Absolute path to a .blend file"},
                "max_objects": {"type": "integer", "default": 500},
            },
            "required": ["blend_file"],
        },
    },
    {
        "name": "validate_asset",
        "description": "Validate a .blend asset for engine import: triangles, UVs, transforms, missing textures, armature/action presence, bounds and budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blend_file": {"type": "string"},
                "max_triangles": {"type": "integer", "default": 150000},
            },
            "required": ["blend_file"],
        },
    },
    {
        "name": "export_asset",
        "description": "Export a .blend to glb/gltf/fbx/obj/usdz with optional transform baking and scaling.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blend_file": {"type": "string"},
                "output": {"type": "string", "description": "Absolute output file path"},
                "format": {"type": "string", "enum": ["glb", "gltf", "fbx", "obj", "usdz"], "default": "glb"},
                "selected_only": {"type": "boolean", "default": False},
                "apply_transforms": {"type": "boolean", "default": True},
                "scale": {"type": "number", "default": 1.0},
            },
            "required": ["blend_file", "output"],
        },
    },
    {
        "name": "import_asset",
        "description": "Import fbx/glb/gltf/obj/blend/usd into a fresh Blender scene and optionally save a .blend.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "save_blend": {"type": "string", "description": "Optional output .blend path"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "render_preview",
        "description": "Render a PNG preview of a .blend scene for visual verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blend_file": {"type": "string"},
                "output_png": {"type": "string"},
                "width": {"type": "integer", "default": 640},
                "height": {"type": "integer", "default": 360},
                "frame": {"type": ["integer", "null"]},
            },
            "required": ["blend_file", "output_png"],
        },
    },
    {
        "name": "run_python",
        "description": "Execute an arbitrary Blender Python script in background mode. Set __mcp_result to return data. Use for creating/modifying scenes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "blend_file": {"type": "string", "description": "Optional .blend to open first"},
                "save": {"type": "boolean", "default": False, "description": "Save the .blend after running"},
            },
            "required": ["code"],
        },
    },
]

HANDLERS = {
    "blender_info": tool_blender_info,
    "inspect_blend": tool_inspect_blend,
    "validate_asset": tool_validate_asset,
    "export_asset": tool_export_asset,
    "import_asset": tool_import_asset,
    "render_preview": tool_render_preview,
    "run_python": tool_run_python,
}


def text_result(payload: dict, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, default=str)[:MAX_TEXT]}],
        "isError": is_error,
    }


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": req.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id, "result": text_result({"error": f"Unknown tool: {name}"}, True)}
        try:
            payload = handler(arguments)
            ok = bool(payload.get("ok", True))
            return {"jsonrpc": "2.0", "id": req_id, "result": text_result(payload, not ok)}
        except Exception:
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result({"ok": False, "error": traceback.format_exc()}, True)}
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": req_id, "result": {key: []}}
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    log(f"starting {SERVER_NAME} {SERVER_VERSION}; blender={blender_exe()}")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"invalid JSON: {exc}")
            continue
        response = handle(req)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
