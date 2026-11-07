"""Provider and model discovery with honest availability states.

Discovery performs one documented read-only request to a provider's model-list
endpoint. It never sends project content and never spends generation credits.
Every response is labelled ``live``, ``unavailable`` or ``deterministic`` so a
mocked test or a fallback result can never be mistaken for a live provider.
"""

from __future__ import annotations

import shutil

from .. import governance
from ..util import ToolError
from . import capabilities
from . import config as llm_config
from .providers import ProviderError, build

REMEDIATION = {
    "auth": ("The provider rejected the credential. Configure a valid key with "
             "llm_configure_credential or the documented environment variable."),
    "rate_limit": "The provider rate-limited the request. Retry later or reduce requests.",
    "not_found": ("The endpoint or model was not found. Check base_url and re-run model "
                  "discovery."),
    "timeout": "The provider did not answer before the connect timeout.",
    "unavailable": ("The provider is not reachable. Check the endpoint, network and, for "
                    "Ollama, whether the local service is running."),
    "config": "Provider configuration is invalid; review the endpoint and provider name.",
    "invalid_response": "The provider returned a response this adapter cannot parse.",
    "unsupported": "This adapter does not implement the requested operation.",
}


def ollama_detection() -> dict:
    """Detect the runtime executable and service without installing or starting it."""
    executable = shutil.which("ollama")
    return {
        "runtime_on_path": bool(executable),
        "executable": executable,
        "installed": bool(executable),
        "started": False,
        "note": ("Detection only. This project never installs Ollama, downloads a model "
                 "or starts a background service."),
    }


def provider_status(provider: str) -> dict:
    """Configuration-only status for one provider. Performs no network I/O."""
    name = llm_config.validate_provider_name(provider)
    cfg = llm_config.provider_config(name)
    allowed, reason = llm_config.provider_allowed(cfg)
    profile = capabilities.provider_profile(name)
    return {
        "provider": name,
        "kind": profile["kind"],
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "credential_required": bool(cfg.get("key_required")),
        "credential_configured": bool(cfg.get("api_key")),
        "credential_source": cfg.get("key_source"),
        "local_only_blocks": bool(cfg["local_only"] and not cfg["local_provider"]),
        "available": allowed,
        "unavailable_reason": reason,
        "reachable": None,
        "live_verified": None,
        "capabilities": profile["capabilities"],
        "limits": {
            "timeout_seconds": cfg["timeout_seconds"],
            "connect_timeout_seconds": cfg["connect_timeout_seconds"],
            "max_tokens": cfg["max_tokens"],
            "max_context_chars": cfg["max_context_chars"],
            "max_requests": cfg["max_requests"],
            "max_requests_per_day": cfg["max_requests_per_day"],
            "retries": cfg["retries"],
        },
        "note": ("Configuration is not evidence of reachability. Reachability requires "
                 "llm_list_models or llm_test_provider with confirm=true."),
    }


def _normalise_error(provider: str, exc: ProviderError, cfg: dict) -> dict:
    message = llm_config.redact(str(exc))
    payload = {
        "ok": False,
        "provider": provider,
        "state": "unavailable",
        "kind": exc.kind,
        "status": getattr(exc, "status", None),
        "retryable": bool(exc.retryable),
        "reachable": False,
        "live_verified": False,
        "mode": "unavailable",
        "error": message,
        "remediation": REMEDIATION.get(exc.kind, "Review the provider diagnostics."),
        "deterministic_fallback": {
            "available": True,
            "module": "game_studio.understanding",
            "behaviour": "deterministic parsing when no provider can answer",
        },
    }
    if provider == "ollama":
        payload["ollama"] = ollama_detection()
        if not payload["ollama"]["installed"]:
            payload["remediation"] = (
                "Ollama is not installed or not on PATH. This project will not install "
                "it. Install Ollama manually and start its service, or choose another "
                "provider / the deterministic fallback.")
        elif exc.kind in ("unavailable", "timeout"):
            payload["remediation"] = (
                "Ollama is installed but its local service is not reachable. Start it "
                "manually, then retry discovery. No model is downloaded automatically.")
    if not cfg.get("api_key") and cfg.get("key_required"):
        payload["remediation"] = (
            "No credential is configured for this provider. Use llm_configure_credential "
            "or set the documented environment variable.")
    return payload


def discover_models(provider: str, *, confirm: bool = False,
                    project_path: str | None = None) -> dict:
    """List models from one provider using its documented discovery endpoint."""
    name = llm_config.validate_provider_name(provider)
    governance.authorize(
        "external_api", project_path=project_path, confirm=confirm,
        action=f"list models for provider {name}")
    cfg = llm_config.provider_config(name)
    allowed, reason = llm_config.provider_allowed(cfg)
    if not allowed:
        payload = {
            "ok": False,
            "provider": name,
            "state": "unavailable",
            "kind": "configuration",
            "reachable": False,
            "live_verified": False,
            "mode": "unavailable",
            "error": reason,
            "remediation": reason,
            "models": [],
            "count": 0,
            "deterministic_fallback": {
                "available": True,
                "module": "game_studio.understanding",
            },
        }
        if cfg.get("key_required") and not cfg.get("api_key"):
            payload["remediation"] = (
                "No credential is configured for this provider. Use "
                "llm_configure_credential or set the documented environment variable.")
        if name == "ollama":
            payload["ollama"] = ollama_detection()
        return payload

    adapter = build(cfg)
    timeout = max(5, int(cfg.get("connect_timeout_seconds") or 10))
    try:
        listing = adapter.list_models(timeout=timeout)
    except ProviderError as exc:
        return _normalise_error(name, exc, cfg)
    except ToolError as exc:
        return {
            "ok": False, "provider": name, "state": "unavailable",
            "kind": "endpoint", "reachable": False, "live_verified": False,
            "mode": "unavailable", "models": [], "count": 0,
            "error": llm_config.redact(str(exc)),
            "remediation": "Check that base_url is a valid documented endpoint.",
            "deterministic_fallback": {"available": True,
                                       "module": "game_studio.understanding"},
        }

    models = listing.get("models") or []
    result = {
        "ok": True,
        "provider": name,
        "state": "reachable",
        "reachable": True,
        "live_verified": True,
        "mode": "live",
        "source": listing.get("source") or "live-discovery",
        "endpoint": listing.get("endpoint"),
        "models": models,
        "count": len(models),
        "capability_metadata_exposed": bool(listing.get("capability_metadata_exposed")),
        "model_level_policy": ("Capabilities not reported by the provider stay unknown; "
                               "a model name is never used as evidence."),
        "configured_model": cfg["model"],
        "configured_model_present": any(m.get("id") == cfg["model"] for m in models),
        "note": "Live model listing succeeded. This is not a generation or quality test.",
    }
    if name == "ollama":
        result["ollama"] = ollama_detection()
    return result


def catalog_snapshot(providers: list[str] | None = None) -> dict:
    """Configuration-only snapshot for reports and the diagnostics tool."""
    names = providers or list(llm_config.PROVIDERS)
    return {
        "ok": True,
        "mode": "configuration-only",
        "network_calls": 0,
        "providers": [provider_status(name) for name in names],
        "capability_report": capabilities.capability_report(),
        "note": ("No provider was contacted. Reachability and model lists are unknown "
                 "until discover_models runs with explicit approval."),
    }
