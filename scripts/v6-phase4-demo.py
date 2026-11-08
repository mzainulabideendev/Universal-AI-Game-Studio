#!/usr/bin/env python3
"""V6 Phase 4 real environment-generation demonstration.

Submits the required tropical-jungle request to the Phase 2 Environment Agent,
adapts its plan into a validated Phase 4 environment specification, and executes
the real local Blender pipeline: terrain, vegetation, rocks/props, river, PBR
materials, lighting/atmosphere, collision/spawn metadata, Phase 3 character
integration, exports, re-import validation and preview renders.

By default it builds LOW, MEDIUM and HIGH tiers so the quality-tier differences
are measured rather than asserted. The MEDIUM tier is written to the top-level
validation directory; LOW and HIGH go into tier subdirectories.

This script calls Blender and writes files. Run it explicitly with --confirm.
It makes no network calls and no paid API requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(SERVER_DIR))

from game_studio import environment_pipeline, environment_spec  # noqa: E402
from game_studio.agents.environment import EnvironmentAgent  # noqa: E402
from game_studio.blender import blender_info  # noqa: E402

REQUEST = (
    "Create a detailed stylized 3D tropical jungle adventure environment for a "
    "third-person monkey game. Include a natural hilly terrain, dense tropical "
    "vegetation, tall trees, grass, ferns, rocks, roots, fallen logs, a flowing "
    "river with river banks, natural sunlight, atmospheric depth, and a clear "
    "playable route. Place the JungleMonkey character at the starting point. The "
    "environment should feel like one cohesive game level and be suitable for "
    "further Unity integration."
)

VALIDATION_DIR = ROOT / "validation" / "v6-environment-pipeline"
REPORTS_DIR = ROOT / "reports"
BLENDER = r"D:\blender data\blender.exe"
CHARACTER = "validation/v6-character-pipeline/JungleMonkey.glb"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True,
                              timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def relative(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return candidate.name


def clean_output_dir(path: Path) -> None:
    resolved = path.resolve()
    allowed = (ROOT / "validation").resolve()
    if allowed not in resolved.parents and resolved != allowed:
        raise SystemExit(f"refusing to clean outside validation/: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def plan() -> tuple[dict, dict]:
    brief = {
        "summary": REQUEST,
        "quality_target": "standard",
        "environment": ["tropical jungle"],
        "engine": "unity",
        "platform": "windows",
        "mechanics": ["third-person exploration"],
        "requirements": [],
    }
    architecture = {"performance": {"budget": {"max_draw_calls": 320,
                                               "texture_budget_mb": 256}}}
    output = EnvironmentAgent().deterministic_output(
        {"brief": brief, "design": {"art_direction": "stylized tropical"},
         "architecture": architecture})
    spec = environment_spec.spec_from_agent_output(
        output, quality_tier="medium", target_engine="unity",
        character_path=CHARACTER)
    return output, spec


def tier_entry(tier: str, report: dict, output_dir: Path) -> dict:
    build = report.get("build") or {}
    terrain = build.get("terrain") or {}
    vegetation = build.get("vegetation") or {}
    props = build.get("props") or {}
    water = build.get("water") or {}
    counts = build.get("counts") or {}
    timings = {
        "blender_build_ms": build.get("duration_ms"),
        "export_processes": {name: value.get("duration_ms")
                             for name, value in (report.get("build") or {})
                             .get("export_processes", {}).items()},
        "total_pipeline_seconds": report.get("duration_seconds"),
    }
    return {
        "quality_tier": tier,
        "status": report.get("status"),
        "ok": report.get("ok"),
        "failed_stages": report.get("failed_stages"),
        "terrain_vertices": terrain.get("vertices"),
        "terrain_triangles": terrain.get("triangles"),
        "terrain_height_range_m": terrain.get("height_range_m"),
        "vegetation_instances": vegetation.get("instance_count"),
        "unique_vegetation_meshes": vegetation.get("unique_meshes"),
        "vegetation_counts": vegetation.get("counts"),
        "prop_counts": props.get("counts"),
        "river_triangles": water.get("triangles"),
        "objects": counts.get("objects"),
        "meshes": counts.get("meshes"),
        "instances": counts.get("instances"),
        "materials": counts.get("materials"),
        "textures": counts.get("textures"),
        "total_triangles": counts.get("triangles_total"),
        "texture_resolution": (report.get("spec") or {}).get(
            "textures", {}).get("resolution"),
        "estimated_memory_mb": (report.get("spec") or {}).get(
            "performance", {}).get("estimated_memory_mb"),
        "memory_label": "estimated, not measured",
        "timings": timings,
        "artifacts": {name: {"path": relative(entry.get("path")),
                             "bytes": entry.get("bytes"),
                             "sha256": entry.get("sha256")}
                      for name, entry in (build.get("artifacts") or {}).items()},
        "output_dir": relative(str(output_dir)),
    }


def validation_entry(report: dict) -> dict:
    build = report.get("build") or {}
    stages = report.get("stages") or {}
    return {
        "status": report.get("status"),
        "ok": report.get("ok"),
        "failed_stages": report.get("failed_stages"),
        "stage_status": {name: {"status": value.get("status"),
                                "issues": value.get("issues") or [],
                                "error": value.get("error")}
                         for name, value in stages.items()},
        "terrain": build.get("terrain"),
        "vegetation": {
            "requested": (stages.get("vegetation-validated") or {}).get("requested"),
            "counts": (stages.get("vegetation-validated") or {}).get("counts"),
            "instance_count": (stages.get("vegetation-validated") or {}).get(
                "instance_count"),
            "unique_meshes": (stages.get("vegetation-validated") or {}).get(
                "unique_meshes"),
            "spacing_violations": (stages.get("vegetation-validated") or {}).get(
                "spacing_violations"),
            "route_conflicts": (stages.get("vegetation-validated") or {}).get(
                "route_conflicts"),
        },
        "props": build.get("props"),
        "water": build.get("water"),
        "materials": {
            "count": len(build.get("materials") or []),
            "channels": build.get("pbr_channels"),
            "textures": build.get("textures"),
        },
        "lighting": build.get("lighting"),
        "layout": build.get("layout"),
        "collision": build.get("collision"),
        "character": build.get("character"),
        "glb_validation": build.get("glb_validation"),
        "gltf_validation": build.get("gltf_validation"),
        "reimport": report.get("reimport"),
        "character_source": report.get("character_source"),
        "export_processes": build.get("export_processes"),
        "render_process": build.get("render_process"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true",
                        help="required: run real Blender builds and write files")
    parser.add_argument("--tiers", default="low,medium,high")
    parser.add_argument("--preview-size", type=int, default=640)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("pass --confirm to run Blender and write evidence files")
    if not Path(BLENDER).is_file():
        raise SystemExit(f"Blender not found at {BLENDER}")

    tiers = [value.strip().lower() for value in args.tiers.split(",") if value.strip()]
    for tier in tiers:
        if tier not in environment_spec.QUALITY_TIERS:
            raise SystemExit(f"unknown tier: {tier}")

    started = time.time()
    agent_output, medium_spec = plan()
    clean_output_dir(VALIDATION_DIR)

    results = {}
    for tier in tiers:
        spec = environment_spec.spec_from_agent_output(
            agent_output, quality_tier=tier, target_engine="unity",
            character_path=CHARACTER)
        output_dir = (VALIDATION_DIR if tier == "medium"
                      else VALIDATION_DIR / tier)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[phase4] building {tier} tier -> {output_dir}", flush=True)
        tier_started = time.time()
        report = environment_pipeline.run_pipeline(
            spec, str(output_dir), timeout=args.timeout, blender_exe=BLENDER,
            preview_size=args.preview_size, character_root=str(ROOT))
        report["duration_seconds"] = round(time.time() - tier_started, 3)
        report["spec"] = spec
        results[tier] = report
        print(f"[phase4] {tier}: {report['status']} "
              f"({report.get('failed_stages')})", flush=True)

    primary = results.get("medium") or results[tiers[0]]
    build = primary.get("build") or {}
    tier_rows = {tier: tier_entry(tier, results[tier],
                                  VALIDATION_DIR if tier == "medium"
                                  else VALIDATION_DIR / tier)
                 for tier in tiers}

    generation = {
        "schema_version": 1,
        "phase": "V6 Phase 4 - environment generation",
        "generated_at": now(),
        "repository": {
            "root": str(ROOT),
            "head": git_head(),
        },
        "request": REQUEST,
        "phase2_agent": {
            "agent": "EnvironmentAgent",
            "deterministic_output": agent_output,
            "agent_reports_generated_content": bool(agent_output.get("generated")),
            "pipeline_generated_content": primary.get("status") == "completed",
        },
        "spec": medium_spec,
        "pipeline": {
            "status": primary.get("status"),
            "ok": primary.get("ok"),
            "failed_stages": primary.get("failed_stages"),
            "stages": primary.get("stages"),
            "build": {
                "blender_executable": build.get("blender_executable"),
                "blender_exit_code": build.get("blender_exit_code"),
                "blender_executed": build.get("blender_executed"),
                "duration_ms": build.get("duration_ms"),
                "counts": build.get("counts"),
                "terrain": build.get("terrain"),
                "vegetation": build.get("vegetation"),
                "vegetation_counts": (build.get("vegetation") or {}).get("counts"),
                "vegetation_instances": (build.get("vegetation") or {}).get(
                    "instance_count"),
                "unique_vegetation_meshes": (build.get("vegetation") or {}).get(
                    "unique_meshes"),
                "props": build.get("props"),
                "prop_counts": (build.get("props") or {}).get("counts"),
                "debris": (build.get("props") or {}).get("debris"),
                "ruin_objects": (build.get("props") or {}).get("ruin_objects"),
                "water": build.get("water"),
                "lighting": build.get("lighting"),
                "layout": build.get("layout"),
                "collision": build.get("collision"),
                "character": build.get("character"),
                "materials": build.get("materials"),
                "glb_validation": build.get("glb_validation"),
                "gltf_validation": build.get("gltf_validation"),
                "export_processes": build.get("export_processes"),
                "render_process": build.get("render_process"),
                "images": build.get("images"),
                "textures": build.get("textures"),
                "pbr_channels": build.get("pbr_channels"),
                "artifacts": {name: {"path": relative(entry.get("path")),
                                     "exists": entry.get("exists"),
                                     "bytes": entry.get("bytes"),
                                     "sha256": entry.get("sha256")}
                              for name, entry in (build.get("artifacts") or {}).items()},
            },
            "reimport": primary.get("reimport"),
            "character_source": primary.get("character_source"),
            "classifications": primary.get("classifications"),
            "limitations": primary.get("limitations"),
        },
        "quality_tiers": tier_rows,
        "profiles": environment_spec.profile_report(),
        "blender": blender_info(),
        "total_seconds": round(time.time() - started, 1),
        "network_calls": 0,
        "downloads": 0,
        "paid_requests": 0,
    }
    write_json(REPORTS_DIR / "v6-environment-generation.json", generation)

    validation = {
        "schema_version": 1,
        "phase": "V6 Phase 4 - environment validation",
        "generated_at": now(),
        "primary_tier": "medium" if "medium" in results else tiers[0],
        "tiers": {tier: validation_entry(results[tier]) for tier in tiers},
        "acceptance_evidence": {
            "terrain_generated": bool(
                (build.get("terrain") or {}).get("triangles")),
            "terrain_non_flat": float(
                (build.get("terrain") or {}).get("height_range_m") or 0) > 1.0,
            "vegetation_generated": int(
                (build.get("vegetation") or {}).get("instance_count") or 0) > 0,
            "props_generated": bool((build.get("props") or {}).get("counts")),
            "river_generated": bool((build.get("water") or {}).get("present")),
            "materials_validated": (
                (primary.get("stages") or {}).get("materials-validated", {})
                .get("status") == "passed"),
            "lighting_validated": (
                (primary.get("stages") or {}).get("lighting-validated", {})
                .get("status") == "passed"),
            "layout_validated": (
                (primary.get("stages") or {}).get("layout-validated", {})
                .get("status") == "passed"),
            "collision_validated": (
                (primary.get("stages") or {}).get("collision-validated", {})
                .get("status") == "passed"),
            "character_integrated": (
                (primary.get("stages") or {}).get("character-integrated", {})
                .get("status") == "passed"),
            "export_validated": bool(
                (build.get("glb_validation") or {}).get("ok")
                and (build.get("gltf_validation") or {}).get("ok")),
            "previews_rendered": bool(
                (build.get("artifacts") or {}).get("preview_overview", {})
                .get("exists")),
            "reimport_validated": bool((primary.get("reimport") or {}).get("ok")),
            "character_source_unchanged": bool(
                (primary.get("character_source") or {}).get("unchanged")),
        },
    }
    write_json(REPORTS_DIR / "v6-environment-validation.json", validation)

    manifest = dict(primary.get("manifest") or {})
    manifest["artifact_hashes"] = {
        name: {"path": relative(entry.get("path")),
               "bytes": entry.get("bytes"), "sha256": entry.get("sha256")}
        for name, entry in (build.get("artifacts") or {}).items()
    }
    manifest["texture_hashes"] = [
        {"path": relative(texture.get("path")), "dimensions": texture.get("dimensions"),
         "bytes": texture.get("bytes"), "sha256": texture.get("sha256"),
         "colorspace": texture.get("colorspace")}
        for texture in build.get("textures") or []
    ]
    manifest["character_source"] = primary.get("character_source")
    manifest["tier_outputs"] = tier_rows
    manifest["declarations"] = {
        "procedural": True,
        "ai_generated": False,
        "external_assets_downloaded": False,
        "paid_generation_used": False,
        "third_party_licenses": [],
        "production_ready": False,
        "engine_integration_verified": False,
    }
    write_json(REPORTS_DIR / "v6-environment-provenance.json", manifest)

    print(f"[phase4] reports written in {round(time.time() - started, 1)}s",
          flush=True)
    return 0 if all(result.get("status") == "completed"
                    for result in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
