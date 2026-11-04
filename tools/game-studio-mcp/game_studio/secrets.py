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
