"""Local secret handling for optional provider API keys.

Secrets are never written into the repository, the studio config file or the
audit log. Resolution order for the Meshy key is:

1. an explicit value passed to a function (not used by MCP tools),
2. the ``MESHY_API_KEY`` environment variable of the server process,
3. a private file under the studio config directory.

The private file lets a user rotate the key from inside the MCP session without
editing client configuration. The environment variable always wins, so a user
who prefers environment-only configuration can ignore the file entirely.
"""

from __future__ import annotations

import os
import stat

from . import config
from .util import ToolError, now_iso, read_json, write_json

MESHY_ENV = "MESHY_API_KEY"
MAX_KEY_LENGTH = 512


def secrets_dir() -> str:
    return os.path.join(config.config_dir(), "secrets")


def meshy_key_file() -> str:
    return os.path.join(secrets_dir(), "meshy.json")


def validate_api_key(value: str | None, *, label: str = "api_key") -> str:
    if not isinstance(value, str):
        raise ToolError(f"{label} must be a string")
    cleaned = value.strip()
    if len(cleaned) < 10:
        raise ToolError(f"{label} is too short to be a Meshy API key")
    if len(cleaned) > MAX_KEY_LENGTH:
        raise ToolError(f"{label} must be at most {MAX_KEY_LENGTH} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise ToolError(f"{label} must not contain control characters or newlines")
    return cleaned


def load_local_meshy_key() -> str | None:
    path = meshy_key_file()
    if not os.path.isfile(path):
        return None
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("meshy_api_key")
    if not isinstance(value, str):
        return None
    try:
        return validate_api_key(value)
    except ToolError:
        return None


def resolve_meshy_key(explicit: str | None = None) -> str | None:
    if explicit:
        return validate_api_key(explicit)
    env_value = os.environ.get(MESHY_ENV, "").strip()
    if env_value:
        return env_value
    return load_local_meshy_key()


def meshy_key_source() -> str | None:
    if os.environ.get(MESHY_ENV, "").strip():
        return "environment"
    if load_local_meshy_key():
        return "local-file"
    return None


def save_meshy_key(value: str) -> dict:
    key = validate_api_key(value)
    path = meshy_key_file()
    os.makedirs(secrets_dir(), exist_ok=True)
    write_json(path, {
        "schema_version": 1,
        "meshy_api_key": key,
        "saved_at": now_iso(),
        "note": "Private local Meshy key. Never commit this file. The MESHY_API_KEY "
                "environment variable overrides it.",
    })
    # Best effort on POSIX. On Windows the file stays under the user profile.
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return {"path": path, "source": "local-file"}


def clear_local_meshy_key() -> bool:
    path = meshy_key_file()
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


# ---------------------------------------------------------------------------
# LLM provider credentials (V6 Phase 1)
#
# Resolution order for a provider key is:
#   1. GAME_STUDIO_LLM_API_KEY (shared override),
#   2. the provider's documented environment variable,
#   3. a private machine-local file under the studio config directory.
#
# Values are never written to project files, the studio config, the audit log or
# any tool response.
# ---------------------------------------------------------------------------
LLM_PROVIDERS = ("openai", "openai_compatible", "anthropic", "gemini", "ollama")
LLM_ENV_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "openai_compatible": "GAME_STUDIO_LLM_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": None,
}


def llm_key_file() -> str:
    return os.path.join(secrets_dir(), "llm.json")


def _validate_llm_provider(provider: str) -> str:
    name = (provider or "").strip().lower()
    if name not in LLM_PROVIDERS:
        raise ToolError(f"unknown provider {provider!r}")
    return name


def validate_llm_key(value: str | None, *, provider: str = "provider") -> str:
    if not isinstance(value, str):
        raise ToolError(f"{provider} api_key must be a string")
    cleaned = value.strip()
    if len(cleaned) < 8:
        raise ToolError(f"{provider} api_key is too short")
    if len(cleaned) > MAX_KEY_LENGTH:
        raise ToolError(f"{provider} api_key must be at most {MAX_KEY_LENGTH} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise ToolError(f"{provider} api_key must not contain control characters or newlines")
    return cleaned


def _load_llm_key_file() -> dict:
    path = llm_key_file()
    if not os.path.isfile(path):
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    keys = data.get("keys")
    return keys if isinstance(keys, dict) else {}


def load_local_llm_key(provider: str) -> str | None:
    name = _validate_llm_provider(provider)
    value = _load_llm_key_file().get(name)
    if not isinstance(value, str):
        return None
    try:
        return validate_llm_key(value, provider=name)
    except ToolError:
        return None


def llm_key_source(provider: str) -> str | None:
    name = _validate_llm_provider(provider)
    if os.environ.get("GAME_STUDIO_LLM_API_KEY", "").strip():
        return "GAME_STUDIO_LLM_API_KEY"
    key_env = LLM_ENV_BY_PROVIDER.get(name)
    if key_env and os.environ.get(key_env, "").strip():
        return key_env
    if load_local_llm_key(name):
        return "local-file"
    return None


def save_llm_key(provider: str, value: str) -> dict:
    name = _validate_llm_provider(provider)
    key = validate_llm_key(value, provider=name)
    keys = dict(_load_llm_key_file())
    keys[name] = key
    path = llm_key_file()
    os.makedirs(secrets_dir(), exist_ok=True)
    write_json(path, {
        "schema_version": 1,
        "keys": keys,
        "saved_at": now_iso(),
        "note": "Private machine-local LLM keys. Never commit this file. Environment "
                "variables override these values.",
    })
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return {"path": path, "source": "local-file", "provider": name}


def clear_llm_key(provider: str) -> bool:
    name = _validate_llm_provider(provider)
    keys = dict(_load_llm_key_file())
    if name not in keys:
        return False
    keys.pop(name, None)
    if keys:
        write_json(llm_key_file(), {
            "schema_version": 1,
            "keys": keys,
            "saved_at": now_iso(),
            "note": "Private machine-local LLM keys. Never commit this file.",
        })
    else:
        try:
            os.remove(llm_key_file())
        except OSError:
            pass
    return True

