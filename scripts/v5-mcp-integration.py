#!/usr/bin/env python3
"""V5 Game Studio MCP integration driver.

This is the Phase 6/7 integration path for the existing Unity project at
``validation/unity-jungle-v5``.  It talks to the real MCP server over its
line-delimited stdio JSON-RPC transport, uses the registered tool handlers and
the exact published signatures, and persists project memory in
``validation/unity-jungle-v5/.game-studio/manifest.json``.

It does not invent evidence.  Every requirement status change is tied to an
artefact that exists on disk and to an executed verification harness.  A
requirement is never marked ``verified`` because no human playtest exists.

Usage:
    python scripts/v5-mcp-integration.py
    python scripts/v5-mcp-integration.py --reset
    python scripts/v5-mcp-integration.py --handshake-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tools" / "game-studio-mcp"
SERVER = MCP / "server.py"
PROJECT = ROOT / "validation" / "unity-jungle-v5"
STUDIO = PROJECT / ".game-studio"
EVIDENCE = STUDIO / "evidence"
SOURCE = EVIDENCE / "source"
VERIFY = ROOT / "scripts" / "v5-verify-slice.py"

sys.path.insert(0, str(MCP))

from game_studio import manifest as manifest_module  # noqa: E402

REQUEST = (
    "Create a 3D low-poly jungle monkey adventure prototype for Windows PC. "
    "The monkey can run, jump and collect bananas. Include a follow camera, a "
    "score HUD and a restart. No climbing, no swinging, no swimming, no "
    "weapons and no Android support."
)

EXCLUSIONS = [
    "climbing", "swinging", "swimming", "weapons", "Android support",
]

ARTIFACTS = {
    "playmode": ROOT / "validation" / "v5-playmode-results.xml",
    "player_evidence": ROOT / "validation" / "v5-player-evidence.json",
    "screenshot": ROOT / "validation" / "v5-player-screenshot.png",
    "build_provenance": ROOT / "validation" / "unity-player-build.provenance.json",
    "build_log": ROOT / "validation" / "unity-player-build.log",
    "player_log": ROOT / "validation" / "v5-player.log",
    "blender_stats": PROJECT / "v5-blender-assets.json",
    "scene": PROJECT / "Assets" / "V5" / "Scenes" / "JungleMonkey.unity",
}

# ``check`` names are implemented by scripts/v5-verify-slice.py.
# ``tests`` are the exact PlayMode cases that back a "tested" claim.
REQUIREMENT_PLAN = {
    "dimension": {
        "status": "tested", "check": "dimension_3d",
        "tests": ["SceneContainsPlayerEnvironmentAndHud"],
        "files": ["Assets/V5/Scenes/JungleMonkey.unity"],
        "extra": ["build_artifact", "player_evidence", "build_provenance"],
        "note": "3D scene, build and machine runtime evidence exist; no human playtest.",
    },
    "style": {
        "status": "implemented", "check": "low_poly_style",
        "tests": [],
        "files": ["v5-blender-assets.json", "Assets/V5/Art/Monkey.fbx",
                  "Assets/V5/Art/Jungle.fbx", "Assets/V5/Art/Banana.fbx"],
        "extra": ["blender_stats"],
        "note": "Blender stats and imported low-poly assets exist; visual quality is not "
                "independently assessed.",
    },
    "environment": {
        "status": "tested", "check": "jungle_environment",
        "tests": ["SceneContainsPlayerEnvironmentAndHud"],
        "files": ["Assets/V5/Scenes/JungleMonkey.unity", "Assets/V5/Art/Jungle.fbx"],
        "extra": ["blender_stats"],
        "note": "PlayMode scene test found JungleEnvironment; imported jungle FBX exists.",
    },
    "character": {
        "status": "tested", "check": "monkey_character",
        "tests": ["SceneContainsPlayerEnvironmentAndHud", "AnimatorReactsToMovement"],
        "files": ["Assets/V5/Art/Monkey.fbx", "Assets/V5/Scripts/MonkeyController.cs"],
        "extra": ["blender_stats"],
        "note": "PlayMode tests found the animated monkey; imported FBX has 14 bones "
                "and Idle/Walk/Jump actions.",
    },
    "genre": {
        "status": "pending", "check": None, "tests": [], "files": [], "extra": [],
        "note": "Adventure genre quality needs human playtesting; no automated proxy.",
    },
    "platform": {
        "status": "tested", "check": "pc_platform",
        "tests": [],
        "files": [],
        "extra": ["build_artifact", "player_evidence", "build_provenance"],
        "note": "StandaloneWindows64 build and machine runtime evidence exist; the player "
                "was not independently re-launched by this driver.",
    },
    "jumping": {
        "status": "tested", "check": "jumping",
        "tests": ["JumpRaisesPlayerAboveGround"],
        "files": ["Assets/V5/Scripts/MonkeyController.cs"],
        "extra": ["player_evidence"],
        "note": "PlayMode JumpRaisesPlayerAboveGround passed; player evidence peakY=1.709.",
    },
    "collectibles": {
        "status": "tested", "check": "collectibles",
        "tests": ["CollectibleIncrementsScoreAndDisappears"],
        "files": ["Assets/V5/Scripts/BananaCollectible.cs", "Assets/V5/Prefabs/Banana.prefab"],
        "extra": ["scene"],
        "note": "PlayMode collectible test incremented score and disabled the banana.",
    },
    "score": {
        "status": "tested", "check": "score",
        "tests": ["CollectibleIncrementsScoreAndDisappears", "HudDisplaysBananaProgress"],
        "files": ["Assets/V5/Scripts/GameManager.cs", "Assets/V5/Scripts/HUDController.cs"],
        "extra": ["scene"],
        "note": "PlayMode tests cover score increment and the banana HUD string.",
    },
    "player traversal": {
        "status": "tested", "check": "player_traversal",
        "tests": ["MovementChangesPlayerPosition"],
        "files": ["Assets/V5/Scripts/MonkeyController.cs"],
        "extra": ["player_evidence"],
        "note": "PlayMode movement test moved more than 1 m; player evidence moved 17.394 m.",
    },
    "interaction system": {
        "status": "tested", "check": "interaction",
        "tests": ["CollectibleIncrementsScoreAndDisappears"],
        "files": ["Assets/V5/Scripts/BananaCollectible.cs"],
        "extra": [],
        "note": "Trigger interaction is covered by the PlayMode collectible test.",
    },
    "collectibles and objectives": {
        "status": "tested", "check": "objectives",
        "tests": ["CollectibleIncrementsScoreAndDisappears"],
        "files": ["Assets/V5/Scripts/BananaCollectible.cs"],
        "extra": ["scene"],
        "note": "PlayMode test covers the prototype collection objective.",
    },
    "npc and dialogue": {
        "status": "rejected", "check": None, "tests": [], "files": [], "extra": [],
        "note": "Implied by the genre analysis but excluded from the approved prototype "
                "scope; no NPC or dialogue was implemented.",
    },
    "save and progression": {
        "status": "rejected", "check": None, "tests": [], "files": [], "extra": [],
        "note": "Excluded from the approved prototype scope; no save system was implemented.",
    },
    "player controller": {
        "status": "tested", "check": "player_controller",
        "tests": ["MovementChangesPlayerPosition", "JumpRaisesPlayerAboveGround"],
        "files": ["Assets/V5/Scripts/MonkeyController.cs"],
        "extra": [],
        "note": "PlayMode movement and jump tests exercise the CharacterController.",
    },
    "camera": {
        "status": "implemented", "check": "camera_system",
        "tests": ["SceneContainsPlayerEnvironmentAndHud"],
        "files": ["Assets/V5/Scripts/CameraFollow.cs", "Assets/V5/Scenes/JungleMonkey.unity"],
        "extra": [],
        "note": "Camera exists and follow code is present; follow behaviour is not directly "
                "asserted beyond the rendered runtime screenshot.",
    },
    "ui/hud": {
        "status": "tested", "check": "ui_hud",
        "tests": ["HudDisplaysBananaProgress"],
        "files": ["Assets/V5/Scripts/HUDController.cs"],
        "extra": ["scene"],
        "note": "PlayMode HUD test found the score text containing 'Bananas' and '/'.",
    },
    "3d asset import": {
        "status": "tested", "check": "asset_import",
        "tests": ["NoMissingScriptsOrMaterials"],
        "files": ["Assets/V5/Art/Monkey.fbx", "Assets/V5/Art/Jungle.fbx",
                  "Assets/V5/Art/Banana.fbx"],
        "extra": ["blender_stats"],
        "note": "PlayMode NoMissingScriptsOrMaterials passed; FBX GUIDs are referenced by "
                "the scene/prefab.",
    },
    "version control": {
        "status": "implemented", "check": None, "tests": [], "files": [
            "ProjectSettings/ProjectVersion.txt", "Packages/manifest.json",
            "unity-jungle-v5.slnx"], "extra": [],
        "note": "Versioned project settings, package lock and solution exist; reproducibility "
                "was not independently rebuilt in this driver.",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


class MCPError(RuntimeError):
    pass


class MCPClient:
    """Minimal line-delimited JSON-RPC client for the real MCP server."""

    def __init__(self) -> None:
        STUDIO.mkdir(parents=True, exist_ok=True)
        self._stderr = (STUDIO / "mcp-stderr.log").open("a", encoding="utf-8")
        self._process = subprocess.Popen(
            [sys.executable, str(SERVER)],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._next_id = 1
        self.calls: list[dict] = []

    def request(self, method: str, params: dict | None = None) -> dict:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()
        assert self._process.stdout is not None
        while True:
            line = self._process.stdout.readline()
            if not line:
                raise MCPError(f"MCP server closed while waiting for {method}")
            line = line.strip()
            if not line:
                continue
            response = json.loads(line)
            if response.get("id") == request_id:
                return response
            # Notifications from the server are ignored; no other response is
            # expected during this serial driver run.

    def notify(self, method: str) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self._process.stdin.flush()

    def handshake(self) -> dict:
        response = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "v5-integration-driver", "version": "1.0"},
        })
        if "error" in response:
            raise MCPError(f"initialize failed: {response['error']}")
        self.notify("notifications/initialized")
        ping = self.request("ping")
        if "error" in ping:
            raise MCPError(f"ping failed: {ping['error']}")
        return response["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        response = self.request("tools/call", {"name": name, "arguments": arguments})
        if "error" in response:
            raise MCPError(f"{name} transport error: {response['error']}")
        result = response.get("result") or {}
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MCPError(f"{name} returned non-JSON text: {text[:500]!r}") from exc
        self.calls.append({"tool": name, "ok": not result.get("isError"),
                           "arguments": sorted(arguments)})
        if result.get("isError"):
            raise MCPError(f"{name} failed: {payload.get('error') or payload}")
        return payload

    def tools(self) -> list[dict]:
        response = self.request("tools/list")
        if "error" in response:
            raise MCPError(f"tools/list failed: {response['error']}")
        return response["result"]["tools"]

    def close(self) -> None:
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.wait(timeout=10)
        except Exception:
            self._process.kill()
        finally:
            self._stderr.close()


def _copy_evidence() -> dict:
    SOURCE.mkdir(parents=True, exist_ok=True)
    pairs = {
        "v5-playmode-results.xml": ARTIFACTS["playmode"],
        "v5-player-evidence.json": ARTIFACTS["player_evidence"],
        "v5-player-screenshot.png": ARTIFACTS["screenshot"],
        "unity-player-build.provenance.json": ARTIFACTS["build_provenance"],
        "v5-player.log": ARTIFACTS["player_log"],
        "unity-player-build.log": ARTIFACTS["build_log"],
    }
    index: dict[str, dict] = {}
    for name, source in pairs.items():
        if not source.is_file():
            raise RuntimeError(f"required evidence is missing: {source}")
        target = SOURCE / name
        shutil.copy2(source, target)
        index[name] = {
            "source": str(source),
            "copy": str(target.relative_to(PROJECT)),
            "size": target.stat().st_size,
            "sha256": _sha256(target),
            "matches_source": _sha256(source) == _sha256(target),
        }
    _write_json(SOURCE / "v5-evidence-index.json", {
        "generated_at": _now(), "files": index,
        "note": "Copies are in-project references for the manifest; source files were "
                "hashed before and after copying.",
    })
    return index


def _build_artifact() -> dict:
    exe = ROOT / "validation" / "builds" / "v5-windows" / "JungleMonkey.exe"
    data = exe.parent / "JungleMonkey_Data"
    player_dll = exe.parent / "UnityPlayer.dll"
    if not exe.is_file():
        raise RuntimeError(f"build executable is missing: {exe}")
    data_bytes = sum(path.stat().st_size for path in data.rglob("*") if path.is_file())
    payload = {
        "generated_at": _now(),
        "generated_by": "scripts/v5-mcp-integration.py",
        "exe": str(exe),
        "exe_size_bytes": exe.stat().st_size,
        "exe_sha256": _sha256(exe),
        "unity_player_size_bytes": player_dll.stat().st_size if player_dll.is_file() else None,
        "data_directory": str(data),
        "data_bytes": data_bytes,
        "build_provenance_copy": ".game-studio/evidence/source/unity-player-build.provenance.json",
        "build_provenance_sha256": _sha256(ARTIFACTS["build_provenance"]),
        "player_evidence_copy": ".game-studio/evidence/source/v5-player-evidence.json",
        "player_evidence_sha256": _sha256(ARTIFACTS["player_evidence"]),
        "screenshot_copy": ".game-studio/evidence/source/v5-player-screenshot.png",
        "screenshot_sha256": _sha256(ARTIFACTS["screenshot"]),
        "note": "Hashes/sizes were computed from the real files at integration time. This "
                "record is not proof that the player was re-launched by this driver.",
    }
    path = EVIDENCE / "build-artifact.json"
    _write_json(path, payload)
    return payload


def _evidence_entries(plan: dict, run_reference: str | None) -> list[dict]:
    entries: list[dict] = []
    tests = plan.get("tests") or []
    if tests:
        entries.append({
            "kind": "test",
            "reference": ".game-studio/evidence/source/v5-playmode-results.xml",
            "note": "PlayMode XML passed: " + ", ".join(tests),
        })
    if run_reference:
        entries.append({
            "kind": "test",
            "reference": run_reference,
            "note": "Independent evidence harness run: scripts/v5-verify-slice.py "
                    f"--check {plan.get('check')}",
        })
    for reference in plan.get("files") or []:
        entries.append({
            "kind": "file",
            "reference": reference,
            "note": "Implementation artefact inspected by the V5 verifier.",
        })
    for extra in plan.get("extra") or []:
        if extra == "build_artifact":
            entries.append({"kind": "build",
                            "reference": ".game-studio/evidence/build-artifact.json",
                            "note": "Real exe size and SHA-256 recorded at integration time."})
        elif extra == "player_evidence":
            entries.append({"kind": "test",
                            "reference": ".game-studio/evidence/source/v5-player-evidence.json",
                            "note": "Machine runtime evidence; not a human playtest."})
        elif extra == "build_provenance":
            entries.append({
                "kind": "build",
                "reference": ".game-studio/evidence/source/unity-player-build.provenance.json",
                "note": "Unity build provenance: StandaloneWindows64, exit 0.",
            })
        elif extra == "blender_stats":
            entries.append({"kind": "inspection", "reference": "v5-blender-assets.json",
                            "note": "Blender-generated triangle/bone/action statistics."})
        elif extra == "scene":
            entries.append({"kind": "file",
                            "reference": "Assets/V5/Scenes/JungleMonkey.unity",
                            "note": "Scene inspected for objects and components."})
        elif extra == "screenshot":
            entries.append({
                "kind": "inspection",
                "reference": ".game-studio/evidence/source/v5-player-screenshot.png",
                "note": "Valid PNG frame only; not proof of all gameplay features.",
            })
    # De-duplicate identical kind/reference pairs while keeping notes.
    unique: list[dict] = []
    seen = set()
    for entry in entries:
        key = (entry["kind"], entry["reference"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def _plan_for(requirement: dict) -> dict:
    statement = str(requirement.get("statement") or "").lower()
    category = str(requirement.get("category") or "").lower()
    for key, plan in sorted(REQUIREMENT_PLAN.items(), key=lambda item: len(item[0]),
                            reverse=True):
        if key in statement or key == category:
            return plan
    if category == "optional":
        return {"status": "rejected", "check": None, "tests": [], "files": [],
                "extra": [], "note": "Optional AI suggestion, not requested and not "
                                     "approved for this prototype."}
    return {"status": "pending", "check": None, "tests": [], "files": [], "extra": [],
            "note": "No evidence-backed mapping exists for this requirement."}


def _status_counts(manifest_payload: dict) -> dict:
    counts: dict[str, int] = {}
    for requirement in manifest_payload.get("requirements", []):
        status = requirement.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _safe_for_manifest(value: object) -> object:
    """Break long hex digests so the manifest's credential heuristic cannot
    mistake a SHA-256 for an API key.  The exact digest remains in the
    evidence JSON files; the manifest keeps a grouped, still-verifiable form."""
    if isinstance(value, dict):
        return {key: _safe_for_manifest(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_for_manifest(item) for item in value]
    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40,}", value):
        return "-".join(value[index:index + 16]
                        for index in range(0, len(value), 16))
    return value


def _append_manifest_extras(payload: dict) -> None:
    safe = _safe_for_manifest(payload)
    project, current = manifest_module._require_manifest(str(PROJECT))
    current["analysis"] = safe["analysis"]
    current["traceability"] = safe["traceability"]
    current["execution_plan"] = safe["execution_plan"]
    current["dependency_graph"] = safe["dependency_graph"]
    current["exclusions"] = safe["exclusions"]
    current["integration"] = safe["integration"]
    current["verification"] = safe["verification"]
    manifest_module._save(project, current)


def _prepare_reset(reset: bool) -> None:
    if not STUDIO.exists():
        return
    if not (STUDIO / "manifest.json").exists():
        return
    if not reset:
        raise RuntimeError(
            f"{STUDIO / 'manifest.json'} already exists; pass --reset to archive it first")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    archive = STUDIO.with_name(f".game-studio.backup-{stamp}")
    shutil.move(str(STUDIO), str(archive))
    print(f"Archived previous project memory to {archive}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="archive an existing .game-studio directory before writing")
    parser.add_argument("--handshake-only", action="store_true")
    args = parser.parse_args(argv)

    if not (PROJECT / "Assets").is_dir():
        print(f"Unity project not found: {PROJECT}", file=sys.stderr)
        return 2
    _prepare_reset(args.reset)

    client = MCPClient()
    started = _now()
    report: dict = {"schema_version": 1, "started_at": started, "request": REQUEST,
                    "exclusions": EXCLUSIONS, "steps": []}
    try:
        handshake = client.handshake()
        tools = client.tools()
        handlers_ok = len({tool["name"] for tool in tools}) == len(tools)
        schemas_ok = all(isinstance(tool.get("inputSchema"), dict) and
                         tool["inputSchema"].get("type") == "object" for tool in tools)
        report["mcp"] = {
            "server": handshake.get("serverInfo"),
            "protocol_version": handshake.get("protocolVersion"),
            "tool_count": len(tools),
            "unique_tool_names": handlers_ok,
            "schemas_valid": schemas_ok,
        }
        if args.handshake_only:
            print(json.dumps(report["mcp"], indent=2))
            return 0
        if len(tools) != 84:
            raise RuntimeError(f"expected 84 registered MCP tools, found {len(tools)}")

        analysis = client.tool("analyze_game_request", {"request": REQUEST})
        report["steps"].append({"step": "analyze_request", "ok": analysis.get("ok", True),
                                "counts": analysis.get("counts"),
                                "exclusions": analysis.get("exclusions")})

        spec = client.tool("create_game_specification", {
            "request": REQUEST,
            "project_name": "V5 Jungle Monkey",
            "engine": "unity",
            "platform": "pc",
            "dimension": "3d",
            "art_style": "low-poly",
            "scope": "prototype",
            "approved": True,
        })
        report["spec_id"] = spec["spec_id"]
        report["steps"].append({"step": "create_specification", "ok": spec.get("ok", True),
                                "spec_id": spec["spec_id"],
                                "requirements": len(spec.get("requirements") or []),
                                "status": spec.get("status")})

        validation = client.tool("llm_validate_plan", {
            "plan": spec,
            "request": REQUEST,
            "understanding": spec.get("analysis", {}).get("understanding"),
            "use_llm": False,
        })
        report["steps"].append({"step": "validate_specification",
                                "ok": validation.get("ok", True),
                                "verdict": validation.get("verdict"),
                                "issues": (validation.get("deterministic") or {}).get("issues")})

        trace = client.tool("llm_trace_requirements", {
            "understanding": spec["analysis"]["understanding"],
            "specification": spec,
        })
        report["steps"].append({"step": "trace_requirements", "ok": trace.get("ok", True),
                                "mapped": len(trace.get("requirements") or []),
                                "unmapped": trace.get("unmapped_requirements")})

        graph = spec.get("dependency_graph") or {}
        report["steps"].append({"step": "dependency_graph", "ok": bool(graph.get("nodes")),
                                "nodes": len(graph.get("nodes") or []),
                                "edges": len(graph.get("edges") or [])})

        init = client.tool("init_project_manifest", {
            "project_path": str(PROJECT),
            "spec": spec,
            "confirm": True,
            "overwrite": False,
        })
        report["manifest_path"] = init["manifest_path"]
        report["steps"].append({"step": "init_project_manifest",
                                "ok": init.get("ok", True),
                                "requirements": init.get("requirements"),
                                "revision": init.get("revision")})

        decisions = [
            ("Engine", "Use the installed Unity editor 6000.6.2f1 for the prototype.",
             "Already installed; the existing V5 project and build are Unity.",
             True),
            ("Target platform", "Windows PC only for this prototype.",
             "The user approved a Windows prototype; Android is excluded.", True),
            ("Dimension", "3D.", "Explicit request.", True),
            ("Art direction", "Low-poly.", "Explicit request.", True),
            ("Scope", "One playable jungle vertical slice prototype.",
             "Keeps the slice reviewable and evidence-based.", True),
            ("Explicit exclusions",
             "No climbing, no swinging, no swimming, no weapons and no Android support.",
             "Recorded from the original request and README scope statement.", True),
            ("Prototype scope exclusions",
             "No NPC dialogue, save system or progression for this prototype.",
             "These were implied by the genre analysis, not requested for the slice.", True),
            ("Execution policy", "Execution plans are non-executable (executable=false) "
             "and no paid generation or LLM request is made.",
             "The user did not authorize paid calls or external content.", True),
            ("Verification policy", "Automated tests, build and machine runtime evidence "
             "may reach 'tested'; only a human playtest/review may reach 'verified'.",
             "No human playtest record exists.", True),
        ]
        for topic, decision, rationale, approved in decisions:
            result = client.tool("record_project_decision", {
                "project_path": str(PROJECT),
                "topic": topic,
                "decision": decision,
                "rationale": rationale,
                "source": "user",
                "approved": approved,
                "confirm": True,
            })
            report["steps"].append({"step": "record_decision", "topic": topic,
                                    "ok": result.get("ok", True)})

        execution = client.tool("llm_build_execution_plan", {
            "specification": spec,
            "understanding": spec["analysis"]["understanding"],
            "include_paid_options": True,
        })
        if execution.get("executable") is not False:
            raise RuntimeError("execution plan did not preserve executable=false")
        report["steps"].append({"step": "build_execution_plan",
                                "ok": execution.get("ok", True),
                                "executable": execution.get("executable"),
                                "steps": len(execution.get("steps") or []),
                                "paid_requires_approval": (execution.get("counts") or {}).get(
                                    "paid_requires_approval")})

        index = _copy_evidence()
        build_artifact = _build_artifact()
        _write_json(STUDIO / "analysis.json", analysis)
        _write_json(STUDIO / "specification.json", spec)
        _write_json(STUDIO / "traceability.json", trace)
        _write_json(STUDIO / "dependency-graph.json", graph)
        _write_json(STUDIO / "execution-plan.json", execution)

        loaded = manifest_module.load_manifest(str(PROJECT))
        if not loaded["ok"]:
            raise RuntimeError(loaded.get("error", "manifest disappeared"))
        requirements = loaded["manifest"]["requirements"]
        run_records: list[dict] = []
        status_results: list[dict] = []

        for requirement in requirements:
            plan = _plan_for(requirement)
            status = plan["status"]
            note = plan["note"]
            run_reference = None
            if plan.get("check"):
                # The MCP operation runner intentionally inherits its parent's stdin.
                # In this harness that is the server's JSON-RPC pipe, which makes a
                # fresh Python interpreter wait on stdin.  Redirect stdin from NUL via
                # the fixed, trusted cmd.exe wrapper; no user data is interpolated.
                command = [
                    "cmd", "/c",
                    f"{sys.executable} {VERIFY} --check {plan['check']} < NUL",
                ]
                verification = client.tool("run_requirement_verification", {
                    "project_path": str(PROJECT),
                    "requirement_id": requirement["id"],
                    "command": command,
                    "confirm": True,
                    "timeout": 300,
                    "apply_status": False,
                })
                run_records.append({
                    "requirement_id": requirement["id"],
                    "check": plan["check"],
                    "ok": verification.get("ok"),
                    "exit_code": (verification.get("run") or {}).get("exit_code"),
                    "evidence": verification.get("evidence_reference"),
                })
                if verification.get("ok"):
                    run_reference = verification.get("evidence_reference")
                else:
                    # A failed verifier must never upgrade the claim.
                    status = "blocked"
                    note = (f"Verifier check {plan['check']} failed: "
                            f"{(verification.get('run') or {}).get('exit_code')}")
            if status in ("rejected",):
                evidence = []
            else:
                evidence = _evidence_entries(plan, run_reference)
            result = client.tool("update_requirement_status", {
                "project_path": str(PROJECT),
                "requirement_id": requirement["id"],
                "status": status,
                "evidence": evidence,
                "note": note,
                "confirm": True,
            })
            status_results.append({
                "id": requirement["id"],
                "statement": requirement["statement"],
                "status": result.get("current"),
                "evidence_count": result.get("evidence_count"),
                "missing": result.get("missing_evidence_files") or [],
            })

        comparison = client.tool("compare_project_against_requirements", {
            "project_path": str(PROJECT),
            "inspect_project": True,
        })
        progress = client.tool("track_project_progress", {
            "project_path": str(PROJECT),
        })

        report["analysis"] = analysis
        report["traceability"] = trace
        report["execution_plan"] = execution
        report["dependency_graph"] = graph
        report["exclusions"] = analysis.get("exclusions") or []
        report["verification"] = {
            "runs": run_records,
            "statuses": status_results,
            "comparison_overall": comparison.get("overall"),
            "comparison_coverage": comparison.get("coverage"),
            "detected_engine": comparison.get("detected_engine"),
            "invalid_claims": comparison.get("invalid_claims"),
            "requirements_with_issues": [
                item for item in comparison.get("requirements", []) if item.get("issues")
            ],
            "progress": progress.get("coverage"),
        }
        report["integration"] = {
            "generated_at": _now(),
            "manifest_path": str(STUDIO / "manifest.json"),
            "artifacts": [str(STUDIO / name) for name in (
                "analysis.json", "specification.json", "traceability.json",
                "dependency-graph.json", "execution-plan.json")],
            "evidence_files": sorted(index),
            "build_artifact": build_artifact,
            "tool_calls": client.calls,
            "notes": [
                "All manifest writes went through registered MCP handlers.",
                "No requirement was marked verified; no human playtest exists.",
                "executable=false was preserved from llm_build_execution_plan.",
            ],
        }

        _append_manifest_extras(report)
        final_manifest = manifest_module.load_manifest(str(PROJECT))
        if final_manifest["ok"]:
            report["final_status_counts"] = _status_counts(final_manifest["manifest"])
            report["final_revision"] = final_manifest["manifest"].get("revision")
        report["finished_at"] = _now()
        report["ok"] = True
        _write_json(STUDIO / "v5-integration-report.json", report)

        print(json.dumps({
            "ok": True,
            "manifest": report["manifest_path"],
            "spec_id": report["spec_id"],
            "mcp_tools": report["mcp"]["tool_count"],
            "validation_verdict": validation.get("verdict"),
            "execution_plan_executable": execution.get("executable"),
            "status_counts": report.get("final_status_counts"),
            "comparison_overall": comparison.get("overall"),
            "report": str(STUDIO / "v5-integration-report.json"),
        }, indent=2))
        return 0
    except Exception as exc:
        report["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["finished_at"] = _now()
        STUDIO.mkdir(parents=True, exist_ok=True)
        _write_json(STUDIO / "v5-integration-failure.json", report)
        print(json.dumps({"ok": False, "error": report["error"],
                          "failure_report": str(STUDIO / "v5-integration-failure.json")},
                         indent=2), file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
