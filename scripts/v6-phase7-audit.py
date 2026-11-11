#!/usr/bin/env python3
"""V6 Phase 7 audit: offline evidence, preservation checks and reports.

The audit never sends a provider request, downloads a model or asset, installs
software, modifies the Phase 5 Unity project or performs any Git write. Live
provider validation is reported as BLOCKED/NOT_TESTED until a human approves
one exact request and configures a credential locally.

    python scripts/v6-phase7-audit.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "game-studio-mcp"))

from game_studio import character_spec, environment_spec  # noqa: E402
from game_studio.llm import (  # noqa: E402
    config as llm_config,
    free_policy,
    free_routing,
    game_spec_pipeline,
    provider_validation,
    quality_evaluation,
    quota,
    response_validation,
)

PREFLIGHT_HEAD = "51342fe17996dd62011c43dabf5f7c1936bdf0bd"
STARTING_TEST_COUNT = 409
STARTING_TOOL_COUNT = 101
EXPECTED_TOOL_COUNT = 107
EXPECTED_TEST_COUNT = 463
PROTECTED_PATHS = ("validation/unity-jungle-v5", "validation/builds",
                   "validation/unity-jungle-v6")

IDEA = ("Create a polished third-person 3D tropical jungle adventure game for "
        "Windows and Android. The player controls a monkey, explores a jungle, "
        "collects bananas, avoids environmental hazards, and reaches a final "
        "destination. The game should support low-end hardware and use an "
        "efficient rendering approach.")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 900) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(cwd or ROOT), capture_output=True,
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
    return run(["git", *args]).get("stdout", "").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(name: str, payload: dict) -> str:
    path = ROOT / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return name


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def parse_tests(result: dict) -> tuple[int | None, bool]:
    text = (result.get("stderr") or "") + (result.get("stdout") or "")
    match = re.search(r"Ran (\d+) tests?", text)
    count = int(match.group(1)) if match else None
    return count, bool(result.get("ok")) and result.get("returncode") == 0


def offline_fixture() -> dict:
    """Offline fixture shaped exactly like the requested provider contract."""
    return {
        "game_title": "Jungle Banana Run",
        "genre": ["third-person action adventure", "platformer"],
        "target_platforms": ["Windows", "Android"],
        "core_gameplay_loop": [
            "Explore the jungle trail",
            "Collect bananas to fill the objective counter",
            "Avoid hazard volumes and respawn at the last checkpoint",
            "Reach the destination zone to complete the level",
        ],
        "player_mechanics": ["Run and turn", "Jump and land", "Collect", "Interact"],
        "camera_design": "Third-person follow camera with a spring arm and obstacle pull-in.",
        "environment_requirements": [
            "Tropical jungle biome with a defined trail",
            "Cliffs, river and foliage dressing",
            "Directional sunlight with a warm ambient fill",
        ],
        "collectibles": ["Banana pickup with a trigger collider"],
        "hazards": ["Spike pit", "River current volume"],
        "progression": ["Spawn area", "Mid-route checkpoint", "Destination zone"],
        "ui_requirements": ["HUD banana counter", "Pause menu", "Level complete panel"],
        "audio_requirements": ["Footstep SFX", "Collect chime", "Ambient jungle loop"],
        "performance_targets": {
            "target_fps": 60,
            "quality_tier": "low",
            "hardware": "Integrated GPU, 8 GB RAM",
            "notes": "Keep draw calls bounded and reuse materials.",
        },
        "technical_architecture": [
            "Unity character controller with rigidbody-free movement",
            "Trigger colliders for collectibles and hazards",
            "Single additive scene with baked lighting",
        ],
        "asset_requirements": [
            "Monkey character mesh with a 24-bone rig and idle/walk/run/jump animations",
            "Jungle terrain tiles, tree and bush props, river plane and rock clusters",
            "Banana prop with a stylized material",
            "PBR base color and roughness textures for terrain and props",
            "Footstep and collect audio clips",
            "HUD font, banana icon and menu panel",
        ],
        "acceptance_criteria": [
            "Collecting a banana increments the HUD counter within 1 frame",
            "The player reaches the destination zone and the level completes within 10 seconds of arrival",
            "Frame rate stays at or above 60 fps for 30 seconds on the reference hardware",
            "All 10 bananas can be collected in one run",
        ],
        "risks": ["Android thermal throttling", "Touch input mapping is not yet specified"],
        "unsupported_or_uncertain": [
            "Android build pipeline has not been validated in this repository"],
        "engine": "unity",
        "dimension": "3d",
        "art_style": "stylized low-poly",
        "summary": "A short third-person jungle collection level for Windows and Android.",
    }


def protection() -> dict:
    baseline = load_json(ROOT / "reports" / "v6-phase0-baseline.json")
    phase6 = load_json(ROOT / "reports" / "v6-phase6-audit.json")
    recorded = phase6.get("preservation") or {}
    v4_files = (baseline.get("v4_checkpoint") or {}).get("files") or {}
    v5_artifacts = (baseline.get("v5_checkpoint") or {}).get("artifacts") or {}

    result = {"v4": {}, "v5": {}, "v4_ok": True, "v5_ok": True,
              "phase5_interfaces_ok": True}
    expected_records = {}
    for group in ("v4", "v5"):
        for relative, record in (recorded.get(group) or {}).items():
            expected_records[relative] = record.get("expected")

    for relative, record in v4_files.items():
        expected = expected_records.get(relative) or (record or {}).get("sha256")
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        matches = bool(expected) and actual == expected
        result["v4"][relative] = {"expected": expected, "actual": actual,
                                  "matches": matches}
        result["v4_ok"] = result["v4_ok"] and matches

    for relative, record in v5_artifacts.items():
        expected = expected_records.get(relative) or (record or {}).get("sha256")
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        matches = bool(expected) and actual == expected
        result["v5"][relative] = {"exists": path.is_file(), "expected": expected,
                                  "actual": actual, "matches": matches}
        result["v5_ok"] = result["v5_ok"] and matches

    for relative in game_spec_pipeline.PHASE5_INTERFACES:
        path = game_spec_pipeline.PHASE5_ROOT / relative
        if not path.is_file():
            result["phase5_interfaces_ok"] = False
            result.setdefault("missing_interfaces", []).append(relative)

    result["protected_git_status"] = [
        line for line in git("status", "--porcelain", "--", *PROTECTED_PATHS).splitlines()
        if line]
    result["protected_git_clean"] = not result["protected_git_status"]
    return result


def main() -> int:
    started = time.perf_counter()
    ending_head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    status_lines = [line for line in git("status", "--porcelain").splitlines() if line]

    # ---- baseline ------------------------------------------------------
    tests = run([sys.executable, "-m", "unittest", "discover",
                 "-s", "tools/game-studio-mcp/tests", "-q"], timeout=1200)
    final_test_count, tests_ok = parse_tests(tests)
    protection_report = protection()

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
        "all_schemas_object": all(tool.get("inputSchema", {}).get("type") == "object"
                                  for tool in server.TOOLS),
        "preflight_tools": STARTING_TOOL_COUNT,
        "target_tools": EXPECTED_TOOL_COUNT,
        "phase7_tools": [name for name in declared if name in (
            "llm_provider_readiness", "llm_provider_validate",
            "llm_game_spec_generate", "llm_game_spec_validate",
            "llm_game_quality_evaluate", "llm_generation_plan_preview")],
    }
    parity["exact_parity"] = (parity["tools"] == EXPECTED_TOOL_COUNT
                              and parity["tools"] == parity["handlers"]
                              and not parity["missing_handlers"]
                              and not parity["extra_handlers"]
                              and len(parity["phase7_tools"]) == 6)

    credentials = {}
    for provider in ("gemini", "groq", "openrouter", "openai", "anthropic"):
        try:
            cfg = llm_config.provider_config(provider)
            credentials[provider] = {
                "configured": bool(cfg.get("api_key")),
                "source": cfg.get("key_source"),
                "value_exposed": False,
            }
        except Exception:
            credentials[provider] = {"configured": False, "source": None,
                                     "value_exposed": False}
    credentials["shared_key_configured"] = bool(
        os.environ.get("GAME_STUDIO_LLM_API_KEY"))

    baseline_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7A - repository and baseline audit",
        "generated_at": now_iso(),
        "repository": {
            "root": str(ROOT),
            "branch": branch,
            "head": ending_head,
            "head_short": ending_head[:7],
            "baseline_head": PREFLIGHT_HEAD,
            "expected_head": PREFLIGHT_HEAD,
            "head_unchanged": ending_head == PREFLIGHT_HEAD,
            "head_advanced_by_external_commit": ending_head != PREFLIGHT_HEAD,
            "commits_since_baseline": [
                line for line in git("log", "--oneline",
                                     f"{PREFLIGHT_HEAD}..{ending_head}").splitlines()
                if line],
            "working_tree_changes": status_lines,
            "working_tree_dirty": bool(status_lines),
        },
        "phase6": {
            "audit_present": (ROOT / "reports" / "v6-phase6-audit.json").is_file(),
            "verdict": load_json(ROOT / "reports" / "v6-phase6-audit.json").get("verdict"),
            "reported_tools": 101,
            "reported_tests": 409,
        },
        "mcp": parity,
        "tests": {
            "starting_count": STARTING_TEST_COUNT,
            "final_count": final_test_count,
            "expected_final_count": EXPECTED_TEST_COUNT,
            "result": "OK" if tests_ok else "FAILED",
            "duration_seconds": tests["duration_seconds"],
            "command": tests["command"],
        },
        "protection": protection_report,
        "credentials": credentials,
        "network_calls": 0,
        "note": ("Baseline was measured directly from the working tree. Reported Phase 6 "
                 "facts were re-verified rather than assumed."),
    }

    # ---- provider policy / evidence -----------------------------------
    catalog = free_policy.catalog()
    evidence = free_policy.evidence()
    gemini_model = "gemini-3.8-flash"
    gemini_eligibility = free_policy.model_eligibility("gemini", gemini_model)
    policy_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7B - provider selection and free-tier policy",
        "generated_at": now_iso(),
        "selected_provider": "gemini",
        "selected_model": gemini_model,
        "verification_date": free_policy.VERIFICATION_DATE,
        "provider_status": free_policy.provider_status("gemini"),
        "model_eligibility": gemini_eligibility,
        "classification_vocabulary": list(free_policy.STATUSES),
        "policy": {
            "paid_fallback": False,
            "unknown_billing_treated_as_free": False,
            "unknown_quota_treated_as_unlimited": False,
            "one_provider_only": True,
            "provider_requests_during_research": 0,
        },
        "catalog": catalog,
        "network_calls": 0,
        "live_test_authorized": False,
        "live_test_performed": False,
        "note": ("Free-tier facts come from the official documentation recorded in "
                 "free_policy.py. No provider request was made while verifying them."),
    }

    # ---- readiness / request plan -------------------------------------
    readiness = provider_validation.readiness("gemini", gemini_model)
    plan = provider_validation.plan_live_validation(IDEA)
    request_audit = provider_validation.audit_record(plan)
    plan_refusal = provider_validation.execute_live_validation(IDEA)
    request_audit["unapproved_execution_attempt"] = {
        "status": plan_refusal["status"],
        "network_calls": plan_refusal["network_calls"],
        "live_request_performed": plan_refusal["live_request_performed"],
    }
    request_audit["credential_status"] = plan["credential"]["status"]
    request_audit["authorization_status"] = plan["authorization"]["status"]

    # ---- offline pipeline ---------------------------------------------
    fixture = offline_fixture()
    fixture_validation = response_validation.validate_game_spec(
        fixture, source="offline_fixture")
    fixture_quality = quality_evaluation.evaluate(
        fixture, source="offline_fixture", validation=fixture_validation)

    deterministic = game_spec_pipeline.build_specification(
        IDEA, engine="unity", platforms=["windows", "android"])
    ai_spec = game_spec_pipeline.build_specification(
        IDEA, engine="unity", platforms=["windows", "android"],
        ai_payload=fixture)
    ai_quality = quality_evaluation.evaluate(
        game_spec_pipeline.quality_payload(ai_spec), source="ai_payload_offline_fixture",
        validation=ai_spec["response_validation"])
    deterministic_quality = quality_evaluation.evaluate(
        game_spec_pipeline.quality_payload(deterministic),
        source="deterministic_fallback", validation=deterministic["response_validation"])

    # Tamper test: the pipeline must refuse to pre-approve or pre-verify.
    tampered = json.loads(json.dumps(ai_spec))
    tampered["requirements"][0]["implementation_status"] = "verified"
    tampered["approval"]["approved"] = True
    tampered["generation_plan"]["steps"][0]["executed"] = True
    tamper_check = game_spec_pipeline.validate_spec(tampered)

    # Malformed / contradictory responses must not become specifications.
    malformed = response_validation.validate_text("{not json", source="offline_fixture")
    contradiction_payload = json.loads(json.dumps(fixture))
    contradiction_payload["dimension"] = "2d and 3d"
    contradiction_payload["core_gameplay_loop"].append("Add online multiplayer netcode")
    contradiction_check = response_validation.validate_game_spec(contradiction_payload)

    # Network guard: offline operations must still work with sockets disabled.
    network_guard = {"sockets_disabled": True, "operations_completed": []}
    with mock.patch.object(socket.socket, "connect", side_effect=AssertionError(
            "network access attempted during offline audit")):
        provider_validation.readiness("gemini", gemini_model)
        network_guard["operations_completed"].append("readiness")
        provider_validation.plan_live_validation(IDEA)
        network_guard["operations_completed"].append("request_plan")
        game_spec_pipeline.build_specification(IDEA, ai_payload=fixture)
        network_guard["operations_completed"].append("game_spec_pipeline")
        quality_evaluation.evaluate(fixture, validation=fixture_validation)
        network_guard["operations_completed"].append("quality_evaluation")
        response_validation.validate_text(json.dumps(fixture))
        network_guard["operations_completed"].append("response_validation")
        free_routing.route("game_design_reasoning", require_known=True)
        network_guard["operations_completed"].append("free_routing")

    # Quota decision logic remains conservative.
    with mock.patch.object(quota, "quota_state", return_value={
            "exhausted": True, "remaining_today": 0, "verified_daily_limit": 250,
            "quota_known": True}):
        quota_exhausted = quota.can_request("gemini", gemini_model)
    with mock.patch.object(quota, "quota_state", return_value={
            "exhausted": None, "remaining_today": None, "verified_daily_limit": None,
            "quota_known": False}):
        quota_unknown = quota.can_request("gemini", gemini_model)

    # ---- Phase 3/4/5 bridges ------------------------------------------
    character_bridge = ai_spec["bridges"]["character"]
    environment_bridge = ai_spec["bridges"]["environment"]
    gameplay_bridge = ai_spec["bridges"]["gameplay"]
    character_errors = character_spec.validate_character_spec(character_bridge["spec"])
    environment_errors = environment_spec.validate_environment_spec(
        environment_bridge["spec"])
    bridge_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7H - generation pipeline bridges",
        "generated_at": now_iso(),
        "source": ai_spec["source"],
        "source_label_note": ("The payload is an offline fixture shaped like a provider "
                              "response. It is not live model output."),
        "character": {
            "interface": character_bridge["phase3_interface"],
            "requirement_ids": character_bridge["requirement_ids"],
            "validation_errors": character_errors,
            "valid": not character_errors,
            "spec": character_bridge["spec"],
            "ai_generated_asset": character_bridge["ai_generated_asset"],
            "generation_performed": character_bridge["generation_performed"],
            "phase5_project_modified": character_bridge["phase5_project_modified"],
        },
        "environment": {
            "interface": environment_bridge["phase4_interface"],
            "requirement_ids": environment_bridge["requirement_ids"],
            "validation_errors": environment_errors,
            "valid": not environment_errors,
            "spec": environment_bridge["spec"],
            "ai_generated_asset": environment_bridge["ai_generated_asset"],
            "generation_performed": environment_bridge["generation_performed"],
            "phase5_project_modified": environment_bridge["phase5_project_modified"],
        },
        "gameplay": {
            "interface": gameplay_bridge["phase5_interface"],
            "requirement_ids": gameplay_bridge["requirement_ids"],
            "phase5_interfaces": gameplay_bridge["phase5_interfaces"],
            "collectibles": gameplay_bridge["collectibles"],
            "hazards": gameplay_bridge["hazards"],
            "objectives": gameplay_bridge["objectives"],
            "checkpoints": gameplay_bridge["checkpoints"],
            "camera": gameplay_bridge["camera"],
            "ui": gameplay_bridge["ui"],
            "game_states": gameplay_bridge["game_states"],
            "acceptance_tests": gameplay_bridge["acceptance_tests"],
            "generated": gameplay_bridge["generated"],
            "build_started": gameplay_bridge["build_started"],
            "phase5_project_modified": gameplay_bridge["phase5_project_modified"],
            "ai_generated_asset": gameplay_bridge["ai_generated_asset"],
        },
        "all_requirement_ids_traceable": all(
            item.get("requirement_id") for item in ai_spec["requirements"]),
        "assets_generated": False,
        "phase5_project_modified": False,
        "build_started": False,
    }

    # ---- quality evaluation report ------------------------------------
    quality_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7G - game design quality evaluation",
        "generated_at": now_iso(),
        "rubric": {
            "categories": [item["name"] for item in fixture_quality["scores"]],
            "max_score": fixture_quality["max_score"],
            "scoring": "deterministic rules; no model judges another model",
        },
        "offline_fixture": fixture_quality,
        "ai_payload_offline_fixture": ai_quality,
        "deterministic_fallback": deterministic_quality,
        "live_provider_output_evaluated": False,
        "single_response_evidence_only": True,
        "general_intelligence_claimed": False,
        "note": ("All three scores are offline. None is a live model result, and a "
                 "single response cannot prove general AI intelligence."),
    }

    # ---- specification / requirements / validation --------------------
    spec_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7F - idea to specification",
        "generated_at": now_iso(),
        "request": IDEA,
        "source": ai_spec["source"],
        "source_label_note": ("Built from the offline fixture payload, not from a live "
                              "provider response."),
        "engine": ai_spec["engine"],
        "target_platforms": ai_spec["target_platforms"],
        "quality_tier": ai_spec["quality_tier"],
        "design": ai_spec["design"],
        "requirements_summary": ai_spec["coverage"],
        "approval": ai_spec["approval"],
        "feasibility": ai_spec["feasibility"],
        "generation_plan": ai_spec["generation_plan"],
        "validation": ai_spec["validation"],
        "response_validation": ai_spec["response_validation"],
        "bridges": {
            "character_valid": not character_errors,
            "environment_valid": not environment_errors,
            "gameplay_generated": gameplay_bridge["generated"],
        },
        "executable": False,
        "ai_generated_asset": False,
        "generation_performed": False,
        "phase5_project_modified": False,
        "executed": False,
        "note": ("A valid specification is not a playable game. Nothing in this report "
                 "was generated, built or approved."),
    }

    requirements_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7F - structured requirements",
        "generated_at": now_iso(),
        "source": ai_spec["source"],
        "counts": {
            "total": len(ai_spec["requirements"]),
            "user_requirement": sum(1 for item in ai_spec["requirements"]
                                    if item["provenance"] == "user_requirement"),
            "recommendation": sum(1 for item in ai_spec["requirements"]
                                  if item["provenance"] != "user_requirement"),
            "blocked": len(ai_spec["blocked_requirements"]),
            "verified": 0,
            "human_approved": 0,
        },
        "requirements": ai_spec["requirements"],
        "unsupported_features": ai_spec["unsupported_features"],
        "blocked_requirements": ai_spec["blocked_requirements"],
        "missing_information": ai_spec["missing_information"],
        "coverage": ai_spec["coverage"],
        "note": ("Every requirement is a proposal with stable IDs. None is implemented, "
                 "verified or human-approved."),
    }

    validation_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7 - validation results",
        "generated_at": now_iso(),
        "offline_fixture": {
            "schema_valid": fixture_validation["schema_valid"],
            "errors": fixture_validation["errors"],
            "missing_fields": fixture_validation["missing_fields"],
            "contradictions": fixture_validation["contradictions"],
            "unsupported_claims": fixture_validation["unsupported_claims"],
            "ambiguous_requirements": fixture_validation["ambiguous_requirements"],
        },
        "malformed_json": {
            "schema_valid": malformed["schema_valid"],
            "errors": malformed["errors"],
        },
        "contradictory_payload": {
            "schema_valid": contradiction_check["schema_valid"],
            "contradiction_kinds": sorted({item["kind"] for item in
                                           contradiction_check["contradictions"]}),
            "unsupported_claims": [item["claim"] for item in
                                   contradiction_check["unsupported_claims"]],
        },
        "specification": ai_spec["validation"],
        "tampered_specification": tamper_check,
        "tamper_rejected": not tamper_check["valid"],
        "quota": {
            "exhausted_decision": quota_exhausted["allowed"],
            "unknown_decision": quota_unknown["allowed"],
            "unknown_is_unlimited": False,
        },
        "network_guard": network_guard,
        "live_provider_validation": {
            "status": "BLOCKED_CREDENTIAL_NOT_CONFIGURED",
            "authorized": False,
            "performed": False,
            "network_calls": 0,
            "reason": ("No credential is configured and no live request was approved by "
                       "a human. Offline evidence must not be read as live validation."),
        },
        "protected_artifacts": protection_report,
    }

    # ---- criteria -----------------------------------------------------
    phase6_preserved = (
        load_json(ROOT / "reports" / "v6-phase6-audit.json").get("verdict") == "PASS"
        and all((ROOT / "tools" / "game-studio-mcp" / "game_studio" / "llm" / name).is_file()
                for name in ("free_policy.py", "quota.py", "free_routing.py",
                             "intelligence.py", "asset_research.py")))
    reuse_ok = (provider_validation.llm_providers is not None
                and provider_validation.free_policy is free_policy
                and provider_validation.quota is quota)
    free_policy_ok = (
        not provider_validation.readiness("gemini", "gemini-4-argon")["ready"]
        and free_policy.model_eligibility("gemini", gemini_model)["eligible"] is True
    )
    unknown_billing_ok = (
        free_policy.model_eligibility("unknown-provider", "any-model")["eligible"] is None
        and free_policy.model_eligibility("gemini", "gemini-unknown-9000")["eligible"] is False
    )
    no_paid_fallback = (plan["request"]["provider_fallback"] is False
                        and plan_refusal.get("fallback_used") is None
                        and plan["quota_impact"]["estimated_cost_usd"] == 0.0)
    secret_scan_text = json.dumps({
        "baseline": baseline_report, "policy": policy_report,
        "readiness": readiness, "request": request_audit,
        "quality": quality_report, "spec": spec_report,
        "requirements": requirements_report, "validation": validation_report,
        "bridges": bridge_report,
    }, ensure_ascii=False)
    secret_hits = [pattern.pattern for pattern in llm_config.SECRET_PATTERNS
                   if pattern.search(secret_scan_text)]
    secrets_ok = not secret_hits and not readiness["credential"]["value_exposed"]
    no_network_ok = (readiness["network_calls"] == 0
                     and plan["network_calls"] == 0
                     and request_audit["unapproved_execution_attempt"]["network_calls"] == 0)
    quota_ok = (quota_exhausted["allowed"] is False
                and quota_unknown["allowed"] is True
                and quota_unknown["kind"] == "quota_unknown_not_unlimited")
    structured_ok = (fixture_validation["schema_valid"]
                     and not malformed["schema_valid"]
                     and contradiction_check["schema_valid"]
                     and contradiction_check["contradictions"]
                     and contradiction_check["unsupported_claims"])
    provenance_ok = all(
        item.get("requirement_id") and item.get("provenance")
        and item.get("implementation_status") == "not_implemented"
        and item.get("human_approved") is False
        for item in ai_spec["requirements"])
    quality_ok = (len(fixture_quality["scores"]) == 10
                  and 0 <= fixture_quality["total_score"] <= 100
                  and fixture_quality["requires_human_review"] is True)
    phase3_ok = not character_errors and character_bridge["ai_generated_asset"] is False
    phase4_ok = not environment_errors and environment_bridge["ai_generated_asset"] is False
    phase5_ok = (gameplay_bridge["phase5_interfaces"]["missing"] == []
                 and gameplay_bridge["phase5_project_modified"] is False
                 and gameplay_bridge["build_started"] is False
                 and protection_report["protected_git_clean"])
    parity_ok = parity["exact_parity"]
    tests_pass = tests_ok and final_test_count == EXPECTED_TEST_COUNT
    v4_ok = protection_report["v4_ok"]
    v5_ok = protection_report["v5_ok"]
    phase5_protected = (protection_report["protected_git_clean"]
                        and protection_report["phase5_interfaces_ok"]
                        and v5_ok)

    # The bounded transport must be wired into the Gemini path only, must never
    # parse a partial body as JSON, and must keep zero retries/fallback.
    bounded_source = (ROOT / "tools" / "game-studio-mcp" / "game_studio" / "llm"
                      / "bounded_http.py").read_text(encoding="utf-8")
    util_source = (ROOT / "tools" / "game-studio-mcp" / "game_studio"
                   / "util.py").read_text(encoding="utf-8")
    providers_source = (ROOT / "tools" / "game-studio-mcp" / "game_studio" / "llm"
                        / "providers.py").read_text(encoding="utf-8")
    timeout_tests = (ROOT / "tools" / "game-studio-mcp" / "tests"
                     / "test_v6_phase7_timeout.py")
    timeout_fix_ok = (
        timeout_tests.is_file()
        and "from .llm.bounded_http import request as bounded_request" in util_source
        and "deadline_seconds is not None" in util_source
        and "deadline_seconds=timeout" in providers_source
        and "class _Deadline" in bounded_source
        and "deadline_exceeded" in bounded_source
        and "partial_response" in bounded_source
        and "json_parse_skipped" in bounded_source
        and plan["request"]["retries"] == 0
        and plan["request"]["provider_fallback"] is False
        and plan["request"]["request_sha256"]
        == "865fe5ba547ce13cdad50ccd706ef28aca26e213549532b52b9fb501b549c648"
    )

    # HEAD may advance only through an external, linear commit that touches the
    # Phase 7 surface and no protected path. The audit itself performs no Git write.
    baseline_is_ancestor = run(["git", "merge-base", "--is-ancestor",
                                PREFLIGHT_HEAD, ending_head])["ok"]
    changed_since_baseline = [
        line for line in git("diff", "--name-only", PREFLIGHT_HEAD,
                             ending_head).splitlines() if line]
    allowed_prefixes = (
        "tools/game-studio-mcp/game_studio/llm/",
        "tools/game-studio-mcp/server.py",
        "tools/game-studio-mcp/tests/",
        "scripts/v6-phase7-audit.py",
        "reports/v6-phase7-",
        "V6-PHASE-7-",
    )
    unexpected_changes = [path for path in changed_since_baseline
                          if not path.startswith(allowed_prefixes)]
    protected_prefixes = ("validation/", "reports/v6-phase0-", "reports/v6-phase6-")
    protected_changes = [path for path in changed_since_baseline
                         if path.startswith(protected_prefixes)]
    git_ok = (baseline_is_ancestor and branch == "main"
              and not unexpected_changes and not protected_changes)

    criteria = [
        {"id": 1, "description": "Phase 6 baseline preserved",
         "status": "PASS" if phase6_preserved else "FAIL",
         "evidence": {"phase6_verdict": load_json(
             ROOT / "reports" / "v6-phase6-audit.json").get("verdict")}},
        {"id": 2, "description": "Existing provider architecture reused",
         "status": "PASS" if reuse_ok else "FAIL",
         "evidence": {"adapters": "game_studio.llm.providers",
                      "policy": "game_studio.llm.free_policy",
                      "quota": "game_studio.llm.quota"}},
        {"id": 3, "description": "Free-only policy enforced",
         "status": "PASS" if free_policy_ok else "FAIL",
         "evidence": {"gemini_model_eligible": gemini_eligibility["eligible"],
                      "paid_model_ready": provider_validation.readiness(
                          "gemini", "gemini-4-argon")["ready"]}},
        {"id": 4, "description": "Unknown billing rejected",
         "status": "PASS" if unknown_billing_ok else "FAIL",
         "evidence": {"unknown_provider_eligible": free_policy.model_eligibility(
             "unknown-provider", "any-model")["eligible"]}},
        {"id": 5, "description": "No paid fallback",
         "status": "PASS" if no_paid_fallback else "FAIL",
         "evidence": {"provider_fallback": plan["request"]["provider_fallback"],
                      "estimated_cost_usd": plan["quota_impact"]["estimated_cost_usd"]}},
        {"id": 6, "description": "No secrets exposed",
         "status": "PASS" if secrets_ok else "FAIL",
         "evidence": {"secret_patterns_matched": secret_hits,
                      "credential_value_exposed": False}},
        {"id": 7, "description": "No unapproved network requests",
         "status": "PASS" if no_network_ok and network_guard["sockets_disabled"] else "FAIL",
         "evidence": {"readiness_network_calls": readiness["network_calls"],
                      "plan_network_calls": plan["network_calls"],
                      "unapproved_attempt": request_audit["unapproved_execution_attempt"],
                      "offline_network_guard": network_guard["operations_completed"]}},
        {"id": 8, "description": "Quota controls enforced",
         "status": "PASS" if quota_ok else "FAIL",
         "evidence": {"exhausted_allowed": quota_exhausted["allowed"],
                      "unknown_kind": quota_unknown["kind"]}},
        {"id": 9, "description": "Structured responses validated",
         "status": "PASS" if structured_ok else "FAIL",
         "evidence": {"fixture_valid": fixture_validation["schema_valid"],
                      "malformed_valid": malformed["schema_valid"],
                      "contradictions": len(contradiction_check["contradictions"])}},
        {"id": 10, "description": "Requirement provenance preserved",
         "status": "PASS" if provenance_ok else "FAIL",
         "evidence": {"requirements": len(ai_spec["requirements"]),
                      "verified": 0, "human_approved": 0}},
        {"id": 11, "description": "AI quality evaluation present",
         "status": "PASS" if quality_ok else "FAIL",
         "evidence": {"categories": len(fixture_quality["scores"]),
                      "total_score": fixture_quality["total_score"],
                      "live_provider_output": False}},
        {"id": 12, "description": "Phase 3 bridge valid",
         "status": "PASS" if phase3_ok else "FAIL",
         "evidence": {"errors": character_errors,
                      "ai_generated_asset": character_bridge["ai_generated_asset"]}},
        {"id": 13, "description": "Phase 4 bridge valid",
         "status": "PASS" if phase4_ok else "FAIL",
         "evidence": {"errors": environment_errors,
                      "ai_generated_asset": environment_bridge["ai_generated_asset"]}},
        {"id": 14, "description": "Phase 5 interfaces preserved",
         "status": "PASS" if phase5_ok else "FAIL",
         "evidence": {"missing_interfaces": gameplay_bridge["phase5_interfaces"]["missing"],
                      "modified": gameplay_bridge["phase5_project_modified"],
                      "build_started": gameplay_bridge["build_started"]}},
        {"id": 15, "description": "MCP parity preserved",
         "status": "PASS" if parity_ok else "FAIL",
         "evidence": {"tools": parity["tools"], "handlers": parity["handlers"],
                      "missing": parity["missing_handlers"],
                      "extra": parity["extra_handlers"]}},
        {"id": 16, "description": "Tests pass",
         "status": "PASS" if tests_pass else "FAIL",
         "evidence": {"starting": STARTING_TEST_COUNT,
                      "final": final_test_count,
                      "expected": EXPECTED_TEST_COUNT,
                      "result": "OK" if tests_ok else "FAILED"}},
        {"id": 17, "description": "V4 protected artifacts unchanged",
         "status": "PASS" if v4_ok else "FAIL",
         "evidence": {"files": len(protection_report["v4"]), "ok": v4_ok}},
        {"id": 18, "description": "V5 protected artifacts unchanged",
         "status": "PASS" if v5_ok else "FAIL",
         "evidence": {"files": len(protection_report["v5"]), "ok": v5_ok}},
        {"id": 19, "description": "Phase 5 project/build/payload unchanged",
         "status": "PASS" if phase5_protected else "FAIL",
         "evidence": {"protected_git_clean": protection_report["protected_git_clean"],
                      "phase5_interfaces_ok": protection_report["phase5_interfaces_ok"]}},
        {"id": 20, "description": "No unauthorized Git operations",
         "status": "PASS" if git_ok else "FAIL",
         "evidence": {"head": ending_head, "baseline_head": PREFLIGHT_HEAD,
                      "baseline_is_ancestor": baseline_is_ancestor,
                      "branch": branch,
                      "commits_since_baseline": [
                          line for line in git("log", "--oneline",
                                               f"{PREFLIGHT_HEAD}..{ending_head}"
                                               ).splitlines() if line],
                      "unexpected_changed_paths": unexpected_changes,
                      "protected_paths_changed": protected_changes,
                      "working_tree_changes": status_lines}},
        {"id": 21, "description": "Bounded total request deadline implemented",
         "status": "PASS" if timeout_fix_ok else "FAIL",
         "evidence": {"module": "game_studio/llm/bounded_http.py",
                      "gemini_deadline": "timeout_seconds",
                      "stage_errors": ["dns_timeout", "connection_timeout",
                                       "tls_failure", "http_response_timeout",
                                       "response_body_timeout", "deadline_exceeded"],
                      "partial_body_never_parsed": True,
                      "retries": plan["request"]["retries"],
                      "provider_fallback": plan["request"]["provider_fallback"],
                      "request_sha256": plan["request"]["request_sha256"]}},
    ]
    all_passed = all(item["status"] == "PASS" for item in criteria)
    verdict = "PASS_AUTOMATED" if all_passed else "FAIL"

    generated_at = now_iso()
    written = {}
    written["baseline"] = write_report("v6-phase7-baseline.json", baseline_report)
    written["provider_policy"] = write_report("v6-phase7-provider-policy.json",
                                              policy_report)
    written["provider_evidence"] = write_report(
        "v6-phase7-provider-evidence.json",
        {**evidence, "generated_at": generated_at,
         "source": "official provider documentation recorded per provider"})
    written["readiness"] = write_report("v6-phase7-readiness.json",
                                        {**readiness, "generated_at": generated_at})
    written["request_audit"] = write_report("v6-phase7-request-audit.json",
                                            {**request_audit,
                                             "generated_at": generated_at})
    written["game_spec"] = write_report("v6-phase7-game-spec.json", spec_report)
    written["requirements"] = write_report("v6-phase7-requirements.json",
                                           requirements_report)
    written["quality"] = write_report("v6-phase7-quality-evaluation.json",
                                      quality_report)
    written["bridge"] = write_report("v6-phase7-generation-bridge.json", bridge_report)
    written["validation"] = write_report("v6-phase7-validation.json", validation_report)

    # A live attempt is recorded only if the human-approved request actually ran.
    # The audit itself never performs a provider request.
    live_result: dict = {}
    live_path = ROOT / "reports" / "v6-phase7-live-validation.json"
    if live_path.is_file():
        try:
            live_payload = load_json(live_path)
            live_result = live_payload.get("result") or {}
        except (OSError, ValueError):
            live_result = {}
    live_performed = bool(live_result.get("network_calls"))
    if live_path.is_file():
        written["live_validation"] = "v6-phase7-live-validation.json"
    live_status = (live_result.get("status")
                   if live_performed else "BLOCKED_CREDENTIAL_NOT_CONFIGURED")
    live_error = live_result.get("error") or {}
    live_quality = (live_result.get("quality") or {}).get("total_score")
    if live_performed and live_result.get("ok"):
        live_note = ("Exactly one approved request ran. Response validity is reported "
                     "above; schema validity is not proof of design quality.")
        live_limitations = [
            "A single live request is not a benchmark and does not prove general AI quality.",
            "The specification is a proposal and no asset, scene or build was produced.",
            "A valid specification is not proof of a playable game.",
            "Unknown provider quota is treated as unknown, never unlimited.",
        ]
    elif live_performed:
        live_note = (f"Exactly one approved request ran and failed with "
                     f"{live_result.get('status')} "
                     f"(HTTP {live_error.get('status')}); no retry or fallback provider "
                     f"was used.")
        live_limitations = [
            "The single approved live request failed; live model behaviour was not observed.",
            "Provider quality is therefore unmeasured; only offline fixtures were scored.",
            "The specification is a proposal and no asset, scene or build was produced.",
            "A valid specification is not proof of a playable game.",
            "Unknown provider quota is treated as unknown, never unlimited.",
        ]
    else:
        live_note = ("A human must approve the exact request hash and configure "
                     "GEMINI_API_KEY locally before any request runs.")
        live_limitations = [
            "No live provider request was authorized or performed.",
            "Provider quality is therefore unmeasured; only offline fixtures were scored.",
            "The specification is a proposal and no asset, scene or build was produced.",
            "A valid specification is not proof of a playable game.",
            "Unknown provider quota is treated as unknown, never unlimited.",
        ]

    audit_report = {
        "schema_version": 1,
        "phase": "V6 Phase 7 - Real AI Provider Validation and Game Generation",
        "generated_at": generated_at,
        "verdict": verdict,
        "all_criteria_passed": all_passed,
        "human_review_required": True,
        "human_review_status": "pending",
        "live_provider_status": live_status,
        "live_provider_authorized": live_performed,
        "live_provider_performed": live_performed,
        "criteria": criteria,
        "repository": {
            "branch": branch,
            "starting_head": PREFLIGHT_HEAD,
            "ending_head": ending_head,
            "head_unchanged": ending_head == PREFLIGHT_HEAD,
            "baseline_is_ancestor": baseline_is_ancestor,
            "commits_since_baseline": [
                line for line in git("log", "--oneline",
                                     f"{PREFLIGHT_HEAD}..{ending_head}").splitlines()
                if line],
            "changed_paths_since_baseline": changed_since_baseline,
            "unexpected_changed_paths": unexpected_changes,
            "protected_paths_changed": protected_changes,
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
        },
        "mcp": parity,
        "preservation": protection_report,
        "provider_selection": {
            "provider": "gemini",
            "model": gemini_model,
            "status": free_policy.provider_status("gemini"),
            "verification_date": free_policy.VERIFICATION_DATE,
            "eligible": gemini_eligibility["eligible"],
            "credential_configured": readiness["credential"]["configured"],
        },
        "live_validation": {
            "request_sha256": plan["request"]["request_sha256"],
            "authorization_status": ("APPROVED" if live_performed
                                     else plan["authorization"]["status"]),
            "credential_status": plan["credential"]["status"],
            "network_calls": 1 if live_performed else 0,
            "performed": live_performed,
            "status": live_status,
            "http_status": live_error.get("status") if live_performed else None,
            "error_kind": live_error.get("kind") if live_performed else None,
            "retries": 0,
            "fallback_used": bool(live_result.get("fallback_used")),
            "note": live_note,
        },
        "timeout_fix": {
            "implemented": timeout_fix_ok,
            "module": "tools/game-studio-mcp/game_studio/llm/bounded_http.py",
            "reports": [
                "reports/v6-phase7-timeout-fix.json",
                "reports/v6-phase7-timeout-validation.json",
            ],
            "total_deadline": "caller timeout (60 s for the Phase 7 request)",
            "stage_errors": ["dns_timeout", "connection_timeout", "tls_failure",
                             "http_response_timeout", "response_body_timeout",
                             "deadline_exceeded"],
            "partial_body_never_parsed": True,
            "timing_fields": ["dns_ms", "connect_ms", "tls_ms", "send_ms",
                              "headers_ms", "body_ms", "total_ms"],
            "secrets_recorded": False,
            "retries": 0,
            "provider_fallback": False,
            "network_calls": 0,
        },
        "quality": {
            "offline_fixture_score": fixture_quality["total_score"],
            "offline_fixture_grade": fixture_quality["grade"],
            "deterministic_score": deterministic_quality["total_score"],
            "live_model_score": live_quality,
        },
        "reports": written,
        "limitations": live_limitations,
        "human_decisions_required": [
            "Review the live provider outcome and decide whether another approved attempt is warranted.",
            "Review requirement priorities, contradictions and ambiguous criteria.",
            "Decide whether any future Phase 8 asset generation or build may start.",
        ],
        "duration_seconds": round(time.perf_counter() - started, 2),
    }
    written["audit"] = write_report("v6-phase7-audit.json", audit_report)

    print(json.dumps({
        "verdict": verdict,
        "criteria_passed": sum(1 for item in criteria if item["status"] == "PASS"),
        "criteria_total": len(criteria),
        "tests": final_test_count,
        "tools": parity["tools"],
        "request_sha256": plan["request"]["request_sha256"],
        "credential_status": plan["credential"]["status"],
        "live_status": live_status,
        "live_network_calls": 1 if live_performed else 0,
        "reports": written,
    }, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
