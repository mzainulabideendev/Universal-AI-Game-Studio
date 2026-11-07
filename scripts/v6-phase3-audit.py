#!/usr/bin/env python3
"""V6 Phase 3 audit.

Runs the full test suite, re-executes a fresh real Blender character build in a
temporary directory, verifies the committed evidence reports and artifacts,
checks protected V4/V5 hashes, MCP tool/handler parity and provider capability
honesty, then writes reports/v6-phase3-audit.json.

No network call, no paid request, no asset download, no commit.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(SERVER_DIR))

from game_studio import character_pipeline, character_spec  # noqa: E402
from game_studio.agents.character import CharacterAgent  # noqa: E402
from game_studio.blender import blender_info  # noqa: E402

REQUEST = (
    "Create a stylized 3D jungle monkey character for a professional third-person "
    "adventure game with expressive eyes, brown fur, a complete body, hands, feet "
    "and idle, walk, run and jump animations."
)

REPORTS = ROOT / "reports"
DELIVERABLES = [
    "V6-PHASE-3-CHARACTER-ASSET-PIPELINE.md",
    "reports/v6-character-pipeline.json",
    "reports/v6-character-validation.json",
    "reports/v6-asset-provenance.json",
    "reports/v6-phase3-audit.json",
    "scripts/v6-phase3-demo.py",
    "scripts/v6-phase3-audit.py",
    "tools/game-studio-mcp/game_studio/character_spec.py",
    "tools/game-studio-mcp/game_studio/character_pipeline.py",
    "tools/game-studio-mcp/tests/test_v6_phase3_character_spec.py",
    "tools/game-studio-mcp/tests/test_v6_phase3_pipeline.py",
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


def sh(args: list[str], *, timeout: int = 1800) -> dict:
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
    result = sh(["git", *args], timeout=120)
    return (result["stdout"] or "").strip()


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
        "v4_preserved": v4_ok,
        "v4_files": v4,
        "v5_preserved": v5_ok,
        "v5_artifacts": v5,
    }


def verify_reports() -> dict:
    pipeline_path = REPORTS / "v6-character-pipeline.json"
    validation_path = REPORTS / "v6-character-validation.json"
    provenance_path = REPORTS / "v6-asset-provenance.json"
    missing = [str(path) for path in (pipeline_path, validation_path,
                                      provenance_path) if not path.is_file()]
    if missing:
        return {"ok": False, "missing": missing}
    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    artifacts = []
    for role, entry in (pipeline.get("artifact_checks") or {}).items():
        path = Path(entry.get("path") or "")
        artifacts.append({
            "role": role,
            "path": str(path),
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": sha256(path),
            "reported_sha256": entry.get("sha256"),
            "matches": path.is_file() and sha256(path) == entry.get("sha256"),
        })
    glb_path = next((Path(item["path"]) for item in artifacts
                     if item["role"] == "glb" and item["exists"]), None)
    glb = character_pipeline.validate_glb(str(glb_path)) if glb_path else None
    return {
        "ok": (pipeline.get("status") == "completed"
               and validation.get("overall_status") == "passed"
               and all(item["matches"] for item in artifacts)
               and provenance.get("license_id") == "project-original-1.0"),
        "pipeline_status": pipeline.get("status"),
        "validation_status": validation.get("overall_status"),
        "failed_stages": pipeline.get("execution", {}).get("failed_stages"),
        "artifacts": artifacts,
        "glb": glb,
        "license": provenance.get("license"),
        "license_id": provenance.get("license_id"),
        "ai_generated": provenance.get("ai_generated"),
        "external_assets_acquired": provenance.get("external_assets_acquired"),
        "report_hashes": provenance.get("report_hashes"),
        "hashes_match": provenance.get("report_hashes") == {
            "reports/v6-character-pipeline.json": sha256(pipeline_path),
            "reports/v6-character-validation.json": sha256(validation_path),
        },
    }


def fresh_blender_build() -> dict:
    spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
    with tempfile.TemporaryDirectory(prefix="v6-phase3-audit-") as tmp:
        started = time.time()
        report = character_pipeline.run_pipeline(spec, tmp, timeout=900,
                                                 preview_size=256)
        build = report.get("build") or {}
        preview_path = (build.get("artifacts", {}).get("preview") or {}).get("path")
        return {
            "status": report.get("status"),
            "ok": report.get("ok"),
            "failed_stages": report.get("failed_stages"),
            "duration_seconds": round(time.time() - started, 1),
            "blender_executed": build.get("blender_executed"),
            "blender_exit_code": build.get("blender_exit_code"),
            "triangles": (build.get("geometry") or {}).get("triangles"),
            "vertices": (build.get("geometry") or {}).get("vertices"),
            "materials": len(build.get("materials") or []),
            "bones": (build.get("rig") or {}).get("bones"),
            "weighted_ratio": (build.get("rig") or {}).get("weighted_ratio"),
            "uv_coverage": (build.get("geometry") or {}).get("uv_coverage"),
            "pbr_channels": build.get("pbr_channels") or {},
            "textures": build.get("textures") or [],
            "animations": [a.get("name") for a in build.get("animations") or []],
            "glb": build.get("glb_validation"),
            "reimport_ok": (report.get("reimport") or {}).get("ok"),
            "preview_dimensions": character_pipeline.png_dimensions(preview_path)
            if preview_path else None,
            "stage_status": {name: entry.get("status")
                             for name, entry in (report.get("stages") or {}).items()},
            "classification": report.get("generation_classification"),
        }


def parity() -> dict:
    import server
    names = [tool["name"] for tool in server.TOOLS]
    return {
        "tools": len(names),
        "handlers": len(server.HANDLERS),
        "unique_tool_names": len(set(names)),
        "missing_handlers": [name for name in names if name not in server.HANDLERS],
        "extra_handlers": [name for name in server.HANDLERS if name not in names],
        "all_schemas_object": all(
            isinstance(tool.get("inputSchema"), dict)
            and tool["inputSchema"].get("type") == "object"
            for tool in server.TOOLS),
        "character_tools": [name for name in names if name.startswith("character_")],
    }


def capability_report() -> dict:
    report = character_spec.provider_capability_report()
    return {
        "authorized_external_generators": report["authorized_external_generators"],
        "authorized_missing": report["authorized_missing"],
        "image_generation_supported": [
            name for name, entry in report["providers"].items()
            if entry["image_generation"] == "supported"],
        "mesh_generation_supported": [
            name for name, entry in report["providers"].items()
            if entry["mesh_generation"] == "supported"],
        "meshy_authorized": report["providers"]["meshy"].get("authorized"),
        "states_used": sorted({state for entry in report["providers"].values()
                               for key, state in entry.items()
                               if key in character_spec.ASSET_CAPABILITIES}),
    }


def agent_integration() -> dict:
    output = CharacterAgent().deterministic_output({
        "brief": {"summary": REQUEST, "quality_target": "standard",
                  "characters": ["jungle monkey"], "mechanics": ["jump"]},
        "design": {"art_direction": "stylized brown fur"},
        "architecture": {},
    })
    spec = output["characters"][0].get("asset_specification") or {}
    return {
        "asset_specification_present": bool(spec),
        "spec_valid": not character_spec.validate_character_spec(spec) if spec else False,
        "quality_tier": spec.get("quality_tier"),
        "agent_assets_generated": output.get("assets_generated"),
        "agent_textures_generated": output.get("textures_generated"),
        "status": output["characters"][0].get("status"),
    }


def security_scan() -> dict:
    patterns = [r"sk-[A-Za-z0-9_-]{16,}", r"msy_[A-Za-z0-9]{8,}",
                r"Bearer\s+[A-Za-z0-9._-]{20,}"]
    hits = []
    for relative in ("reports/v6-character-pipeline.json",
                     "reports/v6-character-validation.json",
                     "reports/v6-asset-provenance.json"):
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                hits.append({"file": relative, "pattern": pattern,
                             "excerpt": match.group(0)[:12] + "..."})
    return {"clean": not hits, "hits": hits}


def main() -> int:
    baseline = json.loads((REPORTS / "v6-phase0-baseline.json").read_text(
        encoding="utf-8"))
    print("[1/6] Running the full test suite...")
    tests = run_tests()
    print(f"      {tests['result']} ({tests['tests']} tests)")

    print("[2/6] Checking protected V4/V5 hashes and MCP parity...")
    preserved = preservation(baseline)
    mcp = parity()
    capabilities = capability_report()
    agent = agent_integration()

    print("[3/6] Verifying committed Phase 3 evidence...")
    reports = verify_reports()
    deliverables = {
        relative: {
            "exists": (ROOT / relative).is_file(),
            "bytes": (ROOT / relative).stat().st_size
            if (ROOT / relative).is_file() else 0,
            "sha256": sha256(ROOT / relative),
        }
        for relative in DELIVERABLES
    }
    security = security_scan()

    print("[4/6] Re-running a fresh real Blender build independently...")
    fresh = fresh_blender_build()
    blender = blender_info()
    blender_version = (blender.get("result") or {}).get("version_string") \
        if blender.get("ok") else None

    print("[5/6] Evaluating acceptance criteria...")
    criteria = {
        "real_character_generation": (
            fresh["status"] == "completed"
            and (fresh["triangles"] or 0) > 1000
            and fresh["materials"] >= 7),
        "blender_executed": bool(fresh["blender_executed"])
        and fresh["blender_exit_code"] == 0,
        "geometry_validated": fresh["stage_status"].get("geometry-validated") == "passed",
        "uv_validated": fresh["stage_status"].get("uv-validated") == "passed"
        and (fresh["uv_coverage"] or 0) > 0.05,
        "materials_and_textures_validated": (
            fresh["stage_status"].get("materials-validated") == "passed"),
        "pbr_channels_honest": tickets_pbr(fresh),
        "rigging_validated": fresh["stage_status"].get("rig-validated") == "passed"
        and (fresh["weighted_ratio"] or 0) >= 0.99,
        "animations_created": fresh["stage_status"].get("animations-created") == "passed",
        "real_exports_succeeded": fresh["stage_status"].get("glb-exported") == "passed"
        and fresh["stage_status"].get("fbx-exported") == "passed",
        "export_validated_and_reimported": fresh["stage_status"].get(
            "glb-validated") == "passed" and bool(fresh["reimport_ok"]),
        "preview_rendered": fresh["stage_status"].get("preview-rendered") == "passed"
        and bool(fresh["preview_dimensions"]),
        "phase2_agent_integration": agent["asset_specification_present"]
        and agent["spec_valid"] and agent["agent_assets_generated"] is False,
        "reports_reproducible": bool(reports.get("ok"))
        and bool(reports.get("hashes_match")),
        "mcp_tool_handler_parity": (
            mcp["tools"] == mcp["handlers"] == mcp["unique_tool_names"]
            and not mcp["missing_handlers"] and not mcp["extra_handlers"]
            and mcp["all_schemas_object"]),
        "v4_preserved": preserved["v4_preserved"],
        "v5_preserved": preserved["v5_preserved"],
        "tests_pass": tests["result"] == "OK" and (tests["tests"] or 0) >= 267,
        "no_fabricated_ai_assets": (
            capabilities["authorized_external_generators"] == []
            and not capabilities["image_generation_supported"]
            and fresh["classification"].get("ai_generated_assets") is False
            and fresh["classification"].get("external_acquired_assets") is False),
        "security_clean": security["clean"],
        "deliverables_present": all(entry["exists"]
                                    for entry in deliverables.values()),
    }
    verdict = "PASS" if all(criteria.values()) else "PARTIAL"

    audit = {
        "schema_version": 1,
        "phase": "V6 Phase 3 - character asset pipeline audit",
        "generated_at": now(),
        "verdict": verdict,
        "repository": {
            "root": str(ROOT),
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": git("rev-parse", "HEAD"),
            "head_short": git("rev-parse", "--short", "HEAD"),
            "dirty_tracked": [line for line in git("status", "--porcelain").splitlines()
                              if line.strip()][:80],
        },
        "blender": {
            "executable": character_pipeline.resolve_blender_executable(),
            "version": blender_version,
            "info_ok": bool(blender.get("ok")),
        },
        "tests": tests,
        "fresh_real_build": fresh,
        "committed_evidence": reports,
        "deliverables": deliverables,
        "preservation": preserved,
        "mcp": mcp,
        "capabilities": capabilities,
        "phase2_integration": agent,
        "security": security,
        "criteria": criteria,
        "not_executed": [
            "Unity/Godot/Unreal engine import (only export-prepared structure was validated)",
            "AI image/texture/3D generation (no authorized provider configured)",
            "Asset downloads (not authorized)",
            "Commits, pushes and tags (not authorized)",
        ],
        "limitations": [
            "The character is a procedural stylized prototype, not production art.",
            "Textures are locally generated procedural images; AO/emission/opacity "
            "maps are absent and reported as such.",
            "Animations are short procedural keyframe clips.",
            "Engine integration is export-prepared and structurally validated only.",
        ],
    }
    (REPORTS / "v6-phase3-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"[6/6] Verdict: {verdict}")
    print(json.dumps({
        "verdict": verdict,
        "tests": tests["tests"],
        "fresh_status": fresh["status"],
        "triangles": fresh["triangles"],
        "glb_ok": fresh["glb"].get("ok") if fresh["glb"] else None,
        "mcp": f"{mcp['tools']}/{mcp['handlers']}",
        "v4_preserved": preserved["v4_preserved"],
        "v5_preserved": preserved["v5_preserved"],
        "failed_criteria": [name for name, value in criteria.items() if not value],
    }, indent=2))
    print(f"audit -> {REPORTS / 'v6-phase3-audit.json'}")
    return 0 if verdict == "PASS" else 1


def tickets_pbr(fresh: dict) -> bool:
    """Honest PBR check against the fresh build's per-material channel report."""
    channels = fresh.get("pbr_channels") or {}
    fur = channels.get("M_Monkey_Fur") or {}
    if not fur:
        return False
    return (fresh["stage_status"].get("materials-validated") == "passed"
            and fur.get("base_color") == "texture"
            and fur.get("roughness") == "texture"
            and fur.get("normal") == "texture"
            and fur.get("ao") == "absent"
            and fur.get("emission") == "absent"
            and fur.get("opacity") == "absent"
            and len(fresh.get("textures") or []) == 3)


if __name__ == "__main__":
    raise SystemExit(main())
