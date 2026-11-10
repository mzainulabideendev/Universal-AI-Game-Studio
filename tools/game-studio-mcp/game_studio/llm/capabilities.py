"""Typed provider/model capability model.

Capabilities are deliberately tri-state: ``supported``, ``unsupported`` and
``unknown``. Nothing here infers a capability from a model or provider name.
Provider-level states describe what the adapters in this repository actually
implement. Model-level states start as ``unknown`` and are only upgraded when a
documented discovery response exposes the information (for example Gemini's
``supportedGenerationMethods`` and token limits).

A downstream router may use a capability that is ``unknown`` only by labelling
it unverified. It must never select a candidate whose required capability is
known to be ``unsupported``.
"""

from __future__ import annotations

SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
UNKNOWN = "unknown"
STATES = (SUPPORTED, UNSUPPORTED, UNKNOWN)

CAPABILITY_KEYS = (
    "text_generation",
    "structured_output",
    "json_mode",
    "tool_calling",
    "vision",
    "streaming",
    "embeddings",
    "context_window",
    "model_listing",
    "health_check",
    "image_generation",
    "texture_generation",
    "3d_mesh_generation",
)

CAPABILITY_LABELS = {
    "text_generation": "Text generation (chat/completion)",
    "structured_output": "Structured JSON output requested by the adapter",
    "json_mode": "Provider JSON mode parameter",
    "tool_calling": "Function/tool calling",
    "vision": "Image input",
    "streaming": "Streaming responses",
    "embeddings": "Embeddings",
    "context_window": "Context window size",
    "model_listing": "Model discovery endpoint implemented",
    "health_check": "Reachability/health check implemented",
    "image_generation": "Text-to-image generation through this adapter",
    "texture_generation": "Texture/material map generation through this adapter",
    "3d_mesh_generation": "3D mesh generation through this adapter",
}

TASK_CATEGORIES = {
    "game_design_reasoning": {
        "description": "Understand a game request, extract requirements and design a game loop.",
        "required_capabilities": ["text_generation", "structured_output"],
    },
    "technical_architecture": {
        "description": "Choose engines, dependencies, performance and platform architecture.",
        "required_capabilities": ["text_generation", "structured_output"],
    },
    "code_generation": {
        "description": "Draft gameplay code or engine scripts from an approved plan.",
        "required_capabilities": ["text_generation"],
    },
    "character_environment_planning": {
        "description": "Plan characters, environments, materials, rigs and animation sets.",
        "required_capabilities": ["text_generation", "structured_output"],
    },
    "asset_analysis": {
        "description": "Reason about existing asset inventories and validation evidence.",
        "required_capabilities": ["text_generation"],
    },
    "qa_verification": {
        "description": "Review test evidence and produce a verification assessment.",
        "required_capabilities": ["text_generation", "structured_output"],
    },
}

# Provider-level facts. These describe the code in ``providers.py`` today, not a
# vendor marketing claim. Where an adapter lacks a wire implementation the state
# is ``unsupported`` even if the vendor's API supports it.
_PROVIDER_PROFILES: dict[str, dict] = {
    "openai": {
        "kind": "hosted",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": SUPPORTED,
            "json_mode": SUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": UNKNOWN,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "The adapter does not send tool/function definitions.",
            "The adapter sends text-only message content; image input is not implemented.",
            "Responses are non-streaming.",
            "Context window is not exposed by the documented model-list payload.",
        ],
    },
    "openai_compatible": {
        "kind": "hosted",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": SUPPORTED,
            "json_mode": SUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": UNKNOWN,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "Capabilities depend on the third-party endpoint, so only adapter-level "
            "behaviour is claimed.",
            "The adapter does not send tool/function definitions, images or streams.",
        ],
    },
    "anthropic": {
        "kind": "hosted",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": UNSUPPORTED,
            "json_mode": UNSUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": UNKNOWN,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "No JSON-mode parameter is sent by the adapter; structured output is not "
            "requested through a documented provider control.",
            "No tool, image or streaming support in the adapter.",
            "Context window is not exposed by the documented model-list payload.",
        ],
    },
    "gemini": {
        "kind": "hosted",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": SUPPORTED,
            "json_mode": SUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": SUPPORTED,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "The adapter does not send tools, inline image parts or streams.",
            "Model context window is only known after discovery returns token limits.",
        ],
    },
    "groq": {
        "kind": "hosted",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": SUPPORTED,
            "json_mode": SUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": UNKNOWN,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "Uses the OpenAI-compatible adapter; no tools, images or streaming are sent.",
            "Free-plan model eligibility and limits are documented per model and must be "
            "re-verified before use.",
        ],
    },
    "openrouter": {
        "kind": "hosted",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": SUPPORTED,
            "json_mode": SUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": UNKNOWN,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "Uses the OpenAI-compatible adapter; no tools, images or streaming are sent.",
            "Only model ids ending in ':free' are eligible; paid variants are refused.",
            "Free-model availability and daily allowance depend on the account.",
        ],
    },
    "ollama": {
        "kind": "local",
        "capabilities": {
            "text_generation": SUPPORTED,
            "structured_output": SUPPORTED,
            "json_mode": SUPPORTED,
            "tool_calling": UNSUPPORTED,
            "vision": UNSUPPORTED,
            "streaming": UNSUPPORTED,
            "embeddings": UNSUPPORTED,
            "context_window": UNKNOWN,
            "model_listing": SUPPORTED,
            "health_check": SUPPORTED,
        },
        "limitations": [
            "Ollama is optional and is never installed or started by this project.",
            "A reachable service must be verified before use.",
            "Individual local models may not support JSON mode; the adapter requests it "
            "but model-level support stays unknown unless discovery reports it.",
            "The adapter does not send tools, images or streams.",
        ],
    },
}

