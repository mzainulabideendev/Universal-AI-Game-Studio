"""Capability-aware provider/model routing.

The router is a pure configuration and capability decision. It performs no
network I/O and never upgrades a requirement status. It refuses a candidate when
a required capability is known to be ``unsupported``, labels ``unknown``
capabilities as unverified, and never silently moves work to a hosted (paid)
provider. When no candidate qualifies the deterministic fallback is returned.
"""

from __future__ import annotations

import shutil

from ..util import ToolError
from . import capabilities
from . import config as llm_config

DETERMINISTIC_FALLBACK = {
    "kind": "deterministic",
    "module": "game_studio.understanding",
    "available": True,
    "behaviour": ("Deterministic request analysis and planning. No provider is "
                  "contacted and the response is labelled deterministic."),
}


def _validate_required(names: list[str] | None) -> list[str]:
    if not names:
        return []
    required = []
    for value in names:
        name = str(value or "").strip().lower()
        if name not in capabilities.CAPABILITY_KEYS:
            raise ToolError(
                f"unknown capability {value!r}; expected one of "
                f"{list(capabilities.CAPABILITY_KEYS)}")
        if name not in required:
            required.append(name)
    return required


def _model_entry(discovered: dict | None, provider: str,
                 model: str) -> dict | None:
    if not isinstance(discovered, dict):
        return None
    entries = discovered.get(provider)
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == model:
            return entry
    return None


def _model_ids(discovered: dict | None, provider: str) -> list[str] | None:
    if not isinstance(discovered, dict):
        return None
    entries = discovered.get(provider)
    if not isinstance(entries, list):
        return None
    return [entry.get("id") for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)]


def evaluate_candidate(provider: str, *, required: list[str], model: str | None,
                       context_chars: int | None, max_tokens: int | None,
                       allow_paid: bool, require_known: bool,
                       discovered: dict | None, explicit: bool = False) -> dict:
    """Evaluate one provider/model. Returns blockers, warnings and compatibility."""
    cfg = llm_config.provider_config(provider)
    profile = capabilities.provider_profile(provider)
    chosen_model = model or cfg["model"]
    hosted = profile["kind"] != "local"
    blockers: list[str] = []
    warnings: list[str] = []
    compatibility: dict[str, dict] = {}

    allowed, reason = llm_config.provider_allowed(cfg)
    if not allowed:
        blockers.append(reason or "provider is not available")
    if hosted and not allow_paid:
        blockers.append(
            f"hosted provider {provider!r} is potentially paid and allow_paid is false; "
            "it is never selected automatically")
    if int(cfg.get("max_requests") or 0) == 0:
        blockers.append("request budget is zero (GAME_STUDIO_LLM_MAX_REQUESTS)")
    if provider == "ollama":
        executable = shutil.which("ollama")
        if not executable:
            message = ("Ollama runtime is not installed or not on PATH; this project "
                       "will not install it. Start a reachable service or choose another "
                       "provider / the deterministic fallback")
            if explicit:
                warnings.append(message + " (explicit provider request kept for a "
                                          "reachable external service)")
            else:
                blockers.append(message)
        elif not explicit:
            warnings.append(
                "Ollama runtime is installed; service reachability is unverified until "
                "llm_list_models succeeds")
    if max_tokens and max_tokens > int(cfg["max_tokens"]):
        blockers.append(
            f"requested {max_tokens} output tokens exceeds the configured budget of "
            f"{cfg['max_tokens']}")
    if context_chars and context_chars > int(cfg["max_context_chars"]):
        blockers.append(
            f"requested context of {context_chars} chars exceeds the configured limit of "
            f"{cfg['max_context_chars']}")

    provider_caps = profile["capabilities"]
    entry = _model_entry(discovered, provider, chosen_model)
    ids = _model_ids(discovered, provider)
    if model and ids is not None and model not in ids:
        blockers.append(
            f"model {model!r} is not present in the discovered model list for {provider!r}")
    if model and ids is None:
        warnings.append(
            "model selection is unverified: no live discovery result was supplied")

    for name in required:
        provider_state = provider_caps.get(name, capabilities.UNKNOWN)
        state = provider_state
        source = "adapter"
        if entry:
            model_state = (entry.get("capabilities") or {}).get(name)
            if isinstance(model_state, dict):
                model_state = model_state.get("state")
            if model_state == capabilities.UNSUPPORTED:
                state = capabilities.UNSUPPORTED
                source = "model"
            elif model_state == capabilities.SUPPORTED and provider_state != capabilities.UNSUPPORTED:
                state = capabilities.SUPPORTED
                source = "model"
            elif provider_state == capabilities.UNKNOWN and model_state == capabilities.UNKNOWN:
                state = capabilities.UNKNOWN
                source = "model"
        compatibility[name] = {"state": state, "source": source}
        if state == capabilities.UNSUPPORTED:
            blockers.append(f"required capability {name!r} is unsupported")
        elif state == capabilities.UNKNOWN:
            if require_known:
                blockers.append(
                    f"required capability {name!r} is unknown and require_known is true")
            else:
                warnings.append(
                    f"required capability {name!r} is unknown; treating it as unverified")

    window = None
    if entry:
        window = (entry.get("capabilities") or {}).get("context_window")
    if context_chars and isinstance(window, dict) and window.get("state") == "supported":
        value = window.get("value")
        if isinstance(value, int) and context_chars > value:
            blockers.append(
                f"requested context of {context_chars} chars exceeds the discovered "
                f"model context window of {value} tokens")

    return {
        "provider": provider,
        "model": chosen_model,
        "kind": profile["kind"],
        "local": profile["kind"] == "local",
        "available": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "compatibility": compatibility,
        "credential_configured": bool(cfg.get("api_key")),
        "credential_source": cfg.get("key_source"),
        "base_url": cfg["base_url"],
        "model_discovered": entry is not None,
        "ollama_runtime_detected": (shutil.which("ollama") is not None
                                    if provider == "ollama" else None),
        "limits": {
            "timeout_seconds": cfg["timeout_seconds"],
            "max_tokens_per_request": cfg["max_tokens"],
            "max_context_chars": cfg["max_context_chars"],
            "max_requests_per_session": cfg["max_requests"],
            "max_requests_per_day": cfg["max_requests_per_day"],
            "retries": cfg["retries"],
            "backoff_seconds": cfg["backoff_seconds"],
        },
    }


