#!/usr/bin/env python3
"""Reproducible regression runner for Universal AI Game Studio.

Runs the offline unit suite (mocked external services only), verifies the MCP
tool registry and stdio handshake, and writes a JSON + Markdown report with
per-test results, failure details, environment and unverified dependencies.

Usage:
    python scripts/run-regression.py
    python scripts/run-regression.py --report-dir reports --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(MCP))

import server  # noqa: E402
from game_studio import blender, detect, engines, secrets  # noqa: E402
from game_studio.llm import config as llm_config  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records: list[dict] = []
        self._started: dict[str, float] = {}

    def startTest(self, test) -> None:  # noqa: N802
        self._started[test.id()] = time.time()
        super().startTest(test)

    def _record(self, test, status: str, detail: str = "") -> None:
        duration = round((time.time() - self._started.get(test.id(), time.time())) * 1000)
        self.records.append({
            "test": test.id(),
            "result": status,
            "duration_ms": duration,
            "failure_details": detail.strip() or None,
        })

    def addSuccess(self, test) -> None:  # noqa: N802
        super().addSuccess(test)
        self._record(test, "passed")

    def addFailure(self, test, err) -> None:  # noqa: N802
        super().addFailure(test, err)
        self._record(test, "failed", self._exc_info_to_string(err, test))

    def addError(self, test, err) -> None:  # noqa: N802
        super().addError(test, err)
        self._record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason) -> None:  # noqa: N802
        super().addSkip(test, reason)
        self._record(test, "skipped", reason)

    def addExpectedFailure(self, test, err) -> None:  # noqa: N802
        super().addExpectedFailure(test, err)
        self._record(test, "expected-failure")

    def addUnexpectedSuccess(self, test) -> None:  # noqa: N802
        super().addUnexpectedSuccess(test)
        self._record(test, "unexpected-success")


def run_suite(verbosity: int) -> tuple[dict, RecordingResult]:
    loader = unittest.TestLoader()
    suite = loader.discover(str(MCP / "tests"), pattern="test_*.py",
                            top_level_dir=str(MCP / "tests"))
    runner = unittest.TextTestRunner(verbosity=verbosity, resultclass=RecordingResult,
                                     stream=sys.stderr)
    started = time.time()
    result = runner.run(suite)
    duration = round(time.time() - started, 2)
    known = {record["test"] for record in result.records}
    for test in loader.errors or []:
        result.records.append({
            "test": "discovery",
            "result": "error",
            "duration_ms": 0,
            "failure_details": test,
        })
    summary = {
        "ran": result.testsRun,
        "passed": sum(1 for r in result.records if r["result"] == "passed"),
        "failed": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "recorded": len(known),
        "duration_seconds": duration,
        "successful": result.wasSuccessful(),
    }
    return summary, result


def registry_checks() -> list[dict]:
    checks = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"test": name, "result": "passed" if ok else "failed",
                       "failure_details": None if ok else detail})

    names = [tool["name"] for tool in server.TOOLS]
    record("registry.unique_tool_names", len(names) == len(set(names)),
           "duplicate tool names")
    record("registry.every_tool_has_handler", set(names) == set(server.HANDLERS),
           f"tools without handlers: {sorted(set(names) - set(server.HANDLERS))}; "
           f"handlers without tools: {sorted(set(server.HANDLERS) - set(names))}")
    record("registry.nonempty_schemas",
           all(isinstance(tool.get("inputSchema"), dict) for tool in server.TOOLS),
           "a tool has no inputSchema")
    required = {"get_execution_mode", "set_execution_mode", "set_permission",
                "cancel_operation", "list_operations", "inspect_requirement_evidence",
                "run_requirement_verification", "llm_status", "llm_understand_request",
                "llm_generate_specification", "llm_review_plan",
                "llm_game_director_plan", "meshy_cancel_task"}
    missing = sorted(required - set(names))
    record("registry.p0_v4_tools_present", not missing, f"missing: {missing}")
    return checks


def handshake_check() -> dict:
    process = subprocess.Popen(
        [sys.executable, str(MCP / "server.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8",
        env={**os.environ, "GAME_STUDIO_HOME": os.path.join(
            os.environ.get("TEMP", "."), "gs-regression-home")},
    )
    try:
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "operation_status", "arguments": {}}},
        ]
        for request in requests:
            process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        responses = [json.loads(process.stdout.readline()) for _ in requests]
        ids = {response.get("id") for response in responses}
        ok = ids == {1, 2, 3} and all("result" in r for r in responses)
        return {"test": "transport.stdio_handshake", "result": "passed" if ok else "failed",
                "failure_details": None if ok else f"unexpected responses: {responses}"}
    except Exception as exc:  # noqa: BLE001
        return {"test": "transport.stdio_handshake", "result": "error",
                "failure_details": str(exc)}
    finally:
        process.kill()
        process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


def environment() -> dict:
    cfg = llm_config.load_config()
    return {
        "generated_at": _now(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "game_studio_home": os.environ.get("GAME_STUDIO_HOME") or "(default)",
        "tools": len(server.TOOLS),
        "server_version": server.SERVER_VERSION,
        "integrations": {
            "blender": {"detected": bool(blender.resolve_blender())},
            "engines": detect.detect_game_engines(discover=False),
            "meshy_key_configured": bool(secrets.meshy_key_source()),
            "sketchfab_token_configured": bool(os.environ.get("SKETCHFAB_TOKEN")),
            "llm": {
                "provider": cfg["provider"],
                "model": cfg["model"],
                "local_only": cfg["local_only"],
                "key_configured": bool(cfg.get("api_key")),
                "live_verified": False,
            },
        },
        "unverified_dependencies": [
            "Real Blender execution is not exercised by the offline suite.",
            "Unity/Unreal/Godot builds are not exercised without installed editors.",
            "Meshy, Sketchfab and LLM calls are mocked or skipped without credentials.",
            "A passed regression suite is not proof that a game build is playable.",
        ],
    }


def write_reports(summary: dict, records: list[dict], env: dict,
                  report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "summary": summary,
        "environment": env,
        "checks": records,
        "regression_status": "passed" if summary["successful"] else "failed",
    }
    json_path = report_dir / "regression-report.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Regression report",
        "",
        f"Generated: {env['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Tests ran: {summary['ran']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Errors: {summary['errors']}",
        f"- Skipped: {summary['skipped']}",
        f"- Duration: {summary['duration_seconds']}s",
        f"- Regression status: **{payload['regression_status']}**",
        "",
        "## Environment",
        "",
        f"- Platform: {env['platform']}",
        f"- Python: {env['python']}",
        f"- Tools registered: {env['tools']}",
        f"- Blender detected: {env['integrations']['blender']['detected']}",
        f"- Meshy key configured: {env['integrations']['meshy_key_configured']}",
        f"- LLM provider: {env['integrations']['llm']['provider']} "
        f"(key configured: {env['integrations']['llm']['key_configured']}, "
        f"live verified: false)",
        "",
        "## Results",
        "",
        "| Test | Result | ms | Failure |",
        "| --- | --- | --- | --- |",
    ]
    for record in records:
        detail = (record.get("failure_details") or "").replace("\n", " ")[:300]
        detail = detail.replace("|", "/")
        lines.append(f"| `{record['test']}` | {record['result']} | "
                     f"{record.get('duration_ms', 0)} | {detail} |")
    lines += [
        "",
        "## Unverified dependencies",
        "",
        *[f"- {item}" for item in env["unverified_dependencies"]],
        "",
        "## Notes",
        "",
        "- External services are mocked only in isolated unit tests and are labelled as such.",
        "- No paid API is required by this suite.",
        "- Passing tests do not prove a game build runs or is fun.",
    ]
    md_path = report_dir / "regression-report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    summary, result = run_suite(2 if args.verbose else 1)
    records = list(result.records)
    records.extend(registry_checks())
    records.append(handshake_check())
    failure_count = sum(1 for record in records if record["result"] in ("failed", "error"))
    summary["failed"] += sum(1 for r in registry_checks() if r["result"] == "failed")
    summary["successful"] = summary["successful"] and failure_count == 0
    env = environment()
    json_path, md_path = write_reports(summary, records, env, Path(args.report_dir))
    print(f"tests ran={summary['ran']} passed={summary['passed']} "
          f"failed={summary['failed']} errors={summary['errors']} "
          f"status={'passed' if summary['successful'] else 'failed'}")
    print(f"report: {json_path}")
    print(f"report: {md_path}")
    return 0 if summary["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
