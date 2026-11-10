"""Free-only routing policy for V6 Phase 6.

This is an additive layer over :mod:`game_studio.llm.routing`. It reuses the
Phase 1 capability evaluation but gates every candidate on the documented free
status, model eligibility and the local quota ledger. Paid, trial-only and
unknown-billing providers are rejected before any request can be sent.

The router performs no network I/O. It never silently switches to a paid
provider, and a provider error produces an explicit deterministic fallback with
a recorded reason.
"""

from __future__ import annotations

from ..util import ToolError
from . import capabilities
from . import config as llm_config
from . import free_policy, quota
from . import routing as phase1_routing

# Documented free providers first, then the optional local runtime. The order is
# a policy decision, not a quality ranking.
FREE_ROUTE_ORDER = ("gemini", "groq", "openrouter", "ollama")

DETERMINISTIC_FALLBACK = dict(phase1_routing.DETERMINISTIC_FALLBACK)


def _validate_required(names: list[str] | None) -> list[str]:
    return phase1_routing._validate_required(names)


def evaluate_candidate(provider: str, *, required: list[str], model: str | None,
                       context_chars: int | None, max_tokens: int | None,
                       require_known: bool, discovered: dict | None,
                       explicit: bool = False,
                       account_credits: float | None = None) -> dict:
    """Evaluate one provider under the free-only policy."""
    key = (provider or "").strip().lower()
    status = free_policy.provider_status(key)
    cfg = llm_config.provider_config(key)
    chosen_model = model or cfg["model"]
    blockers: list[str] = []
    fallback_reasons: list[dict] = []

    # Phase 1 evaluation is reused with allow_paid=True so it still checks
    # capabilities, budgets, credentials and discovery. Paid permission is not
    # granted here: the free-status gate below is the only authority.
    base = phase1_routing.evaluate_candidate(
        key, required=required, model=chosen_model, context_chars=context_chars,
        max_tokens=max_tokens, allow_paid=True, require_known=require_known,
        discovered=discovered, explicit=explicit)
    blockers.extend(base["blockers"])

    if not free_policy.is_free_status(status):
        blockers.append(
            f"provider status is {status!r}; free-only mode refuses paid, trial-only, "
            "unknown or unavailable providers")
        fallback_reasons.append(quota.failure_reason(
            error_kind="paid" if status in (free_policy.PAID, free_policy.TRIAL_ONLY)
            else "unknown_billing",
            detail=f"provider {key!r} status {status!r}"))

    eligibility = free_policy.model_eligibility(
        key, chosen_model, account_credits=account_credits)
    if eligibility["eligible"] is not True:
        blockers.append(eligibility["reason"])
        fallback_reasons.append(quota.failure_reason(
            error_kind="invalid_model", detail=eligibility["reason"]))

    quota_decision = quota.can_request(key, chosen_model)
    if not quota_decision["allowed"]:
        blockers.append(quota_decision["reason"])
        fallback_reasons.append(quota.failure_reason(
            error_kind="quota", detail=quota_decision["reason"]))

    if key == "ollama" and explicit and not base["ollama_runtime_detected"]:
        # Explicit local selection is kept for an externally started service, but
        # the runtime is still labelled unverified rather than assumed present.
        pass

    return {
        "provider": key,
        "model": chosen_model,
        "kind": base["kind"],
        "local": base["local"],
        "free_status": status,
        "free": free_policy.is_free_status(status),
        "model_eligible": eligibility["eligible"],
        "model_eligibility_reason": eligibility["reason"],
        "quota": quota_decision,
        "available": not blockers,
        "blockers": blockers,
        "warnings": base["warnings"],
        "compatibility": base["compatibility"],
        "credential_configured": base["credential_configured"],
        "credential_source": base["credential_source"],
        "base_url": base["base_url"],
        "model_discovered": base["model_discovered"],
        "limits": base["limits"],
        "fallback_reasons": fallback_reasons,
        "paid_switch_possible": False,
    }


