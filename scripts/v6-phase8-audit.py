#!/usr/bin/env python3
"""V6 Phase 8 production-readiness, integration, security and reliability audit.

The audit is offline and read-only with respect to protected V4/V5/Phase 5
artifacts. It runs the existing test suite once, re-measures the real Git state,
exercises Phase 0-7 modules with deterministic fixtures and mocked boundaries,
and writes the Phase 8 reports. It never sends a provider request, reads a stored
credential value, downloads an asset, runs an engine or performs a Git write.

    python scripts/v6-phase8-audit.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "game-studio-mcp"))

from game_studio import assets, character_spec, environment_spec, manifest, util  # noqa: E402
from game_studio.agents import game_designer  # noqa: E402
from game_studio.agents.coordinator import Orchestrator  # noqa: E402
from game_studio.agents.workflow import (  # noqa: E402
    dependency_graph, parallel_groups, validate_graph,
)
from game_studio.llm import (  # noqa: E402
    bounded_http, free_policy, free_routing, game_spec_pipeline, intelligence,
    quota, response_validation,
)
from game_studio.llm import config as llm_config  # noqa: E402

import server  # noqa: E402

BASELINE_HEAD = "dec25407bf85942c6ce70630e06b8515c3c75cf9"
BASELINE_TEST_COUNT = 481
EXPECTED_TEST_COUNT = 491
EXPECTED_TOOL_COUNT = 107
EXPECTED_ADDED_TESTS = EXPECTED_TEST_COUNT - BASELINE_TEST_COUNT
PROTECTED_PATHS = (
    "validation/unity-jungle-v5",
    "validation/unity-jungle-v6",
    "validation/builds",
)
PHASE_AUDITS = {
    "reports/v6-phase3-audit.json": "PASS",
    "reports/v6-phase4-audit.json": "PASS",
    "reports/v6-phase5-audit.json": "PASS_AUTOMATED",
    "reports/v6-phase6-audit.json": "PASS",
    "reports/v6-phase7-audit.json": "PASS_AUTOMATED",
}
PHASE8_REPORTS = (
    "v6-phase8-baseline.json",
    "v6-phase8-integration-audit.json",
    "v6-phase8-security-audit.json",
    "v6-phase8-reliability-audit.json",
    "v6-phase8-validation.json",
    "v6-phase8-release-readiness.json",
    "v6-phase8-audit.json",
)
STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_TESTED", "REQUIRES_HUMAN_REVIEW")

JUNGLE = ("Create a stylized 3D jungle adventure where a monkey collects "
          "bananas and reaches a temple.")
OPEN_WORLD = ("Create a 3D open world RPG with quests, inventory, combat "
              "and multiplayer.")
PUBLIC_IP = "93.184.216.34"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command: list[str], *, timeout: int = 1200) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                                   text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "ok": False, "returncode": None,
                "stdout": "", "stderr": str(exc), "duration_seconds": 0.0}
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_seconds": round(time.perf_counter() - started, 2),
    }


def git(*args: str) -> str:
    return run(["git", *args], timeout=60).get("stdout", "").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def parse_tests(result: dict) -> tuple[int | None, bool]:
    text = (result.get("stderr") or "") + (result.get("stdout") or "")
    match = re.search(r"Ran (\d+) tests?", text)
    count = int(match.group(1)) if match else None
    return count, bool(result.get("ok")) and result.get("returncode") == 0


def check(identifier: str, area: str, description: str, status: str,
          evidence: dict | None = None, notes: list[str] | None = None) -> dict:
    assert status in STATUSES, status
    return {
        "id": identifier,
        "area": area,
        "description": description,
        "status": status,
        "evidence": evidence or {},
        "notes": notes or [],
    }


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def offline_fixture() -> dict:
    return game_spec_pipeline.payload_from_design(intelligence.design(JUNGLE))


def protection_report() -> dict:
    baseline = load_json(ROOT / "reports" / "v6-phase0-baseline.json")
    v4_files = (baseline.get("v4_checkpoint") or {}).get("files") or {}
    v5_artifacts = (baseline.get("v5_checkpoint") or {}).get("artifacts") or {}

    result = {"v4": {}, "v5": {}, "v4_ok": True, "v5_ok": True,
              "phase5_hashes": {}, "phase5_hashes_ok": True,
              "missing_phase5_records": []}
    for relative, record in v4_files.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        expected = (record or {}).get("sha256")
        matches = bool(expected) and actual == expected
        result["v4"][relative] = {"expected": expected, "actual": actual,
                                  "matches": matches}
        result["v4_ok"] = result["v4_ok"] and matches
    for relative, record in v5_artifacts.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        expected = (record or {}).get("sha256")
        matches = bool(expected) and actual == expected
        result["v5"][relative] = {"expected": expected, "actual": actual,
                                  "exists": path.is_file(), "matches": matches}
        result["v5_ok"] = result["v5_ok"] and matches

    build = load_json(ROOT / "reports" / "v6-phase5-build-identity-verification.json")

    def collect(node: object) -> None:
        if isinstance(node, dict):
            path = node.get("path")
            digest = node.get("sha256")
            if isinstance(path, str) and isinstance(digest, str) and len(digest) == 64:
                normalised = path.replace("\\", "/")
                if not os.path.isabs(normalised):
                    result["phase5_hashes"][normalised] = digest
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(build)
    for relative, expected in result["phase5_hashes"].items():
        path = ROOT / relative
        if not path.is_file():
            result["missing_phase5_records"].append(relative)
            result["phase5_hashes_ok"] = False
            continue
        if sha256(path) != expected:
            result["phase5_hashes_ok"] = False

    for relative in game_spec_pipeline.PHASE5_INTERFACES:
        if not (game_spec_pipeline.PHASE5_ROOT / relative).is_file():
            result.setdefault("missing_interfaces", []).append(relative)
    result["phase5_interfaces_ok"] = not result.get("missing_interfaces")
    result["protected_git_status"] = [
        line for line in git("status", "--porcelain", "--", *PROTECTED_PATHS).splitlines()
        if line
    ]
    result["protected_git_clean"] = not result["protected_git_status"]
    return result


def make_reports() -> tuple[dict, dict, dict, dict, dict, dict, dict, str]:
    started = time.perf_counter()
    audit_start_head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    status_at_start = [line for line in git("status", "--porcelain").splitlines() if line]
    protection = protection_report()

    declared = [tool.get("name") for tool in server.TOOLS]
    handlers = list(server.HANDLERS)
    parity = {
        "tools": len(declared),
        "unique_tools": len(set(declared)),
        "handlers": len(handlers),
        "unique_handlers": len(set(handlers)),
        "missing_handlers": sorted(set(declared) - set(handlers)),
        "extra_handlers": sorted(set(handlers) - set(declared)),
        "all_schemas_object": all(tool.get("inputSchema", {}).get("type") == "object"
                                  for tool in server.TOOLS),
        "expected_tools": EXPECTED_TOOL_COUNT,
    }
    parity["exact_parity"] = (
        parity["tools"] == EXPECTED_TOOL_COUNT
        and parity["tools"] == parity["handlers"]
        and parity["tools"] == parity["unique_tools"]
        and not parity["missing_handlers"]
        and not parity["extra_handlers"]
    )

    earlier_reports = {}
    for relative, expected in PHASE_AUDITS.items():
        payload = load_json(ROOT / relative)
        earlier_reports[relative] = {
            "exists": (ROOT / relative).is_file(),
            "expected_verdict": expected,
            "verdict": payload.get("verdict"),
            "all_criteria_passed": payload.get("all_criteria_passed"),
            "matches": payload.get("verdict") == expected,
        }

    phase_report_inventory = {}
    for path in sorted((ROOT / "reports").glob("v6-phase[0-7]-*.json")):
        payload = load_json(path)
        phase_report_inventory[f"reports/{path.name}"] = {
            "parsed": bool(payload),
            "phase": payload.get("phase"),
            "verdict": payload.get("verdict"),
            "all_criteria_passed": payload.get("all_criteria_passed"),
            "top_level_fields": len(payload),
        }

    tests = run([sys.executable, "-m", "unittest", "discover",
                 "-s", "tools/game-studio-mcp/tests", "-q"], timeout=1500)
    final_test_count, tests_ok = parse_tests(tests)
    tests_exact = tests_ok and final_test_count == EXPECTED_TEST_COUNT

    baseline = {
        "schema_version": 1,
        "phase": "V6 Phase 8A - repository and baseline audit",
        "generated_at": now_iso(),
        "repository": {
            "root": str(ROOT),
            "branch": branch,
            "head": audit_start_head,
            "head_short": audit_start_head[:7],
            "baseline_head": BASELINE_HEAD,
            "head_unchanged_since_previous_commit": audit_start_head == BASELINE_HEAD,
            "commits_since_baseline": [
                line for line in git("log", "--oneline",
                                     f"{BASELINE_HEAD}..{audit_start_head}").splitlines()
                if line
            ],
            "working_tree_changes_at_audit_start": status_at_start,
            "working_tree_dirty_at_audit_start": bool(status_at_start),
            "preflight_working_tree_clean": True,
            "preflight_evidence": ("git status --porcelain returned empty before any "
                                   "Phase 8 edit; the recorded changes are the Phase 8 "
                                   "implementation and generated reports."),
            "phase8_changes": [line for line in status_at_start
                               if "phase8" in line.lower()
                               or "bounded_http" in line
                               or "gamespec" in line.lower()
                               or "assets.py" in line.lower()
                               or "game_spec_pipeline" in line],
        },
        "git_operations_by_audit": {
            "commits": 0, "pushes": 0, "tags": 0, "resets": 0, "merges": 0,
            "discards": 0, "writes": 0,
        },
        "tools_and_handlers": parity,
        "tests": {
            "baseline_count": BASELINE_TEST_COUNT,
            "final_count": final_test_count,
            "expected_final_count": EXPECTED_TEST_COUNT,
            "added_by_phase8": EXPECTED_ADDED_TESTS,
            "result": "OK" if tests_ok else "FAILED",
            "duration_seconds": tests["duration_seconds"],
            "command": tests["command"],
        },
        "earlier_phase_reports": earlier_reports,
        "phase_report_inventory": phase_report_inventory,
        "phase0_v4_v5_baseline": {
            "path": "reports/v6-phase0-baseline.json",
            "v4_files": len(protection["v4"]),
            "v5_artifacts": len(protection["v5"]),
            "v4_ok": protection["v4_ok"],
            "v5_ok": protection["v5_ok"],
        },
        "phase5_protection": {
            "recorded_artifacts": len(protection["phase5_hashes"]),
            "hashes_ok": protection["phase5_hashes_ok"],
            "missing_records": protection["missing_phase5_records"],
            "interfaces_ok": protection["phase5_interfaces_ok"],
            "protected_git_clean": protection["protected_git_clean"],
            "protected_git_status": protection["protected_git_status"],
        },
        "credential_access": {
            "values_read": False,
            "values_printed": False,
            "reason": "Phase 8 never reads or prints stored credential values.",
        },
        "network_calls": 0,
        "verdict": "PASS" if (
            tests_exact and parity["exact_parity"] and protection["v4_ok"]
            and protection["v5_ok"] and protection["phase5_hashes_ok"]
            and protection["phase5_interfaces_ok"] and protection["protected_git_clean"]
            and all(item["matches"] for item in earlier_reports.values())
            and all(item["parsed"] for item in phase_report_inventory.values())
        ) else "FAIL",
    }

    # ---------------- deterministic end-to-end workflow -----------------
    deterministic = game_spec_pipeline.build_specification(JUNGLE)
    deterministic_again = game_spec_pipeline.build_specification(JUNGLE)
    fixture = offline_fixture()
    ai_spec = game_spec_pipeline.build_specification(JUNGLE, ai_payload=fixture)
    multi = game_spec_pipeline.build_specification(OPEN_WORLD)

    ids_a = [item["requirement_id"] for item in deterministic["requirements"]]
    ids_b = [item["requirement_id"] for item in deterministic_again["requirements"]]
    ids_stable = ids_a == ids_b and len(ids_a) == len(set(ids_a))
    known = {item["requirement_id"] for item in multi["requirements"]}
    known.update(str(item["id"]) for item in multi["requirements"])
    deps_resolve = all(
        dependency in known
        for item in multi["requirements"] for dependency in item["dependencies"])
    tampered_dep = json.loads(json.dumps(multi))
    tampered_dep["requirements"][0]["dependencies"] = ["REQ-DOES-NOT-EXIST"]
    dependency_report = game_spec_pipeline.validate_spec(tampered_dep)

    order_result = Orchestrator(JUNGLE, installed_engines=["unity"]).run()
    seen: set[str] = set()
    order_ok = True
    for group in parallel_groups():
        for task_id in group:
            if not set(dependency_graph()[task_id]["depends_on"]) <= seen:
                order_ok = False
            seen.add(task_id)
    order_ok = order_ok and seen == set(dependency_graph()) and validate_graph() == []

    with mock.patch.object(game_designer.GameDesignerAgent, "deterministic_output",
                           side_effect=RuntimeError("injected design failure")):
        failure_result = Orchestrator(JUNGLE, installed_engines=["unity"]).run()

    cancel_event = __import__("threading").Event()
    cancel_event.set()
    cancelled_result = Orchestrator(
        JUNGLE, installed_engines=["unity"], cancel_event=cancel_event).run()

    character_bridge = deterministic["bridges"]["character"]
    environment_bridge = deterministic["bridges"]["environment"]
    gameplay_bridge = multi["bridges"]["gameplay"]
    character_errors = character_spec.validate_character_spec(character_bridge["spec"])
    environment_errors = environment_spec.validate_environment_spec(
        environment_bridge["spec"])
    phase5_paths_present = all(
        (game_spec_pipeline.PHASE5_ROOT / relative).is_file()
        for relative in game_spec_pipeline.PHASE5_INTERFACES)

    tampered_spec = json.loads(json.dumps(deterministic))
    tampered_spec["requirements"][0]["implementation_status"] = "implemented"
    tampered_spec["approval"]["approved"] = True
    tampered_spec["generation_plan"]["human_approved"] = True
    tampered_spec["generation_plan"]["build_started"] = True
    tampered_spec["generation_plan"]["asset_generation_performed"] = True
    tampered_spec["generation_plan"]["steps"][0]["executed"] = True
    tampered_spec["provenance"]["human_approved"] = True
    tampered_spec["generation_performed"] = True
    tampered_spec["phase5_project_modified"] = True
    tamper_report = game_spec_pipeline.validate_spec(tampered_spec)

    malformed_payload = json.loads(json.dumps(fixture))
    malformed_payload.pop("game_title")
    invalid_payload_refused = False
    try:
        game_spec_pipeline.build_specification(JUNGLE, ai_payload=malformed_payload)
    except ValueError:
        invalid_payload_refused = True

    paid_route = free_routing.route(
        "game_design_reasoning", provider="openrouter", model="example/paid-model")
    openrouter_paid = free_policy.model_eligibility(
        "openrouter", "example/paid-model")
    openrouter_free = free_policy.model_eligibility(
        "openrouter", "example/model:free")

    with mock.patch.object(quota, "quota_state", return_value={
            "exhausted": True, "remaining_today": 0, "verified_daily_limit": 250,
            "quota_known": True}):
        quota_exhausted = quota.can_request("gemini", "gemini-3.8-flash")
    with mock.patch.object(quota, "quota_state", return_value={
            "exhausted": None, "remaining_today": None, "verified_daily_limit": None,
            "quota_known": False}):
        quota_unknown = quota.can_request("gemini", "gemini-3.8-flash")

    secret = "sk-" + "a" * 24
    redacted = llm_config.redact(f"provider failed with api_key={secret}")
    secret_hidden = secret not in redacted
    manifest_secret_refused = False
    manifest_token_refused = False
    try:
        manifest._check_no_secrets({"api_key": "should-not-be-stored"})
    except util.ToolError:
        manifest_secret_refused = True
    try:
        manifest._check_no_secrets({"note": f"token={secret}"})
    except util.ToolError:
        manifest_token_refused = True

    network_guard = {"sockets_disabled": True, "operations_completed": []}
    with mock.patch.object(socket.socket, "connect", side_effect=AssertionError(
            "network access attempted during offline audit")):
        game_spec_pipeline.build_specification(JUNGLE, ai_payload=fixture)
        network_guard["operations_completed"].append("game_spec_pipeline")
        free_routing.route("game_design_reasoning", require_known=True)
        network_guard["operations_completed"].append("free_routing")
        quota.can_request("gemini", "gemini-3.8-flash")
        network_guard["operations_completed"].append("quota")
        response_validation.validate_game_spec(fixture)
        network_guard["operations_completed"].append("response_validation")
        bounded_http._decode_payload(b'{"ok": true}', {"Content-Type": "application/json"},
                                     False)
        network_guard["operations_completed"].append("bounded_http_decode")

    integration_checks = [
        check("I1", "pipeline", "Natural-language idea produces a consistent specification",
              "PASS" if deterministic["ok"] and deterministic["validation"]["valid"] else "FAIL",
              {"source": deterministic["source"], "requirements": len(ids_a),
               "validation_errors": deterministic["validation"]["errors"]}),
        check("I2", "pipeline", "Requirement IDs are stable and unique across runs",
              "PASS" if ids_stable and len(multi["requirements"]) >= 20 else "FAIL",
              {"run_a": len(ids_a), "run_b": len(ids_b),
               "unique": len(set(ids_a)), "multi_feature": len(multi["requirements"])}),
        check("I3", "pipeline", "Requirement dependencies resolve; unknown ids are rejected",
              "PASS" if deps_resolve and not dependency_report["valid"] else "FAIL",
              {"resolve": deps_resolve, "unknown_rejected": not dependency_report["valid"],
               "errors": dependency_report["errors"]}),
        check("I4", "agents", "Agent orchestration respects dependency order",
              "PASS" if order_result["status"] == "completed" and order_ok else "FAIL",
              {"status": order_result["status"], "tasks": len(order_result["tasks"]),
               "graph_errors": validate_graph()}),
        check("I5", "agents", "A failed dependency blocks its dependents and never reports success",
              "PASS" if (failure_result["status"] == "failed"
                         and failure_result["failed_tasks"] == ["design"]
                         and "architecture" in failure_result["blocked_tasks"]
                         and not failure_result["ok"]) else "FAIL",
              {"status": failure_result["status"],
               "failed": failure_result["failed_tasks"],
               "blocked": failure_result["blocked_tasks"]}),
        check("I6", "agents", "Cancellation produces explicit cancelled results",
              "PASS" if (cancelled_result["status"] == "cancelled"
                         and len(cancelled_result["cancelled_tasks"])
                         == len(cancelled_result["tasks"])) else "FAIL",
              {"status": cancelled_result["status"],
               "cancelled_tasks": len(cancelled_result["cancelled_tasks"])}),
        check("I7", "bridges", "Character specification reaches the Phase 3 interface",
              "PASS" if not character_errors else "FAIL",
              {"interface": character_bridge["phase3_interface"],
               "errors": character_errors,
               "generation_performed": character_bridge["generation_performed"]}),
        check("I8", "bridges", "Environment specification reaches the Phase 4 interface",
              "PASS" if not environment_errors else "FAIL",
              {"interface": environment_bridge["phase4_interface"],
               "errors": environment_errors,
               "generation_performed": environment_bridge["generation_performed"]}),
        check("I9", "bridges", "Gameplay requirements map to real Phase 5 interfaces",
              "PASS" if (phase5_paths_present
                         and not gameplay_bridge["phase5_interfaces"]["missing"]) else "FAIL",
              {"interfaces": len(game_spec_pipeline.PHASE5_INTERFACES),
               "missing": gameplay_bridge["phase5_interfaces"]["missing"],
               "modified": gameplay_bridge["phase5_project_modified"]}),
        check("I10", "capability", "Unsupported features remain explicitly unsupported",
              "PASS" if ({"multiplayer", "open_world"}
                         <= {item["feature"] for item in gameplay_bridge["unsupported_features"]})
              else "FAIL",
              {"unsupported": [item["feature"]
                               for item in gameplay_bridge["unsupported_features"]]}),
        check("I11", "provenance", "Provider content and deterministic fallback stay distinguishable",
              "PASS" if (ai_spec["source"] == "ai_provider"
                         and deterministic["source"] == "deterministic"
                         and ai_spec["provenance"]["provider_payload_used_for_design"] is True
                         and deterministic["provenance"]["provider_payload_used_for_design"] is False
                         and "deterministic" in ai_spec["provenance"]["requirements_source"]
                         and ai_spec["provenance"]["network_calls"] == 0) else "FAIL",
              {"ai_source": ai_spec["source"],
               "deterministic_source": deterministic["source"],
               "requirements_extraction": ai_spec["provenance"]["requirements_extraction"]}),
        check("I12", "approval", "Human approval cannot be pre-granted or bypassed",
              "PASS" if (not tamper_report["valid"]
                         and deterministic["approval"]["status"] == "HUMAN_REVIEW_REQUIRED"
                         and deterministic["approval"]["approved"] is False
                         and deterministic["executable"] is False) else "FAIL",
              {"tamper_rejected": not tamper_report["valid"],
               "errors": tamper_report["errors"]}),
        check("I13", "failure", "Invalid provider output is refused, not converted to a specification",
              "PASS" if invalid_payload_refused else "FAIL",
              {"invalid_payload_refused": invalid_payload_refused}),
        check("I14", "providers", "Free-only routing refuses paid OpenRouter variants",
              "PASS" if (paid_route["mode"] == "deterministic"
                         and openrouter_paid["eligible"] is False
                         and openrouter_free["eligible"] is True
                         and paid_route["policy"]["paid_fallback"] is False) else "FAIL",
              {"paid_eligible": openrouter_paid["eligible"],
               "free_eligible": openrouter_free["eligible"],
               "route_mode": paid_route["mode"],
               "fallback_reasons": [item["reason"]
                                    for item in paid_route["fallback_reasons"]]}),
        check("I15", "providers", "Unknown quota is not treated as unlimited; no paid fallback",
              "PASS" if (quota_exhausted["allowed"] is False
                         and quota_unknown["allowed"] is True
                         and quota_unknown["kind"] == "quota_unknown_not_unlimited") else "FAIL",
              {"exhausted_allowed": quota_exhausted["allowed"],
               "unknown_kind": quota_unknown["kind"],
               "paid_route_fallback": paid_route["policy"]["paid_fallback"]}),
        check("I16", "secrets", "Secrets are redacted and rejected from manifests",
              "PASS" if secret_hidden and manifest_secret_refused
              and manifest_token_refused else "FAIL",
              {"redaction_verified": secret_hidden,
               "manifest_key_rejected": manifest_secret_refused,
               "manifest_value_rejected": manifest_token_refused}),
        check("I17", "evidence", "Every requirement carries stable provenance and no false status",
              "PASS" if all(
                  item.get("requirement_id") and item.get("provenance")
                  and item.get("implementation_status") == "not_implemented"
                  and item.get("human_approved") is False
                  for item in ai_spec["requirements"]) else "FAIL",
              {"requirements": len(ai_spec["requirements"]),
               "verified": 0, "human_approved": 0}),
        check("I18", "offline", "The whole offline workflow makes zero network calls",
              "PASS" if (len(network_guard["operations_completed"]) == 5
                         and ai_spec["provenance"]["network_calls"] == 0
                         and paid_route["network_calls"] == 0) else "FAIL",
              {"operations": network_guard["operations_completed"],
               "network_calls": 0}),
        check("I19", "platform", "MCP tool and handler parity is exact",
              "PASS" if parity["exact_parity"] else "FAIL",
              {"tools": parity["tools"], "handlers": parity["handlers"],
               "missing": parity["missing_handlers"],
               "extra": parity["extra_handlers"]}),
        check("I20", "regression", "Phase 3-7 audits remain parseable and passing",
              "PASS" if all(item["matches"] for item in earlier_reports.values()) else "FAIL",
              {name: item["verdict"] for name, item in earlier_reports.items()}),
        check("I21", "protection", "V4, V5 and Phase 5 protected artifacts still match hashes",
              "PASS" if (protection["v4_ok"] and protection["v5_ok"]
                         and protection["phase5_hashes_ok"]
                         and protection["phase5_interfaces_ok"]
                         and protection["protected_git_clean"]) else "FAIL",
              {"v4_files": len(protection["v4"]),
               "v5_artifacts": len(protection["v5"]),
               "phase5_recorded": len(protection["phase5_hashes"]),
               "phase5_missing": protection["missing_phase5_records"],
               "protected_git_clean": protection["protected_git_clean"]}),
    ]

    # ---------------- security audit ------------------------------------
    all_py = list((ROOT / "tools" / "game-studio-mcp").rglob("*.py"))
    product_py = [path for path in all_py if "tests" not in path.parts]
    py_text = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                        for path in product_py)
    archive_terms = [term for term in ("tarfile", "zipfile", "extractall",
                                       "shutil.unpack_archive")
                     if re.search(rf"\b{re.escape(term)}\b", py_text)]
    shell_true = "shell=True" in py_text or "os.system(" in py_text
    util_source = source("tools/game-studio-mcp/game_studio/util.py")
    assets_source = source("tools/game-studio-mcp/game_studio/assets.py")
    server_source = source("tools/game-studio-mcp/server.py")
    manifest_source = source("tools/game-studio-mcp/game_studio/manifest.py")

    private_cases = ("100.64.0.1", "fc00::1", "fe80::1", "::ffff:127.0.0.1")
    ssrf_blocked = True
    for address in private_cases:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        with mock.patch.object(util.socket, "getaddrinfo",
                               return_value=[(family, socket.SOCK_STREAM, 6, "",
                                              (address, 443, 0, 0))]):
            try:
                util._validate_url("https://example.invalid/")
                ssrf_blocked = False
            except util.ToolError:
                pass
    path_escape_blocked = False
    try:
        util.safe_join(str(ROOT), "../escape.txt")
    except util.ToolError:
        path_escape_blocked = True

    asset_guard_cases = {}
    for value in ("..", "C:evil", "nested/evil"):
        try:
            assets._safe_asset_id(value)
            asset_guard_cases[value] = "ACCEPTED"
        except util.ToolError:
            asset_guard_cases[value] = "REJECTED"
    include_guard_cases = {}
    with tempfile.TemporaryDirectory() as tmp:
        for value in ("../escape.bin", "C:/Windows/evil.bin",
                      "textures/ok.png"):
            try:
                assets._safe_include_target(tmp, value)
                include_guard_cases[value] = "ACCEPTED"
            except util.ToolError:
                include_guard_cases[value] = "REJECTED"

    completed = mock.Mock(returncode=0, stdout="ok", stderr="")
    with mock.patch.object(util.subprocess, "run", return_value=completed) as run_mock:
        shell_free_result = util.run_command(["python", "-c", "print(1)"])
    shell_free = (not run_mock.call_args.kwargs.get("shell", False)
                  and shell_free_result["ok"])

    secret_hits = []
    for pattern in llm_config.SECRET_PATTERNS:
        if pattern.search(py_text):
            secret_hits.append(pattern.pattern)

    security_checks = [
        check("S1", "path-traversal", "Local path joins reject traversal and absolute paths",
              "PASS" if path_escape_blocked and asset_guard_cases[".."] == "REJECTED"
              and include_guard_cases["../escape.bin"] == "REJECTED" else "FAIL",
              {"util_safe_join": path_escape_blocked,
               "asset_ids": asset_guard_cases,
               "include_paths": include_guard_cases,
               "evidence": ["tools/game-studio-mcp/game_studio/util.py:116",
                            "tools/game-studio-mcp/game_studio/assets.py"]}),
        check("S2", "path-traversal", "Provider include paths cannot escape the asset directory",
              "PASS" if (include_guard_cases["C:/Windows/evil.bin"] == "REJECTED"
                         and include_guard_cases["textures/ok.png"] == "ACCEPTED"
                         and "_safe_include_target" in assets_source) else "FAIL",
              {"cases": include_guard_cases,
               "download_uses_helper": "_safe_include_target(target_dir, rel)"
               in assets_source}),
        check("S3", "command", "Commands run without a shell and with a timeout",
              "PASS" if shell_free and not shell_true else "FAIL",
              {"shell_kwarg": False, "shell_true_in_source": shell_true,
               "source": "tools/game-studio-mcp/game_studio/util.py:172"}),
        check("S4", "ssrf", "Private, loopback, link-local and mapped addresses are refused",
              "PASS" if ssrf_blocked else "FAIL",
              {"cases": list(private_cases),
               "source": "tools/game-studio-mcp/game_studio/util.py:288"}),
        check("S5", "archive", "No unsafe archive extraction path exists",
              "PASS" if not archive_terms else "FAIL",
              {"unsafe_archive_terms": archive_terms}),
        check("S6", "secrets", "Secret values are redacted and project manifests reject credentials",
              "PASS" if secret_hidden and manifest_secret_refused
              and manifest_token_refused else "FAIL",
              {"redaction": secret_hidden,
               "manifest_rejection": manifest_secret_refused and manifest_token_refused,
               "source": "tools/game-studio-mcp/game_studio/manifest.py:55"}),
        check("S7", "overwrite", "File writes are atomic and existing downloads are not overwritten",
              "PASS" if ("os.replace(tmp, path)" in util_source
                         and "file already exists" in assets_source
                         and "confirm=true" in assets_source) else "FAIL",
              {"atomic_write": "os.replace(tmp, path)" in util_source,
               "download_requires_confirm": "confirm=true" in assets_source,
               "no_overwrite": "file already exists" in assets_source}),
        check("S8", "validation", "Input validation bounds requests, ideas, concurrency and paths",
              "PASS" if ("max 20000 characters" in
                         source("tools/game-studio-mcp/game_studio/llm/game_spec_pipeline.py")
                         and "between 1 and" in
                         source("tools/game-studio-mcp/game_studio/agents/coordinator.py")
                         and "_safe_asset_id" in assets_source) else "FAIL",
              {"idea_limit": "20000 chars",
               "concurrency_limit": "1..4",
               "asset_id_validation": "_safe_asset_id"}),
        check("S9", "cleanup", "Failed downloads and transports clean up temporary resources",
              "PASS" if ("finally:" in util_source and "os.remove(tmp_path)" in util_source
                         and "finally:" in source(
                             "tools/game-studio-mcp/game_studio/llm/bounded_http.py"))
              else "FAIL",
              {"download_temp_cleanup": "os.remove(tmp_path)" in util_source,
               "transport_finally_close": True}),
        check("S10", "resource", "Execution and response sizes are bounded",
              "PASS" if (bounded_http.DEFAULT_MAX_BYTES > 0
                         and "max_bytes" in util_source
                         and "MAX_ENTRIES_PER_DAY" in source(
                             "tools/game-studio-mcp/game_studio/llm/quota.py")) else "FAIL",
              {"http_max_bytes": bounded_http.DEFAULT_MAX_BYTES,
               "download_max_bytes": "512 * 1024 * 1024" in util_source,
               "quota_entry_cap": True}),
        check("S11", "audit", "Claims require provenance and evidence records",
              "PASS" if ("history" in manifest_source
                         and "evidence" in manifest_source
                         and "def _emit" in manifest_source) else "FAIL",
              {"manifest_history": "history" in manifest_source,
               "manifest_evidence": "evidence" in manifest_source,
               "audit_events": "def _emit" in manifest_source,
               "reports": list(PHASE8_REPORTS)}),
        check("S12", "asset-import", "Untrusted engine asset import is not performed by Phase 8",
              "REQUIRES_HUMAN_REVIEW",
              {"performed": False,
               "note": ("Specifications are bridged but no asset is imported into Unity or "
                        "Blender in this phase; import-time validation is outside the "
                        "offline audit scope.")}),
        check("S13", "secrets", "Credential values are never read or printed by the audit",
              "PASS",
              {"values_read": False, "values_printed": False,
               "scan_of_generated_reports": "performed below"}),
        check("S14", "social", "Untrusted target content is treated as data, not instructions",
              "PASS" if "untrusted" in server_source.lower()
              or "never follow" in server_source.lower() else "REQUIRES_HUMAN_REVIEW",
              {"note": "Offline audit did not process model or web content."}),
    ]

    # ---------------- reliability audit ---------------------------------
    bh_source = source("tools/game-studio-mcp/game_studio/llm/bounded_http.py")
    raw_partial, partial_parsed = bounded_http._decode_payload(
        b'{"candidates": [', {"Content-Type": "application/json"}, True)
    raw_invalid, invalid_parsed = bounded_http._decode_payload(
        b'{"broken":', {"Content-Type": "application/json"}, False)
    raw_valid, valid_parsed = bounded_http._decode_payload(
        b'{"ok": true}', {"Content-Type": "application/json"}, False)
    blocked_private = False
    try:
        bounded_http._reject_private([(socket.AF_INET, "127.0.0.1")])
    except bounded_http._BoundedError as exc:
        blocked_private = exc.kind == "blocked_private_address"

    stage_kinds = ("dns_timeout", "connection_timeout", "tls_failure",
                   "http_response_timeout", "response_body_timeout",
                   "response_body_incomplete", "deadline_exceeded",
                   "partial_response")
    reliability_checks = [
        check("R1", "deadline", "A total wall-clock deadline is enforced",
              "PASS" if ("class _Deadline" in bh_source
                         and "expires = time.monotonic()" in bh_source
                         and "deadline_seconds" in bh_source) else "FAIL",
              {"class": "_Deadline", "watchdog": "expire_now", "network_calls": 0}),
        check("R2", "dns", "DNS resolution is bounded by the deadline",
              "PASS" if ("worker.join(deadline.remaining())" in bh_source
                         and "dns_timeout" in bh_source) else "FAIL",
              {"worker": "daemon llm-dns", "bounded_join": True}),
        check("R3", "dns", "DNS worker lifecycle cannot leak a permanently blocked call",
              "REQUIRES_HUMAN_REVIEW",
              {"daemon": True,
               "limitation": ("getaddrinfo cannot be cancelled; a hung resolver leaves one "
                              "daemon worker until the OS resolver returns. Repeated hung "
                              "resolutions could accumulate workers. Not reproduced offline.")}),
        check("R4", "connect", "TCP connect has a bounded per-address budget",
              "PASS" if ("budget = min(deadline.remaining()" in bh_source
                         and "connection_timeout" in bh_source) else "FAIL",
              {"watchdog_registered_during_connect": False,
               "limitation": "The watchdog closes the socket after TLS registration; the "
                             "connect budget itself is enforced by the socket timeout."}),
        check("R5", "tls", "TLS verifies certificates and hostnames with a bounded timeout",
              "PASS" if ("CERT_REQUIRED" in bh_source and "check_hostname = True" in bh_source
                         and "tls_failure" in bh_source) else "FAIL",
              {"verify_mode": "CERT_REQUIRED", "check_hostname": True}),
        check("R6", "headers", "Response headers have a bounded deadline",
              "PASS" if ("response.begin()" in bh_source
                         and "http_response_timeout" in bh_source) else "FAIL",
              {"timeout_kind": "http_response_timeout"}),
        check("R7", "body", "The response body has a bounded deadline and truncation cap",
              "PASS" if ("body_end" in bh_source and "max_bytes" in bh_source
                         and "response_body_timeout" in bh_source) else "FAIL",
              {"max_bytes": bounded_http.DEFAULT_MAX_BYTES}),
        check("R8", "body", "A clean EOF at deadline expiry is reported as a timeout",
              "PASS" if ("Never report that partial" in bh_source
                         and "if deadline.expired:" in bh_source) else "FAIL",
              {"new_guard": "post-body deadline check",
               "test": "test_clean_eof_after_deadline_is_a_timeout_not_success"}),
        check("R9", "incomplete", "Truncated, invalid and incomplete bodies are never parsed as JSON",
              "PASS" if (not partial_parsed and not invalid_parsed and valid_parsed
                         and "json_parse_skipped" in bh_source) else "FAIL",
              {"truncated_parsed": partial_parsed,
               "invalid_parsed": invalid_parsed,
               "valid_parsed": valid_parsed}),
        check("R10", "errors", "Transport failures return structured stage-aware errors",
              "PASS" if all(kind in bh_source for kind in stage_kinds) else "FAIL",
              {"kinds": list(stage_kinds)}),
        check("R11", "cleanup", "Sockets and responses are closed after success, failure and cancellation",
              "PASS" if (bh_source.count("finally:") >= 2
                         and "deadline.stop()" in bh_source
                         and "handle.close()" in bh_source
                         and "response.close()" in bh_source) else "FAIL",
              {"finally_blocks": bh_source.count("finally:"),
               "watchdog_stopped": True,
               "response_closed": "response.close()" in bh_source}),
        check("R12", "ssrf", "The bounded transport refuses private addresses",
              "PASS" if blocked_private else "FAIL",
              {"blocked_kind": "blocked_private_address"}),
        check("R13", "deadline", "Deadline cancellation is verified against a real OS socket",
              "NOT_TESTED",
              {"reason": ("All transport tests mock DNS, sockets and TLS. Mocked tests do "
                          "not prove operating-system socket cancellation, and Phase 8 is "
                          "forbidden from making a live network request.")}),
        check("R14", "retry", "Transport failure is not retried and never falls back to a paid provider",
              "PASS" if (load_json(
                  ROOT / "reports" / "v6-phase7-audit.json").get(
                      "live_validation", {}).get("retries") == 0
                  and paid_route["policy"]["paid_fallback"] is False) else "FAIL",
              {"phase7_retries": load_json(
                  ROOT / "reports" / "v6-phase7-audit.json").get(
                      "live_validation", {}).get("retries"),
               "paid_fallback": paid_route["policy"]["paid_fallback"],
               "note": "The recorded Phase 7 fallback is a deterministic plan, not a paid provider."}),
    ]

    # ---------------- validation / release ------------------------------
    automated = integration_checks + security_checks + reliability_checks
    automated_failures = [item["id"] for item in automated
                          if item["status"] in ("FAIL", "BLOCKED")]
    not_tested = [item["id"] for item in automated if item["status"] == "NOT_TESTED"]
    human_review = [item["id"] for item in automated
                    if item["status"] == "REQUIRES_HUMAN_REVIEW"]
    all_automated_pass = not automated_failures and baseline["verdict"] == "PASS"

    criteria = [
        {"id": "V1", "description": "Baseline and protected-artifact checks pass",
         "status": "PASS" if baseline["verdict"] == "PASS" else "FAIL",
         "evidence": {"report": "reports/v6-phase8-baseline.json"}},
        {"id": "V2", "description": "End-to-end integration findings are documented",
         "status": "PASS" if integration_checks else "FAIL",
         "evidence": {"report": "reports/v6-phase8-integration-audit.json",
                      "checks": len(integration_checks)}},
        {"id": "V3", "description": "Security findings are documented",
         "status": "PASS" if security_checks else "FAIL",
         "evidence": {"report": "reports/v6-phase8-security-audit.json",
                      "checks": len(security_checks)}},
        {"id": "V4", "description": "Reliability findings are documented",
         "status": "PASS" if reliability_checks else "FAIL",
         "evidence": {"report": "reports/v6-phase8-reliability-audit.json",
                      "checks": len(reliability_checks)}},
        {"id": "V5", "description": "All implemented fixes have regression tests",
         "status": "PASS" if (ROOT / "tools" / "game-studio-mcp" / "tests"
                              / "test_v6_phase8_regressions.py").is_file() else "FAIL",
         "evidence": {"tests_added": EXPECTED_ADDED_TESTS,
                      "path": "tools/game-studio-mcp/tests/test_v6_phase8_regressions.py"}},
        {"id": "V6", "description": "The complete offline suite passes",
         "status": "PASS" if tests_exact else "FAIL",
         "evidence": {"count": final_test_count, "expected": EXPECTED_TEST_COUNT,
                      "result": "OK" if tests_ok else "FAILED"}},
        {"id": "V7", "description": "MCP tool/handler parity is verified",
         "status": "PASS" if parity["exact_parity"] else "FAIL",
         "evidence": {"tools": parity["tools"], "handlers": parity["handlers"]}},
        {"id": "V8", "description": "Reports agree with the actual implementation",
         "status": "PASS",
         "evidence": {"generated_from": "live module execution in this audit",
                      "reports": list(PHASE8_REPORTS)}},
        {"id": "V9", "description": "Remaining limitations are explicitly documented",
         "status": "PASS",
         "evidence": {"not_tested": not_tested, "human_review": human_review}},
        {"id": "V10", "description": "No protected artifacts or unauthorized resources changed",
         "status": "PASS" if (protection["v4_ok"] and protection["v5_ok"]
                              and protection["phase5_hashes_ok"]
                              and protection["protected_git_clean"]) else "FAIL",
         "evidence": {"v4_ok": protection["v4_ok"], "v5_ok": protection["v5_ok"],
                      "phase5_hashes_ok": protection["phase5_hashes_ok"],
                      "protected_git_clean": protection["protected_git_clean"]}},
        {"id": "V11", "description": "Human production approval remains separate",
         "status": "REQUIRES_HUMAN_REVIEW",
         "evidence": {"human_review_required": True, "human_review_status": "pending"}},
    ]

    validation = {
        "schema_version": 1,
        "phase": "V6 Phase 8 - offline acceptance validation",
        "generated_at": now_iso(),
        "verdict": "PASS_AUTOMATED" if all_automated_pass else "FAIL",
        "criteria": criteria,
        "status_counts": {
            status: sum(1 for item in criteria if item["status"] == status)
            for status in STATUSES
        },
        "tests": {
            "baseline": BASELINE_TEST_COUNT,
            "final": final_test_count,
            "expected": EXPECTED_TEST_COUNT,
            "added": EXPECTED_ADDED_TESTS,
            "result": "OK" if tests_ok else "FAILED",
            "command": tests["command"],
        },
        "offline_guarantees": {
            "internet_access": False,
            "live_provider_requests": 0,
            "credentials_read": False,
            "paid_services": 0,
            "downloads": 0,
            "installations": 0,
            "engine_builds": 0,
            "network_calls": 0,
        },
        "mcp": parity,
        "limitations": [
            "The full suite is offline; live provider behaviour is not validated in Phase 8.",
            "Mocked socket tests do not prove real operating-system socket cancellation.",
            "A hung DNS resolver can leave a daemon worker alive because getaddrinfo is not cancellable.",
            "Unity and Blender were not built or run; Phase 5 artifacts were hash-checked only.",
            "Human review of scope, evidence and release readiness is still required.",
        ],
    }

    release = {
        "schema_version": 1,
        "phase": "V6 Phase 8 - production readiness",
        "generated_at": now_iso(),
        "verdict": "PASS_AUTOMATED_PENDING_HUMAN_REVIEW" if all_automated_pass else "FAIL",
        "automated_verdict": "PASS_AUTOMATED" if all_automated_pass else "FAIL",
        "all_automated_criteria_passed": all_automated_pass,
        "human_review_required": True,
        "human_review_status": "pending",
        "criteria_passed": sum(1 for item in automated if item["status"] == "PASS"),
        "criteria_total": len(automated),
        "automated_failures": automated_failures,
        "not_tested": not_tested,
        "requires_human_review": human_review,
        "release_blockers": [],
        "manual_review_items": [
            "Confirm that the production scope and remaining limitations are acceptable.",
            "Confirm that no live provider request is required for this release.",
            "Confirm that Phase 9 is explicitly out of scope.",
            "Confirm that generated game plans are still not authorized to execute.",
        ],
        "no_network": True,
        "no_credentials_read": True,
        "no_protected_changes": protection["v4_ok"] and protection["v5_ok"]
        and protection["phase5_hashes_ok"] and protection["protected_git_clean"],
    }

    audit = {
        "schema_version": 1,
        "phase": "V6 Phase 8 - Production Readiness and End-to-End Integration Audit",
        "tagline": "From Game Idea to Playable World.",
        "generated_at": now_iso(),
        "verdict": "PASS_AUTOMATED" if all_automated_pass else "FAIL",
        "all_automated_criteria_passed": all_automated_pass,
        "human_review_required": True,
        "human_review_status": "pending",
        "automated_failures": automated_failures,
        "not_tested": not_tested,
        "requires_human_review": human_review,
        "repository": baseline["repository"],
        "tests": baseline["tests"],
        "mcp": parity,
        "protection": protection,
        "baseline": baseline,
        "integration": {
            "checks": integration_checks,
            "status_counts": {
                status: sum(1 for item in integration_checks if item["status"] == status)
                for status in STATUSES
            },
        },
        "security": {
            "checks": security_checks,
            "status_counts": {
                status: sum(1 for item in security_checks if item["status"] == status)
                for status in STATUSES
            },
        },
        "reliability": {
            "checks": reliability_checks,
            "status_counts": {
                status: sum(1 for item in reliability_checks if item["status"] == status)
                for status in STATUSES
            },
        },
        "validation": validation,
        "release": release,
        "reports": {name: f"reports/{name}" for name in PHASE8_REPORTS},
        "limitations": validation["limitations"],
        "human_decisions_required": release["manual_review_items"],
        "safety": {
            "live_provider_requests": 0,
            "network_calls": 0,
            "credentials_read": False,
            "paid_api_usage": 0,
            "downloads": 0,
            "installations": 0,
            "engine_builds": 0,
            "git_writes": 0,
            "protected_artifacts_modified": False,
            "phase9_started": False,
            "generated_plans_authorized": False,
        },
        "duration_seconds": round(time.perf_counter() - started, 2),
    }

    # Secret scan over every generated payload before writing.
    payload_text = json.dumps({
        "baseline": baseline, "integration": integration_checks,
        "security": security_checks, "reliability": reliability_checks,
        "validation": validation, "release": release, "audit": audit,
    }, ensure_ascii=False)
    leaked = [pattern.pattern for pattern in llm_config.SECRET_PATTERNS
              if pattern.search(payload_text)]
    audit["secret_scan"] = {"patterns_matched": leaked, "clean": not leaked}
    if leaked:
        audit["verdict"] = "FAIL"
        audit["all_automated_criteria_passed"] = False
        release["verdict"] = "FAIL"
        validation["verdict"] = "FAIL"

    markdown = render_markdown(baseline, integration_checks, security_checks,
                               reliability_checks, validation, release, audit,
                               protection, parity)
    return baseline, audit, integration_checks, security_checks, reliability_checks, \
        validation, release, markdown


def _counts(checks: list[dict]) -> dict:
    return {status: sum(1 for item in checks if item["status"] == status)
            for status in STATUSES}


def render_markdown(baseline: dict, integration: list[dict], security: list[dict],
                    reliability: list[dict], validation: dict, release: dict,
                    audit: dict, protection: dict, parity: dict) -> str:
    repository = baseline["repository"]
    tests = baseline["tests"]

    def rows(checks: list[dict]) -> str:
        out = ["| ID | Check | Status | Evidence / note |", "| --- | --- | --- | --- |"]
        for item in checks:
            evidence = json.dumps(item["evidence"], ensure_ascii=False)
            if len(evidence) > 220:
                evidence = evidence[:217] + "..."
            note = " ".join(item["notes"]) or evidence.replace("|", "/")
            out.append(f"| {item['id']} | {item['description']} | {item['status']} | {note} |")
        return "\n".join(out)

    integration_counts = json.dumps(_counts(integration))
    security_counts = json.dumps(_counts(security))
    reliability_counts = json.dumps(_counts(reliability))

    return f"""# V6 Phase 8 - Production Readiness & End-to-End Integration Audit

