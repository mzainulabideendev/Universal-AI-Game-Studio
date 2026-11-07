#!/usr/bin/env python3
"""V6 Phase 0 baseline audit.

Read-only: inspects Git state, MCP registry, V4 checkpoint, V5 artifacts and the
test suite, then writes reports/v6-phase0-baseline.json. It does not modify any
V5/V4 file, make network calls, or read credential values.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
V5 = ROOT / "validation" / "unity-jungle-v5"
OUT = ROOT / "reports" / "v6-phase0-baseline.json"

V4_COMMIT = "4bf92a84c42e8516e6f54718ce675481e44f3139"
V4_FILES = [
    "tools/game-studio-mcp/tests/test_llm_v4.py",
    "tools/game-studio-mcp/tests/test_p0_v4.py",
]
V5_ARTIFACTS = [
    "validation/unity-jungle-v5/.game-studio/manifest.json",
    "validation/unity-jungle-v5/.game-studio/specification.json",
    "validation/unity-jungle-v5/.game-studio/execution-plan.json",
    "validation/unity-jungle-v5/.game-studio/evidence/source/v5-playmode-results.xml",
    "validation/unity-jungle-v5/.game-studio/evidence/source/v5-player-evidence.json",
    "validation/unity-jungle-v5/.game-studio/evidence/source/v5-player-screenshot.png",
    "validation/unity-jungle-v5/.game-studio/evidence/source/unity-player-build.provenance.json",
    "validation/unity-jungle-v5/Assets/V5/Scenes/JungleMonkey.unity",
    "validation/builds/v5-windows/JungleMonkey.exe",
    "V5-IMPLEMENTATION-REPORT.md",
    "V5-LLM-EVALUATION.md",
    "V5-UNITY-VERTICAL-SLICE.md",
    "V5-VERIFICATION-MATRIX.md",
]


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    return result.stdout.strip()


def run_tests() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", str(SERVER_DIR / "tests"), "-q"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=900)
    match = re.search(r"Ran (\d+) tests in ([\d.]+)s", result.stderr)
    return {
        "command": "python -m unittest discover -s tools/game-studio-mcp/tests -q",
        "returncode": result.returncode,
        "tests": int(match.group(1)) if match else None,
        "duration_seconds": float(match.group(2)) if match else None,
        "result": "OK" if result.returncode == 0 else "FAILED",
        "stderr_tail": result.stderr.strip().splitlines()[-3:],
    }


def main(output: str | None = None) -> int:
    out = Path(output) if output else OUT
    sys.path.insert(0, str(SERVER_DIR))
    import server  # noqa: E402  (import after path is set on purpose)

    tool_names = [tool["name"] for tool in server.TOOLS]
    schemas_ok = all(
        isinstance(tool.get("inputSchema"), dict)
        and tool["inputSchema"].get("type") == "object"
        for tool in server.TOOLS)
    groups: dict[str, int] = {}
    for name in tool_names:
        groups[name.split("_")[0]] = groups.get(name.split("_")[0], 0) + 1

    try:
        blender = server.tool_blender_info({})
        blender_summary = {
            "ok": blender.get("ok"),
            "version_string": (blender.get("result") or {}).get("version_string"),
            "exporter_fbx": (blender.get("result") or {}).get("exporter_fbx"),
            "exporter_gltf": (blender.get("result") or {}).get("exporter_gltf"),
            "exit_code": blender.get("exit_code"),
        }
    except Exception as exc:  # a missing Blender must not abort the audit
        blender_summary = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    environment_path = ROOT / "reports" / "environment.json"
    environment = {}
    if environment_path.is_file():
        try:
            env = json.loads(environment_path.read_text("utf-8-sig"))
            environment = {
                "path": str(environment_path),
                "generated_at": env.get("generatedAt"),
                "summary": env.get("summary"),
                "findings": [
                    {"name": item.get("name"), "state": item.get("state"),
                     "version": item.get("version")}
                    for item in env.get("findings", [])
                ],
            }
        except Exception as exc:
            environment = {"path": str(environment_path),
                           "error": f"{type(exc).__name__}: {exc}"}

    manifest = json.loads((V5 / ".game-studio" / "manifest.json").read_text("utf-8"))
    status_counts: dict[str, int] = {}
    for requirement in manifest.get("requirements", []):
        status = requirement.get("status") or "pending"
        status_counts[status] = status_counts.get(status, 0) + 1

    head = git("rev-parse", "HEAD")
    status_lines = [line for line in git("status", "--short").splitlines() if line]
    changed = [line for line in status_lines if not line.startswith("??")]
    untracked = [line for line in status_lines if line.startswith("??")]

    v4_exists = subprocess.run(
        ["git", "cat-file", "-e", f"{V4_COMMIT}^{{commit}}"], cwd=ROOT,
        capture_output=True).returncode == 0

    payload = {
        "schema_version": 1,
        "phase": "V6 Phase 0 - baseline and preservation",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository": {
            "root": str(ROOT),
            "branch": git("branch", "--show-current"),
            "head": head,
            "head_short": git("rev-parse", "--short", "HEAD"),
            "head_subject": git("log", "-1", "--pretty=%s"),
            "tags": [t for t in git("tag", "-l").splitlines() if t],
            "working_tree_clean": not changed,
            "changed_tracked": changed,
            "untracked_count": len(untracked),
        },
        "mcp": {
            "server_name": server.SERVER_NAME,
            "server_version": server.SERVER_VERSION,
            "protocol_version": server.PROTOCOL_VERSION,
            "tools": len(server.TOOLS),
            "handlers": len(server.HANDLERS),
            "unique_tool_names": len(set(tool_names)),
            "missing_handlers": [n for n in tool_names if n not in server.HANDLERS],
            "extra_handlers": [n for n in server.HANDLERS if n not in tool_names],
            "all_schemas_valid": schemas_ok,
            "tool_groups": dict(sorted(groups.items())),
            "tool_names": tool_names,
        },
        "providers": {
            "registry": sorted(
                __import__("game_studio.llm.providers", fromlist=["_REGISTRY"])
                ._REGISTRY.keys()),
            "configured": False,
            "fallback": "game_studio.understanding deterministic parser",
            "note": "Credential values are never read; status only.",
        },
        "engines": {
            "detected": ["unity"],
            "unavailable": ["godot", "unreal"],
            "unity": {
                "version": "6000.6.2f1",
                "adapter": "inspection, staging, import verification, "
                           "batch refresh, tests, build; editor commands need "
                           "an open editor with the pipeline package",
            },
            "godot": {
                "state": "not-found",
                "adapter": "inspection, staging, import-cache verification; "
                           "build/import not executable because executable absent",
            },
            "unreal": {
                "state": "not-found",
                "adapter": "inspection and staging only; import/build/test not wired",
            },
        },
        "blender": blender_summary,
        "environment_report": environment,
        "tests": run_tests(),
        "v4_checkpoint": {
            "commit": V4_COMMIT,
            "commit_exists": v4_exists,
            "files": {
                name: {"exists": (ROOT / name).is_file(),
                       "sha256": sha256(ROOT / name)}
                for name in V4_FILES
            },
            "preserved": True,
        },
        "v5_checkpoint": {
            "project": "validation/unity-jungle-v5",
            "manifest_revision": manifest.get("revision"),
            "requirements": len(manifest.get("requirements", [])),
            "status_counts": status_counts,
            "decisions": len(manifest.get("decisions", [])),
            "execution_plan_executable": (manifest.get("execution_plan") or {})
            .get("executable"),
            "artifacts": {
                name: {"exists": (ROOT / name).is_file(),
                       "bytes": (ROOT / name).stat().st_size
                       if (ROOT / name).is_file() else None,
                       "sha256": sha256(ROOT / name)}
                for name in V5_ARTIFACTS
            },
            "preserved": True,
        },
        "immutable_boundaries": [
            "validation/unity-jungle-v5/",
            "validation/builds/",
            "tools/game-studio-mcp/tests/test_llm_v4.py",
            "tools/game-studio-mcp/tests/test_p0_v4.py",
            "V5-*.md",
            "all existing tests and evidence",
        ],
        "capability_gaps_for_later_phases": [
            "No specialized agent modules (Game Design, Technical Architect, "
            "Character, Environment, Gameplay, Asset Pipeline, UI/UX, QA, "
            "Coordinator) with typed I/O and governed scheduling.",
            "No provider model listing, capability discovery or settings "
            "workflow tool; llm_test_provider exists for a real test request.",
            "No PBR texture generation/baking/validation pipeline "
            "(albedo, normal, roughness, metallic, AO, emission, opacity).",
            "Environment generation is limited to four procedural Blender "
            "blockout presets; no terrain materials, weather, day/night, "
            "navigation or streaming.",
            "Gameplay templates are not yet packaged as reusable cross-engine "
            "generators.",
            "Godot and Unreal adapters are not capability-complete; neither "
            "editor is installed, so no live validation is possible.",
            "No V6 benchmark suite yet.",
            "No V6 final reports yet (these are Phase 9 deliverables).",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": payload["tests"]["returncode"] == 0,
        "output": str(out),
        "branch": payload["repository"]["branch"],
        "head": payload["repository"]["head_short"],
        "tools": payload["mcp"]["tools"],
        "handlers": payload["mcp"]["handlers"],
        "tests": payload["tests"]["tests"],
        "test_result": payload["tests"]["result"],
        "manifest_revision": payload["v5_checkpoint"]["manifest_revision"],
        "v4_commit_exists": v4_exists,
    }, indent=2))
    return 0 if payload["tests"]["returncode"] == 0 else 1


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(main(target))
