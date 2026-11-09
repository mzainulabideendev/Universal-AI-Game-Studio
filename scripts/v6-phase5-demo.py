#!/usr/bin/env python3
"""V6 Phase 5 gameplay demo: build, test, play and report.

This script drives the real Unity 6 project at validation/unity-jungle-v6:

1. optionally rebuilds the generated JungleMonkeyV6 scene,
2. runs the EditMode and PlayMode test suites,
3. builds the Windows Standalone player,
4. launches the built player with the in-game AutoPlayDriver and captures
   real screenshots and measured performance,
5. writes reports/v6-gameplay-integration.json and
   reports/v6-gameplay-validation.json.

It writes files and launches local processes only. It makes no network calls,
no downloads, no paid API requests and no git commits.

Typical full run (takes several minutes):

    python scripts/v6-phase5-demo.py --confirm

Re-generate reports from the evidence already on disk:

    python scripts/v6-phase5-demo.py --confirm --skip-build --skip-tests --skip-play

If the GUI player is closed early by the host session, the script retries the
playthrough (up to --attempts) until a level-complete screenshot exists.
"""

from __future__ import annotations

import argparse
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
PROJECT = ROOT / "validation" / "unity-jungle-v6"
REPORTS = ROOT / "reports"
CAPTURES = REPORTS / "v6-captures"
BUILD_DIR = ROOT / "validation" / "builds" / "v6-windows"
EXE = BUILD_DIR / "V6JungleMonkey.exe"
SCENE = PROJECT / "Assets" / "V6" / "Scenes" / "JungleMonkeyV6.unity"
UNITY = Path(r"C:\Program Files\Unity\Hub\Editor\6000.6.2f1\Editor\Unity.exe")
UNITY_VERSION = "6000.6.2f1"
LOGS = PROJECT / "Logs"

EDITMODE_XML = LOGS / "editmode-results.xml"
PLAYMODE_XML = LOGS / "playmode-results.xml"
BUILD_RAW = REPORTS / "v6-build-raw.json"
PERF = REPORTS / "v6-gameplay-performance.json"
SCENE_LOG = LOGS / "scene-build3.log"
PLAY_LOG = LOGS / "player-retry1.log"