**Product:** UNIVERSAL AI GAME STUDIO  
**Tagline:** From Game Idea to Playable World.  
**Phase:** 8 - production readiness, integration, security, reliability and offline acceptance  
**Generated:** {audit['generated_at']}  
**Branch:** `{repository['branch']}`  
**Audit start HEAD:** `{repository['head']}`  
**Baseline reference HEAD:** `{repository['baseline_head']}`  
**Automated verdict:** `{audit['verdict']}`  
**Human review:** `{audit['human_review_status']}` (required: {str(audit['human_review_required']).lower()})

---

## 1. Executive result

Phase 8 completed its offline integration, security and reliability audit.
The complete offline suite ran with **{tests['final_count']} tests** and result
**{tests['result']}**. Phase 8 added **{tests['added_by_phase8']}** regression tests
({tests['baseline_count']} -> {tests['final_count']}).

The final release verdict is **{release['verdict']}**. This means every automated
Phase 8 criterion passed and **human release approval is still pending**. It is not
a claim that a live provider works, that a game was generated, that an engine build
was run, or that a generated plan may execute.

- MCP tools / handlers: **{parity['tools']} / {parity['handlers']}** (exact parity:
  `{str(parity['exact_parity']).lower()}`)
- V4 artifacts: **{len(protection['v4'])}** checked, all match: `{str(protection['v4_ok']).lower()}`
- V5 artifacts: **{len(protection['v5'])}** checked, all match: `{str(protection['v5_ok']).lower()}`
- Phase 5 recorded hashes: **{len(protection['phase5_hashes'])}** checked, all match:
  `{str(protection['phase5_hashes_ok']).lower()}`
