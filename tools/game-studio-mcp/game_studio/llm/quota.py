"""Persistent free-quota ledger and cost policy for Phase 6.

The ledger records only what a provider actually returned or what this project
knows from documentation. It never stores a credential, authorization header or
raw prompt. An unknown remaining allowance is reported as ``unknown`` and is
never treated as unlimited.

V6 Phase 1 already has a daily request budget in ``llm.client``. This module is
the provider/model-aware companion used by free-only routing and the Phase 6
MCP tools; it does not replace that budget.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from .. import config as studio_config
from ..util import read_json, write_json
from . import free_policy

SCHEMA_VERSION = 1
MAX_ENTRIES_PER_DAY = 5000
MAX_LEDGER_BYTES = 4 * 1024 * 1024

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|access[_-]?token|authorization)"
               r"\s*[:=]\s*(?:bearer\s+)?\S{6,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{10,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\bsk-or-[A-Za-z0-9_\-]{12,}\b"),
)


def _redact(value: object, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:limit]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path() -> str:
    return os.path.join(studio_config.config_dir(), "llm-free-quota.json")


def _empty(day: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "day": day, "providers": {},
            "note": ("Provider/model free-quota ledger. No credentials or prompts "
                     "are stored.")}


def load_ledger() -> dict:
    path = ledger_path()
    if not os.path.isfile(path):
        return _empty(_today())
    try:
        if os.path.getsize(path) > MAX_LEDGER_BYTES:
            return _empty(_today())
        payload = read_json(path)
    except (OSError, ValueError):
        return _empty(_today())
    if not isinstance(payload, dict) or payload.get("day") != _today():
        return _empty(_today())
    if not isinstance(payload.get("providers"), dict):
        return _empty(_today())
    return payload


def _save(ledger: dict) -> None:
    try:
        os.makedirs(studio_config.config_dir(), exist_ok=True)
        write_json(ledger_path(), ledger)
    except OSError:
        # A ledger write failure must never fabricate a successful request.
        pass


def _bucket(ledger: dict, provider: str, model: str) -> dict:
    providers = ledger.setdefault("providers", {})
    provider_bucket = providers.setdefault(provider, {"models": {}})
    models = provider_bucket.setdefault("models", {})
    return models.setdefault(model, {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "verified_allowance": None,
        "remaining_allowance": None,
        "statuses": {},
        "fallback_reasons": [],
        "last_request_at": None,
        "updated_at": None,
    })


def record(provider: str, model: str, *, requests: int = 1,
           input_tokens: int | None = None, output_tokens: int | None = None,
           estimated_cost_usd: float = 0.0,
           verified_allowance: int | None = None,
           remaining_allowance: int | None = None,
           status: str = "success",
           fallback_reason: str | None = None,
           timestamp: str | None = None) -> dict:
    """Append one request outcome. Unknown allowances stay ``None``."""
    key = _redact(provider, 80).strip().lower()
    name = _redact(model, 200).strip()
    ledger = load_ledger()
    bucket = _bucket(ledger, key, name)
    bucket["requests"] = int(bucket.get("requests") or 0) + max(0, int(requests))
    if isinstance(input_tokens, (int, float)):
        bucket["input_tokens"] = int(bucket.get("input_tokens") or 0) + max(0, int(input_tokens))
    if isinstance(output_tokens, (int, float)):
        bucket["output_tokens"] = int(bucket.get("output_tokens") or 0) + max(0, int(output_tokens))
    if isinstance(estimated_cost_usd, (int, float)):
        bucket["estimated_cost_usd"] = round(
            float(bucket.get("estimated_cost_usd") or 0.0) +
            max(0.0, float(estimated_cost_usd)), 6)
    if verified_allowance is not None:
        bucket["verified_allowance"] = int(verified_allowance)
    if remaining_allowance is not None:
        bucket["remaining_allowance"] = int(remaining_allowance)
    statuses = bucket.setdefault("statuses", {})
    clean_status = _redact(status, 80) or "unknown"
    statuses[clean_status] = int(statuses.get(clean_status, 0)) + 1
    if fallback_reason:
        reasons = bucket.setdefault("fallback_reasons", [])
        reasons.append(_redact(fallback_reason, 300))
        del reasons[:-20]
    stamp = timestamp or _now()
    bucket["last_request_at"] = stamp
    bucket["updated_at"] = stamp

    provider_bucket = ledger["providers"][key]
    provider_bucket["requests"] = sum(
        int(item.get("requests") or 0) for item in provider_bucket["models"].values())
    provider_bucket["updated_at"] = stamp

    total_entries = sum(len(item.get("statuses") or {}) for item in
                        (provider_bucket["models"].values()))
    if total_entries > MAX_ENTRIES_PER_DAY:
        bucket["statuses"] = dict(list(bucket["statuses"].items())[-50:])
    _save(ledger)
    return bucket


def usage(provider: str, model: str) -> dict:
    ledger = load_ledger()
    models = ((ledger.get("providers") or {}).get(provider) or {}).get("models") or {}
    return models.get(model) or {}


def quota_state(provider: str, model: str) -> dict:
    """Compute used/limit/remaining status from documentation plus the ledger."""
    key = (provider or "").strip().lower()
    name = (model or "").strip()
    used = int(usage(key, name).get("requests") or 0)
    limit = free_policy.known_daily_limit(key, name)
    if limit is None:
        remaining = None
        exhausted = None
        reason = ("the provider does not expose a reliable per-key remaining quota; "
                  "unknown is not treated as unlimited")
    else:
        remaining = max(0, limit - used)
        exhausted = remaining <= 0
        reason = ("documented daily request allowance reached"
                  if exhausted else "documented daily request allowance remains")
    return {
        "provider": key,
        "model": name,
        "status": free_policy.provider_status(key),
        "free": free_policy.is_free_status(free_policy.provider_status(key)),
        "requests_today": used,
        "verified_daily_limit": limit,
        "remaining_today": remaining,
        "exhausted": exhausted,
        "quota_known": limit is not None,
        "reason": reason,
        "evidence": ("limit from official documentation; usage from this machine's "
                     "ledger" if limit is not None else
                     "no documented per-key daily limit"),
    }


def can_request(provider: str, model: str, *, reserve: int = 0) -> dict:
    """Return an explicit free-quota decision. Never assumes unknown == unlimited."""
    state = quota_state(provider, model)
    if state["exhausted"] is True:
        return {"allowed": False, "kind": "free_quota_exhausted",
                "fallback_reason": "free_quota_exhausted", **state}
    if state["exhausted"] is None:
        return {"allowed": True, "kind": "quota_unknown_not_unlimited",
                "fallback_reason": None, **state}
    if reserve and (state["remaining_today"] or 0) <= reserve:
        return {"allowed": False, "kind": "free_quota_reserved",
                "fallback_reason": "free_quota_reserved", **state}
    return {"allowed": True, "kind": "within_documented_allowance",
            "fallback_reason": None, **state}


def status() -> dict:
    ledger = load_ledger()
    providers = []
    for provider in ("gemini", "groq", "openrouter", "ollama"):
        entry = free_policy.provider_entry(provider)
        models = []
        eligible = list(entry.get("eligible_models") or [])
        if provider == "openrouter":
            eligible = ["<model-id>:free"]
        if provider == "ollama":
            eligible = ["<locally installed model>"]
        for model in eligible:
            state = quota_state(provider, model)
            state["estimated_cost_usd"] = float(
                (usage(provider, model) or {}).get("estimated_cost_usd") or 0.0)
            models.append(state)
        providers.append({
            "provider": provider,
            "status": entry["status"],
            "free": entry["status"] in free_policy.FREE_STATUSES,
            "requires_payment_info": entry["billing_basis"]["requires_payment_info"],
            "models": models,
        })
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "day": ledger["day"],
        "path": ledger_path(),
        "providers": providers,
        "totals": {
            "requests_today": sum(int(item.get("requests") or 0)
                                  for item in (ledger.get("providers") or {}).values()),
            "estimated_cost_usd": round(sum(
                float((model_data or {}).get("estimated_cost_usd") or 0.0)
                for provider_data in (ledger.get("providers") or {}).values()
                for model_data in ((provider_data or {}).get("models") or {}).values()), 6),
        },
        "policy": {
            "unknown_quota_is_unlimited": False,
            "paid_fallback": False,
            "secrets_stored": False,
        },
        "network_calls": 0,
    }


def failure_reason(*, status_code: int | None = None, error_kind: str | None = None,
                   detail: str | None = None) -> dict:
    """Classify a provider failure into a stable fallback reason."""
    kind = (error_kind or "").strip().lower()
    code = status_code
    mapping = {
        429: ("http_429_rate_limited", "provider rate limit or free quota exhausted"),
        401: ("http_401_unauthorized", "credential rejected or missing"),
        403: ("http_403_forbidden", "account or model access forbidden"),
    }
    if code in mapping:
        reason, text = mapping[code]
    elif kind in ("rate_limit", "quota"):
        reason, text = "rate_limit", "provider reported a rate limit"
    elif kind in ("auth", "unauthorized", "forbidden"):
        reason, text = "auth_failure", "credential or access was rejected"
    elif kind == "timeout":
        reason, text = "timeout", "request timed out"
    elif kind in ("network", "connection", "unavailable"):
        reason, text = "network_failure", "provider was unreachable"
    elif kind in ("not_found", "invalid_model"):
        reason, text = "invalid_model", "model or endpoint was not found"
    elif kind in ("deprecation", "deprecated"):
        reason, text = "deprecated", "model or endpoint is deprecated"
    elif kind in ("invalid_output", "malformed_output", "schema"):
        reason, text = "malformed_output", "output failed schema validation"
    else:
        reason, text = "provider_error", "provider request failed"
    return {
        "reason": reason,
        "message": _redact(text),
        "detail": _redact(detail, 300) if detail else None,
        "status_code": code,
        "error_kind": error_kind,
        "timestamp": _now(),
    }
