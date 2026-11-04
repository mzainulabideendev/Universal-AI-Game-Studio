#!/usr/bin/env python3
"""Universal AI Game Studio MCP server (stdio, dependency-free).

The server exposes real tools for detection, Blender automation, Meshy tasks,
licensed asset search, animation inspection and engine staging/build commands.
Tools that need credentials or extra confirmation return explicit errors rather
than simulated successes.

Run:
    python tools/game-studio-mcp/server.py

Configure your MCP client to start that command with the desired environment
variables (MESHY_API_KEY, SKETCHFAB_TOKEN, optional BLENDER_EXE, GAME_STUDIO_HOME).
"""

from __future__ import annotations

import json
import os
import sys
import traceback

from game_studio import SERVER_NAME, SERVER_VERSION, PROTOCOL_VERSION
from game_studio import animations, assets, blender, config, detect, engines, meshy, projects, secrets
from game_studio.util import ToolError, now_iso

MAX_TEXT = 200_000
LOG_PREFIX = "[universal-game-studio]"


def log(message: str) -> None:
    print(f"{LOG_PREFIX} {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# argument helpers
# --------------------------------------------------------------------------
def _str(args: dict, key: str, *, required: bool = False, default: str | None = None,
         max_length: int = 4096) -> str | None:
    value = args.get(key, default)
    if value is None:
        if required:
            raise ToolError(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise ToolError(f"{key} is required")
    if len(value) > max_length:
        raise ToolError(f"{key} must be at most {max_length} characters")
    return value or None


def _int(args: dict, key: str, *, default: int | None = None,
         minimum: int | None = None, maximum: int | None = None) -> int | None:
    value = args.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ToolError(f"{key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ToolError(f"{key} must be at most {maximum}")
    return value


def _float(args: dict, key: str, *, default: float | None = None,
           minimum: float | None = None, maximum: float | None = None) -> float | None:
    value = args.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError(f"{key} must be a number")
    value = float(value)
    if minimum is not None and value < minimum:
        raise ToolError(f"{key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ToolError(f"{key} must be at most {maximum}")
    return value


def _bool(args: dict, key: str, *, default: bool = False) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise ToolError(f"{key} must be a boolean")
    return value


def _list(args: dict, key: str) -> list | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ToolError(f"{key} must be an array")
    return value


# --------------------------------------------------------------------------
# studio tools
# --------------------------------------------------------------------------
def tool_studio_info(args: dict) -> dict:
    cfg = config.load_config()
    return {
        "ok": True,
        "server": {"name": SERVER_NAME, "version": SERVER_VERSION,
                   "protocol": PROTOCOL_VERSION, "generated_at": now_iso()},
        "platform": detect.platform_name() if hasattr(detect, "platform_name") else os.name,
        "config_path": config.config_path(),
        "audit_path": config.audit_path(),
        "download_root": cfg.get("download_root"),
        "selected_engine": cfg.get("selected_engine"),
        "selected_engine_path": cfg.get("selected_engine_path"),
        "integrations": {
            "meshy": {"configured": bool(secrets.meshy_key_source()),
                      "source": secrets.meshy_key_source(),
                      "env": "MESHY_API_KEY",
                      "setup_tool": "meshy_setup_guide"},
            "sketchfab": {"configured": bool(os.environ.get("SKETCHFAB_TOKEN")),
                          "env": "SKETCHFAB_TOKEN"},
            "blender": {"configured": bool(blender.resolve_blender())},
        },
        "secrets_note": "Credential values are never stored in the config or returned by tools.",
        "confirmation_model": {
            "confirm_required": [
                "Meshy generation, rigging and animation tasks (credits)",
                "Poly Haven downloads and asset staging (writes files)",
                "Unity batch refresh, tests, builds and editor commands",
                "Godot import and export",
                "blender_run_python (arbitrary code)",
            ],
            "overwrite_requires": "confirm_overwrite=true on export/render/stage when the target exists",
        },
    }


def tool_detect_system(args: dict) -> dict:
    return {"ok": True, **detect.inspect_system()}


def tool_detect_game_engines(args: dict) -> dict:
    discover_projects = _bool(args, "discover_projects", default=True)
    roots = _list(args, "roots")
    return detect.detect_game_engines(discover=discover_projects, roots=roots)


def tool_list_available_engines(args: dict) -> dict:
    return engines.list_available_engines()


def tool_select_game_engine(args: dict) -> dict:
    return engines.select_engine(
        _str(args, "engine", required=True),
        engine_path=_str(args, "engine_path"),
        persist=_bool(args, "persist", default=True),
    )


def tool_inspect_engine_capabilities(args: dict) -> dict:
    return engines.inspect_engine_capabilities(_str(args, "engine"))


def tool_inspect_game_project(args: dict) -> dict:
    return projects.inspect_game_project(
        _str(args, "project_path", required=True),
        include_editor_status=_bool(args, "include_editor_status", default=False),
    )


def tool_configure_studio(args: dict) -> dict:
    updates: dict = {}
    for key in ("selected_engine", "selected_engine_path", "blender_exe", "unity_exe",
                "unreal_editor_cmd", "godot_exe", "download_root"):
        value = _str(args, key)
        if value is not None:
            updates[key] = value
    if "project_roots" in args:
        roots = _list(args, "project_roots")
        updates["project_roots"] = [str(root) for root in (roots or [])]
    if "allow_overwrite" in args:
        updates["allow_overwrite"] = _bool(args, "allow_overwrite")
    if not updates:
        raise ToolError("provide at least one configuration value to change")
    try:
        saved = config.save_config(updates)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    config.audit("studio.configure", tool="configure_studio",
                 details={"keys": sorted(updates)})
    return {
        "ok": True,
        "config_path": config.config_path(),
        "updated_keys": sorted(updates),
        "config": {key: saved.get(key) for key in
                   ("selected_engine", "selected_engine_path", "project_roots",
                    "blender_exe", "unity_exe", "unreal_editor_cmd", "godot_exe",
                    "download_root", "allow_overwrite")},
    }


def tool_list_studio_projects(args: dict) -> dict:
    roots = _list(args, "roots")
    found = detect.discover_projects(roots)
    return {"ok": True, "count": len(found), "projects": found,
            "roots": roots or config.load_config().get("project_roots")}


def tool_read_studio_audit(args: dict) -> dict:
    limit = _int(args, "limit", default=50, minimum=1, maximum=1000)
    records = config.read_audit(limit or 50)
    return {"ok": True, "count": len(records), "records": records,
            "path": config.audit_path()}


# --------------------------------------------------------------------------
# Blender tools
# --------------------------------------------------------------------------
def tool_blender_info(args: dict) -> dict:
    return blender.blender_info(_str(args, "blender_exe"))


def tool_blender_inspect(args: dict) -> dict:
    return blender.inspect_blend(_str(args, "blend_file", required=True),
                                 _int(args, "max_objects", default=500, minimum=1,
                                      maximum=5000) or 500)


def tool_blender_validate(args: dict) -> dict:
    return blender.validate_blend(_str(args, "blend_file", required=True),
                                  _int(args, "max_triangles", default=150_000,
                                       minimum=1) or 150_000)


def tool_blender_export(args: dict) -> dict:
    return blender.export_blend(
        _str(args, "blend_file", required=True),
        _str(args, "output", required=True),
        _str(args, "format", default="glb") or "glb",
        selected_only=_bool(args, "selected_only"),
        apply_transforms=_bool(args, "apply_transforms", default=True),
        scale=_float(args, "scale", default=1.0, minimum=0.0001) or 1.0,
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_import(args: dict) -> dict:
    return blender.import_to_blend(
        _str(args, "source", required=True),
        save_blend=_str(args, "save_blend"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_render(args: dict) -> dict:
    return blender.render_preview(
        _str(args, "blend_file", required=True),
        _str(args, "output_png", required=True),
        width=_int(args, "width", default=640, minimum=16, maximum=4096) or 640,
        height=_int(args, "height", default=360, minimum=16, maximum=4096) or 360,
        frame=_int(args, "frame"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_environment(args: dict) -> dict:
    return blender.create_environment_blockout(
        _str(args, "preset", default="jungle") or "jungle",
        seed=_int(args, "seed", default=1337) or 1337,
        size=_float(args, "size", default=100.0, minimum=5.0, maximum=2000.0) or 100.0,
        segments=_int(args, "segments", default=64, minimum=16, maximum=256) or 64,
        tree_count=_int(args, "tree_count", default=60, minimum=0, maximum=5000) or 0,
        rock_count=_int(args, "rock_count", default=25, minimum=0, maximum=5000) or 0,
        water_level=_float(args, "water_level", default=0.0) or 0.0,
        include_water=_bool(args, "include_water", default=True),
        save_blend=_str(args, "save_blend"),
        export_glb=_str(args, "export_glb"),
        render_png=_str(args, "render_png"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_run_python(args: dict) -> dict:
    return blender.run_python(
        _str(args, "code", required=True, max_length=100_000) or "",
        blend_file=_str(args, "blend_file"),
        save=_bool(args, "save"),
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=900, minimum=10, maximum=7200) or 900,
    )


# --------------------------------------------------------------------------
# Meshy tools
# --------------------------------------------------------------------------
def tool_meshy_balance(args: dict) -> dict:
    return meshy.balance()


def tool_meshy_setup(args: dict) -> dict:
    return meshy.setup_guide()


def tool_meshy_configure(args: dict) -> dict:
    return meshy.configure_api_key(
        _str(args, "api_key", required=True, max_length=secrets.MAX_KEY_LENGTH) or "",
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_clear(args: dict) -> dict:
    return meshy.clear_api_key()


def tool_meshy_text_to_3d(args: dict) -> dict:
    return meshy.create_text_to_3d(
        _str(args, "prompt", default="") or "",
        mode=_str(args, "mode", default="preview") or "preview",
        preview_task_id=_str(args, "preview_task_id"),
        ai_model=_str(args, "ai_model"),
        target_polycount=_int(args, "target_polycount", minimum=100, maximum=300_000),
        should_remesh=args.get("should_remesh") if isinstance(args.get("should_remesh"), bool) else None,
        pose_mode=_str(args, "pose_mode"),
        target_formats=_list(args, "target_formats"),
        enable_pbr=_bool(args, "enable_pbr", default=True),
        texture_resolution=_str(args, "texture_resolution"),
        texture_prompt=_str(args, "texture_prompt"),
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_rig(args: dict) -> dict:
    return meshy.create_rigging(
        input_task_id=_str(args, "input_task_id"),
        model_url=_str(args, "model_url"),
        height_meters=_float(args, "height_meters", default=1.7, minimum=0.2,
                             maximum=10.0) or 1.7,
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_animation_library(args: dict) -> dict:
    action_ids = _list(args, "action_ids")
    if action_ids is not None:
        action_ids = [int(i) for i in action_ids]
    return meshy.animation_library(
        search=_str(args, "search"),
        category=_str(args, "category"),
        action_ids=action_ids,
    )


def tool_meshy_create_animation(args: dict) -> dict:
    action_ids = _list(args, "action_ids")
    if action_ids is not None:
        action_ids = [int(i) for i in action_ids]
    return meshy.create_animation(
        rig_task_id=_str(args, "rig_task_id", required=True) or "",
        action_id=_int(args, "action_id"),
        action_ids=action_ids,
        motion_task_id=_str(args, "motion_task_id"),
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_task_status(args: dict) -> dict:
    return meshy.get_task(
        _str(args, "task_id", required=True) or "",
        _str(args, "task_type", required=True) or "",
    )


def tool_meshy_wait(args: dict) -> dict:
    return meshy.wait_for_task(
        _str(args, "task_id", required=True) or "",
        _str(args, "task_type", required=True) or "",
        timeout_seconds=_int(args, "timeout_seconds", default=120, minimum=0,
                             maximum=1800) or 0,
        poll_seconds=_float(args, "poll_seconds", default=5.0, minimum=1.0,
                            maximum=60.0) or 5.0,
    )


def tool_meshy_download(args: dict) -> dict:
    return meshy.download_output(
        _str(args, "task_id", required=True) or "",
        _str(args, "task_type", required=True) or "",
        _str(args, "output_key", required=True) or "",
        _str(args, "destination", required=True) or "",
    )


def tool_meshy_generate(args: dict) -> dict:
    return meshy.generate_asset(
        _str(args, "prompt", required=True) or "",
        refine=_bool(args, "refine"),
        wait=_bool(args, "wait", default=True),
        timeout_seconds=_int(args, "timeout_seconds", default=180, minimum=0,
                             maximum=1800) or 0,
        ai_model=_str(args, "ai_model"),
        target_polycount=_int(args, "target_polycount", minimum=100, maximum=300_000),
        pose_mode=_str(args, "pose_mode"),
        enable_pbr=_bool(args, "enable_pbr", default=True),
        texture_resolution=_str(args, "texture_resolution"),
        confirm=_bool(args, "confirm"),
    )


# --------------------------------------------------------------------------
# Asset tools
# --------------------------------------------------------------------------
def tool_asset_providers(args: dict) -> dict:
    return assets.providers()


def tool_asset_search(args: dict) -> dict:
    return assets.search_assets(
        _str(args, "query", required=True) or "",
        kind=_str(args, "kind", default="model") or "model",
        provider=_str(args, "provider", default="auto") or "auto",
        limit=_int(args, "limit", default=20, minimum=1, maximum=60) or 20,
        max_polycount=_int(args, "max_polycount", minimum=1),
    )


def tool_asset_download(args: dict) -> dict:
    return assets.download_polyhaven(
        _str(args, "asset_id", required=True) or "",
        fmt=_str(args, "format", default="glb") or "glb",
        resolution=_str(args, "resolution", default="2k") or "2k",
        destination_dir=_str(args, "destination_dir"),
        confirm=_bool(args, "confirm"),
        max_bytes=_int(args, "max_bytes", default=512 * 1024 * 1024, minimum=1) or
        512 * 1024 * 1024,
    )


def tool_asset_license(args: dict) -> dict:
    return assets.inspect_asset_license(
        _str(args, "provider", required=True) or "",
        asset_id=_str(args, "asset_id"),
    )


def tool_asset_validate(args: dict) -> dict:
    return assets.validate_asset_file(
        _str(args, "path", required=True) or "",
        max_triangles=_int(args, "max_triangles", minimum=1),
    )


def tool_asset_manifest(args: dict) -> dict:
    paths = _list(args, "paths")
    if not paths:
        raise ToolError("paths must contain at least one file")
    return assets.asset_manifest([str(p) for p in paths], _str(args, "destination"))


# --------------------------------------------------------------------------
# Animation tools
# --------------------------------------------------------------------------
def tool_animation_inspect(args: dict) -> dict:
    return animations.inspect_rig(_str(args, "path", required=True) or "")


def tool_animation_retarget_map(args: dict) -> dict:
    return animations.create_retarget_map(
        _str(args, "character_path", required=True) or "",
        _str(args, "animation_path", required=True) or "",
        destination=_str(args, "destination"),
    )


def tool_animation_compatibility(args: dict) -> dict:
    return animations.check_compatibility(
        _str(args, "character_path", required=True) or "",
        _str(args, "animation_path", required=True) or "",
    )


def tool_animation_sources(args: dict) -> dict:
    return animations.list_animation_sources()


# --------------------------------------------------------------------------
# Engine tools
# --------------------------------------------------------------------------
def tool_engine_stage(args: dict) -> dict:
    return engines.stage_asset(
        _str(args, "source", required=True) or "",
        _str(args, "project_path", required=True) or "",
        engine=_str(args, "engine"),
        relative_path=_str(args, "relative_path"),
        confirm=_bool(args, "confirm"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_engine_verify(args: dict) -> dict:
    return engines.verify_staged_import(
        _str(args, "project_path", required=True) or "",
        _str(args, "relative_path", required=True) or "",
    )


def tool_engine_build(args: dict) -> dict:
    return engines.engine_build(
        _str(args, "engine", required=True) or "",
        _str(args, "project_path", required=True) or "",
        target=_str(args, "target"),
        output_path=_str(args, "output_path"),
        preset=_str(args, "preset"),
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unity_status(args: dict) -> dict:
    return engines.unity_editor_status()


def tool_unity_commands(args: dict) -> dict:
    return engines.unity_list_commands(_str(args, "project_path", required=True) or "")


def tool_unity_run_command(args: dict) -> dict:
    arguments = _list(args, "arguments")
    return engines.unity_run_command(
        _str(args, "project_path", required=True) or "",
        _str(args, "command", required=True) or "",
        [str(a) for a in (arguments or [])],
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=300, minimum=5, maximum=3600) or 300,
    )


def tool_unity_refresh(args: dict) -> dict:
    return engines.unity_batch_refresh(
        _str(args, "project_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unity_tests(args: dict) -> dict:
    return engines.unity_run_tests(
        _str(args, "project_path", required=True) or "",
        mode=_str(args, "mode", default="EditMode") or "EditMode",
        test_filter=_str(args, "filter"),
        output=_str(args, "output"),
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unity_build(args: dict) -> dict:
    return engines.unity_build(
        _str(args, "project_path", required=True) or "",
        target=_str(args, "target", required=True) or "",
        output_path=_str(args, "output_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
        allow_dirty_build=_bool(args, "allow_dirty_build"),
    )


def tool_godot_import(args: dict) -> dict:
    return engines.godot_batch_import(
        _str(args, "project_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_godot_build(args: dict) -> dict:
    return engines.godot_build(
        _str(args, "project_path", required=True) or "",
        preset=_str(args, "preset", required=True) or "",
        output_path=_str(args, "output_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unreal_status(args: dict) -> dict:
    return engines.unreal_stage_only(_str(args, "project_path", required=True) or "")


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------
def _tool(name: str, description: str, properties: dict | None = None,
          required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = required
    return {"name": name, "description": description, "inputSchema": schema}


PROJECT_PATH = {"type": "string", "description": "Absolute path to the game project"}
ENGINE_ENUM = {"type": "string", "enum": list(engines.ENGINES)}
CONFIRM = {"type": "boolean", "default": False,
           "description": "Explicit approval for a write, credit spend or editor run"}
OVERWRITE = {"type": "boolean", "default": False,
             "description": "Allow replacing an existing target file"}

TOOLS = [
    # studio
    _tool("studio_info", "Report server version, config location, selected engine and which "
          "credentialed integrations are configured. Never returns secret values."),
    _tool("detect_system", "Inspect OS, CPU, memory, GPUs and disk space."),
    _tool("detect_game_engines", "Detect Unity, Unreal and Godot installations and optionally "
          "discover game projects under configured roots.", {
              "discover_projects": {"type": "boolean", "default": True},
              "roots": {"type": "array", "items": {"type": "string"},
                        "description": "Optional roots; defaults to configured project_roots"},
          }),
    _tool("list_available_engines", "List engines with detection state, adapter capabilities and "
          "the current selection."),
    _tool("select_game_engine", "Persist the engine the user wants to work in. Requires a "
          "verified installation.", {
              "engine": ENGINE_ENUM,
              "engine_path": {"type": "string",
                              "description": "Optional explicit editor/CLI path"},
              "persist": {"type": "boolean", "default": True},
          }, ["engine"]),
    _tool("inspect_engine_capabilities", "Show exactly which engine operations are implemented, "
          "verified, or unavailable in this environment.", {
              "engine": ENGINE_ENUM,
          }),
    _tool("inspect_game_project", "Inspect a Unity/Unreal/Godot project: version, packages, render "
          "pipeline, scenes, missing scripts and warnings.", {
              "project_path": PROJECT_PATH,
              "include_editor_status": {"type": "boolean", "default": False},
          }, ["project_path"]),
    _tool("configure_studio", "Persist machine-local studio settings (tool paths, project roots, "
          "download root). Credentials are not accepted here.", {
              "selected_engine": ENGINE_ENUM,
              "selected_engine_path": {"type": "string"},
              "project_roots": {"type": "array", "items": {"type": "string"}},
              "blender_exe": {"type": "string"},
              "unity_exe": {"type": "string"},
              "unreal_editor_cmd": {"type": "string"},
              "godot_exe": {"type": "string"},
              "download_root": {"type": "string"},
              "allow_overwrite": {"type": "boolean"},
          }),
    _tool("list_studio_projects", "Discover game projects under the provided or configured roots.", {
        "roots": {"type": "array", "items": {"type": "string"}},
    }),
    _tool("read_studio_audit", "Read the append-only audit log of write/generation actions.", {
        "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 1000},
    }),
    # blender
    _tool("blender_info", "Probe the real Blender executable and report version and addons.", {
        "blender_exe": {"type": "string"},
    }),
    _tool("blender_inspect_blend", "Inspect objects, meshes, UVs, materials, armatures, actions and "
          "missing images in a .blend file.", {
              "blend_file": {"type": "string"},
              "max_objects": {"type": "integer", "default": 500, "minimum": 1, "maximum": 5000},
          }, ["blend_file"]),
    _tool("blender_validate_asset", "Validate a .blend for engine import (triangles, UVs, transforms, "
          "textures, armature, bounds).", {
              "blend_file": {"type": "string"},
              "max_triangles": {"type": "integer", "default": 150000, "minimum": 1},
          }, ["blend_file"]),
    _tool("blender_export_asset", "Export a .blend to glb/gltf/fbx/obj/stl/usdz and return a hash.", {
        "blend_file": {"type": "string"},
        "output": {"type": "string"},
        "format": {"type": "string", "enum": ["glb", "gltf", "fbx", "obj", "stl", "usdz"],
                   "default": "glb"},
        "selected_only": {"type": "boolean", "default": False},
        "apply_transforms": {"type": "boolean", "default": True},
        "scale": {"type": "number", "default": 1.0},
        "confirm_overwrite": OVERWRITE,
    }, ["blend_file", "output"]),
    _tool("blender_import_asset", "Import fbx/glb/gltf/obj/blend/usd into a fresh Blender scene and "
          "optionally save a .blend.", {
              "source": {"type": "string"},
              "save_blend": {"type": "string"},
              "confirm_overwrite": OVERWRITE,
          }, ["source"]),
    _tool("blender_render_preview", "Render a PNG preview of a .blend for visual verification.", {
        "blend_file": {"type": "string"},
        "output_png": {"type": "string"},
        "width": {"type": "integer", "default": 640, "minimum": 16, "maximum": 4096},
        "height": {"type": "integer", "default": 360, "minimum": 16, "maximum": 4096},
        "frame": {"type": ["integer", "null"]},
        "confirm_overwrite": OVERWRITE,
    }, ["blend_file", "output_png"]),
    _tool("blender_create_environment_blockout", "Generate a procedural terrain blockout "
          "(jungle/forest/desert/alpine) with trees, rocks, water, sun and camera. This is a "
          "blockout, not production environment art.", {
              "preset": {"type": "string", "enum": ["jungle", "forest", "desert", "alpine"],
                         "default": "jungle"},
              "seed": {"type": "integer", "default": 1337},
              "size": {"type": "number", "default": 100.0, "minimum": 5, "maximum": 2000},
              "segments": {"type": "integer", "default": 64, "minimum": 16, "maximum": 256},
              "tree_count": {"type": "integer", "default": 60, "minimum": 0, "maximum": 5000},
              "rock_count": {"type": "integer", "default": 25, "minimum": 0, "maximum": 5000},
              "water_level": {"type": "number", "default": 0.0},
              "include_water": {"type": "boolean", "default": True},
              "save_blend": {"type": "string"},
              "export_glb": {"type": "string"},
              "render_png": {"type": "string"},
              "confirm_overwrite": OVERWRITE,
          }),
    _tool("blender_run_python", "Execute arbitrary Blender Python in background mode. Requires "
          "explicit confirm=true; set __mcp_result to return data.", {
              "code": {"type": "string"},
              "blend_file": {"type": "string"},
              "save": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
              "timeout": {"type": "integer", "default": 900, "minimum": 10, "maximum": 7200},
          }, ["code"]),
    # meshy
    _tool("meshy_setup_guide", "Explain how to create a Meshy API key, where to store it, how "
          "to rotate it, and whether one is currently configured. Never returns the key."),
    _tool("meshy_configure_api_key", "Validate a Meshy API key against the balance endpoint, "
          "then save it in the studio's private config directory outside the repository. "
          "Requires confirm=true. The environment variable MESHY_API_KEY overrides it.", {
              "api_key": {"type": "string", "maxLength": 512,
                          "description": "The Meshy key. It is validated and stored locally; "
                                         "tools never return it."},
              "confirm": CONFIRM,
          }, ["api_key", "confirm"]),
    _tool("meshy_clear_api_key", "Delete the locally saved Meshy key. An environment variable "
          "cannot be removed by this tool and still takes precedence."),
    _tool("meshy_balance", "Read the Meshy credit balance. Requires a configured API key."),
    _tool("meshy_text_to_3d", "Create a Meshy text-to-3D preview or refine task. Spends credits; "
          "requires confirm=true.", {
              "prompt": {"type": "string", "maxLength": 800},
              "mode": {"type": "string", "enum": ["preview", "refine"], "default": "preview"},
              "preview_task_id": {"type": "string"},
              "ai_model": {"type": "string"},
              "target_polycount": {"type": "integer", "minimum": 100, "maximum": 300000},
              "should_remesh": {"type": ["boolean", "null"]},
              "pose_mode": {"type": "string"},
              "target_formats": {"type": "array", "items": {"type": "string"}},
              "enable_pbr": {"type": "boolean", "default": True},
              "texture_resolution": {"type": "string", "enum": ["2k", "4k", "8k"]},
              "texture_prompt": {"type": "string"},
              "confirm": CONFIRM,
          }, ["confirm"]),
    _tool("meshy_rig_character", "Rig a humanoid model through Meshy. Spends credits; confirm=true.", {
        "input_task_id": {"type": "string"},
        "model_url": {"type": "string", "description": "Public https model URL"},
        "height_meters": {"type": "number", "default": 1.7, "minimum": 0.2, "maximum": 10},
        "confirm": CONFIRM,
    }, ["confirm"]),
    _tool("meshy_animation_library", "Search Meshy's animation library (read-only).", {
        "search": {"type": "string"},
        "category": {"type": "string"},
        "action_ids": {"type": "array", "items": {"type": "integer"}},
    }),
    _tool("meshy_create_animation", "Apply library actions or a motion task to a Meshy rig. Spends "
          "credits; confirm=true.", {
              "rig_task_id": {"type": "string"},
              "action_id": {"type": "integer"},
              "action_ids": {"type": "array", "items": {"type": "integer"}},
              "motion_task_id": {"type": "string"},
              "confirm": CONFIRM,
          }, ["rig_task_id", "confirm"]),
    _tool("meshy_task_status", "Read one Meshy task's status, progress, error and output URLs.", {
        "task_id": {"type": "string"},
        "task_type": {"type": "string",
                      "enum": ["text-to-3d", "rigging", "animation"]},
    }, ["task_id", "task_type"]),
    _tool("meshy_wait_for_task", "Poll a Meshy task until it finishes or the timeout is reached.", {
        "task_id": {"type": "string"},
        "task_type": {"type": "string",
                      "enum": ["text-to-3d", "rigging", "animation"]},
        "timeout_seconds": {"type": "integer", "default": 120, "minimum": 0, "maximum": 1800},
        "poll_seconds": {"type": "number", "default": 5, "minimum": 1, "maximum": 60},
    }, ["task_id", "task_type"]),
    _tool("meshy_download_output", "Download a finished Meshy output to a local path and hash it.", {
        "task_id": {"type": "string"},
        "task_type": {"type": "string",
                      "enum": ["text-to-3d", "rigging", "animation"]},
        "output_key": {"type": "string", "description": "Key from meshy_task_status output_urls"},
        "destination": {"type": "string"},
    }, ["task_id", "task_type", "output_key", "destination"]),
    _tool("meshy_generate_asset", "Create a preview and optionally refine it in one call. Spends "
          "credits; confirm=true.", {
              "prompt": {"type": "string", "maxLength": 800},
              "refine": {"type": "boolean", "default": False},
              "wait": {"type": "boolean", "default": True},
              "timeout_seconds": {"type": "integer", "default": 180, "minimum": 0,
                                  "maximum": 1800},
              "ai_model": {"type": "string"},
              "target_polycount": {"type": "integer", "minimum": 100, "maximum": 300000},
              "pose_mode": {"type": "string"},
              "enable_pbr": {"type": "boolean", "default": True},
              "texture_resolution": {"type": "string", "enum": ["2k", "4k", "8k"]},
              "confirm": CONFIRM,
          }, ["prompt", "confirm"]),
    # assets
    _tool("list_asset_providers", "Show which asset providers have real automated search/download "
          "and which are manual-only, with license notes."),
    _tool("search_assets", "Search licensed assets. Poly Haven is keyless; Sketchfab needs "
          "SKETCHFAB_TOKEN. Manual-only providers are reported, never simulated.", {
              "query": {"type": "string"},
              "kind": {"type": "string",
                       "enum": ["model", "texture", "hdri", "character", "environment", "animation"],
                       "default": "model"},
              "provider": {"type": "string",
                           "enum": ["auto", "polyhaven", "sketchfab", "meshy", "mixamo",
                                    "kenney", "opengameart", "unity_asset_store", "fab"],
                           "default": "auto"},
              "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 60},
              "max_polycount": {"type": "integer", "minimum": 1},
          }, ["query"]),
    _tool("download_polyhaven_asset", "Download a CC0 Poly Haven asset with dependencies, verify "
          "MD5 and write provenance.json. confirm=true.", {
              "asset_id": {"type": "string"},
              "format": {"type": "string", "default": "glb"},
              "resolution": {"type": "string", "default": "2k"},
              "destination_dir": {"type": "string"},
              "max_bytes": {"type": "integer", "default": 536870912, "minimum": 1},
              "confirm": CONFIRM,
          }, ["asset_id", "confirm"]),
    _tool("inspect_asset_license", "Read provider/asset license information. Sketchfab and "
          "manual-only providers require per-asset human review.", {
              "provider": {"type": "string"},
              "asset_id": {"type": "string"},
          }, ["provider"]),
    _tool("validate_asset_file", "Validate glTF/GLB/OBJ/STL/FBX/BLEND/image files and report "
          "triangles, UVs, textures, animations and issues.", {
              "path": {"type": "string"},
              "max_triangles": {"type": "integer", "minimum": 1},
          }, ["path"]),
    _tool("create_asset_manifest", "Hash files and write an asset manifest with sizes and extensions.", {
        "paths": {"type": "array", "items": {"type": "string"}},
        "destination": {"type": "string"},
    }, ["paths"]),
    # animations
    _tool("inspect_animation_rig", "Classify a GLB/glTF rig (humanoid/quadruped/generic), list "
          "joints, clips and durations.", {
              "path": {"type": "string"},
          }, ["path"]),
    _tool("create_animation_retarget_map", "Build a bone-name retarget map between a character and "
          "an animated file, optionally writing JSON.", {
              "character_path": {"type": "string"},
              "animation_path": {"type": "string"},
              "destination": {"type": "string"},
          }, ["character_path", "animation_path"]),
    _tool("check_animation_compatibility", "Check whether an animation's skeleton is compatible "
          "with a character skeleton.", {
              "character_path": {"type": "string"},
              "animation_path": {"type": "string"},
          }, ["character_path", "animation_path"]),
    _tool("list_animation_sources", "List animation sources with their real availability and "
          "manual-only limitations."),
    # engines
    _tool("stage_asset_for_engine", "Copy an asset into a Unity/Unreal/Godot project and record "
          "provenance. Staging is not import. Requires confirm=true.", {
              "source": {"type": "string"},
              "project_path": PROJECT_PATH,
              "engine": ENGINE_ENUM,
              "relative_path": {"type": "string",
                                "description": "Destination relative to Assets/, Content/ or the "
                                               "Godot project root"},
              "confirm": CONFIRM,
              "confirm_overwrite": OVERWRITE,
          }, ["source", "project_path", "confirm"]),
    _tool("verify_staged_import", "Check real import evidence for a staged asset (.meta, .import, "
          "import cache) without claiming visual or runtime correctness.", {
              "project_path": PROJECT_PATH,
              "relative_path": {"type": "string"},
          }, ["project_path", "relative_path"]),
    _tool("engine_build", "Build a player through the engine CLI. Requires confirm=true. A produced "
          "artifact is not proof the game runs.", {
              "engine": ENGINE_ENUM,
              "project_path": PROJECT_PATH,
              "target": {"type": "string", "description": "Unity build target"},
              "preset": {"type": "string", "description": "Godot export preset"},
              "output_path": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["engine", "project_path", "output_path", "confirm"]),
    _tool("unity_editor_status", "Show live Unity Editor connections through the Unity CLI."),
    _tool("unity_list_commands", "List Editor Pipeline commands registered by an open Unity editor.", {
        "project_path": PROJECT_PATH,
    }, ["project_path"]),
    _tool("unity_run_command", "Run a registered Unity Editor Pipeline command. Can modify the "
          "project; requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "command": {"type": "string"},
              "arguments": {"type": "array", "items": {"type": "string"}},
              "timeout": {"type": "integer", "default": 300, "minimum": 5, "maximum": 3600},
              "confirm": CONFIRM,
          }, ["project_path", "command", "confirm"]),
    _tool("unity_batch_refresh", "Run Unity batch import (-quit -batchmode -nographics) and report "
          "the log. Requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "confirm"]),
    _tool("unity_run_tests", "Run Unity EditMode/PlayMode tests and parse the NUnit report. Requires "
          "confirm=true.", {
              "project_path": PROJECT_PATH,
              "mode": {"type": "string", "enum": ["EditMode", "PlayMode"], "default": "EditMode"},
              "filter": {"type": "string"},
              "output": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "confirm"]),
    _tool("unity_build", "Build a Unity player with the Unity CLI and verify artifacts exist. "
          "Requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "target": {"type": "string"},
              "output_path": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "allow_dirty_build": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
          }, ["project_path", "target", "output_path", "confirm"]),
    _tool("godot_batch_import", "Run Godot headless import and check the .godot import cache. "
          "Requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "confirm"]),
    _tool("godot_build", "Export a Godot project with an existing export preset. Requires "
          "confirm=true.", {
              "project_path": PROJECT_PATH,
              "preset": {"type": "string"},
              "output_path": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "preset", "output_path", "confirm"]),
    _tool("unreal_status", "Inspect an Unreal project and state the staged-only automation limits.", {
        "project_path": PROJECT_PATH,
    }, ["project_path"]),
]

HANDLERS = {
    "studio_info": tool_studio_info,
    "detect_system": tool_detect_system,
    "detect_game_engines": tool_detect_game_engines,
    "list_available_engines": tool_list_available_engines,
    "select_game_engine": tool_select_game_engine,
    "inspect_engine_capabilities": tool_inspect_engine_capabilities,
    "inspect_game_project": tool_inspect_game_project,
    "configure_studio": tool_configure_studio,
    "list_studio_projects": tool_list_studio_projects,
    "read_studio_audit": tool_read_studio_audit,
    "blender_info": tool_blender_info,
    "blender_inspect_blend": tool_blender_inspect,
    "blender_validate_asset": tool_blender_validate,
    "blender_export_asset": tool_blender_export,
    "blender_import_asset": tool_blender_import,
    "blender_render_preview": tool_blender_render,
    "blender_create_environment_blockout": tool_blender_environment,
    "blender_run_python": tool_blender_run_python,
    "meshy_balance": tool_meshy_balance,
    "meshy_setup_guide": tool_meshy_setup,
    "meshy_configure_api_key": tool_meshy_configure,
    "meshy_clear_api_key": tool_meshy_clear,
    "meshy_text_to_3d": tool_meshy_text_to_3d,
    "meshy_rig_character": tool_meshy_rig,
    "meshy_animation_library": tool_meshy_animation_library,
    "meshy_create_animation": tool_meshy_create_animation,
    "meshy_task_status": tool_meshy_task_status,
    "meshy_wait_for_task": tool_meshy_wait,
    "meshy_download_output": tool_meshy_download,
    "meshy_generate_asset": tool_meshy_generate,
    "list_asset_providers": tool_asset_providers,
    "search_assets": tool_asset_search,
    "download_polyhaven_asset": tool_asset_download,
    "inspect_asset_license": tool_asset_license,
    "validate_asset_file": tool_asset_validate,
    "create_asset_manifest": tool_asset_manifest,
    "inspect_animation_rig": tool_animation_inspect,
    "create_animation_retarget_map": tool_animation_retarget_map,
    "check_animation_compatibility": tool_animation_compatibility,
    "list_animation_sources": tool_animation_sources,
    "stage_asset_for_engine": tool_engine_stage,
    "verify_staged_import": tool_engine_verify,
    "engine_build": tool_engine_build,
    "unity_editor_status": tool_unity_status,
    "unity_list_commands": tool_unity_commands,
    "unity_run_command": tool_unity_run_command,
    "unity_batch_refresh": tool_unity_refresh,
    "unity_run_tests": tool_unity_tests,
    "unity_build": tool_unity_build,
    "godot_batch_import": tool_godot_import,
    "godot_build": tool_godot_build,
    "unreal_status": tool_unreal_status,
}


# --------------------------------------------------------------------------
# MCP transport
# --------------------------------------------------------------------------
def text_result(payload: object, is_error: bool = False) -> dict:
    text = json.dumps(payload, indent=2, default=str)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n... [truncated]"
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _error(message: str, **extra) -> dict:
    return {"ok": False, "error": message, "generated_at": now_iso(), **extra}


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": (req.get("params") or {}).get(
                    "protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Real game-studio tools. Read studio_info and detect_game_engines first. "
                    "Never claim an asset is imported or a build is verified without evidence. "
                    "Paid Meshy calls and all project writes require explicit user approval."
                ),
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
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(_error(f"unknown tool: {name}"), True)}
        if not isinstance(arguments, dict):
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(_error("arguments must be an object"), True)}
        try:
            payload = handler(arguments)
            ok = bool(payload.get("ok", True)) if isinstance(payload, dict) else True
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(payload, not ok)}
        except ToolError as exc:
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(_error(str(exc), tool=name), True)}
        except Exception as exc:  # keep the transport alive, log the trace to stderr
            log(f"{name} failed: {exc}")
            traceback.print_exc(file=sys.stderr)
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(
                        _error(f"unexpected failure in {name}: {exc}", tool=name), True)}
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": req_id, "result": {key: []}}
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    log(f"starting {SERVER_NAME} {SERVER_VERSION}")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"invalid JSON: {exc}")
            continue
        if isinstance(request, list):
            responses = [response for response in
                         (handle(item) for item in request if isinstance(item, dict))
                         if response is not None]
        else:
            responses = handle(request) if isinstance(request, dict) else None
        if responses:
            sys.stdout.write(json.dumps(responses, default=str) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
