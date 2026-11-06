#!/usr/bin/env python3
"""Independent evidence verifier for the V5 Unity jungle vertical slice.

This script reads the real artefacts produced by the V5 workflow and checks
their contents.  It deliberately distinguishes:

* PASS          an artefact exists and its content satisfies the check;
* FAIL          an artefact exists but is malformed or contradicts the claim;
* BLOCKED       a required artefact is missing, so the check cannot run;
* NOT VERIFIED  the claim needs evidence this script cannot provide (for
                example human playtesting, fun, visual quality).

It never launches Unity, Blender or the player.  A screenshot on disk is not
proof that every gameplay feature works.

Usage:
    python scripts/v5-verify-slice.py
    python scripts/v5-verify-slice.py --check jumping
    python scripts/v5-verify-slice.py --check all --json
    python scripts/v5-verify-slice.py --list-checks
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import zlib
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "validation" / "unity-jungle-v5"
BUILD_DIR = ROOT / "validation" / "builds" / "v5-windows"
PLAYMODE_XML = ROOT / "validation" / "v5-playmode-results.xml"
PLAYER_JSON = ROOT / "validation" / "v5-player-evidence.json"
PLAYER_LOG = ROOT / "validation" / "v5-player.log"
SCREENSHOT = ROOT / "validation" / "v5-player-screenshot.png"
PROVENANCE = ROOT / "validation" / "unity-player-build.provenance.json"
BUILD_LOG = ROOT / "validation" / "unity-player-build.log"
BLENDER_STATS = PROJECT / "v5-blender-assets.json"
SCENE = PROJECT / "Assets" / "V5" / "Scenes" / "JungleMonkey.unity"
SCRIPTS = PROJECT / "Assets" / "V5" / "Scripts"
ART = PROJECT / "Assets" / "V5" / "Art"
PREFABS = PROJECT / "Assets" / "V5" / "Prefabs"
MATERIALS = PROJECT / "Assets" / "V5" / "Materials"
EVIDENCE_COPIES = PROJECT / ".game-studio" / "evidence" / "source"

PASS, FAIL, BLOCKED, NOT_VERIFIED = "PASS", "FAIL", "BLOCKED", "NOT VERIFIED"

REQUIRED_SCRIPTS = {
    "MonkeyController.cs": ["class MonkeyController", "jumpHeight", "CharacterController",
                            "SetTestInput", "Teleport"],
    "CameraFollow.cs": ["class CameraFollow", "target", "LateUpdate"],
    "BananaCollectible.cs": ["class BananaCollectible", "OnTriggerEnter", "GameManager"],
    "GameManager.cs": ["class GameManager", "TotalBananas", "ResetState", "Score"],
    "HUDController.cs": ["class HUDController", "scoreText"],
    "V5DemoDriver.cs": ["class V5DemoDriver", "screenshot"],
}

PLAYMODE_TESTS = [
    "AnimatorReactsToMovement",
    "CollectibleIncrementsScoreAndDisappears",
    "HudDisplaysBananaProgress",
    "JumpRaisesPlayerAboveGround",
    "MovementChangesPlayerPosition",
    "NoMissingScriptsOrMaterials",
    "PlayerIsGroundedByPhysics",
    "RestartResetsScorePlayerAndBananas",
    "SceneContainsPlayerEnvironmentAndHud",
]


def _result(name: str, status: str, summary: str, **details: object) -> dict:
    return {"name": name, "status": status, "summary": summary, "details": details}


def _missing(name: str, path: Path) -> dict:
    return _result(name, BLOCKED, f"required artefact is missing: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_playmode() -> tuple[dict[str, str] | None, dict, str | None]:
    if not PLAYMODE_XML.is_file():
        return None, {}, f"missing {PLAYMODE_XML}"
    try:
        tree = ElementTree.parse(PLAYMODE_XML)
    except ElementTree.ParseError as exc:
        return None, {}, f"invalid XML: {exc}"
    root = tree.getroot()
    cases: dict[str, str] = {}
    for node in root.iter("test-case"):
        name = node.get("name") or node.get("methodname") or ""
        cases[name] = node.get("result") or "unknown"
    details = {
        "root_result": root.get("result"),
        "total": root.get("total"),
        "passed": root.get("passed"),
        "failed": root.get("failed"),
        "skipped": root.get("skipped"),
        "duration": root.get("duration"),
        "start_time": root.get("start-time"),
        "end_time": root.get("end-time"),
        "cases": cases,
        "sha256": _sha256(PLAYMODE_XML),
    }
    return cases, details, None


def check_playmode() -> dict:
    cases, details, error = _load_playmode()
    if cases is None:
        return _result("unity_playmode_xml", BLOCKED, error or "playmode XML unavailable")
    missing = [name for name in PLAYMODE_TESTS if name not in cases]
    failed = [name for name in PLAYMODE_TESTS if cases.get(name) not in (None, "Passed")]
    if missing or failed:
        return _result("unity_playmode_xml", FAIL,
                       "PlayMode results do not cover all required tests",
                       missing_tests=missing, failed_tests=failed, **details)
    if details.get("root_result") != "Passed" or details.get("failed") not in ("0", None):
        return _result("unity_playmode_xml", FAIL,
                       "PlayMode run did not report an overall pass", **details)
    return _result("unity_playmode_xml", PASS,
                   f"{len(PLAYMODE_TESTS)}/{len(PLAYMODE_TESTS)} required PlayMode tests passed",
                   **details)


def _playmode_case(name: str, label: str) -> dict:
    cases, details, error = _load_playmode()
    if cases is None:
        return _result(label, BLOCKED, error or "playmode XML unavailable")
    if name not in cases:
        return _result(label, FAIL, f"PlayMode test {name!r} is absent", **details)
    if cases[name] != "Passed":
        return _result(label, FAIL, f"PlayMode test {name!r} result={cases[name]!r}",
                       **details)
    return _result(label, PASS, f"PlayMode test {name!r} passed", **details)


def check_executable() -> dict:
    exe = BUILD_DIR / "JungleMonkey.exe"
    data = BUILD_DIR / "JungleMonkey_Data"
    player_dll = BUILD_DIR / "UnityPlayer.dll"
    if not exe.is_file():
        return _missing("windows_executable", exe)
    stat = exe.stat()
    with exe.open("rb") as handle:
        magic = handle.read(2)
    problems = []
    if magic != b"MZ":
        problems.append("executable does not start with the PE MZ signature")
    if stat.st_size < 100_000:
        problems.append(f"executable is implausibly small ({stat.st_size} bytes)")
    if not player_dll.is_file():
        problems.append("UnityPlayer.dll is missing")
    if not data.is_dir():
        problems.append("JungleMonkey_Data directory is missing")
    else:
        for required in ("globalgamemanagers", "level0", "sharedassets0.assets"):
            if not (data / required).is_file():
                problems.append(f"player data file missing: {required}")
    details = {
        "path": str(exe),
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 3),
        "sha256": _sha256(exe),
        "unity_player_bytes": player_dll.stat().st_size if player_dll.is_file() else None,
        "data_directory": str(data),
    }
    if problems:
        return _result("windows_executable", FAIL, "; ".join(problems), **details)
    return _result("windows_executable", PASS,
                   f"Windows player exists ({details['size_mb']} MB) with data and Unity runtime",
                   **details)


def check_build_evidence() -> dict:
    if not PROVENANCE.is_file():
        return _missing("build_evidence", PROVENANCE)
    try:
        payload = _read_json(PROVENANCE)
    except (OSError, ValueError) as exc:
        return _result("build_evidence", FAIL, f"build provenance is unreadable: {exc}")
    if not isinstance(payload, dict):
        return _result("build_evidence", FAIL, "build provenance is not a JSON object")
    build = payload.get("build") or {}
    editor = payload.get("editor") or {}
    problems = []
    if payload.get("outcome") != "success":
        problems.append(f"outcome={payload.get('outcome')!r}")
    if payload.get("exitCode") != 0:
        problems.append(f"exitCode={payload.get('exitCode')!r}")
    if build.get("target") != "StandaloneWindows64":
        problems.append(f"target={build.get('target')!r}")
    method = str(build.get("executeMethod") or "")
    if "V5Build" not in method or "Windows" not in method:
        problems.append(f"unexpected executeMethod={method!r}")
    if not str(editor.get("version") or "").startswith("6000."):
        problems.append(f"unexpected editor version={editor.get('version')!r}")
    log_tail = ""
    if BUILD_LOG.is_file():
        log_text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
        if "Build Finished, Result: Success." not in log_text:
            problems.append("build log does not record 'Build Finished, Result: Success.'")
        log_tail = log_text[-1200:]
    else:
        problems.append("build log is missing")
    details = {
        "path": str(PROVENANCE),
        "sha256": _sha256(PROVENANCE),
        "outcome": payload.get("outcome"),
        "exit_code": payload.get("exitCode"),
        "target": build.get("target"),
        "execute_method": method,
        "editor_version": editor.get("version"),
        "started_at": payload.get("startedAt"),
        "ended_at": payload.get("endedAt"),
        "build_log_tail": log_tail[-400:],
    }
    if problems:
        return _result("build_evidence", FAIL, "; ".join(problems), **details)
    return _result("build_evidence", PASS,
                   "build provenance and log record a successful StandaloneWindows64 build",
                   **details)


def check_player_runtime() -> dict:
    if not PLAYER_JSON.is_file():
        return _missing("player_runtime_evidence", PLAYER_JSON)
    try:
        payload = _read_json(PLAYER_JSON)
    except (OSError, ValueError) as exc:
        return _result("player_runtime_evidence", FAIL,
                       f"player evidence is unreadable: {exc}")
    if not isinstance(payload, dict):
        return _result("player_runtime_evidence", FAIL,
                       "player evidence is not a JSON object")
    problems = []
    if payload.get("demoRan") is not True:
        problems.append("demoRan is not true")
    if payload.get("scene") != "JungleMonkey":
        problems.append(f"scene={payload.get('scene')!r}")
    try:
        distance = float(payload.get("distanceMoved"))
    except (TypeError, ValueError):
        distance = -1.0
    if distance <= 1.0:
        problems.append(f"distanceMoved={payload.get('distanceMoved')!r}")
    try:
        peak = float(payload.get("peakY"))
    except (TypeError, ValueError):
        peak = -1.0
    if peak <= 0.2:
        problems.append(f"peakY={payload.get('peakY')!r}")
    if payload.get("groundedAtEnd") is not True:
        problems.append("groundedAtEnd is not true")
    if payload.get("totalBananas") != 10:
        problems.append(f"totalBananas={payload.get('totalBananas')!r}")
    try:
        score = int(payload.get("score"))
    except (TypeError, ValueError):
        score = -1
    if not 0 <= score <= int(payload.get("totalBananas") or 0):
        problems.append(f"score={payload.get('score')!r}")
    if payload.get("animatorPresent") is not True:
        problems.append("animatorPresent is not true")
    if payload.get("error"):
        problems.append(f"player reported error={payload.get('error')!r}")
    shot = Path(str(payload.get("screenshot") or ""))
    if not shot.is_file():
        problems.append(f"player evidence screenshot is missing: {shot}")
    log_ok = False
    if PLAYER_LOG.is_file():
        log_text = PLAYER_LOG.read_text(encoding="utf-8", errors="replace")
        log_ok = "Initialize engine version: 6000.6.2f1" in log_text
    if not log_ok:
        problems.append("player log does not show a 6000.6.2f1 engine start")
    details = {
        "path": str(PLAYER_JSON),
        "sha256": _sha256(PLAYER_JSON),
        "demo_ran": payload.get("demoRan"),
        "distance_moved": payload.get("distanceMoved"),
        "peak_y": payload.get("peakY"),
        "grounded_at_end": payload.get("groundedAtEnd"),
        "score": payload.get("score"),
        "total_bananas": payload.get("totalBananas"),
        "animator_present": payload.get("animatorPresent"),
        "screenshot_from_evidence": str(shot),
        "player_log_engine_start": log_ok,
        "caveat": "Machine-generated runtime evidence; it is not a human playtest and "
                  "was not independently re-run by this script.",
    }
    if problems:
        return _result("player_runtime_evidence", FAIL, "; ".join(problems), **details)
    return _result("player_runtime_evidence", PASS,
                   "built player evidence records movement, jump, grounding, score and animator",
                   **details)


def _png_info(path: Path) -> tuple[dict | None, str | None]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, str(exc)
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, "missing PNG signature"
    offset = 8
    width = height = None
    chunk_count = 0
    saw_iend = False
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc_bytes = data[offset + 8 + length:offset + 12 + length]
        if len(crc_bytes) != 4:
            return None, f"truncated {kind!r} chunk"
        crc = struct.unpack(">I", crc_bytes)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            return None, f"bad CRC in {kind!r} chunk"
        if kind == b"IHDR":
            if len(payload) != 13:
                return None, "IHDR has an unexpected length"
            width, height = struct.unpack(">II", payload[:8])
        chunk_count += 1
        offset += 12 + length
        if kind == b"IEND":
            saw_iend = True
            break
    if width is None or height is None:
        return None, "no IHDR dimensions"
    if not saw_iend:
        return None, "missing IEND chunk"
    return {"width": width, "height": height, "bytes": len(data),
            "chunks": chunk_count}, None


def check_screenshot() -> dict:
    if not SCREENSHOT.is_file():
        return _missing("screenshot", SCREENSHOT)
    info, error = _png_info(SCREENSHOT)
    if info is None:
        return _result("screenshot", FAIL, f"invalid PNG: {error}")
    problems = []
    if info["width"] < 320 or info["height"] < 180:
        problems.append(f"implausible dimensions {info['width']}x{info['height']}")
    if info["bytes"] < 10_000:
        problems.append(f"implausibly small PNG ({info['bytes']} bytes)")
    if PLAYER_JSON.is_file():
        try:
            payload = _read_json(PLAYER_JSON)
            referenced = Path(str(payload.get("screenshot") or ""))
            if referenced.is_file() and referenced.resolve() != SCREENSHOT.resolve():
                problems.append("player evidence references a different screenshot")
        except (OSError, ValueError):
            pass
    details = {"path": str(SCREENSHOT), "sha256": _sha256(SCREENSHOT), **info,
               "caveat": "A valid screenshot shows one rendered frame. It is not proof "
                         "that every gameplay feature works."}
    if problems:
        return _result("screenshot", FAIL, "; ".join(problems), **details)
    return _result("screenshot", PASS,
                   f"valid PNG {info['width']}x{info['height']} ({info['bytes']} bytes)",
                   **details)


def check_blender_assets() -> dict:
    if not BLENDER_STATS.is_file():
        return _missing("blender_assets", BLENDER_STATS)
    try:
        stats = _read_json(BLENDER_STATS)
    except (OSError, ValueError) as exc:
        return _result("blender_assets", FAIL, f"asset stats are unreadable: {exc}")
    if not isinstance(stats, dict):
        return _result("blender_assets", FAIL, "asset stats are not an object")
    monkey = stats.get("monkey") or {}
    jungle = stats.get("jungle") or {}
    banana = stats.get("banana") or {}
    problems = []
    if int(monkey.get("triangles") or 0) < 1_000:
        problems.append("monkey triangle count is too low")
    if int(monkey.get("bones") or 0) != 14:
        problems.append(f"monkey bones={monkey.get('bones')!r}, expected 14")
    if sorted(monkey.get("actions") or []) != ["Idle", "Jump", "Walk"]:
        problems.append(f"unexpected monkey actions={monkey.get('actions')!r}")
    if int(jungle.get("triangles") or 0) < 5_000:
        problems.append("jungle triangle count is too low")
    if len(jungle.get("materials") or []) < 6:
        problems.append("jungle material list has fewer than 6 entries")
    if int(banana.get("triangles") or 0) < 100:
        problems.append("banana triangle count is too low")
    files = {}
    for key, name in (("monkey", "Monkey.fbx"), ("jungle", "Jungle.fbx"),
                      ("banana", "Banana.fbx")):
        path = ART / name
        files[key] = {"path": str(path), "exists": path.is_file()}
        if not path.is_file():
            problems.append(f"missing {name}")
            continue
        with path.open("rb") as handle:
            header = handle.read(18)
        if header != b"Kaydara FBX Binary":
            problems.append(f"{name} is not a binary FBX file")
        files[key]["bytes"] = path.stat().st_size
    details = {"path": str(BLENDER_STATS), "sha256": _sha256(BLENDER_STATS),
               "monkey": monkey, "jungle": jungle, "banana": banana, "files": files,
               "caveat": "Counts come from the Blender generation step; this script does "
                         "not re-open Blender."}
    if problems:
        return _result("blender_assets", FAIL, "; ".join(problems), **details)
    return _result("blender_assets", PASS,
                   "Blender stats and binary FBX files are present and plausible", **details)


def _guid(meta: Path) -> str | None:
    if not meta.is_file():
        return None
    text = meta.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^guid:\s*([0-9a-fA-F]{32})\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def check_imported_assets() -> dict:
    scene_text = SCENE.read_text(encoding="utf-8", errors="replace") if SCENE.is_file() else ""
    prefab_text = (PREFABS / "Banana.prefab").read_text(
        encoding="utf-8", errors="replace") if (PREFABS / "Banana.prefab").is_file() else ""
    problems = []
    assets = {}
    for name, consumer in (("Monkey.fbx", scene_text), ("Jungle.fbx", scene_text),
                           ("Banana.fbx", prefab_text)):
        fbx = ART / name
        meta = ART / f"{name}.meta"
        guid = _guid(meta)
        entry = {"fbx": str(fbx), "meta": str(meta), "guid": guid,
                 "scene_or_prefab_reference": bool(guid and guid in consumer)}
        assets[name] = entry
        if not fbx.is_file():
            problems.append(f"missing imported source {name}")
        if not meta.is_file():
            problems.append(f"missing Unity meta for {name}")
        if not guid:
            problems.append(f"meta for {name} has no GUID")
        if not entry["scene_or_prefab_reference"]:
            problems.append(f"{name} GUID is not referenced by the scene/prefab")
        if meta.is_file():
            meta_text = meta.read_text(encoding="utf-8", errors="replace")
            if "ModelImporter:" not in meta_text:
                problems.append(f"meta for {name} has no ModelImporter")
    materials = sorted(path.name for path in MATERIALS.glob("*.mat"))
    if len(materials) < 9:
        problems.append(f"only {len(materials)} material assets found")
    banana_prefab = PREFABS / "Banana.prefab"
    if not banana_prefab.is_file():
        problems.append("Banana.prefab is missing")
    details = {"assets": assets, "materials": materials,
               "prefab": str(banana_prefab),
               "scene_references_monkey": assets["Monkey.fbx"]["scene_or_prefab_reference"],
               "scene_references_jungle": assets["Jungle.fbx"]["scene_or_prefab_reference"],
               "prefab_references_banana": assets["Banana.fbx"]["scene_or_prefab_reference"]}
    if problems:
        return _result("imported_unity_assets", FAIL, "; ".join(problems), **details)
    return _result("imported_unity_assets", PASS,
                   "FBX imports have GUIDs referenced by the scene and banana prefab",
                   **details)


def check_scene() -> dict:
    if not SCENE.is_file():
        return _missing("unity_scene", SCENE)
    text = SCENE.read_text(encoding="utf-8", errors="replace")
    problems = []
    required_names = ["Player", "HUD", "GameManager", "Main Camera"]
    missing_names = [name for name in required_names if f"m_Name: {name}" not in text]
    if missing_names:
        problems.append("missing scene objects: " + ", ".join(missing_names))
    script_markers = ["V5.Runtime::V5.MonkeyController", "V5.Runtime::V5.GameManager",
                      "V5.Runtime::V5.HUDController", "V5.Runtime::V5.CameraFollow",
                      "V5.Runtime::V5.BananaCollectible"]
    missing_scripts = [marker for marker in script_markers if marker not in text]
    if missing_scripts:
        problems.append("scene does not reference: " + ", ".join(missing_scripts))
    banana_count = text.count("m_EditorClassIdentifier: V5.Runtime::V5.BananaCollectible")
    if banana_count < 10:
        problems.append(f"only {banana_count} BananaCollectible components in the scene")
    if "TotalBananas: 10" not in text:
        problems.append("scene does not record TotalBananas: 10")
    if "Bananas:" not in text or "m_Text:" not in text:
        problems.append("HUD text is missing from the scene")
    if "JungleEnvironment" not in text:
        problems.append("jungle environment reference is missing")
    details = {"path": str(SCENE), "sha256": _sha256(SCENE),
               "bytes": SCENE.stat().st_size, "banana_components": banana_count,
               "script_markers": script_markers, "objects": required_names}
    if problems:
        return _result("unity_scene", FAIL, "; ".join(problems), **details)
    return _result("unity_scene", PASS,
                   "scene contains player, jungle, HUD, camera, manager and 10 bananas",
                   **details)


def check_runtime_scripts() -> dict:
    problems = []
    found = {}
    for name, markers in REQUIRED_SCRIPTS.items():
        path = SCRIPTS / name
        entry = {"path": str(path), "exists": path.is_file(), "markers": {}}
        found[name] = entry
        if not path.is_file():
            problems.append(f"missing {name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            present = marker in text
            entry["markers"][marker] = present
            if not present:
                problems.append(f"{name} lacks {marker!r}")
        entry["sha256"] = _sha256(path)
    assembly = SCRIPTS / "V5.Runtime.asmdef"
    if not assembly.is_file():
        problems.append("V5.Runtime.asmdef is missing")
    details = {"scripts": found, "assembly": str(assembly)}
    if problems:
        return _result("runtime_scripts", FAIL, "; ".join(problems), **details)
    return _result("runtime_scripts", PASS,
                   f"{len(REQUIRED_SCRIPTS)} runtime scripts contain the expected systems",
                   **details)


def check_gameplay_systems() -> dict:
    checks = {
        "movement": _playmode_case("MovementChangesPlayerPosition", "movement"),
        "jumping": _playmode_case("JumpRaisesPlayerAboveGround", "jumping"),
        "collectibles": _playmode_case(
            "CollectibleIncrementsScoreAndDisappears", "collectibles"),
        "score_hud": _playmode_case("HudDisplaysBananaProgress", "score_hud"),
        "restart": _playmode_case("RestartResetsScorePlayerAndBananas", "restart"),
        "animation": _playmode_case("AnimatorReactsToMovement", "animation"),
        "camera_and_scene": _playmode_case(
            "SceneContainsPlayerEnvironmentAndHud", "camera_and_scene"),
        "physics": _playmode_case("PlayerIsGroundedByPhysics", "physics"),
        "imports": _playmode_case("NoMissingScriptsOrMaterials", "imports"),
    }
    bad = {name: item["status"] for name, item in checks.items()
           if item["status"] != PASS}
    details = {"systems": {name: item["status"] for name, item in checks.items()}}
    if bad:
        return _result("gameplay_systems", FAIL,
                       "some required gameplay systems are not evidenced: " +
                       ", ".join(f"{name}={status}" for name, status in bad.items()),
                       **details)
    return _result("gameplay_systems", PASS,
                   "movement, jump, collectibles, score/HUD, restart, animation, camera, "
                   "physics and imports are backed by PlayMode tests", **details)


def check_human_playtest() -> dict:
    return _result(
        "human_playtest", NOT_VERIFIED,
        "no human playtest record exists; automated tests and a screenshot cannot "
        "verify fun, visual quality or every feature",
        expected_evidence="a dated human playtest checklist with build hash and observations")


def check_evidence_copies() -> dict:
    if not EVIDENCE_COPIES.is_dir():
        return _result("evidence_copies", NOT_VERIFIED,
                       "no in-project evidence copies are present")
    pairs = [
        (PLAYMODE_XML, "v5-playmode-results.xml"),
        (PLAYER_JSON, "v5-player-evidence.json"),
        (SCREENSHOT, "v5-player-screenshot.png"),
        (PROVENANCE, "unity-player-build.provenance.json"),
        (PLAYER_LOG, "v5-player.log"),
    ]
    mismatched = []
    checked = {}
    for source, name in pairs:
        copy = EVIDENCE_COPIES / name
        entry = {"source": str(source), "copy": str(copy),
                 "source_exists": source.is_file(), "copy_exists": copy.is_file()}
        if source.is_file() and copy.is_file():
            entry["source_sha256"] = _sha256(source)
            entry["copy_sha256"] = _sha256(copy)
            entry["match"] = entry["source_sha256"] == entry["copy_sha256"]
            if not entry["match"]:
                mismatched.append(name)
        checked[name] = entry
    if mismatched:
        return _result("evidence_copies", FAIL,
                       "in-project evidence copies differ from the originals: " +
                       ", ".join(mismatched), **checked)
    return _result("evidence_copies", PASS,
                   "in-project evidence copies match the original artefacts", **checked)


CHECKS = {
    "playmode": check_playmode,
    "jump": lambda: _playmode_case("JumpRaisesPlayerAboveGround", "jump"),
    "movement": lambda: _playmode_case("MovementChangesPlayerPosition", "movement"),
    "collect": lambda: _playmode_case("CollectibleIncrementsScoreAndDisappears", "collect"),
    "hud": lambda: _playmode_case("HudDisplaysBananaProgress", "hud"),
    "restart": lambda: _playmode_case("RestartResetsScorePlayerAndBananas", "restart"),
    "camera": lambda: _playmode_case("SceneContainsPlayerEnvironmentAndHud", "camera"),
    "animation": lambda: _playmode_case("AnimatorReactsToMovement", "animation"),
    "physics": lambda: _playmode_case("PlayerIsGroundedByPhysics", "physics"),
    "imports_playmode": lambda: _playmode_case("NoMissingScriptsOrMaterials", "imports"),
    "executable": check_executable,
    "build": check_build_evidence,
    "runtime": check_player_runtime,
    "screenshot": check_screenshot,
    "blender": check_blender_assets,
    "imported": check_imported_assets,
    "scene": check_scene,
    "scripts": check_runtime_scripts,
    "gameplay": check_gameplay_systems,
    "human": check_human_playtest,
    "evidence_copies": check_evidence_copies,
}

ALIASES = {
    "dimension_3d": ["scene", "build", "runtime"],
    "low_poly_style": ["blender", "imported"],
    "jungle_environment": ["scene", "imported", "camera"],
    "monkey_character": ["imported", "playmode", "scripts"],
    "pc_platform": ["executable", "build", "runtime"],
    "jumping": ["jump", "scripts", "runtime"],
    "collectibles": ["collect", "scene", "scripts"],
    "score": ["collect", "hud"],
    "player_traversal": ["movement", "scripts"],
    "interaction": ["collect", "scripts"],
    "objectives": ["collect", "scene"],
    "player_controller": ["movement", "jump", "scripts"],
    "camera_system": ["camera", "scripts"],
    "ui_hud": ["hud", "scene"],
    "asset_import": ["blender", "imported", "imports_playmode"],
    "animation": ["animation", "blender"],
    "platform_build": ["executable", "build", "runtime"],
    "all": ["playmode", "executable", "build", "runtime", "screenshot", "blender",
            "imported", "scene", "scripts", "gameplay", "evidence_copies", "human"],
}


def _aggregate(name: str, check_names: list[str]) -> dict:
    results = []
    for check_name in check_names:
        function = CHECKS.get(check_name)
        if function is None:
            results.append(_result(check_name, FAIL, "unknown check"))
        else:
            results.append(function())
    statuses = [item["status"] for item in results]
    if FAIL in statuses:
        status = FAIL
    elif BLOCKED in statuses:
        status = BLOCKED
    elif NOT_VERIFIED in statuses:
        status = NOT_VERIFIED
    else:
        status = PASS
    return {
        "name": name,
        "status": status,
        "summary": f"{sum(1 for item in results if item['status'] == PASS)}"
                   f"/{len(results)} component checks passed",
        "details": {"checks": results},
    }


def run(names: list[str]) -> list[dict]:
    results = []
    for name in names:
        if name in ALIASES:
            results.append(_aggregate(name, ALIASES[name]))
        elif name in CHECKS:
            results.append(CHECKS[name]())
        else:
            results.append(_result(name, FAIL, f"unknown check {name!r}"))
    return results


def _print_text(results: list[dict]) -> None:
    for item in results:
        print(f"[{item['status']}] {item['name']}: {item['summary']}")
        if item["status"] != PASS:
            details = item.get("details") or {}
            for key in ("missing_tests", "failed_tests", "expected_evidence"):
                if details.get(key):
                    print(f"    {key}: {details[key]}")
    counts = {status: sum(1 for item in results if item["status"] == status)
              for status in (PASS, FAIL, BLOCKED, NOT_VERIFIED)}
    print("Summary: " + ", ".join(f"{status}={count}" for status, count in counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="append", default=[],
                        help="check or alias to run; may be repeated")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--list-checks", action="store_true")
    args = parser.parse_args(argv)
    if args.list_checks:
        print("Checks: " + ", ".join(sorted(CHECKS)))
        print("Aliases: " + ", ".join(sorted(ALIASES)))
        return 0
    names: list[str] = []
    for value in args.check or ["all"]:
        names.extend(part.strip() for part in value.split(",") if part.strip())
    results = run(names)
    if args.json:
        print(json.dumps({"ok": all(item["status"] == PASS for item in results),
                          "checks": results}, indent=2, default=str))
    else:
        _print_text(results)
    if any(item["status"] == FAIL for item in results):
        return 1
    if any(item["status"] in (BLOCKED, NOT_VERIFIED) for item in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