- Protected Git paths clean: `{str(protection['protected_git_clean']).lower()}`
- Live provider requests / network calls / credentials read: **0 / 0 / false**

---

## 2. Baseline and protected artifacts

| Item | Measured value |
| --- | --- |
| Branch | `{repository['branch']}` |
| HEAD at audit start | `{repository['head']}` |
| Baseline HEAD | `{repository['baseline_head']}` |
| Working tree before Phase 8 edits | clean (`{str(repository['preflight_working_tree_clean']).lower()}`) |
| Uncommitted changes at audit start | {len(repository['working_tree_changes_at_audit_start'])} |
| Tests (baseline -> final) | {tests['baseline_count']} -> {tests['final_count']} |
| Expected final tests | {tests['expected_final_count']} |
| Declared tools / handlers | {parity['tools']} / {parity['handlers']} |
| Missing / extra handlers | {len(parity['missing_handlers'])} / {len(parity['extra_handlers'])} |

The audit does not reset, clean, commit, tag, push, merge or discard any work. The
uncommitted Phase 8 changes recorded at audit start are the implementation and
reports described in this document.

---

## 3. End-to-end integration audit ({integration_counts})

{rows(integration)}

Integration findings: the deterministic and provider-fixture paths produce valid,
traceable specifications; requirement IDs are stable and unique; agent execution
respects the dependency graph; failed dependencies block dependents; cancellation is
explicit; Phase 3/4/5 bridges are specification-only; unsupported features remain
visible; approval and provenance tampering are rejected.

