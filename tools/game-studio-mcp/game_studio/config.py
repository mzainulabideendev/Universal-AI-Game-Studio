"""Studio configuration, project registry and the audit trail.

Configuration lives outside the repository in the user's config directory so
machine-specific paths never get committed. API keys are deliberately not
stored here: Meshy and Sketchfab credentials are read from environment
variables at call time.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from .util import expand, now_iso, read_json, write_json

DEFAULT_ROOTS = {
    "windows": [
        r"D:\Unity Projects",
        r"C:\Unity Projects",
        r"D:\Projects",
    ],
    "macos": ["~/Unity Projects", "~/Projects"],
    "linux": ["~/Unity Projects", "~/projects"],
}


def platform_name() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def config_dir() -> str:
    override = os.environ.get("GAME_STUDIO_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = Path.home()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return os.path.join(base, "UniversalAIGameStudio")
    if sys.platform == "darwin":
        return str(home / "Library" / "Application Support" / "UniversalAIGameStudio")
    return os.environ.get("XDG_CONFIG_HOME", str(home / ".config")) + "/universal-game-studio"


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def audit_path() -> str:
    return os.path.join(config_dir(), "audit.jsonl")


DEFAULT_CONFIG = {
    "schema_version": 1,
    "selected_engine": None,
    "selected_engine_path": None,
    "project_roots": [],
    "blender_exe": None,
    "unity_exe": None,
    "unreal_editor_cmd": None,
    "godot_exe": None,
    "download_root": None,
    "allow_overwrite": False,
}


def load_config() -> dict:
    path = config_path()
    data = dict(DEFAULT_CONFIG)
    if os.path.isfile(path):
        try:
            loaded = read_json(path)
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    if not data.get("project_roots"):
        data["project_roots"] = [
            expand(root) for root in DEFAULT_ROOTS[platform_name()]
            if expand(root) and os.path.isdir(expand(root))
        ]
    if not data.get("download_root"):
        data["download_root"] = os.path.join(config_dir(), "downloads")
    return data


def save_config(updates: dict) -> dict:
    data = load_config()
    allowed = {
        "selected_engine", "selected_engine_path", "project_roots", "blender_exe",
        "unity_exe", "unreal_editor_cmd", "godot_exe", "download_root",
        "allow_overwrite",
    }
    unknown = set(updates) - allowed
    if unknown:
        raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
    for key, value in updates.items():
        if key == "project_roots":
            value = [expand(v) for v in value if expand(v)]
        elif key in ("blender_exe", "unity_exe", "unreal_editor_cmd", "godot_exe", "download_root"):
            value = expand(value) if value else None
        data[key] = value
    os.makedirs(config_dir(), exist_ok=True)
    write_json(config_path(), data)
    try:
        os.chmod(config_path(), stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return data


def audit(action: str, *, tool: str | None = None, details: dict | None = None) -> None:
    """Append an audit record. Never include credentials in ``details``."""
    record = {
        "timestamp": now_iso(),
        "action": action,
        "tool": tool,
        "details": details or {},
    }
    os.makedirs(config_dir(), exist_ok=True)
    with open(audit_path(), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def read_audit(limit: int = 50) -> list[dict]:
    path = audit_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []
