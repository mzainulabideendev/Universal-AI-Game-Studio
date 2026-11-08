#!/usr/bin/env python3
"""V6 Phase 4 independent audit.

Runs the full test suite, verifies the committed Phase 4 evidence reports and
artifacts, checks quality-tier measurability, Phase 2 agent integration,
protected V4/V5 hashes, MCP tool/handler parity and provenance honesty, then
writes reports/v6-phase4-audit.json.

No network call, no paid request, no asset download, no commit.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(SERVER_DIR))

import server  # noqa: E402

REPORTS = ROOT / "reports"
DELIVERABLES = [
    "V6-PHASE-4-ENVIRONMENT-GENERATION.md",
    "reports/v6-environment-generation.json",
    "reports/v6-environment-validation.json",
    "reports/v6-environment-provenance.json",
    "reports/v6-phase4-audit.json",
    "scripts/v6-phase4-demo.py",
    "scripts/v6-phase4-audit.py",
    "tools/game-studio-mcp/game_studio/environment_spec.py",
    "tools/game-studio-mcp/game_studio/environment_pipeline.py",
    "tools/game-studio-mcp/tests/test_v6_phase4_environment_spec.py",
    "tools/game-studio-mcp/tests/test_v6_phase4_pipeline.py",
]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sh(args: list[str], *, timeout: int = 2400) -> dict:
    started = time.time()
    proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                          timeout=timeout)
    return {
        "command": " ".join(args),
        "exit_code": proc.returncode,
        "duration_seconds": round(time.time() - started, 1),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def git(*args: str) -> str:
    return (sh(["git", *args], timeout=120)["stdout"] or "").strip()


def run_tests() -> dict:
    result = sh([sys.executable, "-m", "unittest", "discover",
                 "-s", "tools/game-studio-mcp/tests", "-q"])
    output = (result["stdout"] or "") + "\n" + (result["stderr"] or "")
    match = re.search(r"Ran (\d+) tests?", output)
    ok = re.search(r"^OK\b", output, re.MULTILINE) is not None
    return {
        "result": "OK" if ok and result["exit_code"] == 0 else "FAILED",
        "tests": int(match.group(1)) if match else None,
        "exit_code": result["exit_code"],
        "duration_seconds": result["duration_seconds"],
        "tail": output.strip().splitlines()[-3:],
        "output_tail": (None if ok and result["exit_code"] == 0
                        else output.strip()[-20000:]),
    }


def preservation(baseline: dict) -> dict:
    v4 = {}
    v4_ok = True
    for relative, entry in baseline["v4_checkpoint"]["files"].items():
        actual = sha256(ROOT / relative)
        matches = actual == entry.get("sha256")
        v4_ok = v4_ok and matches
        v4[relative] = {"expected": entry.get("sha256"), "actual": actual,
                        "matches": matches}
    v5 = {}
    v5_ok = True
    for relative, entry in baseline["v5_checkpoint"]["artifacts"].items():
        path = ROOT / relative
        actual = sha256(path)
        matches = path.is_file() and actual == entry.get("sha256")
        v5_ok = v5_ok and matches
        v5[relative] = {"exists": path.is_file(), "expected": entry.get("sha256"),
                        "actual": actual, "matches": matches}
    return {
        "v4_commit": baseline["v4_checkpoint"]["commit"],
        "v4_ok": v4_ok,
        "v4_files": len(v4),
        "v5_ok": v5_ok,
        "v5_artifacts": len(v5),
        "details": {"v4": v4, "v5": v5},
    }


def artifact_checks(generation: dict) -> dict:
    details = {}
    ok = True
    for tier, row in (generation.get("quality_tiers") or {}).items():
        for name, artifact in (row.get("artifacts") or {}).items():
            raw = artifact.get("path")
            if raw is None:
                continue
            path = ROOT / raw
            exists = path.is_file()
            actual = sha256(path) if exists else None
            matches = exists and actual == artifact.get("sha256")
            ok = ok and matches
            details[f"{tier}:{name}"] = {
                "path": raw, "exists": exists, "expected": artifact.get("sha256"),
                "actual": actual, "matches": matches,
            }
    return {"ok": ok, "artifacts": details}


def png_dimensions(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def main() -> int:
    started = time.time()
    baseline = json.loads((REPORTS / "v6-phase0-baseline.json")
                          .read_text(encoding="utf-8"))
    generation = json.loads((REPORTS / "v6-environment-generation.json")
                            .read_text(encoding="utf-8"))
    validation = json.loads((REPORTS / "v6-environment-validation.json")
                            .read_text(encoding="utf-8"))
    provenance = json.loads((REPORTS / "v6-environment-provenance.json")
                            .read_text(encoding="utf-8"))

    tests = run_tests()
    preserved = preservation(baseline)
    artifacts = artifact_checks(generation)

    tool_names = [tool["name"] for tool in server.TOOLS]
    mcp = {
        "tools": len(tool_names),
        "handlers": len(server.HANDLERS),
        "unique": len(set(tool_names)) == len(tool_names),
        "parity": set(tool_names) == set(server.HANDLERS),
        "environment_tools": sorted(name for name in tool_names
                                    if name.startswith("environment_")),
    }

    pipeline = generation.get("pipeline") or {}
    build = pipeline.get("build") or {}
    terrain = build.get("terrain") or {}
    vegetation = build.get("vegetation") or {}
    props = build.get("props") or {}
    water = build.get("water") or {}
    layout = build.get("layout") or {}
    collision = build.get("collision") or {}
    character = build.get("character") or {}
    images = build.get("images") or []
    stages = pipeline.get("stages") or {}
    tier_rows = generation.get("quality_tiers") or {}
    tier_segments = [row.get("terrain_vertices") or 0
                     for row in tier_rows.values()]
    tier_instances = [row.get("vegetation_instances") or 0
                      for row in tier_rows.values()]
    tier_textures = [row.get("texture_resolution") or 0
                     for row in tier_rows.values()]

    preview_overview = ROOT / "validation/v6-environment-pipeline/preview_overview.png"
    preview_spawn = ROOT / "validation/v6-environment-pipeline/preview_spawn.png"
    previews = {
        "overview_exists": preview_overview.is_file(),
        "spawn_exists": preview_spawn.is_file(),
        "overview_dimensions": list(png_dimensions(preview_overview) or []),
        "spawn_dimensions": list(png_dimensions(preview_spawn) or []),
    }

    agent = generation.get("phase2_agent") or {}
    provenance_clean = bool(
        provenance.get("declarations", {}).get("procedural")
        and not provenance.get("declarations", {}).get("ai_generated")
        and not provenance.get("declarations", {}).get(
            "external_assets_downloaded")
        and not (provenance.get("downloads") or [])
    )

    criteria = {
        "1_terrain_generation": (
            (stages.get("terrain-validated") or {}).get("status") == "passed"
            and int(terrain.get("triangles") or 0) > 1000),
        "2_terrain_non_flat": float(terrain.get("height_range_m") or 0) > 1.0,
        "3_vegetation_generation": (
            (stages.get("vegetation-validated") or {}).get("status") == "passed"
            and int(vegetation.get("instance_count") or 0) > 0),
        "4_rocks_and_props": (
            (stages.get("props-validated") or {}).get("status") == "passed"
            and int((props.get("counts") or {}).get("rock") or 0) > 0
            and int((props.get("counts") or {}).get("large_rock") or 0) > 0
            and int(props.get("ruin_objects") or 0) > 0),
        "5_water_feature": (
            (stages.get("water-validated") or {}).get("status") == "passed"
            and bool(water.get("present"))
            and int(water.get("triangles") or 0) > 0),
        "6_materials_validated": (
            (stages.get("materials-validated") or {}).get("status") == "passed"
            and len(build.get("textures") or []) >= 3),
        "7_lighting_atmosphere": (
            (stages.get("lighting-validated") or {}).get("status") == "passed"
            and bool((build.get("lighting") or {}).get("sun"))
            and bool((build.get("lighting") or {}).get("world"))),
        "8_playable_layout": (
            (stages.get("layout-validated") or {}).get("status") == "passed"
            and int(layout.get("waypoint_count") or 0) >= 2
            and bool(layout.get("landmark"))),
        "9_collision_and_spawn": (
            (stages.get("collision-validated") or {}).get("status") == "passed"
            and bool(collision.get("terrain_collider"))
            and bool(collision.get("obstacles"))),
        "10_character_integration": (
            (stages.get("character-integrated") or {}).get("status") == "passed"
            and bool(character.get("imported"))),
        "11_real_export": (
            bool((build.get("artifacts") or {}).get("blend", {}).get("exists"))
            and bool((build.get("artifacts") or {}).get("glb", {}).get("exists"))),
        "12_export_validation": (
            bool((build.get("glb_validation") or {}).get("ok"))
            and bool((build.get("gltf_validation") or {}).get("ok"))
            and bool((pipeline.get("reimport") or {}).get("ok"))),
        "13_previews": bool(previews["overview_exists"]
                            and previews["spawn_exists"]),
        "14_phase2_agent_integration": bool(
            agent.get("agent") == "EnvironmentAgent"
            and agent.get("deterministic_output")
            and agent.get("agent_reports_generated_content") is False
            and agent.get("pipeline_generated_content") is True),
        "15_previous_tests_preserved": bool(
            tests["result"] == "OK" and (tests["tests"] or 0) >= 320),
        "16_new_tests_pass": bool(
            tests["result"] == "OK" and (tests["tests"] or 0) > 320),
        "17_v4_v5_preserved": bool(preserved["v4_ok"] and preserved["v5_ok"]),
        "18_mcp_parity": bool(mcp["parity"] and mcp["unique"]),
        "19_audit_evidence": bool(
            artifacts["ok"] and provenance_clean and pipeline.get("ok") is True),
        "20_quality_tier_differences_measured": bool(
            len(tier_rows) >= 3
            and tier_segments == sorted(tier_segments)
            and len(set(tier_segments)) == len(tier_segments)
            and tier_textures == sorted(tier_textures)
            and len(set(tier_textures)) == len(tier_textures)
            and tier_instances == sorted(tier_instances)
            and len(set(tier_instances)) == len(tier_instances)),
    }

    deliverables = {relative: (ROOT / relative).is_file()
                    for relative in DELIVERABLES}
    all_criteria = all(criteria.values())
    verdict = "PASS" if (all_criteria and all(deliverables.values())) else "PARTIAL"

    audit = {
        "schema_version": 1,
        "phase": "V6 Phase 4 - environment generation audit",
        "generated_at": now(),
        "verdict": verdict,
        "all_criteria_passed": all_criteria,
        "criteria": criteria,
        "deliverables": deliverables,
        "repository": {
            "head": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "status_short": git("status", "--short").splitlines(),
            "commit_made": False,
        },
        "tests": tests,
        "preservation": preserved,
        "mcp": mcp,
        "artifacts": artifacts,
        "previews": previews,
        "provenance_honest": provenance_clean,
        "pipeline": {
            "status": pipeline.get("status"),
            "failed_stages": pipeline.get("failed_stages"),
            "terrain": terrain,
            "vegetation_instances": vegetation.get("instance_count"),
            "vegetation_counts": vegetation.get("counts"),
            "prop_counts": props.get("counts"),
            "water": {"present": water.get("present"),
                      "triangles": water.get("triangles"),
                      "width_m": water.get("width_m")},
            "character": {key: character.get(key) for key in (
                "imported", "height_m", "source_height_m", "scale_factor",
                "ground_contact_error_m", "intersects_terrain")},
            "textures": len(build.get("textures") or []),
            "images": len(images),
        },
        "quality_tiers": {
            tier: {
                "status": row.get("status"),
                "terrain_vertices": row.get("terrain_vertices"),
                "terrain_triangles": row.get("terrain_triangles"),
                "vegetation_instances": row.get("vegetation_instances"),
                "texture_resolution": row.get("texture_resolution"),
                "estimated_memory_mb": row.get("estimated_memory_mb"),
                "timings": row.get("timings"),
            }
            for tier, row in tier_rows.items()
        },
        "limitations": [
            "The environment is a stylized procedural prototype, not "
            "hand-authored production art.",
            "Water is visual-only with boundary metadata; no swimming or water "
            "physics are implemented.",
            "Navigation is metadata only; no runtime navmesh is implemented.",
            "Engine integration is export-prepared and structurally validated; "
            "no Unity/Godot/Unreal import was executed.",
            "Lighting/atmosphere is world haze plus fog metadata; volumetric fog "
            "is not rendered in the EEVEE previews.",
            "No AI provider was contacted and no external asset was downloaded.",
        ],
        "duration_seconds": round(time.time() - started, 1),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "v6-phase4-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"[phase4-audit] {verdict} ({sum(criteria.values())}/{len(criteria)} "
          f"criteria, tests={tests['tests']} {tests['result']})")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