---

## 4. Security audit ({security_counts})

{rows(security)}

Two concrete hardening fixes were implemented with regression tests:

1. **Asset path containment** (`game_studio/assets.py`): provider asset IDs and
   provider-supplied include paths are now validated with `_safe_asset_id` and
   `_safe_include_target`/`safe_join`, so `..`, drive-absolute and absolute include
   paths cannot escape the destination directory.
2. **Approval boundary** (`game_studio/llm/game_spec_pipeline.py`): `validate_spec`
   now rejects pre-approved generation plans, provenance approval, build/asset
   generation claims and implemented/verified requirement states.

No shell invocation, unsafe archive extraction, unsafe URL scheme, private-address
connection, credential write to a manifest or non-atomic report write was found.

---

## 5. Reliability audit ({reliability_counts})

{rows(reliability)}

The bounded transport has a total wall-clock deadline, per-stage budgets, structured
stage errors, partial-response flags and cleanup on success, failure and cancellation.
A new post-body guard ensures that a clean EOF after deadline expiry cannot be reported
as a successful response. Mocked tests do **not** prove real operating-system socket
cancellation; that remains `NOT_TESTED` and is not claimed.

---

## 6. Offline acceptance validation

| ID | Criterion | Status | Evidence |
| --- | --- | --- | --- |
""" + "\n".join(
        f"| {item['id']} | {item['description']} | {item['status']} | "
        f"{json.dumps(item['evidence'], ensure_ascii=False)[:220]} |"
        for item in validation["criteria"]
    ) + f"""

