#!/usr/bin/env python3
"""End-to-end check for request understanding, specification and project memory.

Creates an isolated temporary Unity-shaped project, runs the real modules and
verifies the evidence rules. It needs no engine, network or API key and removes
its temporary directory on success.

Run:
    python scripts/validate-intent-memory.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "game-studio-mcp"))

from game_studio import manifest, specification, understanding  # noqa: E402
from game_studio.util import ToolError  # noqa: E402


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    roman = understanding.analyze_request(
        "Bhai ek realistic 3D bandar adventure game banao jungle mein. "
        "Bandar ped par charh sake aur pani mein tair sake. Bandooq nahi chahiye.")
    assert roman["understanding"]["characters"] == ["monkey"], roman["understanding"]
    if "roman-urdu" not in roman["language"]["detected"]:
        fail("Roman Urdu was not detected")
    if not {"climbing", "swimming"} <= set(roman["understanding"]["mechanics"]):
        fail("climbing/swimming were not understood")
    if [item["value"] for item in roman["exclusions"]] != ["weapons"]:
        fail("the negated weapon request was not excluded")
    if roman["conflicts"]:
        fail(f"unexpected conflicts: {roman['conflicts']}")

    with tempfile.TemporaryDirectory(prefix="game-studio-validation-") as temp:
        project = os.path.join(temp, "MonkeyQuest")
        os.makedirs(os.path.join(project, "ProjectSettings"))
        os.makedirs(os.path.join(project, "Assets", "Scenes"))
        Path(project, "ProjectSettings", "ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.6.2f1\n", encoding="utf-8")
        Path(project, "Assets", "Scenes", "Main.unity").write_text(
            "%YAML 1.1\n", encoding="utf-8")

        spec = specification.create_specification(
            request=roman["original_request"], project_name="Monkey Quest",
            engine="unity", platform="pc", approved=True, installed_engines=["unity"])
        if spec["dependency_graph"]["cycles"]:
            fail("dependency graph contains cycles")
        if not spec["characters"] or "quadruped" not in spec["characters"][0]["rig_requirement"]:
            fail("the monkey did not receive a non-humanoid rig requirement")
        if spec["engine"]["selected"] != "unity" or not spec["engine"]["verified"]:
            fail("engine selection was not applied")

        created = manifest.init_manifest(project, spec, confirm=True)
        requirement_id = spec["requirements"][0]["id"]
        Path(project, "Assets", "validation.log").write_text(
            "test output\n", encoding="utf-8")

        try:
            manifest.update_requirement_status(project, requirement_id, "verified",
                                               confirm=True)
            fail("verified was accepted without evidence")
        except ToolError:
            pass

        manifest.update_requirement_status(
            project, requirement_id, "tested",
            evidence=[{"kind": "test", "reference": "Assets/validation.log"}],
            confirm=True)
        manifest.record_decision(project, topic="engine", decision="Unity 6",
                                 rationale="installed and verified", approved=True,
                                 confirm=True)

        progress = manifest.track_progress(project)
        if progress["coverage"]["tested"] != 1:
            fail("tested status was not persisted")
        reloaded = manifest.load_manifest_view(project)
        if reloaded["project_id"] != spec["spec_id"]:
            fail("manifest did not reload with the same project id")
        if not reloaded["decisions"]:
            fail("decision was not persisted")

        comparison = manifest.compare_project_against_requirements(project)
        if comparison["detected_engine"] != "unity":
            fail("engine detection during comparison failed")
        if comparison["invalid_claims"]:
            fail(f"valid evidence was flagged: {comparison['invalid_claims']}")

        summary = {
            "language": roman["language"]["detected"],
            "explicit_requirements": roman["counts"]["explicit"],
            "implied_requirements": roman["counts"]["implied"],
            "questions": len(roman["questions"]),
            "spec_id": spec["spec_id"],
            "graph_nodes": len(spec["dependency_graph"]["nodes"]),
            "milestones": len(spec["milestones"]),
            "tests": len(spec["acceptance_tests"]),
            "manifest_revision": created["revision"],
            "coverage": progress["coverage"],
            "comparison": comparison["overall"],
            "detected_engine": comparison["detected_engine"],
        }
        print(json.dumps(summary, indent=2))
        print("PASS: understanding, planning, persistence and evidence guards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
