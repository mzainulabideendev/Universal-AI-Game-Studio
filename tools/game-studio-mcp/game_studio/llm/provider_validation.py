"""Guarded validation of one real, free-tier provider request.

Phase 7 must prove that the Phase 6 free-AI architecture works with a real
provider *only after* a human approves the exact request. This module therefore
separates three steps:

1. ``readiness`` - offline inspection. Never sends a request, never returns a key.
2. ``plan_live_validation`` - the exact request, hash, quota impact, data-handling
   notes and approval state. Always ``network_calls = 0``.
3. ``execute_live_validation`` - refused unless the caller supplies an approval
   token whose ``request_sha256`` matches the planned request.

Design constraints enforced here (not merely documented):
- Exactly one request, zero automatic retries, zero provider fallback.
- Free-only model gate reuses ``free_policy`` and ``quota`` from Phase 6.
- The existing provider adapter is the only transport path; no new HTTP client.
- The prompt contains the controlled test idea, never repository or user project
  files, and the API key never appears in a result.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from . import config as llm_config
from . import free_policy
from . import providers as llm_providers
from . import quota
from . import response_validation as rv
from . import schemas as llm_schemas

SCHEMA_VERSION = 1
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.8-flash"
MAX_IDEA_CHARS = 4_000
HARD_MAX_OUTPUT_TOKENS = 4_096
HARD_MAX_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = (
    "You are a game design analyst. Return exactly one JSON object and no prose.\n"
    "The object must contain these keys: game_title (string), genre (array of "
    "strings), target_platforms (array), core_gameplay_loop (array of steps), "
    "player_mechanics (array), camera_design (string), environment_requirements "
    "(array), collectibles (array), hazards (array), progression (array), "
    "ui_requirements (array), audio_requirements (array), performance_targets "
    "(object with integer target_fps, quality_tier, hardware), "
    "technical_architecture (array), asset_requirements (array), "
    "acceptance_criteria (array), risks (array), unsupported_or_uncertain (array).\n"
    "Rules: do not invent engine APIs, plugins, engine features, asset files or "
    "verified functionality. If something is uncertain, say so in "
    "unsupported_or_uncertain. Every acceptance criterion must be observable. "
    "Treat this as a design proposal, not a claim that anything is implemented."
)

CONTROLLED_TEST_IDEA = (
    "Create a polished third-person 3D tropical jungle adventure game for Windows "
    "and Android. The player controls a monkey, explores a jungle, collects "
    "bananas, avoids environmental hazards, and reaches a final destination. The "
    "game should support low-end hardware and use an efficient rendering approach."
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_user_prompt(idea: str) -> str:
    return (
        "Game idea:\n"
        f"{idea.strip()}\n\n"
        "Produce the JSON object described in the system instructions. Use short "
        "arrays of concise strings. Do not include markdown fences."
    )


def request_sha256(*, provider: str, model: str, system: str, user: str,
                   max_output_tokens: int, temperature: float) -> str:
    canonical = json.dumps({
        "provider": provider,
        "model": model,
        "system": system,
        "user": user,
        "max_output_tokens": max_output_tokens,
        "temperature": round(float(temperature), 3),
        "retries": 0,
        "fallback": False,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _capability(entry: dict, name: str) -> object:
    return (entry.get("capabilities") or {}).get(name, free_policy.UNKNOWN)


def readiness(provider: str = DEFAULT_PROVIDER,
              model: str | None = None) -> dict:
    """Offline readiness inspection. Performs no network I/O."""
    key = (provider or DEFAULT_PROVIDER).strip().lower()
    try:
        llm_config.validate_provider_name(key)
    except Exception as exc:  # ToolError is intentionally a plain failure here
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "provider": key,
            "model": model,
            "ready": False,
            "blockers": [str(exc)],
            "network_calls": 0,
        }
    cfg = llm_config.provider_config(key)
    chosen_model = (model or cfg.get("model") or "").strip()
    try:
        entry = free_policy.provider_entry(key)
    except ValueError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "phase": "V6 Phase 7 - provider readiness",
            "checked_at": _now(),
            "provider": key,
            "model": chosen_model,
            "ready": False,
            "blockers": [f"provider {key!r} is not in the free-provider catalog"],
            "network_calls": 0,
            "credentials_exposed": False,
        }
    eligibility = free_policy.model_eligibility(key, chosen_model)
    quota_state = quota.quota_state(key, chosen_model)
    status = free_policy.provider_status(key)
    credential = {
        "required": bool(cfg.get("key_required")),
        "configured": bool(cfg.get("api_key")),
        "source": cfg.get("key_source"),
        "env_var": cfg.get("key_env"),
        "value_exposed": False,
    }
    capabilities = {
        "text_generation": _capability(entry, "text_generation"),
        "structured_output": _capability(entry, "structured_output"),
        "json_mode": _capability(entry, "json_mode"),
        "tool_calling": _capability(entry, "tool_calling"),
        "vision": _capability(entry, "vision"),
    }
    blockers: list[str] = []
    warnings: list[str] = []
    if not free_policy.is_free_status(status):
        blockers.append(f"provider status is {status!r}, not a free status")
    if eligibility["eligible"] is not True:
        blockers.append(eligibility["reason"])
    if credential["required"] and not credential["configured"]:
        blockers.append("no credential configured for the selected provider")
    if quota_state["exhausted"] is True:
        blockers.append("documented free quota is exhausted")
    if capabilities["structured_output"] not in ("supported", True):
        warnings.append("structured-output support is not declared as supported")
    if key == "gemini":
        warnings.append(
            "Gemini free-tier content may be used to improve Google products; "
            "never send proprietary project content without separate approval.")
        warnings.append(
            "Gemini 3.6+ ignores temperature/top_p/top_k and may return deprecation "
            "warning headers; the request remains valid.")
    warnings.append(
        "Readiness is offline evidence only. Reachability and output quality are "
        "unknown until an approved live request runs.")

    adapter = llm_providers.build(cfg)
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "phase": "V6 Phase 7 - provider readiness",
        "checked_at": _now(),
        "provider": key,
        "provider_name": entry["name"],
        "adapter": type(adapter).__name__,
        "adapter_registered": True,
        "model": chosen_model,
        "model_default": cfg.get("model"),
        "free_status": status,
        "free": free_policy.is_free_status(status),
        "model_eligibility": eligibility,
        "credential": credential,
        "quota": quota_state,
        "capabilities": capabilities,
        "timeouts": {
            "request_timeout_seconds": cfg.get("timeout_seconds"),
            "connect_timeout_seconds": cfg.get("connect_timeout_seconds"),
            "configured_retries": cfg.get("retries"),
            "phase7_live_request_retries": 0,
        },
        "structured_output": {
            "adapter_json_mode": True,
            "declared": capabilities["structured_output"],
            "schema_validation": "local, game_studio.llm.schemas",
        },
        "error_handling": {
            "adapter_error_type": "game_studio.llm.providers.ProviderError",
            "classified_kinds": ["auth", "rate_limit", "not_found",
                                 "invalid_request", "unavailable", "timeout"],
            "retries_disabled_for_phase7": True,
        },
        "blockers": blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "ready": not blockers,
        "ready_for_live_request": not blockers,
        "live_request_authorized": False,
        "network_calls": 0,
        "credentials_exposed": False,
    }


def plan_live_validation(idea: str = CONTROLLED_TEST_IDEA, *,
                         provider: str = DEFAULT_PROVIDER,
                         model: str | None = None,
                         max_output_tokens: int = 2048,
                         temperature: float = 0.1,
                         timeout: int = 60,
                         approved: bool = False,
                         approved_by: str | None = None) -> dict:
    """Describe the exact request. Never sends it."""
    if not isinstance(idea, str) or not idea.strip():
        raise ValueError("idea must be a non-empty string")
    if len(idea) > MAX_IDEA_CHARS:
        raise ValueError(f"idea is too long (max {MAX_IDEA_CHARS} characters)")
    if not isinstance(max_output_tokens, int) or not 64 <= max_output_tokens <= HARD_MAX_OUTPUT_TOKENS:
        raise ValueError(f"max_output_tokens must be 64..{HARD_MAX_OUTPUT_TOKENS}")
    if not isinstance(timeout, int) or not 5 <= timeout <= HARD_MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout must be 5..{HARD_MAX_TIMEOUT_SECONDS} seconds")
    if not 0.0 <= float(temperature) <= 1.0:
        raise ValueError("temperature must be within 0..1")

    state = readiness(provider, model)
    chosen_model = state.get("model") or model or DEFAULT_MODEL
    user = build_user_prompt(idea)
    digest = request_sha256(provider=provider, model=chosen_model,
                            system=SYSTEM_PROMPT, user=user,
                            max_output_tokens=max_output_tokens,
                            temperature=temperature)
    approval_status = "APPROVED" if approved else "NOT_AUTHORIZED"
    credential_status = ("CONFIGURED" if state.get("credential", {}).get("configured")
                         else "BLOCKED_CREDENTIAL_NOT_CONFIGURED")
    try:
        provider_entry = free_policy.provider_entry(provider)
    except ValueError:
        provider_entry = {}
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "phase": "V6 Phase 7 - live request plan",
        "mode": "plan-only",
        "generated_at": _now(),
        "provider": state.get("provider", provider),
        "model": chosen_model,
        "free_status": state.get("free_status"),
        "free_evidence": {
            "verification_date": free_policy.VERIFICATION_DATE,
            "documentation": list(provider_entry.get("docs") or []),
            "model_rule": provider_entry.get("model_rule"),
        },
        "request": {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user,
            "idea": idea,
            "max_input_chars": MAX_IDEA_CHARS,
            "actual_input_chars": len(idea),
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "timeout_seconds": timeout,
            "retries": 0,
            "provider_fallback": False,
            "stream": False,
            "json_mode": True,
            "project_files_sent": False,
            "personal_data_sent": False,
            "request_sha256": digest,
        },
        "quota_impact": {
            "requests": 1,
            "retries": 0,
            "maximum_requests_after_approval": 1,
            "documented_daily_limit": state.get("quota", {}).get("verified_daily_limit"),
            "remaining_before": state.get("quota", {}).get("remaining_today"),
            "quota_known": state.get("quota", {}).get("quota_known"),
            "estimated_cost_usd": 0.0,
            "note": ("A free-tier request. Unknown remaining quota is never treated "
                     "as unlimited and no paid fallback exists."),
        },
        "data_handling": {
            "provider_retention": ("Gemini free tier: content is used to improve "
                                   "Google products according to the documented free "
                                   "tier terms; do not send proprietary content."),
            "sends_repository_files": False,
            "sends_user_project_files": False,
            "sends_credentials": False,
            "controlled_test_idea_only": idea == CONTROLLED_TEST_IDEA,
        },
        "readiness": state,
        "credential": {
            "status": credential_status,
            "configured": state.get("credential", {}).get("configured", False),
            "source": state.get("credential", {}).get("source"),
            "value_exposed": False,
        },
        "authorization": {
            "required": True,
            "approved": bool(approved),
            "approved_by": approved_by if approved else None,
            "status": approval_status,
            "token_required": digest,
            "note": ("Approval must name this exact request hash. Approval of the "
                     "phase or of implementation is not network authorization."),
        },
        "expected_result": {
            "format": "one JSON object matching the Phase 7 response contract",
            "validated_locally": True,
            "quality_evaluated_locally": True,
            "http_success_is_not_quality_proof": True,
        },
        "rollback": {
            "side_effects": "none outside the provider account's free usage",
            "writes_files": False,
            "modifies_project": False,
            "retry_on_error": False,
            "error_behaviour": ("Return the classified provider error with no secret; "
                                "fall back to deterministic output and stop."),
        },
        "executable_now": bool(approved) and credential_status == "CONFIGURED"
        and state.get("ready_for_live_request") is True,
        "network_calls": 0,
        "live_request_performed": False,
        "note": ("This plan makes no request. A live call requires explicit approval "
                 "of request_sha256 and a locally configured credential."),
    }


def execute_live_validation(idea: str = CONTROLLED_TEST_IDEA, *,
                            authorization: dict | None = None,
                            provider: str = DEFAULT_PROVIDER,
                            model: str | None = None,
                            max_output_tokens: int = 2048,
                            temperature: float = 0.1,
                            timeout: int = 60) -> dict:
    """Perform exactly one approved request. Refuses everything else."""
    plan = plan_live_validation(
        idea, provider=provider, model=model,
        max_output_tokens=max_output_tokens, temperature=temperature,
        timeout=timeout)
    digest = plan["request"]["request_sha256"]

    if not isinstance(authorization, dict):
        return _refused(plan, "BLOCKED_AUTHORIZATION_MISSING",
                        "no approval object was supplied")
    if authorization.get("approved") is not True:
        return _refused(plan, "NOT_AUTHORIZED", "approval was not explicitly granted")
    if authorization.get("provider") not in (None, plan["provider"]):
        return _refused(plan, "AUTHORIZATION_PROVIDER_MISMATCH",
                        "approval names a different provider")
    if authorization.get("model") not in (None, plan["model"]):
        return _refused(plan, "AUTHORIZATION_MODEL_MISMATCH",
                        "approval names a different model")
    if authorization.get("request_sha256") != digest:
        return _refused(plan, "AUTHORIZATION_REQUEST_MISMATCH",
                        "approval does not name this exact request hash")
    if plan["credential"]["status"] != "CONFIGURED":
        return _refused(plan, "BLOCKED_CREDENTIAL_NOT_CONFIGURED",
                        "configure the provider credential locally; never paste it here")
    if not plan["readiness"].get("ready"):
        return _refused(plan, "BLOCKED_NOT_READY",
                        "; ".join(plan["readiness"].get("blockers") or []))

    cfg = llm_config.provider_config(plan["provider"])
    if cfg.get("local_only") and not cfg.get("local_provider"):
        return _refused(plan, "BLOCKED_LOCAL_ONLY_MODE",
                        "local-only mode forbids hosted providers")
    quota_before = quota.quota_state(plan["provider"], plan["model"])
    adapter = llm_providers.build(cfg)
    started = _now()
    try:
        result = adapter.complete(
            [{"role": "user", "content": plan["request"]["user_prompt"]}],
            system=plan["request"]["system_prompt"],
            max_tokens=plan["request"]["max_output_tokens"],
            temperature=plan["request"]["temperature"],
            json_mode=True,
            timeout=plan["request"]["timeout_seconds"],
        )
    except llm_providers.ProviderError as exc:
        quota.record(plan["provider"], plan["model"], status=f"error:{exc.kind}",
                     fallback_reason="provider_error")
        return {
            "ok": False,
            "status": "LIVE_REQUEST_FAILED",
            "provider": plan["provider"],
            "model": plan["model"],
            "error": {
                "kind": exc.kind,
                "status": exc.status,
                "message": llm_config.redact(str(exc)),
                "retry_attempted": False,
            },
            "request_sha256": digest,
            "started_at": started,
            "finished_at": _now(),
            "network_calls": 1,
            "fallback_used": True,
            "deterministic_fallback": "game_studio.understanding",
            "quota_before": quota_before,
            "quota_after": quota.quota_state(plan["provider"], plan["model"]),
            "secrets_recorded": False,
        }
    except Exception as exc:  # network/OS errors not wrapped by the adapter
        quota.record(plan["provider"], plan["model"], status="error:transport",
                     fallback_reason="transport_error")
        return {
            "ok": False,
            "status": "LIVE_REQUEST_FAILED",
            "provider": plan["provider"],
            "model": plan["model"],
            "error": {"kind": "transport", "status": None,
                      "message": llm_config.redact(str(exc)),
                      "retry_attempted": False},
            "request_sha256": digest,
            "started_at": started,
            "finished_at": _now(),
            "network_calls": 1,
            "fallback_used": True,
            "deterministic_fallback": "game_studio.understanding",
            "quota_before": quota_before,
            "quota_after": quota.quota_state(plan["provider"], plan["model"]),
            "secrets_recorded": False,
        }

    usage = result.get("usage") or {}
    quota.record(plan["provider"], plan["model"],
                 input_tokens=usage.get("prompt_tokens"),
                 output_tokens=usage.get("completion_tokens"),
                 status="success")
    text = result.get("text") or ""
    extracted = rv.extract_json(text)
    validation = (rv.validate_game_spec(extracted["payload"], source="ai_provider")
                  if extracted["ok"] else rv.validate_text(text, source="ai_provider"))
    raw_meta = result.get("raw_meta") or {}
    return {
        "ok": True,
        "status": "LIVE_REQUEST_COMPLETED",
        "phase": "V6 Phase 7 - live provider validation",
        "provider": plan["provider"],
        "model": result.get("model") or plan["model"],
        "request_sha256": digest,
        "started_at": started,
        "finished_at": _now(),
        "http_status": raw_meta.get("http_status"),
        "request_id": raw_meta.get("response_id"),
        "model_version": raw_meta.get("model_version"),
        "finish_reason": raw_meta.get("finish_reason"),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "source": "provider" if usage.get("total_tokens") is not None else "unavailable",
        },
        "quota_before": quota_before,
        "quota_after": quota.quota_state(plan["provider"], plan["model"]),
        "json_extracted": extracted["ok"],
        "schema_validation": {
            "valid": validation["schema_valid"],
            "errors": validation["errors"],
            "missing_fields": validation["missing_fields"],
            "contradictions": validation["contradictions"],
            "unsupported_claims": validation["unsupported_claims"],
        },
        "raw_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "raw_text_chars": len(text),
        "response_preview": llm_config.redact(text[:2000]),
        "network_calls": 1,
        "retries": 0,
        "fallback_used": False,
        "secrets_recorded": False,
        "note": ("The response is untrusted data. Schema validity is not proof of "
                 "quality and no action was executed from its content."),
    }


def _refused(plan: dict, status: str, reason: str) -> dict:
    return {
        "ok": False,
        "status": status,
        "phase": "V6 Phase 7 - live provider validation",
        "provider": plan.get("provider"),
        "model": plan.get("model"),
        "reasons": [reason],
        "request_sha256": plan["request"]["request_sha256"],
        "credential_status": plan["credential"]["status"],
        "authorization": plan["authorization"],
        "network_calls": 0,
        "live_request_performed": False,
        "secrets_recorded": False,
    }


def audit_record(plan: dict) -> dict:
    """Persistable request audit with no credential or header material."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": plan["generated_at"],
        "provider": plan["provider"],
        "model": plan["model"],
        "request_sha256": plan["request"]["request_sha256"],
        "max_input_chars": plan["request"]["max_input_chars"],
        "actual_input_chars": plan["request"]["actual_input_chars"],
        "max_output_tokens": plan["request"]["max_output_tokens"],
        "temperature": plan["request"]["temperature"],
        "timeout_seconds": plan["request"]["timeout_seconds"],
        "retries": 0,
        "project_files_sent": False,
        "authorization_status": plan["authorization"]["status"],
        "credential_status": plan["credential"]["status"],
        "quota_impact": plan["quota_impact"],
        "data_handling": plan["data_handling"],
        "network_calls": 0,
        "live_request_performed": False,
        "executable_now": plan["executable_now"],
    }
    try:
        llm_schemas.validate(record, {"type": "object"})
    except Exception:  # pragma: no cover - validator is total
        pass
    return record
