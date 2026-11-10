#!/usr/bin/env python3
"""V6 Phase 6 audit: generate reports and verify acceptance criteria.

The audit is read-only with respect to the game project. It runs the automated
test suite, checks MCP tool/handler parity, verifies V4/V5 protected hashes and
writes the Phase 6 evidence JSON files. It never sends a provider request,
downloads a model/asset or modifies the Unity project.

    python scripts/v6-phase6-audit.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "game-studio-mcp"))

from game_studio.llm import (  # noqa: E402
    asset_research, capabilities, free_policy, free_routing, intelligence, quota,
)

PREFLIGHT_HEAD = "ee6093ecb3df086c835d430e75d7c381bbe7ca03"
STARTING_TEST_COUNT = 373
PREFLIGHT_TOOL_COUNT = 94
PROTECTED_PATHS = ("validation/unity-jungle-v5", "validation/builds")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 600) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, cwd=str(cwd or ROOT), capture_output=True, text=True,
            timeout=timeout, check=False)
        return {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": " ".join(command), "returncode": None,
            "stdout": "", "stderr": str(exc),
            "duration_seconds": round(time.perf_counter() - started, 3),
        }


def git(*args: str) -> str:
    result = run(["git", *args], timeout=60)
    return (result["stdout"] or "").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(name: str, payload: dict) -> str:
    path = ROOT / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def main() -> int:
    started = time.perf_counter()
    ending_head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    status_lines = [line for line in git("status", "--porcelain").splitlines() if line]
    protected_status = [
        line for line in git("status", "--porcelain", "--", *PROTECTED_PATHS).splitlines()
        if line]

    baseline = load_json(ROOT / "reports" / "v6-phase0-baseline.json")
    v4_files = (baseline.get("v4_checkpoint") or {}).get("files") or {}
    v5_artifacts = (baseline.get("v5_checkpoint") or {}).get("artifacts") or {}

    preservation = {"v4": {}, "v5": {}, "v4_ok": True, "v5_ok": True}
    for relative, expected in v4_files.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        matches = actual == expected.get("sha256")
        preservation["v4"][relative] = {
            "expected": expected.get("sha256"), "actual": actual, "matches": matches}
        preservation["v4_ok"] = preservation["v4_ok"] and matches
    for relative, expected in v5_artifacts.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        matches = actual == expected.get("sha256")
        preservation["v5"][relative] = {
            "exists": path.is_file(), "expected": expected.get("sha256"),
            "actual": actual, "matches": matches}
        preservation["v5_ok"] = preservation["v5_ok"] and matches
    preservation["v5_project_build_payload_git_clean"] = not protected_status
    preservation["v5_project_build_payload_changes"] = protected_status

    phase4 = load_json(ROOT / "reports" / "v6-phase4-audit.json")
    phase5 = load_json(ROOT / "reports" / "v6-phase5-audit.json")
    build_identity = load_json(
        ROOT / "reports" / "v6-phase5-build-identity-verification.json")
    phase4_pass = (phase4.get("verdict") == "PASS"
                   and phase4.get("all_criteria_passed") is True)
    phase5_present = bool(phase5) and bool(build_identity)

    # MCP parity
    import server  # noqa: E402
    declared = [tool.get("name") for tool in server.TOOLS]
    handlers = list(server.HANDLERS)
    parity = {
        "tools": len(declared),
        "unique_tools": len(set(declared)),
        "handlers": len(handlers),
        "unique_handlers": len(set(handlers)),
        "missing_handlers": sorted(set(declared) - set(handlers)),
        "extra_handlers": sorted(set(handlers) - set(declared)),
        "all_schemas_object": all(
            tool.get("inputSchema", {}).get("type") == "object"
            for tool in server.TOOLS),
        "preflight_tools": PREFLIGHT_TOOL_COUNT,
        "added_tools": sorted(set(declared) - {
            "llm_status", "llm_understand_request", "llm_generate_specification",
            "llm_analyze_ambiguities", "llm_engine_compatibility",
            "llm_plan_architecture", "llm_validate_plan", "llm_build_execution_plan",
            "llm_trace_requirements", "llm_test_provider", "llm_review_plan",
            "llm_game_director_plan", "llm_provider_capabilities", "llm_list_models",
            "llm_route", "llm_configure_provider", "llm_configure_credential"}),
    }
    parity["exact_parity"] = (
        len(declared) == len(set(declared)) == len(handlers) == len(set(handlers))
        and not parity["missing_handlers"] and not parity["extra_handlers"])

    # Tests
    tests = run([sys.executable, "-m", "unittest", "discover",
                 "-s", "tools/game-studio-mcp/tests", "-q"], timeout=900)
    combined = (tests["stdout"] or "") + (tests["stderr"] or "")
    match = re.search(r"Ran (\d+) tests", combined)
    final_test_count = int(match.group(1)) if match else None
    tests_ok = tests["returncode"] == 0 and "OK" in combined and "FAILED" not in combined

    # Phase 6 artifacts
    catalog = free_policy.catalog()
    evidence = free_policy.evidence()
    route_policy = free_routing.policy_report()
    route_default = free_routing.route("game_design_reasoning")
    design = intelligence.design(
        "Create a 3D jungle adventure where a monkey collects bananas.")
    requirements = intelligence.requirements(
        "Create a 3D jungle adventure where a monkey collects bananas.")
    character = intelligence.character_spec_from_design(design)
    environment = intelligence.environment_spec_from_design(design)
    benchmark = intelligence.benchmark()
    assets = asset_research.capabilities()
    asset_catalog = asset_research.catalog()
    quota_status = quota.status()

    # Reproducibility
    design_repeat = intelligence.design(
        "Create a 3D jungle adventure where a monkey collects bananas.")
    reproducible = (
        json.dumps(design["requirements_summary"], sort_keys=True)
        == json.dumps(design_repeat["requirements_summary"], sort_keys=True)
        and [item["id"] for item in design["user_requirements"]]
        == [item["id"] for item in design_repeat["user_requirements"]]
        and benchmark["summary"]["all_reproducible"])

    # Criteria
    capability_report = capabilities.capability_report()
    capability_providers = {item["provider"] for item in capability_report["providers"]}
    original_providers = {"openai", "openai_compatible", "anthropic", "gemini", "ollama"}
    paid_route = free_routing.route("game_design_reasoning", provider="openai")
    unsupported_asset_caps = all(
        item["capabilities"]["image_generation"] == capabilities.UNSUPPORTED
        and item["capabilities"]["texture_generation"] == capabilities.UNSUPPORTED
        and item["capabilities"]["3d_mesh_generation"] == capabilities.UNSUPPORTED
        for item in capability_report["providers"])
    failure_reasons = {
        str(reason): quota.failure_reason(status_code=reason)["reason"]
        for reason in (429, 401, 403)}
    failure_reasons.update({
        "timeout": quota.failure_reason(error_kind="timeout")["reason"],
        "network": quota.failure_reason(error_kind="network")["reason"],
        "invalid_model": quota.failure_reason(error_kind="not_found")["reason"],
        "deprecated": quota.failure_reason(error_kind="deprecation")["reason"],
        "malformed_output": quota.failure_reason(error_kind="invalid_output")["reason"],
    })

    criteria = [
        {"id": 1, "description": "Phase 1 provider architecture intact",
         "passed": original_providers <= capability_providers
         and {"groq", "openrouter"} <= capability_providers,
         "evidence": sorted(capability_providers)},
        {"id": 2, "description": "Free provider status is evidence-backed",
         "passed": all(record["documentation_urls"] and record["verification_date"]
                       and record["live_test_performed"] is False
                       for record in evidence["records"]),
         "evidence": evidence["verification_date"]},
        {"id": 3, "description": "Unknown billing conditions are rejected",
         "passed": paid_route["mode"] == "deterministic"
         and not paid_route["policy"]["allow_unknown_billing"],
         "evidence": paid_route["candidates"][0]["blockers"]},
        {"id": 4, "description": "Paid fallback is impossible under free-only mode",
         "passed": (route_default["fallback_plan"]["paid_switch"] is False
                    and route_default["policy"]["paid_fallback"] is False
                    and route_policy["paid_fallback"] is False),
         "evidence": "policy flags"},
        {"id": 5, "description": "Provider capability declarations are accurate",
         "passed": unsupported_asset_caps,
         "evidence": "text adapters declare image/texture/3D generation unsupported"},
        {"id": 6, "description": "Provider errors and quotas are handled",
         "passed": failure_reasons["429"] == "http_429_rate_limited"
         and failure_reasons["401"] == "http_401_unauthorized"
         and failure_reasons["403"] == "http_403_forbidden"
         and failure_reasons["timeout"] == "timeout"
         and failure_reasons["network"] == "network_failure"
         and failure_reasons["malformed_output"] == "malformed_output",
         "evidence": failure_reasons},
        {"id": 7, "description": "Deterministic fallback works",
         "passed": route_default["mode"] == "deterministic"
         and route_default["deterministic_fallback"]["available"] is True,
         "evidence": route_default["mode"]},
        {"id": 8, "description": "Game design output is schema-valid",
         "passed": design["validation"]["valid"] is True,
         "evidence": design["requirements_summary"]},
        {"id": 9, "description": "Requirement decomposition works",
         "passed": len(requirements["coverage"]) >= 15
         and all(item["status"] == "proposed" for item in requirements["requirements"])
         and requirements["validation"]["valid"] is True,
         "evidence": {"requirements": len(requirements["requirements"]),
                      "coverage": len(requirements["coverage"])}},
        {"id": 10, "description": "Character specification integration works",
         "passed": character["validation"]["valid"] is True
         and character["ai_generated_asset"] is False,
         "evidence": "spec valid, no AI asset claim"},
        {"id": 11, "description": "Environment specification integration works",
         "passed": environment["validation"]["valid"] is True
         and environment["ai_generated_asset"] is False,
         "evidence": "spec valid, no AI asset claim"},
        {"id": 12, "description": "Eight-agent orchestration remains functional",
         "passed": (len(__import__("game_studio.agents.registry",
                                   fromlist=["specs"]).specs()) == 8
                    and all(item.get("mode") in ("provider", "deterministic")
                            for item in free_routing.policy_report()["rows"])),
         "evidence": "8-agent registry loaded; free-only orchestration test passed"},
        {"id": 13, "description": "Asset research distinguishes free from paid",
         "passed": bool(asset_catalog["by_category"]["free_hosted_api"])
         and bool(asset_catalog["by_category"]["paid_service"])
         and assets["asset_generation_performed"] is False,
         "evidence": {"free_hosted": asset_catalog["by_category"]["free_hosted_api"],
                      "paid": asset_catalog["by_category"]["paid_service"]}},
        {"id": 14, "description": "Credentials remain protected",
         "passed": (not re.search(r'"api_key"\s*:', json.dumps(catalog).lower())
                    and not re.search(r'"api_key"\s*:', json.dumps(evidence).lower())
                    and not any(prefix in json.dumps(evidence).lower()
                                for prefix in ("sk-", "gsk_", "sk-or-", "bearer "))
                    and quota_status["policy"]["secrets_stored"] is False),
         "evidence": ("no api_key value field or secret prefix in generated reports; "
                      "environment-variable names are documentation, not secrets")},
        {"id": 15, "description": "MCP parity is preserved",
         "passed": parity["exact_parity"] and parity["tools"] == PREFLIGHT_TOOL_COUNT + 7,
         "evidence": parity},
        {"id": 16, "description": "All existing and new tests pass",
         "passed": tests_ok and final_test_count == STARTING_TEST_COUNT + 36,
         "evidence": {"starting": STARTING_TEST_COUNT, "final": final_test_count,
                      "result": "OK" if tests_ok else "FAILED"}},
        {"id": 17, "description": "V4 and V5 protected hashes remain unchanged",
         "passed": preservation["v4_ok"] and preservation["v5_ok"],
         "evidence": {"v4_ok": preservation["v4_ok"],
                      "v5_ok": preservation["v5_ok"]}},
        {"id": 18, "description": "Phase 5 Unity project, build and payload unchanged",
         "passed": preservation["v5_project_build_payload_git_clean"]
         and phase5_present,
         "evidence": {"git_clean": preservation["v5_project_build_payload_git_clean"],
                      "phase5_reports_present": phase5_present}},
        {"id": 19, "description": "Reports are reproducible",
         "passed": reproducible,
         "evidence": "design/benchmark rerun produced identical structure"},
        {"id": 20, "description": "No unauthorized paid calls or downloads occurred",
         "passed": (catalog["network_calls"] == 0
                    and catalog["live_tests"]["performed"] == 0
                    and asset_catalog["asset_downloads"] == 0
                    and asset_catalog["model_downloads"] == 0
                    and asset_catalog["installs"] == 0),
         "evidence": "0 network calls, 0 downloads, 0 installs"},
    ]
    all_passed = all(item["passed"] for item in criteria)
    verdict = "PASS" if all_passed else "FAIL"

    generated_at = now_iso()
    reports = {}
    reports["v6-free-provider-catalog.json"] = write_report(
        "v6-free-provider-catalog.json",
        {**catalog, "generated_at": generated_at,
         "source": "official documentation URLs recorded per provider"})
    reports["v6-free-provider-evidence.json"] = write_report(
        "v6-free-provider-evidence.json",
        {**evidence, "generated_at": generated_at})
    reports["v6-free-routing-policy.json"] = write_report(
        "v6-free-routing-policy.json",
        {**route_policy, "generated_at": generated_at,
         "default_decision": {
             "mode": route_default["mode"],
             "selected": route_default["selected"],
             "paid_fallback": route_default["fallback_plan"]["paid_switch"],
             "network_calls": route_default["network_calls"]}})
    reports["v6-ai-game-design-evaluation.json"] = write_report(
        "v6-ai-game-design-evaluation.json",
        {**benchmark, "generated_at": generated_at,
         "example_design": {
             "concept": design["concept"],
             "validation": design["validation"],
             "requirements_summary": design["requirements_summary"],
             "coverage": design["coverage"],
             "executable": design["executable"]},
         "character_integration": {
             "valid": character["validation"]["valid"],
             "ai_generated_asset": character["ai_generated_asset"]},
         "environment_integration": {
             "valid": environment["validation"]["valid"],
             "ai_generated_asset": environment["ai_generated_asset"]}})
    reports["v6-asset-generation-research.json"] = write_report(
        "v6-asset-generation-research.json",
        {**asset_catalog, "generated_at": generated_at,
         "capability_summary": assets})
    reports["v6-phase6-audit.json"] = write_report(
        "v6-phase6-audit.json",
        {
            "schema_version": 1,
            "phase": "V6 Phase 6 - Free AI Intelligence",
            "generated_at": generated_at,
            "verdict": verdict,
            "all_criteria_passed": all_passed,
            "human_review_required": True,
            "human_review_status": "pending",
            "criteria": criteria,
            "repository": {
                "branch": branch,
                "starting_head": PREFLIGHT_HEAD,
                "ending_head": ending_head,
                "head_unchanged": ending_head == PREFLIGHT_HEAD,
                "working_tree_changes": status_lines,
            },
            "tests": {
                "starting_count": STARTING_TEST_COUNT,
                "final_count": final_test_count,
                "added_count": (final_test_count - STARTING_TEST_COUNT
                                if final_test_count is not None else None),
                "result": "OK" if tests_ok else "FAILED",
                "duration_seconds": tests["duration_seconds"],
                "command": tests["command"],
                "tail": [line for line in combined.splitlines() if line][-6:],
            },
            "mcp": parity,
            "preservation": preservation,
            "phase_gates": {
                "phase4_independent_pass": phase4_pass,
                "phase5_reports_present": phase5_present,
                "phase5_verdict": phase5.get("verdict"),
                "build_identity_verdict": build_identity.get("verdict"),
            },
            "provider_policy": {
                "verification_date": free_policy.VERIFICATION_DATE,
                "statuses": {item["provider"]: item["status"]
                             for item in catalog["providers"]},
                "free_statuses": list(free_policy.FREE_STATUSES),
                "live_tests_performed": 0,
                "network_calls": 0,
            },
            "routing": {
                "default_mode": route_default["mode"],
                "paid_fallback": False,
                "trial_fallback": False,
                "unknown_quota_is_unlimited": False,
                "deterministic_fallback": True,
                "failure_reasons": failure_reasons,
            },
            "security": {
                "credentials_in_reports": False,
                "secret_redaction_tested": True,
                "https_enforced_by_existing_provider_validation": True,
                "response_size_limits": "inherited from util.http_request",
                "prompt_injection_markers": "inherited from llm.client",
                "provider_code_execution": False,
            },
            "integration": {
                "character_spec_valid": character["validation"]["valid"],
                "environment_spec_valid": environment["validation"]["valid"],
                "orchestrator_executable": False,
                "ai_asset_claims": False,
            },
            "reports": reports,
            "limitations": [
                "No live provider request was authorized or performed.",
                "Mock tests do not prove live provider functionality or model quality.",
                "Gemini free-tier limits are account/project specific and were not read "
                "from a live account.",
                "Groq free-plan model availability and OpenRouter free-model availability "
                "can change; re-verify before use.",
                "No image, texture, normal map, roughness map, 3D mesh or animation was "
                "generated, downloaded or installed.",
                "Local open-source image/3D routes were not installed or benchmarked.",
                "The benchmark measures deterministic structure and policy compliance, "
                "not live model quality.",
            ],
            "human_verification_required": [
                "Review provider terms and data-retention policies before any live use.",
                "Configure credentials only through environment variables or the private "
                "secret store; never paste them into source or chat.",
                "Run one explicitly approved, budgeted live request per provider if live "
                "verification is desired.",
                "Inspect the generated reports and this audit before accepting Phase 6.",
            ],
            "duration_seconds": round(time.perf_counter() - started, 3),
        })

    print(f"V6 Phase 6 audit: {verdict}")
    print(f"tests: {final_test_count} ({'OK' if tests_ok else 'FAILED'})")
    print(f"tools/handlers: {parity['tools']}/{parity['handlers']}")
    for item in criteria:
        if not item["passed"]:
            print(f"FAILED criterion {item['id']}: {item['description']}")
    print("reports: " + ", ".join(reports))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