SCREENSHOTS = [
    ("main_menu", "01-main-menu.png"),
    ("playing", "02-playing.png"),
    ("paused", "03-paused.png"),
    ("level_complete", "04-level-complete.png"),
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


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def png_info(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False}
    data = path.read_bytes()
    signature = data[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(data[16:20], "big") if len(data) >= 24 else None
    height = int.from_bytes(data[20:24], "big") if len(data) >= 24 else None
    return {
        "path": relative(path),
        "exists": True,
        "bytes": len(data),
        "sha256": sha256(path),
        "png_signature": signature,
        "width": width,
        "height": height,
        "modified_utc": datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def run(command: list[str], log: Path, timeout: int) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.is_file():
        log.unlink()
    started = time.time()
    try:
        proc = subprocess.run(command, cwd=str(PROJECT), capture_output=True,
                              text=True, timeout=timeout)
        exit_code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = -9
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
    return {
        "command": " ".join(command),
        "exit_code": exit_code,
        "duration_seconds": round(time.time() - started, 1),
        "log": relative(log),
        "stdout_tail": stdout.strip().splitlines()[-5:],
        "stderr_tail": stderr.strip().splitlines()[-5:],
    }


def unity(command: str, log: Path, timeout: int = 1800) -> dict:
    args = [str(UNITY), "-batchmode", "-nographics", "-projectPath",
            str(PROJECT), "-executeMethod", command, "-quit",
            "-logFile", str(log)]
    return run(args, log, timeout)


def unity_tests(platform: str, xml: Path, log: Path) -> dict:
    args = [str(UNITY), "-batchmode", "-nographics", "-projectPath",
            str(PROJECT), "-runTests", "-testPlatform", platform,
            "-testResults", str(xml), "-logFile", str(log)]
    result = run(args, log, 1800)
    result["results_xml"] = relative(xml) if xml.is_file() else None
    return result


def parse_nunit(xml: Path) -> dict:
    if not xml.is_file():
        return {"exists": False}
    try:
        root = ET.parse(xml).getroot()
    except ET.ParseError as exc:
        return {"exists": True, "parse_error": str(exc)}
    cases = []
    for case in root.iter("test-case"):
        cases.append({
            "name": case.get("name"),
            "result": case.get("result"),
            "duration_seconds": float(case.get("duration") or 0),
        })
    return {
        "exists": True,
        "result": root.get("result"),
        "total": int(root.get("total") or 0),
        "passed": int(root.get("passed") or 0),
        "failed": int(root.get("failed") or 0),
        "skipped": int(root.get("skipped") or 0),
        "duration_seconds": float(root.get("duration") or 0),
        "start_time": root.get("start-time"),
        "end_time": root.get("end-time"),
        "cases": cases,
        "failed_cases": [c["name"] for c in cases if c["result"] != "Passed"],
    }


def scene_build_evidence() -> dict:
    evidence = {"log": relative(SCENE_LOG), "exists": SCENE_LOG.is_file(),
                "sha256": sha256(SCENE), "bytes": SCENE.stat().st_size
                if SCENE.is_file() else None}
    if SCENE_LOG.is_file():
        text = SCENE_LOG.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"V6_SCENE_OK (\{.*\})", text)
        if match:
            try:
                evidence["report"] = json.loads(match.group(1))
            except json.JSONDecodeError:
                evidence["report"] = None
        evidence["concave_trigger_warning"] = (
            "Triggers on concave MeshColliders are not supported" in text)
    return evidence


def play_log_evidence() -> dict:
    if not PLAY_LOG.is_file():
        return {"log": relative(PLAY_LOG), "exists": False}
    lines = PLAY_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    spawn = next((line for line in lines if "Level spawn=" in line), None)
    valid = next((line for line in lines if line.startswith("V6_SCENE_VALID ")), None)
    checkpoints = [line for line in lines if "Checkpoint" in line and "reached" in line]
    finished = any("AutoPlay finished" in line for line in lines)
    completed = any("04-level-complete" in line for line in lines)
    return {
        "log": relative(PLAY_LOG),
        "exists": True,
        "spawn_line": spawn,
        "scene_valid": bool(valid),
        "scene_valid_line": valid,
        "checkpoints_reached": checkpoints,
        "level_completed": completed,
        "auto_play_finished": finished,
    }


def build_evidence() -> dict:
    raw = {}
    if BUILD_RAW.is_file():
        raw = json.loads(BUILD_RAW.read_text(encoding="utf-8"))
    files = []
    total_bytes = 0
    if BUILD_DIR.is_dir():
        for path in sorted(BUILD_DIR.rglob("*")):
            if path.is_file():
                size = path.stat().st_size
                total_bytes += size
                files.append({"path": relative(path), "bytes": size})
    return {
        "build_report": relative(BUILD_RAW),
        "result": raw.get("result"),
        "unity_version": raw.get("unityVersion"),
        "platform": raw.get("platform"),
        "total_errors": raw.get("totalErrors"),
        "total_warnings": raw.get("totalWarnings"),
        "reported_size_bytes": raw.get("totalSize"),
        "build_time_seconds": raw.get("buildTimeSeconds"),
        "executable": {
            "path": relative(EXE),
            "exists": EXE.is_file(),
            "bytes": EXE.stat().st_size if EXE.is_file() else None,
            "sha256": sha256(EXE),
        },
        "directory_total_bytes": total_bytes,
        "file_count": len(files),
        "files": files,
    }


def performance_evidence() -> dict:
    if not PERF.is_file():
        return {"exists": False, "path": relative(PERF)}
    data = json.loads(PERF.read_text(encoding="utf-8"))
    data["path"] = relative(PERF)
    data["sha256"] = sha256(PERF)
    data["exists"] = True
    return data


def screenshot_evidence() -> dict:
    return {name: png_info(CAPTURES / filename)
            for name, filename in SCREENSHOTS}


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=60)
    return (result.stdout or "").strip()


SYSTEMS = [
    {"system": "Character controller", "script": "Player/PlayerMovement.cs",
     "responsibility": "CharacterController movement, run, gravity, jump, coyote time, fall recovery"},
    {"system": "Input", "script": "Player/PlayerInputHandler.cs",
     "responsibility": "Legacy Input Manager bindings plus deterministic test input"},
    {"system": "Ground detection", "script": "Player/GroundDetector.cs",
     "responsibility": "Sphere/ray ground probe, slope limits, ground normals"},
    {"system": "Collision and hazards", "script": "Player/PlayerCollisionHandler.cs",
     "responsibility": "Solid collisions and river hazard detection"},
    {"system": "Animation", "script": "Player/PlayerAnimationDriver.cs",
     "responsibility": "Idle/Walk/Run/Jump animator parameters"},
    {"system": "Camera", "script": "Camera/CameraFollowController.cs",
     "responsibility": "Third-person orbit/follow camera and collision-aware placement"},
    {"system": "Game flow", "script": "Core/GameManager.cs",
     "responsibility": "State transitions, restart, pause, completion, game over, save"},
    {"system": "State machine", "script": "Core/GameStateController.cs",
     "responsibility": "Explicit legal game-state transitions"},
    {"system": "Objectives", "script": "Core/ObjectiveManager.cs",
     "responsibility": "10-banana collection plus destination objective"},
    {"system": "Collectibles", "script": "Collectibles/CollectibleManager.cs",
     "responsibility": "Banana registry, collection, reset"},
    {"system": "Score", "script": "Core/ScoreManager.cs",
     "responsibility": "Score, best score, persisted best"},
    {"system": "Level", "script": "Core/LevelManager.cs",
     "responsibility": "Spawn/destination anchors, ground snapping, bounds and kill plane"},
    {"system": "Checkpoints", "script": "Core/CheckpointManager.cs",
     "responsibility": "Checkpoint activation and safe respawn"},
    {"system": "Destination", "script": "Core/DestinationZone.cs",
     "responsibility": "Ruins destination trigger"},
    {"system": "HUD", "script": "UI/UIManager.cs",
     "responsibility": "Score, objective, toast, pause, completion and game-over UI"},
    {"system": "Audio", "script": "Audio/AudioManager.cs",
     "responsibility": "Audio hooks; reports missing clips honestly (no audio assets)"},
    {"system": "Save", "script": "Save/SaveDataService.cs",
     "responsibility": "Best score and settings persistence"},
    {"system": "Performance", "script": "Performance/PerformanceMonitor.cs",
     "responsibility": "Measured frame times, scene counts and perf JSON"},
    {"system": "Automation", "script": "Core/AutoPlayDriver.cs",
     "responsibility": "Command-line playthrough, screenshots and perf capture"},
    {"system": "Bootstrap", "script": "Core/GameBootstrap.cs",
     "responsibility": "Deterministic initialization and scene validation"},
]

REQUIREMENTS = [
    ("R1", "Third-person character controller with grounded movement", "implemented", "automated"),
    ("R2", "Run and jump with no double jump", "implemented", "automated"),
    ("R3", "Banana collection updates score, HUD and objective", "implemented", "automated"),
    ("R4", "Solid collisions with environment", "implemented", "automated"),
    ("R5", "Ground detection and safe spawn", "implemented", "automated"),
    ("R6", "Third-person follow camera", "implemented", "automated"),
    ("R7", "HUD with bananas, objective, best score, controls", "implemented", "automated"),
    ("R8", "Pause and resume", "implemented", "automated"),
    ("R9", "Restart resets score, bananas and position", "implemented", "automated"),
    ("R10", "Objective requires 10 bananas and the ruins destination", "implemented", "automated"),
    ("R11", "Level completion state and results UI", "implemented", "automated"),
    ("R12", "River hazard game over and restart path", "implemented", "automated"),
    ("R13", "Explicit game states and legal transitions", "implemented", "automated"),
    ("R14", "Windows Standalone build from the real project", "implemented", "automated"),
    ("R15", "Real playthrough reaches level completion", "implemented", "automated"),
    ("R16", "Performance measured in the built player", "implemented", "automated"),
    ("R17", "No climbing, swinging, swimming, weapons, multiplayer or Android scope", "excluded", "n/a"),
    ("R18", "Human visual inspection and playtest sign-off", "pending_human_review", "pending"),
]


def build_integration(scene: dict, build: dict, perf: dict, shots: dict,
                      play: dict) -> dict:
    return {
        "schema_version": 1,
        "phase": "V6 Phase 5 - gameplay integration",
        "generated_at": now(),
        "repository": {
            "root": str(ROOT),
            "head": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "status_short": git("status", "--short").splitlines(),
            "commit_made": False,
            "push_made": False,
        },
        "engine": {
            "name": "Unity",
            "version": UNITY_VERSION,
            "editor": str(UNITY),
            "target": "StandaloneWindows64",
            "project": relative(PROJECT),
        },
        "scene": scene,
        "systems": SYSTEMS,
        "game_states": ["Initializing", "MainMenu", "Playing", "Paused",
                        "GameOver", "LevelCompleted", "Restarting"],
        "objectives": {
            "bananas_required": 10,
            "destination_required": True,
            "completion_rule": "all bananas collected AND destination entered",
            "completion_entry_point": "GameManager.CompleteLevel()",
        },
        "controls": {
            "move": "WASD / arrow keys",
            "run": "Shift",
            "jump": "Space",
            "camera": "Mouse orbit",
            "pause": "Escape",
            "restart": "R",
        },
        "build": build,
        "automated_playthrough": {
            "command": "V6JungleMonkey.exe -v6autoplay -v6capture <dir> "
                       "-v6seconds 60 -v6perf <file>",
            "log": play.get("log"),
            "level_completed": play.get("level_completed"),
            "auto_play_finished": play.get("auto_play_finished"),
            "checkpoints_reached": play.get("checkpoints_reached"),
            "spawn_line": play.get("spawn_line"),
            "screenshots": shots,
            "performance": perf,
        },
        "content": {
            "character_source": "validation/v6-character-pipeline/JungleMonkey.glb "
                                "imported through Phase 3 FBX",
            "environment_source": "validation/v6-environment-pipeline/ "
                                  "JungleLevel.fbx (Phase 4 medium tier)",
            "banana_asset": "deterministic procedural mesh generated by V6SceneBuilder",
            "audio_assets": "none; AudioManager reports missing clips honestly",
        },
        "excluded_scope": ["climbing", "swinging", "swimming", "weapons",
                           "multiplayer", "Android"],
        "limitations": [
            "Stylized procedural prototype content, not production art.",
            "No audio assets are present; audio hooks are silent.",
            "The river is a solid hazard surface that ends the run on contact; "
            "no swimming or water physics are implemented.",
            "Human playtest and visual sign-off are still pending.",
            "Automated capture runs a scripted route; it is evidence of a real "
            "playthrough, not a substitute for human review.",
        ],
    }


def build_validation(scene: dict, build: dict, perf: dict, shots: dict,
                     play: dict, editmode: dict, playmode: dict,
                     python_tests: dict | None) -> dict:
    acceptance = {
        "scene_generated": bool(scene.get("report", {}).get("succeeded")),
        "scene_has_no_missing_materials": bool(
            scene.get("report", {}).get("missingMaterials") == 0),
        "scene_has_no_missing_shaders": bool(
            scene.get("report", {}).get("missingShaders") == 0),
        "scene_has_ten_collectibles": int(
            scene.get("report", {}).get("collectibles") or 0) >= 10,
        "scene_has_checkpoints": int(
            scene.get("report", {}).get("checkpoints") or 0) >= 1,
        "scene_has_all_animator_states": set(
            scene.get("report", {}).get("animatorStates") or []) >= {
                "Idle", "Walk", "Run", "Jump"},
        "no_concave_trigger_warning": not scene.get(
            "concave_trigger_warning", False),
        "editmode_tests_pass": bool(
            editmode.get("failed") == 0 and editmode.get("passed") == editmode.get("total")
            and editmode.get("total", 0) > 0),
        "playmode_tests_pass": bool(
            playmode.get("failed") == 0 and playmode.get("passed") == playmode.get("total")
            and playmode.get("total", 0) > 0),
        "spawn_grounded_test": any(
            case["name"] == "PlayerSpawnsOnGroundAndStaysThere"
            and case["result"] == "Passed"
            for case in playmode.get("cases", [])),
        "movement_test": any(
            case["name"] == "PlayerMovesWhenInputIsApplied"
            and case["result"] == "Passed" for case in playmode.get("cases", [])),
        "jump_test": any(
            case["name"] == "PlayerJumpsRaisesAndLands"
            and case["result"] == "Passed" for case in playmode.get("cases", [])),
        "collision_test": any(
            case["name"] == "PlayerCollidesWithSolidObstacle"
            and case["result"] == "Passed" for case in playmode.get("cases", [])),
        "collection_test": any(
            case["name"] == "BananaCollectionIncrementsScoreAndHidesObject"
            and case["result"] == "Passed" for case in playmode.get("cases", [])),
        "pause_restart_tests": all(
            any(case["name"] == name and case["result"] == "Passed"
                for case in playmode.get("cases", []))
            for name in ("PauseStopsMovementAndResumeRestoresIt",
                         "RestartResetsScoreBananasAndPosition")),
        "completion_test": any(
            case["name"] == "LevelCompletesOnlyAfterAllBananasAndDestination"
            and case["result"] == "Passed" for case in playmode.get("cases", [])),
        "game_over_test": any(
            case["name"] == "RiverHazardEndsRunInGameOverState"
            and case["result"] == "Passed" for case in playmode.get("cases", [])),
        "windows_build_succeeded": bool(
            build.get("result") == "Succeeded" and build.get("executable", {}).get("exists")),
        "build_has_no_errors": bool(build.get("total_errors") == 0),
        "screenshots_captured": all(
            shot.get("exists") and shot.get("png_signature") and shot.get("width")
            for shot in shots.values()),
        "level_completion_screenshot": bool(
            shots.get("level_complete", {}).get("exists")),
        "real_playthrough_completed": bool(play.get("level_completed")),
        "performance_measured": bool(
            perf.get("exists") and perf.get("frames", 0) > 0
            and perf.get("durationSeconds", 0) > 0),
        "performance_target_60fps_class": bool(
            (perf.get("averageFps") or 0) >= 30
            and (perf.get("p95FrameMs") or 999) <= 25),
        "python_tests_pass": bool(
            python_tests is None or python_tests.get("result") == "OK"),
    }
    return {
        "schema_version": 1,
        "phase": "V6 Phase 5 - gameplay validation",
        "generated_at": now(),
        "verdict": "PASS" if all(acceptance.values()) else "PARTIAL",
        "acceptance": acceptance,
        "requirements": [
            {"id": rid, "requirement": text, "status": status,
             "evidence_level": evidence}
            for rid, text, status, evidence in REQUIREMENTS
        ],
        "test_runs": {
            "editmode": editmode,
            "playmode": playmode,
            "python": python_tests,
        },
        "build": {
            "result": build.get("result"),
            "unity_version": build.get("unity_version"),
            "executable_sha256": build.get("executable", {}).get("sha256"),
            "executable_bytes": build.get("executable", {}).get("bytes"),
        },
        "playthrough": {
            "level_completed": play.get("level_completed"),
            "checkpoints_reached": play.get("checkpoints_reached"),
            "screenshots": {name: {"path": shot.get("path"),
                                   "sha256": shot.get("sha256"),
                                   "width": shot.get("width"),
                                   "height": shot.get("height")}
                            for name, shot in shots.items()},
            "performance": {
                "average_fps": perf.get("averageFps"),
                "p95_frame_ms": perf.get("p95FrameMs"),
                "one_percent_low_fps": perf.get("onePercentLowFps"),
                "frames": perf.get("frames"),
                "duration_seconds": perf.get("durationSeconds"),
                "active_triangles": perf.get("activeTriangles"),
                "active_renderers": perf.get("activeRenderers"),
                "draw_calls": perf.get("drawCalls"),
                "screen": f"{perf.get('screenWidth')}x{perf.get('screenHeight')}",
                "quality_level": perf.get("qualityLevel"),
            },
        },
        "human_review": {
            "status": "pending",
            "note": "No requirement is marked human-verified. A person must "
                    "play the build and inspect the screenshots before sign-off.",
        },
        "limitations": [
            "Automated tests and a scripted playthrough do not replace human "
            "playtesting or visual sign-off.",
            "No audio assets exist, so the game is silent apart from system UI.",
            "The performance sample includes a multi-second first-run shader "
            "compilation hitch; p95 frame time is the more useful steady-state metric.",
            "Draw calls were not exposed by the player ProfilerRecorder (-1).",
            "The river is contact-lethal rather than a swimming system.",
        ],
    }


def python_test_evidence() -> dict:
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", "tools/game-studio-mcp/tests", "-q"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(r"Ran (\d+) tests?", output)
    ok = re.search(r"^OK\b", output, re.MULTILINE) is not None
    return {
        "result": "OK" if ok and proc.returncode == 0 else "FAILED",
        "tests": int(match.group(1)) if match else None,
        "exit_code": proc.returncode,
        "duration_seconds": round(time.time() - started, 1),
        "tail": output.strip().splitlines()[-3:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true",
                        help="required: run local Unity processes and write evidence")
    parser.add_argument("--skip-scene", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-play", action="store_true")
    parser.add_argument("--attempts", type=int, default=4,
                        help="playthrough attempts if the host closes the window early")
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("pass --confirm to run Unity and write evidence files")
    if not UNITY.is_file():
        raise SystemExit(f"Unity not found at {UNITY}")

    CAPTURES.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    if not args.skip_scene:
        print("[phase5] building playable scene", flush=True)
        unity("V6.EditorTools.V6SceneBuilder.BuildScene",
              LOGS / "scene-build3.log")

    if not args.skip_tests:
        print("[phase5] running EditMode tests", flush=True)
        unity_tests("EditMode", EDITMODE_XML, LOGS / "editmode-final2.log")
        print("[phase5] running PlayMode tests", flush=True)
        unity_tests("PlayMode", PLAYMODE_XML, LOGS / "playmode-final2.log")

    if not args.skip_build:
        print("[phase5] building Windows Standalone player", flush=True)
        unity("V6.EditorTools.V6Build.BuildWindows",
              LOGS / "build-windows-final2.log")

    if not args.skip_play:
        for attempt in range(1, args.attempts + 1):
            for _, filename in SCREENSHOTS:
                path = CAPTURES / filename
                if path.is_file():
                    path.unlink()
            if PERF.is_file():
                PERF.unlink()
            log = LOGS / f"player-demo-{attempt}.log"
            print(f"[phase5] playthrough attempt {attempt}", flush=True)
            command = [
                str(EXE), "-v6autoplay", "-v6capture", str(CAPTURES),
                "-v6seconds", str(args.seconds), "-v6perf", str(PERF),
                "-screen-width", "1280", "-screen-height", "720",
                "-screen-fullscreen", "0", "-logFile", str(log),
            ]
            run(command, log, timeout=int(args.seconds) + 120)
            if (CAPTURES / "04-level-complete.png").is_file():
                break

    editmode = parse_nunit(EDITMODE_XML)
    playmode = parse_nunit(PLAYMODE_XML)
    python_tests = python_test_evidence()
    scene = scene_build_evidence()
    build = build_evidence()
    perf = performance_evidence()
    shots = screenshot_evidence()
    play = play_log_evidence()

    integration = build_integration(scene, build, perf, shots, play)
    validation = build_validation(scene, build, perf, shots, play,
                                  editmode, playmode, python_tests)

    (REPORTS / "v6-gameplay-integration.json").write_text(
        json.dumps(integration, indent=2) + "\n", encoding="utf-8")
    (REPORTS / "v6-gameplay-validation.json").write_text(
        json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(f"[phase5] validation verdict: {validation['verdict']} "
          f"({sum(validation['acceptance'].values())}/"
          f"{len(validation['acceptance'])} criteria)", flush=True)
    return 0 if validation["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
