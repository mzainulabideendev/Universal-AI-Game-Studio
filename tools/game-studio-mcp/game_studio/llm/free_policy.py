"""Verified free-provider policy, quota basis and documentation evidence.

This module is deliberately static and performs no network I/O. It records what
the official provider documentation said on ``VERIFICATION_DATE``. A provider is
never relabelled free because a model name looks cheap: the status below is the
only accepted evidence, and anything undocumented stays ``unknown``.

Status vocabulary
-----------------
``verified_free``  Current official documentation states a free allowance with no
                    payment requirement and no expiry.
``free_limited``   Current official documentation states a free allowance that is
                    rate/token limited (or account dependent) and finite.
``local_free``     Software runs locally with no hosted billing (optional runtime).
``paid``           Officially paid; using it under free-only mode is refused.
``trial_only``     A one-off trial credit; not an ongoing free allowance.
``unknown``        Documentation could not be checked or does not state pricing.
``unavailable``    No usable API route.

``trial_only``, ``paid`` and ``unknown`` never satisfy free-only acceptance.
"""

from __future__ import annotations

SCHEMA_VERSION = 1
VERIFICATION_DATE = "2026-11-10"

FREE = "verified_free"
FREE_LIMITED = "free_limited"
LOCAL_FREE = "local_free"
PAID = "paid"
TRIAL_ONLY = "trial_only"
UNKNOWN = "unknown"
UNAVAILABLE = "unavailable"

STATUSES = (FREE, FREE_LIMITED, LOCAL_FREE, PAID, TRIAL_ONLY, UNKNOWN, UNAVAILABLE)
FREE_STATUSES = (FREE, FREE_LIMITED, LOCAL_FREE)


def is_free_status(status: str | None) -> bool:
    return (status or "").strip().lower() in FREE_STATUSES


def _caps(**values) -> dict:
    keys = ("text_generation", "structured_output", "json_mode", "tool_calling",
            "vision", "streaming", "embeddings", "context_window", "model_listing",
            "health_check", "image_generation", "texture_generation",
            "3d_mesh_generation")
    return {name: values.get(name, UNKNOWN) for name in keys}