def route(task: str, *, required_capabilities: list[str] | None = None,
          context_chars: int | None = None, provider: str | None = None,
          model: str | None = None, allow_paid: bool = False,
          require_known: bool = False,
          discovered: dict | None = None, max_tokens: int | None = None) -> dict:
    """Choose a provider/model for a task, or return the deterministic fallback."""
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
        order = ["ollama"] + [name for name in llm_config.PROVIDERS
                              if name != "ollama"]

    evaluations = []
    selected = None
    for name in order:
        evaluation = evaluate_candidate(
            name, required=required, model=model if explicit_provider else None,
            context_chars=context_chars, max_tokens=max_tokens,
            allow_paid=allow_paid, require_known=require_known,
            discovered=discovered, explicit=bool(explicit_provider))
        evaluations.append(evaluation)
        if evaluation["available"] and selected is None:
            selected = evaluation

    explanation: list[str] = []
    if selected:
        explanation.append(
            f"selected {selected['provider']}/{selected['model']} for task {task_name!r}")
        explanation.append(
            f"provider kind: {selected['kind']}; "
            f"credential configured: {selected['credential_configured']}")
        for name, info in selected["compatibility"].items():
            explanation.append(f"{name}: {info['state']} ({info['source']})")
        explanation.extend(selected["warnings"])
        explanation.append(
            "Routing is a configuration decision only; reachability and output quality "
            "are not verified by this call.")
    else:
        explanation.append("no provider/model satisfies the request")
        if not allow_paid:
            explanation.append(
                "hosted providers were not considered because allow_paid is false; "
                "set allow_paid=true only with explicit approval")
        if explicit_provider:
            explanation.append(
                f"the preferred provider {explicit_provider!r} was rejected; the router "
                "does not silently switch to another provider")
        explanation.append(
            "the deterministic parser remains available and makes no network calls")

    return {
        "ok": True,
        "task": task_name,
        "required_capabilities": required,
        "preferences": {
            "provider": explicit_provider,
            "model": model,
            "allow_paid": bool(allow_paid),
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
            "base_url": selected["base_url"],
            "credential_source": selected["credential_source"],
            "model_discovered": selected["model_discovered"],
        } if selected else None),
        "compatibility": (selected["compatibility"] if selected else {}),
        "constraints": (selected["limits"] if selected else {
            "network_calls": 0,
            "deterministic": True,
        }),
        "explanation": explanation,
        "candidates": evaluations,
        "fallback_plan": {
            "auto_switch": False,
            "paid_switch": False,
            "reason": ("Provider fallback is never automatic. A caller may retry with an "
                       "explicit provider after approval."),
            "alternatives": [
                {"provider": item["provider"], "model": item["model"],
                 "available": item["available"], "blockers": item["blockers"]}
                for item in evaluations
            ],
            "deterministic": dict(DETERMINISTIC_FALLBACK),
        },
        "deterministic_fallback": dict(DETERMINISTIC_FALLBACK),
        "live_verified": False,
        "network_calls": 0,
        "note": ("No provider was contacted. A selected model is not a claim that the "
                 "provider is reachable or that its output is correct."),
    }


def routing_matrix(*, allow_paid: bool = False,
                   require_known: bool = False) -> dict:
    """Configuration-only matrix of task categories against providers."""
    rows = []
    for task, info in capabilities.TASK_CATEGORIES.items():
        decision = route(task, allow_paid=allow_paid, require_known=require_known)
        rows.append({
            "task": task,
            "description": info["description"],
            "required_capabilities": info["required_capabilities"],
            "selected": decision["selected"],
            "mode": decision["mode"],
            "candidates": [
                {"provider": item["provider"], "available": item["available"],
                 "blockers": item["blockers"]}
                for item in decision["candidates"]
            ],
        })
    return {
        "ok": True,
        "mode": "configuration-only",
        "network_calls": 0,
        "allow_paid": bool(allow_paid),
        "require_known": bool(require_known),
        "rows": rows,
        "note": "No provider was contacted.",
    }
