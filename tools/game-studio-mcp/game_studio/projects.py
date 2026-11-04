"""Read-only inspection of real Unity, Unreal and Godot projects."""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

from .detect import detect_godot, detect_unity, detect_unreal
from .util import (
    command_version,
    expand,
    file_stats,
    human_bytes,
    read_json,
    read_text,
    require_path,
    run_command,
)


def detect_project_engine(project_path: str) -> str | None:
    if os.path.isfile(os.path.join(project_path, "ProjectSettings", "ProjectVersion.txt")):
        return "unity"
    if os.path.isfile(os.path.join(project_path, "project.godot")):
        return "godot"
    try:
        with os.scandir(project_path) as entries:
            if any(e.is_file() and e.name.lower().endswith(".uproject") for e in entries):
                return "unreal"
    except OSError:
        pass
    return None


def _yaml_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip('"').strip("'")
    return value if value else None


def _list_from_yaml(text: str, key: str) -> list[str]:
    values = re.findall(rf"^\s*-\s*(.+?)\s*$", text, re.MULTILINE)
    return [v.strip().strip('"') for v in values]


def _count_files(root: str, extensions: tuple[str, ...]) -> int:
    if not os.path.isdir(root):
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("Library", "Temp", "obj", "Logs")]
        total += sum(1 for name in filenames if name.lower().endswith(extensions))
    return total


def _find_missing_scripts(assets_root: str, limit_files: int = 3000) -> dict:
    """Unity marks a missing script reference with m_Script fileID 0."""
    pattern = re.compile(r"m_Script:\s*\{fileID:\s*0\}")
    offenders = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(assets_root):
        dirnames[:] = [d for d in dirnames if d not in ("Library", "Temp", "Plugins")]
        for name in filenames:
            if not name.lower().endswith((".unity", ".prefab")):
                continue
            scanned += 1
            if scanned > limit_files:
                return {"scanned": scanned, "truncated": True, "files": offenders}
            path = os.path.join(dirpath, name)
            try:
                if pattern.search(read_text(path, 2 * 1024 * 1024)):
                    offenders.append(os.path.relpath(path, assets_root).replace("\\", "/"))
            except OSError:
                continue
    return {"scanned": scanned, "truncated": False, "files": offenders}


def _unity_editor_status() -> dict | None:
    unity = _find_unity_cli()
    if not unity:
        return None
    result = run_command([unity, "status", "--format", "json"], timeout=30)
    if not result.get("ok"):
        return {"available": True, "connected": False,
                "detail": (result.get("stdout") or result.get("stderr") or "").strip()[:2000]}
    text = (result.get("stdout") or "").strip()
    if not text:
        return {"available": True, "connected": False, "detail": "no connected editor"}
    try:
        return {"available": True, "connected": True, "editors": json.loads(text)}
    except json.JSONDecodeError:
        return {"available": True, "connected": True, "raw": text[:4000]}


