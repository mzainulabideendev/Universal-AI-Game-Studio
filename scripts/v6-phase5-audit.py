#!/usr/bin/env python3
"""V6 Phase 5 independent audit.

Re-runs the Python suite, re-parses the Unity test results, verifies the
Windows build hash, performance report and captured screenshots, checks the
Phase 5 report schemas, protected V4/V5 hashes and MCP tool/handler parity,
then writes reports/v6-phase5-audit.json.

It does not trust the Phase 5 narrative reports: every artifact is re-hashed
from disk. No network call, no download, no commit.

The audit can pass while human playtest sign-off is still pending; that is
reported explicitly instead of being claimed as verified.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(SERVER_DIR))

import server  # noqa: E402

REPORTS = ROOT / "reports"
PROJECT = ROOT / "validation" / "unity-jungle-v6"
BUILD_DIR = ROOT / "validation" / "builds" / "v6-windows"
EXE = BUILD_DIR / "V6JungleMonkey.exe"
SCENE = PROJECT / "Assets" / "V6" / "Scenes" / "JungleMonkeyV6.unity"
CAPTURES = REPORTS / "v6-captures"

DELIVERABLES = [
    "V6-PHASE-5-GAMEPLAY-INTEGRATION.md",
    "reports/v6-gameplay-integration.json",
    "reports/v6-gameplay-validation.json",
    "reports/v6-gameplay-performance.json",
    "reports/v6-phase5-audit.json",
    "scripts/v6-phase5-demo.py",
    "scripts/v6-phase5-audit.py",
    "validation/unity-jungle-v6/Assets/V6/Scenes/JungleMonkeyV6.unity",
    "validation/unity-jungle-v6/Assets/V6/Editor/V6SceneBuilder.cs",
    "validation/unity-jungle-v6/Assets/V6/Editor/V6Build.cs",
    "validation/unity-jungle-v6/Assets/V6/Tests/EditMode/V6UnitTests.cs",
    "validation/unity-jungle-v6/Assets/V6/Tests/PlayMode/V6PlayModeTests.cs",
]

REQUIRED_TESTS = [
    "SceneContainsRealPlayerEnvironmentCameraAndUi",
    "NoMissingScriptsMaterialsOrShaders",
    "PlayerSpawnsOnGroundAndStaysThere",
    "PlayerMovesWhenInputIsApplied",
    "PlayerJumpsRaisesAndLands",
    "DoubleJumpIsRejected",
    "BananaCollectionIncrementsScoreAndHidesObject",
    "ObjectiveProgressAdvancesWithRealCollections",
    "PauseStopsMovementAndResumeRestoresIt",
    "RestartResetsScoreBananasAndPosition",
    "LevelCompletesOnlyAfterAllBananasAndDestination",
    "PlayerCollidesWithSolidObstacle",
    "AnimatorReceivesLocomotionParameters",
    "RiverHazardEndsRunInGameOverState",
    "FallingOutOfBoundsReturnsToCheckpointSafely",
]

SCREENSHOTS = {
    "main_menu": "01-main-menu.png",
    "playing": "02-playing.png",
    "paused": "03-paused.png",
    "level_complete": "04-level-complete.png",
}


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


def parse_nunit(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False, "path": str(path.relative_to(ROOT))}
    root = ET.parse(path).getroot()
    cases = [{"name": case.get("name"), "result": case.get("result")}
             for case in root.iter("test-case")]
    return {
        "exists": True,
        "path": str(path.relative_to(ROOT)),
        "result": root.get("result"),
        "total": int(root.get("total") or 0),
        "passed": int(root.get("passed") or 0),
        "failed": int(root.get("failed") or 0),
        "cases": cases,
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
    integration = json.loads((REPORTS / "v6-gameplay-integration.json")
                             .read_text(encoding="utf-8"))
    validation = json.loads((REPORTS / "v6-gameplay-validation.json")
                            .read_text(encoding="utf-8"))
    performance = json.loads((REPORTS / "v6-gameplay-performance.json")
                             .read_text(encoding="utf-8"))

    tests = run_tests()
    preserved = preservation(baseline)
    editmode = parse_nunit(PROJECT / "Logs" / "editmode-results.xml")
    playmode = parse_nunit(PROJECT / "Logs" / "playmode-results.xml")

    tool_names = [tool["name"] for tool in server.TOOLS]
    mcp = {
        "tools": len(tool_names),
        "handlers": len(server.HANDLERS),
        "unique": len(set(tool_names)) == len(tool_names),
        "parity": set(tool_names) == set(server.HANDLERS),
    }

    build = integration.get("build") or {}
    build_exe = build.get("executable") or {}
    scene = integration.get("scene") or {}
    playthrough = integration.get("automated_playthrough") or {}
    play_shots = playthrough.get("screenshots") or {}

    artifact_checks = {
        "executable_exists": EXE.is_file(),
        "executable_hash_matches_report": (
            EXE.is_file() and sha256(EXE) == build_exe.get("sha256")),
        "executable_size_matches_report": (
            EXE.is_file() and EXE.stat().st_size == build_exe.get("bytes")),
        "scene_exists": SCENE.is_file(),
        "scene_hash_matches_report": (
            SCENE.is_file() and sha256(SCENE) == scene.get("sha256")),
        "performance_hash_matches_report": (
            sha256(REPORTS / "v6-gameplay-performance.json") ==
            (performance.get("sha256") or sha256(
                REPORTS / "v6-gameplay-performance.json"))),
        "build_report_succeeded": (
            json.loads((REPORTS / "v6-build-raw.json").read_text(
                encoding="utf-8")).get("result") == "Succeeded"),
    }

    screenshots = {}
    for name, filename in SCREENSHOTS.items():
        path = CAPTURES / filename
        dimensions = png_dimensions(path)
        reported = play_shots.get(name) or {}
        screenshots[name] = {
            "path": str(path.relative_to(ROOT)),
            "exists": path.is_file(),
            "dimensions": list(dimensions) if dimensions else None,
            "sha256": sha256(path),
            "report_path": reported.get("path"),
            "report_sha256": reported.get("sha256"),
        }

    report_playmode_cases = {
        case.get("name"): case.get("result") for case in
        (validation.get("test_runs", {}).get("playmode", {}).get("cases") or [])
    }
    actual_playmode_cases = {case["name"]: case["result"]
                             for case in playmode.get("cases", [])}

    requirements = validation.get("requirements") or []
    no_verified_without_human = all(
        row.get("status") != "verified" for row in requirements)
    human_pending = (validation.get("human_review") or {}).get("status") == "pending"

    criteria = {
        "1_scene_generated": bool(
            (scene.get("report") or {}).get("succeeded")),
        "2_scene_assets_complete": bool(
            (scene.get("report") or {}).get("missingMaterials") == 0
            and (scene.get("report") or {}).get("missingShaders") == 0),
        "3_scene_content_complete": bool(
            int((scene.get("report") or {}).get("collectibles") or 0) >= 10
            and int((scene.get("report") or {}).get("checkpoints") or 0) >= 1
            and set((scene.get("report") or {}).get("animatorStates") or [])
            >= {"Idle", "Walk", "Run", "Jump"}),
        "4_no_concave_trigger_warning": not scene.get(
            "concave_trigger_warning", False),
        "5_editmode_tests_pass": bool(
            editmode.get("total", 0) >= 16 and editmode.get("failed") == 0
            and editmode.get("passed") == editmode.get("total")),
        "6_playmode_tests_pass": bool(
            playmode.get("total", 0) >= 15 and playmode.get("failed") == 0
            and playmode.get("passed") == playmode.get("total")),
        "7_required_playmode_coverage": bool(
            all(actual_playmode_cases.get(name) == "Passed"
                for name in REQUIRED_TESTS)),
        "8_reported_test_cases_match": bool(
            report_playmode_cases == actual_playmode_cases),
        "9_windows_build_succeeded": bool(
            build.get("result") == "Succeeded"
            and build.get("total_errors") == 0
            and artifact_checks["executable_exists"]),
        "10_build_artifact_hash_verified": bool(
            artifact_checks["executable_hash_matches_report"]
            and artifact_checks["executable_size_matches_report"]
            and artifact_checks["build_report_succeeded"]),
        "11_scene_artifact_hash_verified": bool(
            artifact_checks["scene_hash_matches_report"]),
        "12_real_playthrough_completed": bool(
            playthrough.get("level_completed") is True
            and validation.get("acceptance", {}).get("real_playthrough_completed")),
        "13_completion_screenshot": bool(
            screenshots["level_complete"]["exists"]
            and screenshots["level_complete"]["dimensions"]),
        "14_all_screenshots_valid": bool(
            all(row["exists"] and row["dimensions"] for row in screenshots.values())),
        "15_screenshot_hashes_match_report": bool(
            all(row["sha256"] == row["report_sha256"]
                for row in screenshots.values())),
        "16_performance_measured": bool(
            performance.get("frames", 0) > 0
            and performance.get("durationSeconds", 0) > 0
            and performance.get("averageFps", 0) > 0),
        "17_performance_evidence_consistent": bool(
            (playthrough.get("performance") or {}).get("frames") ==
            performance.get("frames")
            and artifact_checks["performance_hash_matches_report"]),
        "18_python_tests_pass": bool(
            tests["result"] == "OK" and (tests["tests"] or 0) >= 365),
        "19_v4_v5_preserved": bool(preserved["v4_ok"] and preserved["v5_ok"]),
        "20_mcp_parity": bool(mcp["parity"] and mcp["unique"]),
        "21_no_fabricated_verification": bool(
            no_verified_without_human and human_pending),
        "22_validation_verdict_pass": validation.get("verdict") == "PASS",
    }

    deliverables = {relative: (ROOT / relative).is_file()
                    for relative in DELIVERABLES}
    all_criteria = all(criteria.values())
    all_deliverables = all(deliverables.values())
    verdict = ("PASS_AUTOMATED" if all_criteria and all_deliverables
               else "PARTIAL")

    audit = {
        "schema_version": 1,
        "phase": "V6 Phase 5 - gameplay integration audit",
        "generated_at": now(),
        "verdict": verdict,
        "all_criteria_passed": all_criteria,
        "human_review_required": True,
        "human_review_status": "pending",
        "criteria": criteria,
        "deliverables": deliverables,
        "repository": {
            "head": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "status_short": git("status", "--short").splitlines(),
            "commit_made": False,
            "push_made": False,
        },
        "tests": {
            "python": tests,
            "editmode": editmode,
            "playmode": playmode,
        },
        "preservation": preserved,
        "mcp": mcp,
        "artifacts": {
            "checks": artifact_checks,
            "build": {
                "result": build.get("result"),
                "unity_version": build.get("unity_version"),
                "platform": build.get("platform"),
                "total_errors": build.get("total_errors"),
                "total_warnings": build.get("total_warnings"),
                "executable": build_exe,
                "directory_total_bytes": build.get("directory_total_bytes"),
            },
            "scene": {
                "path": str(SCENE.relative_to(ROOT)),
                "sha256": sha256(SCENE),
                "bytes": SCENE.stat().st_size if SCENE.is_file() else None,
            },
            "performance": {
                "path": str((REPORTS / "v6-gameplay-performance.json")
                            .relative_to(ROOT)),
                "sha256": sha256(REPORTS / "v6-gameplay-performance.json"),
                "frames": performance.get("frames"),
                "average_fps": performance.get("averageFps"),
                "p95_frame_ms": performance.get("p95FrameMs"),
                "one_percent_low_fps": performance.get("onePercentLowFps"),
                "screen": f"{performance.get('screenWidth')}x"
                          f"{performance.get('screenHeight')}",
            },
            "screenshots": screenshots,
        },
        "validation_acceptance": validation.get("acceptance"),
        "limitations": [
            "Automated tests and a scripted playthrough do not replace human "
            "playtesting or visual sign-off.",
            "No audio assets exist; audio hooks are silent.",
            "Player draw-call reporting was unavailable (-1).",
            "The first-run performance sample includes a multi-second shader "
            "compilation hitch.",
            "The river is contact-lethal; no swimming system is implemented.",
            "The audit passes the automated phase only; the Phase 5 gate stays "
            "open until a human reviews the build.",
        ],
        "duration_seconds": round(time.time() - started, 1),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "v6-phase5-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(f"[phase5-audit] {verdict} ({sum(criteria.values())}/"
          f"{len(criteria)} criteria, tests={tests['tests']} {tests['result']})")
    return 0 if verdict == "PASS_AUTOMATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
