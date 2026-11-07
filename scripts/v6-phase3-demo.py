#!/usr/bin/env python3
"""V6 Phase 3 real character pipeline demonstration.

Submits the required character request to the Phase 2 Character Agent, builds a
validated Phase 3 asset specification, executes the real local Blender pipeline
(geometry, UVs, PBR textures, rig, animations, .blend/.glb/.fbx export, GLB
re-import and a rendered preview), then writes the Phase 3 evidence reports.

This script calls Blender and writes files. Run it explicitly with --confirm.
It makes no network calls and no paid API requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(SERVER_DIR))

from game_studio import character_pipeline, character_spec  # noqa: E402
from game_studio.agents.character import CharacterAgent  # noqa: E402
from game_studio.agents.coordinator import Orchestrator  # noqa: E402
from game_studio.blender import blender_info  # noqa: E402

REQUEST = (
    "Create a stylized 3D jungle monkey character for a professional third-person "
    "adventure game. It should have expressive eyes, detailed facial features, brown "
    "fur coloration, realistic proportions for a stylized game character, a complete "
    "body, hands, feet, and a game-ready material setup. Prepare the character for "
    "idle, walk, run, and jump animations."
)

VALIDATION_DIR = ROOT / "validation" / "v6-character-pipeline"
REPORTS_DIR = ROOT / "reports"


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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def clean_output_dir(path: Path) -> None:
    resolved = path.resolve()
    allowed = (ROOT / "validation").resolve()
    if allowed not in resolved.parents and resolved != allowed:
        raise SystemExit(f"refusing to clean a directory outside validation/: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def run_agent() -> tuple[dict, dict, dict]:
    brief = {
        "summary": REQUEST,
        "quality_target": "standard",
        "characters": ["jungle monkey"],
        "mechanics": ["third person", "jump"],
        "engine": "unity",
        "platform": "windows",
        "requirements": [],
    }
    design = {"art_direction": "stylized-realistic jungle adventure",
              "visual_style": "stylized"}
    output = CharacterAgent().deterministic_output(
        {"brief": brief, "design": design, "architecture": {}})
    spec = output["characters"][0]["asset_specification"]
    orchestrator = Orchestrator(
        REQUEST, installed_engines=["unity"], quality_target="standard",
        concurrency=2, max_retries=0, use_provider=False)
    orchestration = orchestrator.run()
    return output, spec, orchestration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(VALIDATION_DIR))
    parser.add_argument("--quality", default="medium",
                        choices=list(character_spec.QUALITY_TIERS))
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--preview-size", type=int, default=720)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        print("This demo executes Blender and writes files. Re-run with --confirm.",
              file=sys.stderr)
        return 2

    started = time.time()
    output_dir = Path(args.output).resolve()
    clean_output_dir(output_dir)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] Submitting the request to the Character Agent...")
    character_output, spec, orchestration = run_agent()
    errors = character_spec.validate_character_spec(spec)
    if errors:
        print(f"Character Agent produced an invalid specification: {errors}",
              file=sys.stderr)
        return 3
    if args.quality != spec["quality_tier"]:
        spec = character_spec.build_character_spec(
            REQUEST, quality_tier=args.quality,
            animations=[a["name"] for a in spec["animations"]],
            target_engine=spec["export"]["target_engine"])

    print(f"[2/5] Building a real Blender character ({spec['quality_tier']} tier)...")
    pipeline = character_pipeline.run_pipeline(
        spec, str(output_dir), timeout=args.timeout,
        preview_size=args.preview_size)
    build = pipeline.get("build") or {}
    if not build.get("blender_executed"):
        print("Blender was not executed; see the report for the error.", file=sys.stderr)

    blender = blender_info()
    blender_version = (blender.get("result") or {}).get("version_string") \
        if blender.get("ok") else None

    print("[3/5] Verifying reported artifacts against the filesystem...")
    artifact_checks = {}
    for role, entry in (build.get("artifacts") or {}).items():
        path = Path(entry.get("path") or "")
        artifact_checks[role] = {
            "path": str(path),
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": sha256(path),
            "size_matches_report": (path.stat().st_size if path.is_file() else 0)
            == entry.get("bytes"),
            "hash_matches_report": sha256(path) == entry.get("sha256"),
        }
    textures = []
    for texture in build.get("textures") or []:
        path = Path(texture.get("path", ""))
        textures.append({
            **texture,
            "exists": path.is_file(),
            "sha256": sha256(path),
            "dimensions": list(character_pipeline.png_dimensions(str(path)) or []),
        })

    stages = pipeline.get("stages") or {}
    stage_status = {name: entry.get("status") for name, entry in stages.items()}
    checks = {
        "specification_valid": {
            "status": "passed" if not errors else "failed",
            "errors": errors,
        },
        "agent_asset_specification": {
            "status": "passed"
            if character_output["characters"][0].get("asset_specification")
            else "failed",
            "agent_assets_generated": character_output.get("assets_generated"),
            "agent_plan_only": character_output.get("status", "planned"),
        },
        "geometry": {
            "status": stage_status.get("geometry-validated"),
            "triangles": build.get("geometry", {}).get("triangles"),
            "vertices": build.get("geometry", {}).get("vertices"),
            "non_manifold_edges": build.get("geometry", {}).get("non_manifold_edges"),
            "degenerate_faces": build.get("geometry", {}).get("degenerate_faces"),
        },
        "uv_mapping": {
            "status": stage_status.get("uv-validated"),
            "uv_layers": build.get("geometry", {}).get("uv_layers"),
            "coverage": build.get("geometry", {}).get("uv_coverage"),
            "method": spec["uv"]["method"],
        },
        "materials": {
            "status": stage_status.get("materials-validated"),
            "material_count": len(build.get("materials") or []),
            "channels": build.get("pbr_channels") or {},
            "issues": (stages.get("materials-validated") or {}).get("issues"),
        },
        "textures": {
            "status": "passed" if textures and all(t["exists"] for t in textures)
            and len(textures) == 3 else "failed",
            "resolution": spec["textures"]["resolution"],
            "files": textures,
            "absent_channels": spec["textures"]["maps_absent"],
        },
        "rigging": {
            "status": stage_status.get("rig-validated"),
            "bones": build.get("rig", {}).get("bones"),
            "weight_mode": build.get("rig", {}).get("weight_mode"),
            "weighted_ratio": build.get("rig", {}).get("weighted_ratio"),
            "vertex_groups": build.get("rig", {}).get("vertex_groups"),
            "armature_modifier": build.get("rig", {}).get("armature_modifier"),
        },
        "animations": {
            "status": stage_status.get("animations-created"),
            "requested": [a["name"] for a in spec["animations"]],
            "actions": build.get("animations") or [],
            "exported": (build.get("glb_validation") or {}).get("animation_names"),
        },
        "export": {
            "status": "passed" if all(
                stage_status.get(name) == "passed"
                for name in ("blend-saved", "glb-exported", "fbx-exported")) else "failed",
            "formats": ["blend", "glb", "fbx"],
            "artifacts": artifact_checks,
        },
        "glb_validation": {
            "status": stage_status.get("glb-validated"),
            "details": build.get("glb_validation"),
        },
        "reimport": {
            "status": stage_status.get("glb-reimported"),
            "checks": (pipeline.get("reimport") or {}).get("checks"),
            "metrics": (pipeline.get("reimport") or {}).get("metrics"),
        },
        "preview": {
            "status": stage_status.get("preview-rendered"),
            "engine": (stages.get("preview-rendered") or {}).get("engine"),
            "path": (build.get("artifacts", {}).get("preview") or {}).get("path"),
        },
        "engine_compatibility": {
            "status": "export-prepared-unverified",
            "details": (pipeline.get("manifest") or {}).get("engine_compatibility"),
        },
    }
    all_passed = (
        pipeline.get("status") == "completed"
        and all(check.get("status") in ("passed", "export-prepared-unverified")
                for check in checks.values())
        and all(entry["hash_matches_report"] for entry in artifact_checks.values())
    )

    print("[4/5] Writing pipeline, validation and provenance reports...")
    pipeline_report = {
        "schema_version": 1,
        "phase": "V6 Phase 3 - character asset pipeline",
        "generated_at": now(),
        "request": REQUEST,
        "agent": {
            "name": "CharacterAgent",
            "version": "1.0.0",
            "output_summary": character_output.get("summary"),
            "assets_generated_by_agent": character_output.get("assets_generated"),
            "textures_generated_by_agent": character_output.get("textures_generated"),
            "capability_gaps": character_output.get("capability_gaps"),
            "orchestration_status": orchestration.get("status"),
            "orchestration_executable": orchestration.get("executable"),
            "orchestration_agent_count": len(orchestration.get("outputs") or {}),
            "orchestration_limitations": orchestration.get("limitations"),
        },
        "specification": spec,
        "execution": {
            "blender_executable": build.get("blender_executable"),
            "blender_version": blender_version,
            "blender_exit_code": build.get("blender_exit_code"),
            "blender_duration_ms": build.get("duration_ms"),
            "pipeline_status": pipeline.get("status"),
            "failed_stages": pipeline.get("failed_stages"),
            "stage_status": stage_status,
            "wall_clock_seconds": round(time.time() - started, 1),
        },
        "geometry": build.get("geometry"),
        "rig": build.get("rig"),
        "animations": build.get("animations"),
        "quality": build.get("quality"),
        "bounds": build.get("bounds"),
        "materials": build.get("materials"),
        "artifact_checks": artifact_checks,
        "glb_validation": build.get("glb_validation"),
        "reimport": pipeline.get("reimport"),
        "classification": pipeline.get("generation_classification"),
        "capabilities": character_spec.provider_capability_report(),
        "limitations": pipeline.get("limitations"),
        "status": "completed" if all_passed else "partial",
    }

    validation_report = {
        "schema_version": 1,
        "phase": "V6 Phase 3 - character validation",
        "generated_at": now(),
        "overall_status": "passed" if all_passed else "failed",
        "checks": checks,
        "summary": {
            "required_stage_count": len(character_pipeline.REQUIRED_STAGES),
            "passed_stage_count": sum(
                1 for name in character_pipeline.REQUIRED_STAGES
                if stage_status.get(name) == "passed"),
            "failed_stages": pipeline.get("failed_stages"),
        },
        "honest_channel_report": {
            "generated_images": ["base_color", "roughness", "normal"],
            "constant_values": ["metallic"],
            "absent": ["ambient_occlusion", "emission", "opacity"],
            "note": ("Base color, roughness and normal maps are procedural images "
                     "generated locally. AO, emission and opacity were not generated "
                     "and are reported as absent."),
        },
        "engine_compatibility": (pipeline.get("manifest") or {}).get(
            "engine_compatibility"),
        "classification": pipeline.get("generation_classification"),
    }

    provenance = dict(pipeline.get("manifest") or {})
    provenance.update({
        "phase": "V6 Phase 3 - asset provenance",
        "generated_at": now(),
        "request": REQUEST,
        "classification": pipeline.get("generation_classification"),
        "procedurally_generated": True,
        "imported_existing_geometry": False,
        "ai_generated": False,
        "external_assets_acquired": False,
        "placeholder_only": False,
        "provider_capabilities": character_spec.provider_capability_report(),
        "artifact_checks": artifact_checks,
        "texture_checks": textures,
    })

    write_json(REPORTS_DIR / "v6-character-pipeline.json", pipeline_report)
    write_json(REPORTS_DIR / "v6-character-validation.json", validation_report)
    provenance["report_hashes"] = {
        "reports/v6-character-pipeline.json": sha256(
            REPORTS_DIR / "v6-character-pipeline.json"),
        "reports/v6-character-validation.json": sha256(
            REPORTS_DIR / "v6-character-validation.json"),
    }
    write_json(REPORTS_DIR / "v6-asset-provenance.json", provenance)

    print("[5/5] Result")
    print(json.dumps({
        "status": pipeline_report["status"],
        "quality_tier": spec["quality_tier"],
        "triangles": build.get("geometry", {}).get("triangles"),
        "vertices": build.get("geometry", {}).get("vertices"),
        "materials": len(build.get("materials") or []),
        "bones": build.get("rig", {}).get("bones"),
        "weighted_ratio": build.get("rig", {}).get("weighted_ratio"),
        "uv_coverage": build.get("geometry", {}).get("uv_coverage"),
        "animations": [a.get("name") for a in build.get("animations") or []],
        "glb": (build.get("artifacts", {}).get("glb") or {}).get("path"),
        "glb_sha256": (build.get("artifacts", {}).get("glb") or {}).get("sha256"),
        "preview": (build.get("artifacts", {}).get("preview") or {}).get("path"),
        "failed_stages": pipeline.get("failed_stages"),
        "output_dir": str(output_dir),
    }, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