def _find_unity_cli() -> str | None:
    for candidate in (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Unity", "bin", "unity.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Unity", "bin", "unity.exe"),
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    import shutil
    return shutil.which("unity")


def inspect_unity_project(project_path: str, *, include_editor_status: bool = False) -> dict:
    project = require_path(project_path, kind="dir", label="project_path")
    version_file = os.path.join(project, "ProjectSettings", "ProjectVersion.txt")
    version_text = read_text(version_file) if os.path.isfile(version_file) else ""
    editor_version = _yaml_value(version_text, "m_EditorVersion")
    revision = _yaml_value(version_text, "m_EditorVersionWithRevision") or _yaml_value(version_text, "m_EditorVersionRevision")

    manifest_path = os.path.join(project, "Packages", "manifest.json")
    dependencies = {}
    if os.path.isfile(manifest_path):
        try:
            manifest = read_json(manifest_path)
            dependencies = manifest.get("dependencies", {}) if isinstance(manifest, dict) else {}
        except (OSError, json.JSONDecodeError):
            dependencies = {}
    render_pipeline = "built-in"
    if "com.unity.render-pipelines.universal" in dependencies:
        render_pipeline = "urp"
    elif "com.unity.render-pipelines.high-definition" in dependencies:
        render_pipeline = "hdrp"
    input_system = "unknown"
    settings_text = ""
    settings_path = os.path.join(project, "ProjectSettings", "ProjectSettings.asset")
    if os.path.isfile(settings_path):
        settings_text = read_text(settings_path, 4 * 1024 * 1024)
        raw_input = _yaml_value(settings_text, "activeInputHandler")
        input_system = {"0": "legacy", "1": "new-input-system", "2": "both"}.get(raw_input, raw_input or "unknown")

    assets = os.path.join(project, "Assets")
    scenes = glob.glob(os.path.join(assets, "**", "*.unity"), recursive=True)
    prefabs = glob.glob(os.path.join(assets, "**", "*.prefab"), recursive=True)
    scenes_out = []
    for scene in sorted(scenes)[:100]:
        scenes_out.append({
            "path": os.path.relpath(scene, project).replace("\\", "/"),
            "bytes": os.path.getsize(scene),
        })
    missing_scripts = _find_missing_scripts(assets) if os.path.isdir(assets) else {"files": [], "scanned": 0}
    tests = [p for p in glob.glob(os.path.join(assets, "**", "*Test*.cs"), recursive=True)]
    asmdefs = glob.glob(os.path.join(assets, "**", "*.asmdef"), recursive=True)
    packages_locked = os.path.isfile(os.path.join(project, "Packages", "packages-lock.json"))

    warnings = []
    if not editor_version:
        warnings.append("ProjectVersion.txt is missing or unreadable")
    if missing_scripts.get("files"):
        warnings.append(f"{len(missing_scripts['files'])} scene/prefab files reference missing scripts")
    if not dependencies:
        warnings.append("Packages/manifest.json not found or empty")
    if not os.path.isdir(assets):
        warnings.append("Assets/ folder is missing")

    result = {
        "ok": editor_version is not None and os.path.isdir(assets),
        "engine": "unity",
        "project_path": project,
        "name": _yaml_value(settings_text, "productName") or os.path.basename(project),
        "company": _yaml_value(settings_text, "companyName"),
        "editor_version": editor_version,
        "editor_revision": revision,
        "render_pipeline": render_pipeline,
        "input_system": input_system,
        "packages": dependencies,
        "packages_locked": packages_locked,
        "structure": {
            "assets_bytes": file_stats(assets) if os.path.isdir(assets) else None,
            "scenes": scenes_out,
            "scene_count": len(scenes),
            "prefab_count": len(prefabs),
            "script_count": _count_files(assets, (".cs",)),
            "asmdef_count": len(asmdefs),
            "test_file_count": len(tests),
            "streaming_assets": os.path.isdir(os.path.join(assets, "StreamingAssets")),
            "editor_folder": os.path.isdir(os.path.join(assets, "Editor")),
        },
        "missing_scripts": missing_scripts,
        "warnings": warnings,
        "engine_installation": detect_unity(),
        "capabilities": {
            "editor_mcp_possible": "com.unity.pipeline" in dependencies,
            "build_cli_possible": _find_unity_cli() is not None,
            "tests_cli_possible": _find_unity_cli() is not None,
        },
    }
    if include_editor_status:
        result["editor_status"] = _unity_editor_status()
    return result


def inspect_unreal_project(project_path: str, *, include_editor_status: bool = False) -> dict:
    project = require_path(project_path, kind="dir", label="project_path")
    uprojects = glob.glob(os.path.join(project, "*.uproject"))
    if not uprojects:
        return {"ok": False, "engine": "unreal", "error": "no .uproject file found", "project_path": project}
    descriptor_path = uprojects[0]
    try:
        descriptor = read_json(descriptor_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "engine": "unreal", "error": f"unreadable .uproject: {exc}", "project_path": project}
    config_dir = os.path.join(project, "Config")
    configs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(config_dir, "*.ini")))
    content = os.path.join(project, "Content")
    maps = glob.glob(os.path.join(content, "**", "*.umap"), recursive=True)
    plugins_enabled = []
    for plugin in descriptor.get("Plugins", []) or []:
        if isinstance(plugin, dict) and plugin.get("Enabled"):
            plugins_enabled.append(plugin.get("Name"))
    association = descriptor.get("EngineAssociation")
    installs = detect_unreal()
    matching = [i for i in installs.get("installs", [])
                if association and association in (i.get("version"), os.path.basename(i.get("root", "")))]
    warnings = []
    if not configs:
        warnings.append("Config/*.ini missing; project may be incomplete")
    if not os.path.isdir(content):
        warnings.append("Content/ folder missing")
    if not matching:
        warnings.append(f"EngineAssociation {association!r} has no detected matching engine install")
    return {
        "ok": True,
        "engine": "unreal",
        "project_path": project,
        "name": descriptor.get("FileVersion") and os.path.splitext(os.path.basename(descriptor_path))[0],
        "descriptor": descriptor_path,
        "engine_association": association,
        "plugins_enabled": plugins_enabled,
        "configs": configs,
        "structure": {
            "content_bytes": file_stats(content) if os.path.isdir(content) else None,
            "map_count": len(maps),
            "source_cpp_count": _count_files(os.path.join(project, "Source"), (".cpp", ".h")),
        },
        "matching_installs": matching,
        "warnings": warnings,
        "capabilities": {
            "editor_cmd": bool(matching),
            "python_automation": bool(matching),
            "import_verified": False,
        },
        "editor_status": None if not include_editor_status else {
            "note": "Unreal has no bundled read-only status command; check the running editor manually.",
        },
    }