# Provider-level capability declarations are about this repository's adapter as
# well as the documented service. Text adapters never imply image/texture/3D
# generation. Unknown is used where the adapter does not implement the feature
# and the vendor may; the adapter state still blocks routing.
PROVIDERS: dict[str, dict] = {
    "gemini": {
        "name": "Google Gemini Developer API",
        "kind": "hosted",
        "status": FREE_LIMITED,
        "integrated": True,
        "adapter": "gemini",
        "docs": [
            "https://ai.google.dev/gemini-api/docs/pricing",
            "https://ai.google.dev/gemini-api/docs/rate-limits",
            "https://ai.google.dev/gemini-api/docs/models",
        ],
        "verified_on": VERIFICATION_DATE,
        "billing_basis": {
            "requires_payment_info": False,
            "free_allowance": ("Free tier for selected Flash/Flash-Lite models with "
                               "free input and output tokens"),
            "quota_reliable": False,
            "quota_basis": ("Per-project RPM, TPM and RPD. Exact values are account and "
                            "model specific and are displayed in Google AI Studio; RPD "
                            "resets at midnight Pacific time."),
            "paid_upgrade_possible": True,
        },
        "eligible_models": [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
        ],
        "model_rule": ("The pricing page marks each model's Free Tier individually. Only "
                       "models explicitly marked 'Free of charge' are eligible; "
                       "gemini-4-argon and Pro preview models are documented as not "
                       "available on the free tier."),
        "capabilities": _caps(
            text_generation="supported", structured_output="supported",
            json_mode="supported", tool_calling="unsupported", vision="unsupported",
            streaming="unsupported", embeddings="unsupported",
            context_window="supported", model_listing="supported",
            health_check="supported", image_generation="unsupported",
            texture_generation="unsupported", **{"3d_mesh_generation": "unsupported"}),
        "restrictions": [
            "Free-tier content may be used to improve Google products (documented).",
            "Rate limits are applied per project, not per API key.",
            "Advanced models are paid only; automatic paid upgrade is forbidden.",
        ],
        "geographic": [
            "Availability follows Google's supported-regions list for the Gemini API; "
            "verify the account's region in AI Studio.",
        ],
        "privacy": [
            "Free-tier prompts/responses are documented as usable for product "
            "improvement; do not send proprietary project content without approval.",
        ],
        "auth": {"env_var": "GEMINI_API_KEY", "key_required": True},
        "live_test": {"authorized": False, "performed": False,
                      "reason": "No credential was provided and no live request was approved."},
        "confidence": "high",
    },
    "groq": {
        "name": "GroqCloud",
        "kind": "hosted",
        "status": FREE_LIMITED,
        "integrated": True,
        "adapter": "openai_compatible",
        "docs": [
            "https://console.groq.com/docs/rate-limits",
            "https://console.groq.com/docs/models",
            "https://console.groq.com/docs/structured-outputs",
        ],
        "verified_on": VERIFICATION_DATE,
        "billing_basis": {
            "requires_payment_info": False,
            "free_allowance": ("Free plan with per-model request and token limits; the "
                               "Free Plan tab documents the eligible models"),
            "quota_reliable": True,
            "quota_basis": ("Per-model RPM, RPD, TPM and TPD. HTTP 429 is returned when "
                            "a limit is exceeded; rate-limit headers are documented."),
            "paid_upgrade_possible": True,
        },
        "eligible_models": [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ],
        "model_limits": {
            "openai/gpt-oss-120b": {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
            "openai/gpt-oss-20b": {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
            "qwen/qwen3.8-27b": {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
        },
        "model_rule": ("Only models listed on the Free Plan tab are eligible. Fast "
                       "inference is not unlimited inference."),
        "capabilities": _caps(
            text_generation="supported", structured_output="supported",
            json_mode="supported", tool_calling="unsupported", vision="unsupported",
            streaming="unsupported", embeddings="unsupported",
            context_window="unknown", model_listing="supported",
            health_check="supported", image_generation="unsupported",
            texture_generation="unsupported", **{"3d_mesh_generation": "unsupported"}),
        "restrictions": [
            "Free-plan model catalogue and limits can change; re-verify before use.",
            "The adapter does not send tools, images or streaming requests.",
        ],
        "geographic": [
            "Service availability depends on GroqCloud's supported regions and account "
            "eligibility.",
        ],
        "privacy": [
            "Review GroqCloud's data-retention terms before sending project content.",
        ],
        "auth": {"env_var": "GROQ_API_KEY", "key_required": True},
        "live_test": {"authorized": False, "performed": False,
                      "reason": "No credential was provided and no live request was approved."},
        "confidence": "high",
    },
    "openrouter": {
        "name": "OpenRouter",
        "kind": "hosted",
        "status": FREE_LIMITED,
        "integrated": True,
        "adapter": "openai_compatible",
        "docs": [
            "https://openrouter.ai/docs/api-reference/limits",
            "https://openrouter.ai/docs/guides/overview/models",
            "https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties",
        ],
        "verified_on": VERIFICATION_DATE,
        "billing_basis": {
            "requires_payment_info": False,
            "free_allowance": ("Models whose id ends with ':free' are free-model "
                               "variants; paid variants are separate model ids"),
            "quota_reliable": True,
            "quota_basis": ("Free-model rate limit is 20 requests/minute. Daily free "
                            "requests are 50 for accounts with under 10 all-time "
                            "credits and 1000 for accounts with at least 10 credits. "
                            "GET /api/v1/key exposes free_model_daily_requests."),
            "paid_upgrade_possible": True,
        },
        "eligible_models": [],
        "model_rule": ("A model is eligible only when its id ends with ':free'. Never "
                       "route an OpenRouter request to a paid variant."),
        "free_suffix": ":free",
        "limits": {"rpm": 20, "rpd_without_credit": 50, "rpd_with_credits": 1000,
                   "credit_threshold": 10},
        "capabilities": _caps(
            text_generation="supported", structured_output="supported",
            json_mode="supported", tool_calling="unsupported", vision="unsupported",
            streaming="unsupported", embeddings="unsupported",
            context_window="unknown", model_listing="supported",
            health_check="supported", image_generation="unsupported",
            texture_generation="unsupported", **{"3d_mesh_generation": "unsupported"}),
        "restrictions": [
            "Daily free-request allowance depends on all-time credit purchases.",
            "Model availability and deprecation change frequently; discover the model "
            "list before use.",
            "Credit-purchase or paid-variant routing is refused under free-only mode.",
        ],
        "geographic": [
            "Availability depends on the upstream model provider and OpenRouter's "
            "routing rules.",
        ],
        "privacy": [
            "The upstream provider receives the request; review both OpenRouter and "
            "upstream data policies.",
        ],
        "auth": {"env_var": "OPENROUTER_API_KEY", "key_required": True},
        "live_test": {"authorized": False, "performed": False,
                      "reason": "No credential was provided and no live request was approved."},
        "confidence": "high",
    },
    "ollama": {
        "name": "Ollama (local runtime)",
        "kind": "local",
        "status": LOCAL_FREE,
        "integrated": True,
        "adapter": "ollama",
        "docs": [
            "https://docs.ollama.com/api/tags",
            "https://docs.ollama.com/api/generate",
            "https://docs.ollama.com/api/chat",
        ],
        "verified_on": VERIFICATION_DATE,
        "billing_basis": {
            "requires_payment_info": False,
            "free_allowance": "Local execution; no hosted per-request billing.",
            "quota_reliable": False,
            "quota_basis": ("Constrained by local CPU/RAM/GPU, not by a hosted quota. "
                            "No quota is claimed."),
            "paid_upgrade_possible": False,
        },
        "eligible_models": [],
        "model_rule": ("Any locally installed model may be used, but capabilities stay "
                       "unknown until /api/show or live discovery establishes them."),
        "capabilities": _caps(
            text_generation="supported", structured_output="supported",
            json_mode="supported", tool_calling="unsupported", vision="unsupported",
            streaming="unsupported", embeddings="unsupported",
            context_window="unknown", model_listing="supported",
            health_check="supported", image_generation="unsupported",
            texture_generation="unsupported", **{"3d_mesh_generation": "unsupported"}),
        "restrictions": [
            "This project never installs Ollama, starts the service or downloads a model.",
            "A reachable loopback service must be verified before use.",
            "Large models may not be practical on the documented 16 GB / integrated-GPU "
            "hardware; no performance claim is made without measurement.",
        ],
        "geographic": ["Runs wherever the local machine runs."],
        "privacy": ["Prompts stay on the local machine."],
        "auth": {"env_var": None, "key_required": False},
        "live_test": {"authorized": False, "performed": False,
                      "reason": "No local service was verified and nothing was started."},
        "confidence": "high",
    },
}

# Providers researched for asset generation only. They are not text providers and
# are never added to the routing registry.
ASSET_PROVIDERS: dict[str, dict] = {
    "pollinations": {
        "name": "Pollinations (Classic image API)",
        "status": FREE_LIMITED,
        "kind": "hosted-image",
        "docs": ["https://github.com/pollinations/pollinations/blob/master/APIDOCS.md"],
        "verified_on": VERIFICATION_DATE,
        "notes": [
            "Free, no signup documented; rate limited to roughly one request per 45 s.",
            "One model, JPEG output with a small logo; best-effort with no uptime guarantee.",
            "Not a texture-map, normal-map or 3D mesh service.",
        ],
        "requires_payment_info": False,
        "commercial_use": "Check the current project license/terms before commercial use.",
    },
    "stability": {
        "name": "Stability AI API",
        "status": TRIAL_ONLY,
        "kind": "hosted-image",
        "docs": ["https://platform.stability.ai/pricing"],
        "verified_on": VERIFICATION_DATE,
        "notes": ["25 free credits (1 credit = $0.01) then paid; this is a trial only."],
        "requires_payment_info": True,
    },
    "huggingface": {
        "name": "Hugging Face Inference Providers",
        "status": PAID,
        "kind": "hosted-inference",
        "docs": ["https://huggingface.co/docs/api-inference/pricing"],
        "verified_on": VERIFICATION_DATE,
        "notes": ["Free accounts receive no monthly credits; credits must be purchased."],
        "requires_payment_info": True,
    },
    "meshy": {
        "name": "Meshy API",
        "status": PAID,
        "kind": "hosted-3d",
        "docs": ["https://docs.meshy.ai/en/api/pricing"],
        "verified_on": VERIFICATION_DATE,
        "notes": ["Prepaid-credit 3D generation; no ongoing free API allowance."],
        "requires_payment_info": True,
    },
    "tripo": {
        "name": "Tripo API",
        "status": PAID,
        "kind": "hosted-3d",
        "docs": ["https://platform.tripo3d.ai/docs/pricing"],
        "verified_on": VERIFICATION_DATE,
        "notes": ["Usage-based paid credits for the hosted API."],
        "requires_payment_info": True,
    },
    "triposr": {
        "name": "TripoSR",
        "status": LOCAL_FREE,
        "kind": "local-3d",
        "docs": ["https://github.com/VAST-AI-Research/TripoSR"],
        "verified_on": VERIFICATION_DATE,
        "notes": ["Open-source image-to-3D model that must be installed and run locally; "
                  "this project does not download model weights or run it."],
        "requires_payment_info": False,
        "license": "MIT (verify the repository before redistribution)",
    },
}


def provider_status(provider: str) -> str:
    entry = PROVIDERS.get((provider or "").strip().lower())
    return entry["status"] if entry else UNKNOWN


def provider_entry(provider: str) -> dict:
    key = (provider or "").strip().lower()
    entry = PROVIDERS.get(key)
    if not entry:
        raise ValueError(f"unknown free-policy provider: {provider!r}")
    return {"provider": key, **entry}


def model_eligibility(provider: str, model: str | None,
                      *, account_credits: float | None = None) -> dict:
    """Return whether a model is eligible under the documented free allowance.

    Returns ``eligible`` as ``True``/``False``/``None``. ``None`` means the
    documentation does not establish eligibility, which free-only routing treats
    as a refusal (never as unlimited free use).
    """
    key = (provider or "").strip().lower()
    entry = PROVIDERS.get(key)
    name = (model or "").strip()
    if not entry:
        return {"eligible": None, "provider": key, "model": name,
                "reason": "provider is not in the free-provider catalog"}
    if entry["status"] not in FREE_STATUSES:
        return {"eligible": False, "provider": key, "model": name,
                "reason": f"provider status is {entry['status']!r}, not a free status"}
    if not name:
        return {"eligible": None, "provider": key, "model": name,
                "reason": "no model selected"}
    if key == "ollama":
        return {"eligible": True, "provider": key, "model": name,
                "reason": "local model; capability and resource suitability stay unverified"}
    if key == "openrouter":
        suffix = entry.get("free_suffix") or ":free"
        if name.endswith(suffix):
            return {"eligible": True, "provider": key, "model": name,
                    "reason": "model id uses the documented free-model suffix"}
        return {"eligible": False, "provider": key, "model": name,
                "reason": (f"OpenRouter model {name!r} does not end with {suffix!r}; "
                           "paid variants are refused")}
    if key == "groq":
        if name in entry.get("model_limits", {}):
            return {"eligible": True, "provider": key, "model": name,
                    "reason": "model is listed on the documented free plan"}
        return {"eligible": False, "provider": key, "model": name,
                "reason": "model is not in the documented Groq free-plan list"}
    if key == "gemini":
        if name in entry.get("eligible_models", []):
            return {"eligible": True, "provider": key, "model": name,
                    "reason": "model is documented with a free tier"}
        return {"eligible": False, "provider": key, "model": name,
                "reason": ("model is not in the documented free-tier list; check AI "
                           "Studio because eligibility is per model")}
    return {"eligible": None, "provider": key, "model": name,
            "reason": "free eligibility could not be established from documentation"}


def known_daily_limit(provider: str, model: str | None) -> int | None:
    """Return a documented daily request limit, or ``None`` when not exposed."""
    key = (provider or "").strip().lower()
    entry = PROVIDERS.get(key) or {}
    name = (model or "").strip()
    if key == "groq":
        limits = (entry.get("model_limits") or {}).get(name)
        return int(limits["rpd"]) if limits else None
    if key == "openrouter":
        return int(entry["limits"]["rpd_without_credit"])
    if key in ("gemini", "ollama"):
        # Gemini limits are account/project specific; Ollama has no hosted quota.
        return None
    return None


def catalog() -> dict:
    """Full free-provider catalog used by MCP and reports. No network calls."""
    providers = []
    for key in ("gemini", "groq", "openrouter", "ollama"):
        entry = provider_entry(key)
        providers.append({
            "provider": key,
            "name": entry["name"],
            "kind": entry["kind"],
            "status": entry["status"],
            "free": entry["status"] in FREE_STATUSES,
            "integrated": entry["integrated"],
            "adapter": entry["adapter"],
            "eligible_models": list(entry.get("eligible_models") or []),
            "model_rule": entry["model_rule"],
            "known_daily_limit": known_daily_limit(
                key, (entry.get("eligible_models") or [None])[0]),
            "requires_payment_info": entry["billing_basis"]["requires_payment_info"],
            "docs": list(entry["docs"]),
            "verified_on": entry["verified_on"],
            "confidence": entry["confidence"],
        })
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "verification_date": VERIFICATION_DATE,
        "statuses": {
            "verified_free": "Documented free allowance, no payment and no expiry.",
            "free_limited": "Documented finite free allowance, rate/token limited.",
            "local_free": "Local software with no hosted billing.",
            "paid": "Officially paid; refused under free-only mode.",
            "trial_only": "One-off trial credit; not an ongoing free allowance.",
            "unknown": "Not established; refused under free-only mode.",
            "unavailable": "No usable API route.",
        },
        "free_statuses": list(FREE_STATUSES),
        "providers": providers,
        "live_tests": {"authorized": 0, "performed": 0},
        "network_calls": 0,
        "note": ("Documentation evidence only. A configured credential is still required "
                 "for hosted providers, and no live provider request was made."),
    }


def evidence() -> dict:
    """Per-provider documentation evidence without secrets."""
    records = []
    for key in ("gemini", "groq", "openrouter", "ollama"):
        entry = provider_entry(key)
        records.append({
            "provider": key,
            "official_name": entry["name"],
            "documentation_urls": list(entry["docs"]),
            "verification_date": entry["verified_on"],
            "free_tier_status": entry["status"],
            "eligible_models": list(entry.get("eligible_models") or []),
            "model_rule": entry["model_rule"],
            "rate_limits": entry["billing_basis"]["quota_basis"],
            "quota_reliable_from_documentation": entry["billing_basis"]["quota_reliable"],
            "token_or_context_limits": (
                entry.get("model_limits") or entry.get("limits")
                or "not exposed by the documented free-tier summary"),
            "capabilities": dict(entry["capabilities"]),
            "restrictions": list(entry["restrictions"]),
            "geographic_limitations": list(entry["geographic"]),
            "privacy_considerations": list(entry["privacy"]),
            "authentication": dict(entry["auth"]),
            "requires_payment_info": entry["billing_basis"]["requires_payment_info"],
            "live_test_authorized": entry["live_test"]["authorized"],
            "live_test_performed": entry["live_test"]["performed"],
            "live_test_reason": entry["live_test"]["reason"],
            "verification_confidence": entry["confidence"],
        })
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "verification_date": VERIFICATION_DATE,
        "provider_count": len(records),
        "records": records,
        "secrets_recorded": False,
        "network_calls": 0,
        "note": ("Evidence comes from the official documentation URLs listed in each "
                 "record. No API key or account identifier is stored here."),
    }


def asset_provider_catalog() -> dict:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "verification_date": VERIFICATION_DATE,
        "providers": {key: {"provider": key, **value}
                      for key, value in ASSET_PROVIDERS.items()},
        "secrets_recorded": False,
        "network_calls": 0,
    }

