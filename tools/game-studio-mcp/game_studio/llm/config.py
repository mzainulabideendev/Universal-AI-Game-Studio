"""LLM provider configuration and secret-safe status reporting.

Configuration comes from environment variables or the studio's private config
file. Credentials are never written to project files, logs, manifests or tool
responses. A provider is never assumed to work because it was configured: the
status tool reports ``configured`` separately from ``verified``.
"""

from __future__ import annotations

import os
import re

from .. import config as studio_config
from ..util import safe_join

PROVIDERS = ("openai", "openai_compatible", "anthropic", "gemini", "ollama")

DEFAULTS: dict[str, dict] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
        "key_required": True,
        "local": False,
    },
    "openai_compatible": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_env": "GAME_STUDIO_LLM_API_KEY",
        "key_required": True,
        "local": False,
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet-latest",
        "key_env": "ANTHROPIC_API_KEY",
        "key_required": True,
        "local": False,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-1.5-flash",
        "key_env": "GEMINI_API_KEY",
        "key_required": True,
        "local": False,
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "llama3.1",
        "key_env": None,
        "key_required": False,
        "local": True,
    },
}

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|access[_-]?token|authorization)"
               r"\s*[:=]\s*(?:bearer\s+)?\S{6,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\bmsy_[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{10,}\b"),
)


def redact(text: object) -> str:
    """Remove credential-looking substrings before anything is logged/returned."""
    if text is None:
        return ""
    value = str(text)
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return max(minimum, value)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _stored() -> dict:
    path = os.path.join(studio_config.config_dir(), "llm.json")
    if not os.path.isfile(path):
        return {}
    try:
        import json
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _key_for(provider: str) -> tuple[str | None, str | None]:
    default = DEFAULTS[provider]
    shared = os.environ.get("GAME_STUDIO_LLM_API_KEY")
    if shared:
        return shared, "GAME_STUDIO_LLM_API_KEY"
    key_env = default.get("key_env")
    if key_env:
        value = os.environ.get(key_env)
        if value:
            return value, key_env
    return None, None


def load_config() -> dict:
    stored = _stored()
    provider = (os.environ.get("GAME_STUDIO_LLM_PROVIDER")
                or stored.get("provider") or "openai").strip().lower()
    if provider not in PROVIDERS:
        provider = "openai"
    default = DEFAULTS[provider]
    base_url = (os.environ.get("GAME_STUDIO_LLM_BASE_URL")
                or stored.get("base_url") or default["base_url"]).rstrip("/")
    model = (os.environ.get("GAME_STUDIO_LLM_MODEL")
             or stored.get("model") or default["model"])
    api_key, key_source = _key_for(provider)
    local_only = _env_bool("GAME_STUDIO_LLM_LOCAL_ONLY", False)
    return {
        "schema_version": 1,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "key_source": key_source,
        "key_env": default.get("key_env"),
        "key_required": bool(default.get("key_required")),
        "local_provider": bool(default.get("local")),
        "local_only": local_only,
        "timeout_seconds": _env_int("GAME_STUDIO_LLM_TIMEOUT", 60, minimum=5),
        "connect_timeout_seconds": _env_int("GAME_STUDIO_LLM_CONNECT_TIMEOUT", 10,
                                            minimum=2),
        "max_tokens": _env_int("GAME_STUDIO_LLM_MAX_TOKENS", 4096, minimum=128),
        "max_context_chars": _env_int("GAME_STUDIO_LLM_MAX_CONTEXT_CHARS", 64_000,
                                      minimum=4_000),
        "max_requests": _env_int("GAME_STUDIO_LLM_MAX_REQUESTS", 20, minimum=0),
        "max_requests_per_day": _env_int("GAME_STUDIO_LLM_MAX_REQUESTS_PER_DAY", 200,
                                         minimum=0),
        "retries": _env_int("GAME_STUDIO_LLM_RETRIES", 2, minimum=0),
        "backoff_seconds": _env_float("GAME_STUDIO_LLM_BACKOFF", 1.5, minimum=0.0),
        "temperature": _env_float("GAME_STUDIO_LLM_TEMPERATURE", 0.2, minimum=0.0),
        "cache_enabled": _env_bool("GAME_STUDIO_LLM_CACHE", False),
        "allow_project_content": _env_bool("GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT", False),
        "prompt_version": "1.0",
    }