def _parse_godot_project(path: str) -> dict:
    values = {}
    section = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[f"{section}.{key.strip()}" if section else key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return values


def inspect_godot_project(project_path: str, *, include_editor_status: bool = False) -> dict:
    project = require_path(project_path, kind="dir", label="project_path")
    project_file = os.path.join(project, "project.godot")
    if not os.path.isfile(project_file):
        return {"ok": False, "engine": "godot", "error": "project.godot not found", "project_path": project}
    values = _parse_godot_project(project_file)
    scenes = glob.glob(os.path.join(project, "**", "*.tscn"), recursive=True)
    tscn = [s for s in scenes if ".godot" not in s.split(os.sep)]
    warnings = []
    if not values.get("application.run/main_scene") and not tscn:
        warnings.append("No main scene configured and no .tscn files found")
    if not os.path.isdir(os.path.join(project, ".godot")):
        warnings.append(".godot import cache missing (project has not been imported by the editor yet)")
    return {
        "ok": True,
        "engine": "godot",
        "project_path": project,
        "name": values.get("application.config/name"),
        "config_version": values.get("config_version"),
        "main_scene": values.get("application.run/main_scene"),
        "renderer": values.get("rendering.renderer/rendering_method"),
        "features": values.get("application.config/features"),
        "structure": {
            "scene_count": len(tscn),
            "scripts": _count_files(project, (".gd", ".cs")),
            "export_presets": os.path.isfile(os.path.join(project, "export_presets.cfg")),
            "bytes": file_stats(project),
        },
        "warnings": warnings,
        "engine_installation": detect_godot(),
        "capabilities": {
            "headless_import": detect_godot().get("state") == "verified",
            "export_presets_configured": os.path.isfile(os.path.join(project, "export_presets.cfg")),
        },
        "editor_status": None if not include_editor_status else {
            "note": "Godot has no editor status server; use headless commands.",
        },
    }


def inspect_game_project(project_path: str, *, include_editor_status: bool = False) -> dict:
    project = require_path(project_path, kind="dir", label="project_path")
    kind = detect_project_engine(project)
    if kind == "unity":
        return inspect_unity_project(project, include_editor_status=include_editor_status)
    if kind == "unreal":
        return inspect_unreal_project(project, include_editor_status=include_editor_status)
    if kind == "godot":
        return inspect_godot_project(project, include_editor_status=include_editor_status)
    return {
        "ok": False,
        "error": "unrecognised game project",
        "project_path": project,
        "expected": ["ProjectSettings/ProjectVersion.txt (Unity)",
                     "project.godot (Godot)", "*.uproject (Unreal)"],
        "top_level": sorted(os.listdir(project))[:50],
    }
