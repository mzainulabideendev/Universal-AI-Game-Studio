"""Shared deterministic helpers for the Phase 2 specialist agents."""

from __future__ import annotations

QUALITY_PROFILES = {
    "prototype": {
        "target_fps": 60, "max_draw_calls": 150, "texture_budget_mb": 128,
        "character_triangles": 12_000, "lod_levels": 2,
        "environment_props": 80,
    },
    "standard": {
        "target_fps": 60, "max_draw_calls": 300, "texture_budget_mb": 512,
        "character_triangles": 30_000, "lod_levels": 3,
        "environment_props": 200,
    },
    "high": {
        "target_fps": 60, "max_draw_calls": 600, "texture_budget_mb": 1024,
        "character_triangles": 60_000, "lod_levels": 4,
        "environment_props": 450,
    },
    "cinematic": {
        "target_fps": 30, "max_draw_calls": 1000, "texture_budget_mb": 2048,
        "character_triangles": 120_000, "lod_levels": 4,
        "environment_props": 700,
    },
}

ENGINE_PLANNING_CAPABILITIES = {
    "unity": {
        "scenes": True, "physics": True, "input": True, "animation": True,
        "ui": True, "audio": True, "build_windows": True, "build_android": True,
        "editor_automation": "available-with-pipeline-package",
    },
    "godot": {
        "scenes": True, "physics": True, "input": True, "animation": True,
        "ui": True, "audio": True, "build_windows": "implemented-unverified",
        "build_android": "unverified", "editor_automation": False,
    },
    "unreal": {
        "scenes": "planning-only", "physics": "planning-only", "input": "planning-only",
        "animation": "planning-only", "ui": "planning-only", "audio": "planning-only",
        "build_windows": False, "build_android": False, "editor_automation": False,
    },
}


def quality_profile(name: str | None) -> dict:
    key = (name or "prototype").strip().lower()
    return dict(QUALITY_PROFILES.get(key, QUALITY_PROFILES["prototype"])), (
        key if key in QUALITY_PROFILES else "prototype")


def requirement_ids(brief: dict) -> list[str]:
    ids = []
    for requirement in brief.get("requirements") or []:
        if isinstance(requirement, dict) and requirement.get("id"):
            ids.append(str(requirement["id"]))
    return ids


def clean_values(brief: dict, key: str, default: list[str] | None = None) -> list[str]:
    values = [str(item) for item in (brief.get(key) or []) if str(item).strip()]
    return values or list(default or [])


def excluded_values(brief: dict) -> list[str]:
    values = []
    for item in brief.get("exclusions") or []:
        if isinstance(item, dict):
            value = item.get("value")
        else:
            value = item
        if value:
            values.append(str(value).strip().lower())
    return sorted(set(values))


def has_exclusion(brief: dict, *names: str) -> bool:
    excluded = set(excluded_values(brief))
    return any(name.lower() in excluded for name in names)