def route(task: str, *, required_capabilities: list[str] | None = None,
          context_chars: int | None = None, provider: str | None = None,
          model: str | None = None, require_known: bool = False,
          discovered: dict | None = None, max_tokens: int | None = None,
          account_credits: float | None = None) -> dict:
    """Choose a free provider/model, or return the deterministic fallback."""
    task_name = (task or "").strip().lower()
    if task_name not in capabilities.TASK_CATEGORIES and not required_capabilities:
        raise ToolError(
            f"unknown task {task!r}; provide a task category or required_capabilities "
            f"({list(capabilities.TASK_CATEGORIES)})")
    task_requirements = list(
        (capabilities.TASK_CATEGORIES.get(task_name) or {}).get(
            "required_capabilities") or [])
    required = list(dict.fromkeys(
        task_requirements + _validate_required(required_capabilities)))

    if context_chars is not None and (not isinstance(context_chars, int)
                                      or context_chars < 0):
        raise ToolError("context_chars must be a non-negative integer")
    if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens < 1):
        raise ToolError("max_tokens must be a positive integer")

    explicit_provider = None
    if provider:
        explicit_provider = llm_config.validate_provider_name(provider)
        order = [explicit_provider]
    else:
        order = list(FREE_ROUTE_ORDER)

    evaluations = []
    selected = None
    for name in order:
        evaluation = evaluate_candidate(
            name, required=required,
            model=model if explicit_provider else None,
            context_chars=context_chars, max_tokens=max_tokens,
            require_known=require_known, discovered=discovered,
            explicit=bool(explicit_provider), account_credits=account_credits)
        evaluations.append(evaluation)
        if evaluation["available"] and selected is None:
            selected = evaluation

    explanation: list[str] = []
    if selected:
        explanation.append(
            f"selected free {selected['provider']}/{selected['model']} for "
            f"task {task_name!r}")
        explanation.append(f"documented status: {selected['free_status']}")
        explanation.append(f"quota: {selected['quota']['kind']}")
        explanation.extend(selected["warnings"])
        explanation.append(
            "Routing is a policy decision only; reachability and output quality are "
            "not verified by this call.")
    else:
        explanation.append("no free provider/model satisfies the request")
        if explicit_provider:
            explanation.append(
                f"the requested provider {explicit_provider!r} was refused; the router "
                "never silently switches to another provider")
        explanation.append(
            "Free-only mode never falls back to a paid provider; the deterministic "
            "parser remains available and makes no network calls")

    return {
        "ok": True,
        "schema_version": 1,
        "task": task_name,
        "required_capabilities": required,
        "policy": {
            "mode": "free-only",
            "allow_paid": False,
            "allow_trial_only": False,
            "allow_unknown_billing": False,
            "unknown_quota_is_unlimited": False,
            "paid_fallback": False,
        },
        "preferences": {
            "provider": explicit_provider,
            "model": model,
            "require_known": bool(require_known),
            "context_chars": context_chars,
            "max_tokens": max_tokens,
        },
        "mode": "provider" if selected else "deterministic",
        "selected": ({
            "provider": selected["provider"],
            "model": selected["model"],
            "kind": selected["kind"],
            "local": selected["local"],
            "free_status": selected["free_status"],
            "base_url": selected["base_url"],
            "credential_source": selected["credential_source"],
            "model_discovered": selected["model_discovered"],
            "quota": selected["quota"],
        } if selected else None),
        "compatibility": (selected["compatibility"] if selected else {}),
        "candidates": evaluations,
        "fallback_reasons": [
            reason for item in evaluations for reason in item["fallback_reasons"]],
        "fallback_plan": {
            "auto_switch": False,
            "paid_switch": False,
            "trial_switch": False,
            "reason": ("A provider fallback is never automatic. Only a documented free "
                       "candidate may be selected, and only when its capability, model "
                       "and quota checks pass."),
            "alternatives": [
                {"provider": item["provider"], "model": item["model"],
                 "free_status": item["free_status"],
                 "available": item["available"], "blockers": item["blockers"]}
                for item in evaluations
            ],
            "deterministic": dict(DETERMINISTIC_FALLBACK),
        },
        "deterministic_fallback": dict(DETERMINISTIC_FALLBACK),
        "executable": False,
        "live_verified": False,
        "network_calls": 0,
        "note": ("No provider was contacted. A selected free model is not a claim that "
                 "the provider is reachable or that its output is correct."),
    }


def record_outcome(provider: str, model: str, *, status: str = "success",
                   input_tokens: int | None = None, output_tokens: int | None = None,
                   estimated_cost_usd: float = 0.0,
                   status_code: int | None = None,
                   error_kind: str | None = None,
                   detail: str | None = None) -> dict:
    """Record one real outcome in the ledger and return a fallback decision."""
    state = quota.quota_state(provider, model)
    failure = None
    if status != "success":
        failure = quota.failure_reason(status_code=status_code,
                                       error_kind=error_kind, detail=detail)
    remaining = state["remaining_today"]
    if remaining is not None and status == "success":
        remaining = max(0, remaining - 1)
    quota.record(
        provider, model, requests=1, input_tokens=input_tokens,
        output_tokens=output_tokens, estimated_cost_usd=estimated_cost_usd,
        verified_allowance=state["verified_daily_limit"],
        remaining_allowance=remaining, status=status,
        fallback_reason=(failure or {}).get("reason"))
    return {
        "recorded": True,
        "provider": provider,
        "model": model,
        "status": status,
        "estimated_cost_usd": float(estimated_cost_usd or 0.0),
        "failure": failure,
        "fallback": ("deterministic" if failure else None),
        "paid_fallback": False,
        "next_action": (None if not failure else
                        "Do not retry against a paid provider. Wait for the documented "
                        "free allowance to reset or use the deterministic fallback."),
    }


def classify_failure(*, status_code: int | None = None,
                     error_kind: str | None = None,
                     detail: str | None = None) -> dict:
    return quota.failure_reason(status_code=status_code, error_kind=error_kind,
                                detail=detail)


def policy_report() -> dict:
    """Configuration-only report used by the routing-policy artifact."""
    rows = []
    for task in capabilities.TASK_CATEGORIES:
        decision = route(task)
        rows.append({
            "task": task,
            "mode": decision["mode"],
            "selected": decision["selected"],
            "candidates": [
                {"provider": item["provider"], "free_status": item["free_status"],
                 "model_eligible": item["model_eligible"],
                 "quota_known": item["quota"]["quota_known"],
                 "available": item["available"],
                 "blockers": item["blockers"]}
                for item in decision["candidates"]
            ],
        })
    return {
        "ok": True,
        "schema_version": 1,
        "policy": "free-only",
        "route_order": list(FREE_ROUTE_ORDER),
        "paid_fallback": False,
        "trial_fallback": False,
        "unknown_billing_accepted": False,
        "unknown_quota_is_unlimited": False,
        "rows": rows,
        "network_calls": 0,
        "executable": False,
    }
