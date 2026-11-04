#!/usr/bin/env python3
"""End-to-end *reasoning* demonstration for the monkey adventure request.

This demonstrates understanding -> specification -> dependency graph ->
clarifications -> approval workflow -> manifest -> MCP execution plan, and then
reports the real blockers that prevent producing a playable Unity build here.

It never fakes a game, engine import, asset or build. Running it makes no paid
API call: without a configured LLM it uses the deterministic fallback and says
so explicitly.

Usage:
    python scripts/demo-monkey-adventure.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(MCP))

from game_studio import blender, detect, engines, manifest, specification  # noqa: E402

REQUEST = (
    "Create a realistic 3D monkey adventure game for Android. The monkey can run, "
    "jump, climb trees, swing between branches, swim in rivers and collect bananas. "
    "Include multiple jungle environments, day-night cycles, weather changes, "
    "wildlife, progression and mobile-friendly controls. No weapons."
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def execution_plan(spec: dict) -> list[dict]:
    """Map requirement categories to authorized MCP tools (no execution here)."""
    mapping = {
        "character": ["search_assets", "meshy_text_to_3d", "meshy_rig_character",
                      "meshy_create_animation", "inspect_animation_rig"],
        "animation": ["search_assets", "meshy_animation_library",
                      "check_animation_compatibility", "create_animation_retarget_map"],
        "environment": ["blender_create_environment_blockout", "search_assets",
                        "download_polyhaven_asset"],
        "physics": ["blender_run_python", "stage_asset_for_engine"],
        "engine": ["inspect_game_project", "stage_asset_for_engine", "unity_batch_refresh",
                   "unity_run_tests", "unity_build"],
        "ui": ["unity_run_command"],
        "performance": ["detect_system", "unity_run_tests"],
        "testing": ["run_requirement_verification", "compare_project_against_requirements"],
    }
    plan = []
    for requirement in spec.get("requirements", []):
        category = str(requirement.get("category") or "").lower()
        tools = []
        for key, values in mapping.items():
            if key in category:
                tools = values
                break
        plan.append({
            "requirement_id": requirement.get("id"),
            "priority": requirement.get("priority"),
            "classification": requirement.get("classification"),
            "statement": requirement.get("statement"),
            "mcp_tools": tools or ["analyze_game_request"],
            "requires_approval": True,
            "executed": False,
            "note": "Planned only. Nothing in this step imports, builds or tests a game.",
        })
    return plan


def environment_report() -> dict:
    """Detect real tools without pretending missing ones exist."""
    try:
        blender_exe = blender.resolve_blender()
    except Exception:  # noqa: BLE001
        blender_exe = None
    try:
        available = engines.list_available_engines()
    except Exception as exc:  # noqa: BLE001
        available = {"error": str(exc), "available": []}
    detected_engines = available.get("available") or []
    return {
        "blender": {"path": blender_exe, "available": bool(blender_exe)},
        "engines": {
            "available": detected_engines,
            "unity_available": "unity" in detected_engines,
            "unreal_available": "unreal" in detected_engines,
            "godot_available": "godot" in detected_engines,
        },
        "system": detect.inspect_system(),
    }


def blockers(env: dict, project_dir: Path) -> list[dict]:
    result = []
    unity = Path("ProjectSettings/ProjectVersion.txt")
    if not env["engines"]["unity_available"]:
        result.append({
            "blocker": "Unity editor/CLI is not available",
            "impact": "cannot create/import the Unity project, run PlayMode tests or build",
            "resolution": "install Unity Hub + an editor version and run "
                          "detect_game_engines / select_game_engine",
        })
    if not env["blender"]["available"]:
        result.append({
            "blocker": "Blender executable is not available",
            "impact": "cannot generate the character or environment blockout",
            "resolution": "install Blender and set BLENDER_EXE or configure_studio",
        })
    if not (project_dir / unity).is_file():
        result.append({
            "blocker": "no Unity project exists for this demonstration",
            "impact": "there is no scene, controller or build to test",
            "resolution": "create a Unity project, then stage assets and implement gameplay "
                          "through approved MCP tools",
        })
    result.append({
        "blocker": "no licensed monkey character or compatible animation set is installed",
        "impact": "character/rig/animation requirements cannot be verified",
        "resolution": "use Meshy (paid, explicit approval) or a licensed asset source, then "
                      "check_animation_compatibility",
    })
    result.append({
        "blocker": "no automated gameplay test exists yet",
        "impact": "run_requirement_verification cannot prove movement, climbing or swimming",
        "resolution": "implement PlayMode/edit-mode tests, then run them via unity_run_tests "
                      "or run_requirement_verification",
    })
    return result


def main() -> int:
    report_dir = ROOT / "reports" / "demo-monkey-adventure"
    project_dir = report_dir / "project"
    project_dir.mkdir(parents=True, exist_ok=True)

    analysis = specification.create_specification(
        request=REQUEST,
        project_name="Monkey Adventure",
        engine=None,
        platform="android",
        dimension="3d",
        art_style="realistic",
        scope="vertical-slice",
        installed_engines=None,
        known_engine=None,
        approved=False,
    )
    plan = execution_plan(analysis)
    (project_dir / ".game-studio").mkdir(parents=True, exist_ok=True)
    (project_dir / ".game-studio" / "execution-plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8")

    manifest_result = None
    try:
        manifest_result = manifest.init_manifest(project_dir, analysis, confirm=True)
    except Exception as exc:  # noqa: BLE001
        manifest_result = {"ok": False, "error": str(exc)}

    env = environment_report()
    blocked = blockers(env, project_dir)

    report = {
        "schema_version": 1,
        "generated_at": _now(),
        "request": REQUEST,
        "pipeline": {
            "understanding_source": "deterministic-fallback",
            "llm_used": False,
            "note": "No paid provider was called. Configure an LLM and run "
                    "llm_understand_request with confirm=true to compare.",
            "specification_source": "deterministic",
            "approval_state": "awaiting-user-approval",
        },
        "specification": {
            "spec_id": analysis.get("spec_id"),
            "engine": analysis.get("engine"),
            "requirement_count": len(analysis.get("requirements", [])),
            "requirements_by_classification": analysis.get("counts"),
            "dependency_graph": analysis.get("dependency_graph"),
            "milestones": analysis.get("milestones"),
            "questions": analysis.get("questions"),
            "assumptions": analysis.get("assumptions"),
        },
        "execution_plan": plan,
        "manifest": manifest_result,
        "environment": env,
        "blockers": blocked,
        "completion": {
            "reasoning_pipeline": "completed",
            "game_created": False,
            "assets_imported": False,
            "gameplay_implemented": False,
            "build_produced": False,
            "playable_scene_verified": False,
            "honest_summary": "The plan is complete and verifiable. No playable Unity game "
                              "was produced, because the required editor, project, character "
                              "and animation assets are not available in this environment.",
        },
    }
    json_path = report_dir / "demo-report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    question_lines = [f"- {q.get('question')} ({q.get('why_it_matters')})"
                      for q in analysis.get("questions", [])] or ["- none"]
    lines = [
        "# Monkey Adventure — end-to-end reasoning demo",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Request (verbatim)",
        "",
        f"> {REQUEST}",
        "",
        "## Pipeline",
        "",
        "- Understanding: deterministic fallback (no paid LLM call in this run)",
        "- Specification: deterministic dependency graph, milestones and acceptance tests",
        "- Approval: awaiting user approval; no engine, asset or build action was taken",
        "- Manifest: "
        + ("created" if manifest_result and manifest_result.get("ok") else "not created"),
        "",
        "## Specification summary",
        "",
        f"- Spec id: `{analysis.get('spec_id')}`",
        f"- Requirements: {len(analysis.get('requirements', []))}",
        f"- Layers: `{json.dumps(analysis.get('counts'))}`",
        f"- Engine recommendation: `{json.dumps(analysis.get('engine'))}`",
        "",
        "## Dependency graph",
        "",
        f"```json\n{json.dumps(analysis.get('dependency_graph'), indent=2)[:4000]}\n```",
        "",
        "## Material questions",
        "",
        *question_lines,
        "",
        "## Blockers (honest)",
        "",
        *[f"- **{b['blocker']}** — {b['impact']}. Resolution: {b['resolution']}"
          for b in blocked],
        "",
        "## Completion state",
        "",
        *[f"- {key}: `{value}`" for key, value in report["completion"].items()],
        "",
        "## What is still required",
        "",
        "1. Approve engine/platform/art direction.",
        "2. Install Unity + Blender and select the engine.",
        "3. Create/import the character and compatible animations (licensed or paid, "
        "with explicit approval).",
        "4. Generate the environment, implement the controller/physics, and create the scene.",
        "5. Add gameplay tests and run them; only then upgrade requirements to tested/verified.",
        "6. Build and playtest the actual build before any completion claim.",
        "",
    ]
    md_path = report_dir / "README.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"demo report: {json_path}")
    print(f"demo report: {md_path}")
    print(f"requirements: {len(analysis.get('requirements', []))}")
    print(f"blockers: {len(blocked)}")
    print("game_created: False (honest; see blockers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