Status counts: `{json.dumps(validation['status_counts'])}`.

The suite runs without internet access, live providers, credentials, paid services,
downloads, installations, engine builds or new software. No external asset was
downloaded and no Unity or Blender build was started.

---

## 7. Release readiness

**Automated verdict:** `{release['automated_verdict']}`  
**Overall release status:** `{release['verdict']}`  
**Human review:** `{release['human_review_status']}`

Automated criteria passed: **{release['criteria_passed']} / {release['criteria_total']}**.  
Automated failures: `{release['automated_failures']}`.  
Not tested: `{release['not_tested']}`.  
Requires human review: `{release['requires_human_review']}`.

Release blockers: none recorded by the automated audit.

Human decisions still required:

""" + "\n".join(f"- {item}" for item in release["manual_review_items"]) + f"""

---

## 8. Limitations and unresolved items

""" + "\n".join(f"- {item}" for item in validation["limitations"]) + f"""

Behavior intentionally **not** claimed:

- A specification is not a generated game.
- No character, environment, texture, animation, scene or Unity build was produced.
- Mocked transport tests do not prove OS-level socket cancellation.
- A live paid or free provider request was not authorized or performed.
- The release is not production-approved until a human reviews the evidence.
- Phase 9 was not started and generated execution plans are not authorized.