def public_view(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    return {
        "provider": cfg["provider"],
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "local_provider": cfg["local_provider"],
        "local_only": cfg["local_only"],
        "api_key_configured": bool(cfg.get("api_key")),
        "api_key_source": cfg.get("key_source"),
        "key_env": cfg.get("key_env"),
        "timeouts": {
            "request_seconds": cfg["timeout_seconds"],
            "connect_seconds": cfg["connect_timeout_seconds"],
        },
        "budgets": {
            "max_tokens_per_request": cfg["max_tokens"],
            "max_context_chars": cfg["max_context_chars"],
            "max_requests_per_session": cfg["max_requests"],
            "max_requests_per_day": cfg["max_requests_per_day"],
        },
        "retries": cfg["retries"],
        "backoff_seconds": cfg["backoff_seconds"],
        "cache_enabled": cfg["cache_enabled"],
        "allow_project_content": cfg["allow_project_content"],
        "prompt_version": cfg["prompt_version"],
    }


def status() -> dict:
    cfg = load_config()
    view = public_view(cfg)
    missing = []
    if cfg["key_required"] and not cfg.get("api_key"):
        missing.append(f"set {cfg.get('key_env')} or GAME_STUDIO_LLM_API_KEY")
    providers = []
    for name in PROVIDERS:
        default = DEFAULTS[name]
        key, source = _key_for(name)
        providers.append({
            "provider": name,
            "kind": "local" if default.get("local") else "hosted",
            "default_model": default["model"],
            "default_base_url": default["base_url"],
            "credential_required": bool(default.get("key_required")),
            "credential_configured": bool(key),
            "credential_source": source,
            "implemented": True,
            "live_verified": None,
            "note": ("Live verification requires a real request; this status never "
                     "claims a provider works because it is configured."),
        })
    return {
        "ok": True,
        "configured": not missing,
        "selectable": True,
        "active": view,
        "providers": providers,
        "missing": missing,
        "env_example": {
            "GAME_STUDIO_LLM_PROVIDER": "ollama | openai | openai_compatible | anthropic | gemini",
            "GAME_STUDIO_LLM_MODEL": "provider model id",
            "GAME_STUDIO_LLM_BASE_URL": "optional custom endpoint",
            "GAME_STUDIO_LLM_API_KEY": "preferred shared key variable (never commit it)",
            "GAME_STUDIO_LLM_LOCAL_ONLY": "true blocks every hosted provider",
            "GAME_STUDIO_LLM_MAX_TOKENS": "per-request output budget",
            "GAME_STUDIO_LLM_MAX_CONTEXT_CHARS": "hard prompt-size limit before a request is refused",
            "GAME_STUDIO_LLM_MAX_REQUESTS_PER_DAY": "hard request budget",
            "GAME_STUDIO_LLM_CACHE": "true enables a local cache for non-sensitive prompts",
            "GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT": "must be true before project context is sent",
        },
        "privacy": {
            "default": "no project files are sent automatically",
            "project_content_requires": "allow_project_content=true and explicit approval",
            "local_only": "GAME_STUDIO_LLM_LOCAL_ONLY=true rejects hosted providers",
            "secrets": "keys are read from the environment and never returned",
        },
        "fallback": {
            "available": True,
            "module": "game_studio.understanding",
            "behaviour": "deterministic parsing when no provider is configured or the "
                         "provider fails; the response says which path produced it",
        },
    }


def provider_allowed(cfg: dict) -> tuple[bool, str | None]:
    if cfg["local_only"] and not cfg["local_provider"]:
        return False, ("local-only mode is enabled, so the hosted provider "
                       f"{cfg['provider']!r} is refused")
    if cfg["key_required"] and not cfg.get("api_key"):
        return False, (f"no API key configured for {cfg['provider']!r}; set "
                       f"{cfg.get('key_env')} or GAME_STUDIO_LLM_API_KEY")
    return True, None


def cache_path() -> str:
    return os.path.join(studio_config.config_dir(), "llm-cache")


def budget_path() -> str:
    return os.path.join(studio_config.config_dir(), "llm-budget.json")


def ensure_inside_studio(path: str) -> str:
    return safe_join(studio_config.config_dir(), path)
