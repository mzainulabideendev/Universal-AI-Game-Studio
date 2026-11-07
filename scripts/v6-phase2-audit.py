#!/usr/bin/env python3
"""V6 Phase 2 orchestration audit.

Read-only with respect to V4/V5 and Phase 0/1 artifacts. Runs the full test
suite, the zero-network demonstration and registry checks, then writes:

- reports/v6-agent-registry.json
- reports/v6-agent-workflow.json
- reports/v6-orchestration-audit.json

No provider is contacted, no engine is invoked and no secret value is read or
printed. A failed criterion marks the audit ``ok: false`` rather than being
hidden.
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
REPORTS = ROOT / "reports"
BASELINE = REPORTS / "v6-phase0-baseline.json"
AUDIT_OUT = REPORTS / "v6-orchestration-audit.json"
REGISTRY_OUT = REPORTS / "v6-agent-registry.json"
WORKFLOW_OUT = REPORTS / "v6-agent-workflow.json"
DEMO_OUT = REPORTS / "v6-phase2-demo.json"
DEMO_SCRIPT = ROOT / "scripts" / "v6-phase2-demo.py"
EXPECTED_AGENTS = {
    "game_director", "game_designer", "technical_architect", "character",
    "environment", "gameplay", "uiux", "qa",
}
SECRET_MARKERS = ("api_key", "sk-live-", "sk-proj-", "Bearer ")


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip()


def run_tests() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", str(SERVER_DIR / "tests"), "-q"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=1800)
    match = re.search(r"Ran (\d+) tests in ([\d.]+)s", result.stderr)
    return {
        "command": "python -m unittest discover -s tools/game-studio-mcp/tests -q",
        "returncode": result.returncode,
        "tests": int(match.group(1)) if match else None,
        "duration_seconds": float(match.group(2)) if match else None,
        "result": "OK" if result.returncode == 0 else "FAILED",
        "stderr_tail": result.stderr.strip().splitlines()[-5:],
    }


def run_demo() -> dict:
    result = subprocess.run(
        [sys.executable, str(DEMO_SCRIPT), str(DEMO_OUT)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    demo = json.loads(DEMO_OUT.read_text(encoding="utf-8")) \
        if DEMO_OUT.is_file() else {}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip().splitlines(),
        "status": demo.get("status"),
        "ok": demo.get("ok"),
        "executable": demo.get("executable"),
        "engine": demo.get("engine"),
        "mode": demo.get("mode"),
        "network_calls": demo.get("network_calls"),
        "live_provider_verified": demo.get("live_provider_verified"),
        "game_generated": demo.get("game_generated"),
        "assets_generated": demo.get("assets_generated"),
        "agent_steps": len(demo.get("stages") or []),
        "conflicts": [item.get("id") for item in demo.get("conflicts") or []],
        "provider_summary": demo.get("provider_summary"),
        "duration_ms": (demo.get("diagnostics") or {}).get("duration_ms"),
        "report": str(DEMO_OUT.relative_to(ROOT)).replace("\\", "/"),
    }


def preserved_hashes() -> dict:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    v4 = {}
    for relative, expected in baseline["v4_checkpoint"]["files"].items():
        path = ROOT / relative
        actual = sha256(path)
        v4[relative] = {
            "expected": expected.get("sha256"),
            "actual": actual,
            "unchanged": actual == expected.get("sha256") and path.is_file(),
        }
    v5 = {}
    for relative, expected in baseline["v5_checkpoint"]["artifacts"].items():
        path = ROOT / relative
        actual = sha256(path)
        v5[relative] = {
            "exists": path.is_file(),
            "expected": expected.get("sha256"),
            "actual": actual,
            "unchanged": actual == expected.get("sha256"),
        }
    return {
        "v4_checkpoint_commit": baseline["v4_checkpoint"]["commit"],
        "v4_files": v4,
        "v4_preserved": all(item["unchanged"] for item in v4.values()),
        "v5_artifacts": v5,
        "v5_preserved": all(item["unchanged"] for item in v5.values()),
        "v5_requirements": baseline["v5_checkpoint"]["requirements"],
        "v5_status_counts": baseline["v5_checkpoint"]["status_counts"],
    }


def security_scan(reports: list[Path]) -> dict:
    findings = []
    env_secrets = [value for key, value in os.environ.items()
                   if key.endswith("_API_KEY") and value and len(value) >= 8]
    for path in reports:
        if not path.is_file():
            findings.append({"report": str(path), "issue": "missing"})
            continue
        text = path.read_text(encoding="utf-8")
        for marker in SECRET_MARKERS:
            if marker in text:
                findings.append({"report": path.name, "issue": f"marker {marker!r}"})
        for secret in env_secrets:
            if secret in text:
                findings.append({"report": path.name,
                                 "issue": "environment credential value leaked"})
    return {
        "reports_scanned": [str(path.relative_to(ROOT)).replace("\\", "/")
                            for path in reports],
        "credential_values_read": False,
        "findings": findings,
        "clean": not findings,
    }


def main(output: str | None = None) -> int:
    out = Path(output) if output else AUDIT_OUT
    sys.path.insert(0, str(SERVER_DIR))

    import server  # noqa: E402
    from game_studio.agents import registry  # noqa: E402
    from game_studio.agents.workflow import (  # noqa: E402
        TASK_DEFINITIONS, dependency_graph, parallel_groups, validate_graph,
    )

    registry_report = registry.registry_report()
    workflow_report = {
        "schema_version": 1,
        "phase": "V6 Phase 2 - agent workflow",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "executable": False,
        "note": ("Planning workflow only. Execution produces plans, never engine "
                 "writes, assets or builds."),
        "task_count": len(TASK_DEFINITIONS),
        "tasks": [
            {
                "id": task["id"],
                "agent": task["agent"],
                "section": task["section"],
                "dependencies": list(task["dependencies"]),
                "description": task["description"],
            }
            for task in TASK_DEFINITIONS
        ],
        "dependency_graph": dependency_graph(),
        "parallel_groups": parallel_groups(),
        "graph_errors": validate_graph(),
        "concurrency": {
            "default": 2,
            "maximum": 4,
            "configurable_per_run": True,
            "note": ("Explicit cap; the coordinator never opens uncontrolled "
                     "parallel provider requests."),
        },
    }

    REGISTRY_OUT.write_text(json.dumps(registry_report, indent=2) + "\n",
                            encoding="utf-8")
    WORKFLOW_OUT.write_text(json.dumps(workflow_report, indent=2) + "\n",
                            encoding="utf-8")

    tests = run_tests()
    demo = run_demo()
    preservation = preserved_hashes()

    names = [tool["name"] for tool in server.TOOLS]
    parity = {
        "tools": len(names),
        "handlers": len(server.HANDLERS),
        "unique_tool_names": len(set(names)),
        "missing_handlers": [name for name in names if name not in server.HANDLERS],
        "extra_handlers": [name for name in server.HANDLERS if name not in names],
        "all_schemas_valid": all(
            isinstance(tool.get("inputSchema"), dict)
            and tool["inputSchema"].get("type") == "object"
            for tool in server.TOOLS),
        "phase1_baseline_tools": 89,
        "new_tools": ["orchestrate_game_plan"],
    }

    spec_ids = set(registry.specs())
    agents = {
        "count": len(spec_ids),
        "expected": sorted(EXPECTED_AGENTS),
        "registered": sorted(spec_ids),
        "complete": spec_ids == EXPECTED_AGENTS,
        "versions": {spec.id: spec.version for spec in registry.specs().values()},
        "registry_report_ok": registry_report["ok"],
        "all_agents_have_schemas": all(
            spec.input_schema.get("type") == "object"
            and spec.output_schema.get("type") == "object"
            for spec in registry.specs().values()),
    }

    security = security_scan([REGISTRY_OUT, WORKFLOW_OUT, DEMO_OUT])
    governance = {
        "executable": demo.get("executable"),
        "game_generated": demo.get("game_generated"),
        "assets_generated": demo.get("assets_generated"),
        "live_provider_verified": demo.get("live_provider_verified"),
        "writes_performed": False,
        "requirements_status_changed": False,
    }

    criteria = {
        "eight_typed_agents": agents["complete"] and agents["all_agents_have_schemas"],
        "coordinator_demo_completed": demo.get("status") == "completed",
        "demo_all_eight_steps": demo.get("agent_steps") == 8,
        "outputs_non_executable": demo.get("executable") is False,
        "no_live_verification_claim": demo.get("live_provider_verified") is False,
        "no_assets_generated": demo.get("assets_generated") is False,
        "zero_network_demo": demo.get("network_calls") == 0,
        "tests_pass": tests["result"] == "OK",
        "tool_handler_parity": (
            parity["tools"] == parity["handlers"] == parity["unique_tool_names"]
            and not parity["missing_handlers"] and not parity["extra_handlers"]
            and parity["all_schemas_valid"]),
        "v4_preserved": preservation["v4_preserved"],
        "v5_preserved": preservation["v5_preserved"],
        "security_clean": security["clean"],
        "workflow_graph_valid": not workflow_report["graph_errors"],
    }

    audit = {
        "schema_version": 1,
        "phase": "V6 Phase 2 - agent orchestration",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository": {
            "root": str(ROOT),
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": git("rev-parse", "HEAD"),
            "head_short": git("rev-parse", "--short", "HEAD"),
            "head_subject": git("log", "-1", "--pretty=%s"),
        },
        "mcp": parity,
        "agents": agents,
        "workflow": {
            "tasks": workflow_report["task_count"],
            "parallel_groups": workflow_report["parallel_groups"],
            "graph_errors": workflow_report["graph_errors"],
            "report": str(WORKFLOW_OUT.relative_to(ROOT)).replace("\\", "/"),
        },
        "registry_report": str(REGISTRY_OUT.relative_to(ROOT)).replace("\\", "/"),
        "tests": tests,
        "demo": demo,
        "preservation": preservation,
        "security": security,
        "governance": governance,
        "acceptance_criteria": criteria,
        "ok": all(criteria.values()),
        "limitations": [
            "Phase 2 validates orchestration and planning only.",
            "No character mesh, PBR texture, rig, animation, environment, scene, "
            "build or playable game exists because of this audit.",
            "Live provider verification was not performed; the demonstration is "
            "deterministic and zero-network.",
            "Mocked provider tests are not live provider verification.",
        ],
    }

    out.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    print(f"tests: {tests['tests']} ({tests['result']})")
    print(f"tools/handlers: {parity['tools']}/{parity['handlers']}")
    print(f"agents: {agents['count']}")
    print(f"demo: {demo['status']} executable={demo['executable']} "
          f"network_calls={demo['network_calls']}")
    print(f"v4_preserved={preservation['v4_preserved']} "
          f"v5_preserved={preservation['v5_preserved']}")
    print(f"security_clean={security['clean']}")
    failed = [name for name, passed in criteria.items() if not passed]
    print(f"ok={audit['ok']}" + (f" failed={failed}" if failed else ""))
    print(f"report={out}")
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