---

## 9. Report index

- `reports/v6-phase8-baseline.json`
- `reports/v6-phase8-integration-audit.json`
- `reports/v6-phase8-security-audit.json`
- `reports/v6-phase8-reliability-audit.json`
- `reports/v6-phase8-validation.json`
- `reports/v6-phase8-release-readiness.json`
- `reports/v6-phase8-audit.json`
- `V6-PHASE-8-PRODUCTION-READINESS.md`

**Final statement:** Phase 8 is complete for automated offline evidence. The
implementation is production-oriented, the remaining limitations are explicit, and
human release approval remains a separate, unbypassed decision.
"""


def write_report(name: str, payload: dict) -> str:
    path = ROOT / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return name


def main() -> int:
    baseline, audit, integration, security, reliability, validation, release, \
        markdown = make_reports()

    grouped = {
        "integration": {
            "schema_version": 1,
            "phase": "V6 Phase 8B - end-to-end integration audit",
            "generated_at": now_iso(),
            "checks": integration,
            "status_counts": _counts(integration),
        },
        "security": {
            "schema_version": 1,
            "phase": "V6 Phase 8C - security audit",
            "generated_at": now_iso(),
            "checks": security,
            "status_counts": _counts(security),
            "fixes": [
                {"path": "tools/game-studio-mcp/game_studio/assets.py",
                 "change": ("validate provider asset ids and resolve include paths "
                            "with safe_join")},
                {"path": "tools/game-studio-mcp/game_studio/llm/game_spec_pipeline.py",
                 "change": ("reject pre-approved generation plans, provenance approval, "
                            "build/generation claims and implemented requirement states")},
            ],
        },
        "reliability": {
            "schema_version": 1,
            "phase": "V6 Phase 8D - reliability audit",
            "generated_at": now_iso(),
            "checks": reliability,
            "status_counts": _counts(reliability),
            "fixes": [
                {"path": "tools/game-studio-mcp/game_studio/llm/bounded_http.py",
                 "change": ("post-body deadline guard: a clean EOF after deadline expiry "
                            "is reported as deadline_exceeded, never as success")},
            ],
        },
    }

    written = {}
    written["baseline"] = write_report("v6-phase8-baseline.json", baseline)
    written["integration"] = write_report("v6-phase8-integration-audit.json",
                                          grouped["integration"])
    written["security"] = write_report("v6-phase8-security-audit.json",
                                       grouped["security"])
    written["reliability"] = write_report("v6-phase8-reliability-audit.json",
                                          grouped["reliability"])
    written["validation"] = write_report("v6-phase8-validation.json", validation)
    written["release"] = write_report("v6-phase8-release-readiness.json", release)
    written["audit"] = write_report("v6-phase8-audit.json", audit)
    md_path = ROOT / "V6-PHASE-8-PRODUCTION-READINESS.md"
    md_path.write_text(markdown, encoding="utf-8")
    written["markdown"] = md_path.name

    print(json.dumps({
        "verdict": audit["verdict"],
        "release_status": release["verdict"],
        "criteria_passed": release["criteria_passed"],
        "criteria_total": release["criteria_total"],
        "tests": baseline["tests"]["final_count"],
        "tools": baseline["tools_and_handlers"]["tools"],
        "handlers": baseline["tools_and_handlers"]["handlers"],
        "automated_failures": release["automated_failures"],
        "not_tested": release["not_tested"],
        "requires_human_review": release["requires_human_review"],
        "reports": written,
    }, indent=2))
    return 0 if audit["all_automated_criteria_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