# These adapters are text-only by design. A text model never implies image,
# texture or 3D generation, so the adapter-level state is explicitly unsupported.
for _profile in _PROVIDER_PROFILES.values():
    for _name in ("image_generation", "texture_generation", "3d_mesh_generation"):
        _profile["capabilities"].setdefault(_name, UNSUPPORTED)


MODEL_CAPABILITY_KEYS = (
    "text_generation",
    "structured_output",
    "json_mode",
    "tool_calling",
    "vision",
    "streaming",
    "embeddings",
    "image_generation",
    "texture_generation",
    "3d_mesh_generation",
)


def provider_profile(provider: str) -> dict:
    """Return a copy of the adapter-level capability profile for one provider."""
    key = (provider or "").strip().lower()
    profile = _PROVIDER_PROFILES.get(key)
    if not profile:
        raise ValueError(f"unknown provider: {provider!r}")
    return {
        "provider": key,
        "kind": profile["kind"],
        "capabilities": dict(profile["capabilities"]),
        "capabilities_with_state": {
            name: capability_state(name, profile["capabilities"].get(name))
            for name in CAPABILITY_KEYS
        },
        "limitations": list(profile["limitations"]),
        "note": ("Provider-level states describe the adapter implementation in this "
                 "repository. Model-level support is discovered separately and is "
                 "unknown when the provider does not expose it."),
    }


def capability_state(name: str, state: str | None) -> dict:
    """Wrap a raw state string in the documented tri-state object."""
    if state not in STATES:
        state = UNKNOWN
    return {"state": state, "capability": name,
            "label": CAPABILITY_LABELS.get(name, name)}


def model_capabilities(*, text_generation: str | None = None,
                       structured_output: str | None = None,
                       json_mode: str | None = None,
                       tool_calling: str | None = None,
                       vision: str | None = None,
                       streaming: str | None = None,
                       embeddings: str | None = None,
                       image_generation: str | None = None,
                       texture_generation: str | None = None,
                       mesh_generation: str | None = None,
                       context_window: dict | None = None) -> dict:
    """Build a model-level capability object; unspecified values are unknown."""
    explicit = {
        "text_generation": text_generation,
        "structured_output": structured_output,
        "json_mode": json_mode,
        "tool_calling": tool_calling,
        "vision": vision,
        "streaming": streaming,
        "embeddings": embeddings,
        "image_generation": image_generation,
        "texture_generation": texture_generation,
        "3d_mesh_generation": mesh_generation,
    }
    capabilities = {
        name: explicit[name] if explicit[name] in STATES else UNKNOWN
        for name in MODEL_CAPABILITY_KEYS
    }
    window = context_window or {}
    window_state = window.get("state")
    capabilities["context_window"] = {
        "state": window_state if window_state in STATES else UNKNOWN,
        "value": window.get("value") if window_state == SUPPORTED else None,
    }
    return capabilities


def unknown_model_capabilities() -> dict:
    """Every model-level capability is unknown until a documented source says otherwise."""
    return model_capabilities()


def capability_report() -> dict:
    """Provider-independent capability report. Never performs network I/O."""
    providers = [provider_profile(name) for name in _PROVIDER_PROFILES]
    return {
        "ok": True,
        "schema_version": 1,
        "states": {
            "supported": "The adapter implements and tests this capability.",
            "unsupported": "The adapter does not implement this capability.",
            "unknown": "No documented source established the state; do not assume it.",
        },
        "capability_keys": list(CAPABILITY_KEYS),
        "task_categories": {
            name: {
                "description": value["description"],
                "required_capabilities": list(value["required_capabilities"]),
            }
            for name, value in TASK_CATEGORIES.items()
        },
        "providers": providers,
        "model_level": {
            "default": "unknown",
            "rule": ("A model name is never used as evidence. Only documented discovery "
                     "fields can set a model capability to supported or unsupported."),
        },
        "network_calls": 0,
        "live_verified": None,
        "note": ("Provider capabilities are adapter facts recorded without contacting a "
                 "provider. Live reachability and model lists require llm_list_models "
                 "with confirm=true."),
    }
