"""Execution modes and granular, least-privilege permissions.

Policy is stored per project in ``<project>/.game-studio/governance.json`` and
globally (for tools without a project, such as Meshy) in the studio config
directory. A project policy overrides the global one.

Modes never bypass mandatory boundaries:

* ``paid_generation`` and ``upload_content`` always require explicit approval.
* ``delete_files`` always requires explicit approval.
* an explicitly denied permission can never be granted by a mode.

The LLM/agent cannot grant itself permissions: every mutating governance call
requires ``confirm=true`` and is audited.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from . import config
from .util import ToolError, is_within, read_json, require_path, write_json

MODES = ("guided", "balanced", "autonomous")
PERMISSIONS = (
    "read_project",
    "create_files",
    "edit_files",
    "delete_files",
    "execute_process",
    "run_blender",
    "modify_engine_project",
    "download_assets",
    "external_api",
    "upload_content",
    "paid_generation",
    "build_game",
)
EFFECTS = ("allow", "ask", "deny")

GOVERNANCE_DIR = ".game-studio"
GOVERNANCE_FILE = "governance.json"

# allow / ask / deny per mode. Read is safe in every mode.
MODE_DEFAULTS: dict[str, dict[str, str]] = {
    "guided": {permission: "ask" for permission in PERMISSIONS},
    "balanced": {
        "read_project": "allow",
        "create_files": "allow",
        "edit_files": "allow",
        "delete_files": "ask",
        "execute_process": "ask",
        "run_blender": "allow",
        "modify_engine_project": "ask",
        "download_assets": "ask",
        "external_api": "ask",
        "upload_content": "ask",
        "paid_generation": "ask",
        "build_game": "allow",
    },
    "autonomous": {
        "read_project": "allow",
        "create_files": "allow",
        "edit_files": "allow",
        "delete_files": "ask",
        "execute_process": "allow",
        "run_blender": "allow",
        "modify_engine_project": "allow",
        "download_assets": "allow",
        "external_api": "allow",
        "upload_content": "ask",
        "paid_generation": "ask",
        "build_game": "allow",
    },
}
MODE_DEFAULTS["guided"]["read_project"] = "allow"

# These can never be auto-approved, regardless of mode or grants.
MANDATORY_APPROVAL = ("paid_generation", "upload_content", "delete_files")

DEFAULT_BUDGETS = {
    "max_paid_calls_per_day": 0,
    "max_external_calls_per_day": 100,
    "max_upload_bytes": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _policy_path(project: str | None) -> str:
    if project:
        return os.path.join(project, GOVERNANCE_DIR, GOVERNANCE_FILE)
    return os.path.join(config.config_dir(), "governance.json")


def _default_policy() -> dict:
    return {
        "schema_version": 1,
        "mode": "guided",
        "permissions": {},
        "budgets": dict(DEFAULT_BUDGETS),
        "grants": [],
        "updated_at": None,
    }


def _read(path: str) -> dict:
    policy = _default_policy()
    if os.path.isfile(path):
        try:
            data = read_json(path)
            if isinstance(data, dict):
                policy.update(data)
        except (OSError, ValueError):
            pass
    if policy.get("mode") not in MODES:
        policy["mode"] = "guided"
    budget = dict(DEFAULT_BUDGETS)
    budget.update(policy.get("budgets") or {})
    policy["budgets"] = budget
    return policy


def get_policy(project_path: str | None = None) -> dict:
    project = None
    if project_path:
        project = require_path(project_path, kind="dir", label="project_path")
    global_policy = _read(_policy_path(None))
    policy = _read(_policy_path(project)) if project else global_policy
    mode = policy.get("mode") or global_policy.get("mode") or "guided"
    if mode not in MODES:
        mode = "guided"
    permissions = dict(MODE_DEFAULTS[mode])
    # Global overrides apply first, then project overrides.
    for source in (global_policy, policy if project else {}):
        for permission, effect in (source.get("permissions") or {}).items():
            if permission in PERMISSIONS and effect in EFFECTS:
                permissions[permission] = effect
    budgets = dict(global_policy.get("budgets") or {})
    budgets.update(policy.get("budgets") or {})
    return {
        "ok": True,
        "project_path": project,
        "scope": "project" if project else "global",
        "mode": mode,
        "mode_source": ("project" if project and os.path.isfile(_policy_path(project))
                        else "global" if os.path.isfile(_policy_path(None)) else "default"),
        "permissions": permissions,
        "overrides": policy.get("permissions") or {},
        "budgets": budgets,
        "grants": policy.get("grants") or [],
        "policy_path": _policy_path(project),
        "mandatory_approval": list(MANDATORY_APPROVAL),
        "modes": {
            "guided": "Explain and ask before significant actions.",
            "balanced": "Perform safe reversible work; ask before risk, cost or architecture.",
            "autonomous": "Execute only user-granted permissions; never bypass mandatory gates.",
        },
        "note": "A mode is not a permission grant. Explicit deny always wins.",
    }


def _write(project: str | None, policy: dict) -> None:
    path = _policy_path(project)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    policy["schema_version"] = 1
    policy["updated_at"] = _now()
    write_json(path, policy)


def set_mode(mode: str, *, project_path: str | None = None,
             confirm: bool = False) -> dict:
    if mode not in MODES:
        raise ToolError(f"mode must be one of {list(MODES)}")
    if not confirm:
        raise ToolError("changing the execution mode requires explicit confirm=true")
    project = require_path(project_path, kind="dir", label="project_path") if project_path else None
    policy = _read(_policy_path(project))
    previous = policy.get("mode")
    policy["mode"] = mode
    _write(project, policy)
    config.audit("governance.mode", tool="set_execution_mode",
                 details={"mode": mode, "previous": previous,
                          "scope": "project" if project else "global"})
    effective = get_policy(project)
    return {
        "ok": True,
        "status": "completed",
        "mode": mode,
        "previous": previous,
        "scope": effective["scope"],
        "permissions": effective["permissions"],
        "note": "Mode changed. Denied permissions and mandatory approval still apply.",
    }


def set_permission(permission: str, effect: str, *, project_path: str | None = None,
                   confirm: bool = False, reason: str | None = None) -> dict:
    if permission not in PERMISSIONS:
        raise ToolError(f"permission must be one of {list(PERMISSIONS)}")
    if effect not in EFFECTS:
        raise ToolError(f"effect must be one of {list(EFFECTS)}")
    if effect == "allow" and permission in MANDATORY_APPROVAL:
        raise ToolError(
            f"{permission} cannot be set to allow; it always requires explicit per-action "
            "approval")
    if not confirm:
        raise ToolError("changing a permission requires explicit confirm=true")
    project = require_path(project_path, kind="dir", label="project_path") if project_path else None
    policy = _read(_policy_path(project))
    overrides = dict(policy.get("permissions") or {})
    previous = overrides.get(permission)
    overrides[permission] = effect
    policy["permissions"] = overrides
    grants = list(policy.get("grants") or [])
    if effect != "ask":
        grants.append({
            "permission": permission,
            "effect": effect,
            "reason": (reason or "")[:1000],
            "granted_at": _now(),
            "source": "user-confirmed",
        })
    policy["grants"] = grants[-200:]
    _write(project, policy)
    config.audit("governance.permission", tool="set_permission",
                 details={"permission": permission, "effect": effect,
                          "previous": previous,
                          "scope": "project" if project else "global"})
    return {
        "ok": True,
        "status": "completed",
        "permission": permission,
        "effect": effect,
        "previous": previous,
        "scope": "project" if project else "global",
    }


def authorize(permission: str, *, project_path: str | None = None,
              confirm: bool = False, action: str | None = None,
              paid: bool = False) -> dict:
    """Return an allow decision or raise ``ToolError``.

    Call this before the operation, not after. ``confirm`` must represent the
    user's explicit approval for this specific action.
    """
    if permission not in PERMISSIONS:
        raise ToolError(f"unknown permission: {permission}")
    project = None
    if project_path:
        project = require_path(project_path, kind="dir", label="project_path")
    policy = get_policy(project)
    effect = policy["permissions"].get(permission, "ask")
    mandatory = permission in MANDATORY_APPROVAL or paid
    if effect == "deny":
        config.audit("governance.denied", tool="authorize",
                     details={"permission": permission, "action": action or ""})
        raise ToolError(
            f"permission denied for {permission}; enable it with set_permission after "
            "reviewing the risk")
    if effect == "ask" and not confirm:
        raise ToolError(
            f"{permission} requires explicit confirm=true in {policy['mode']} mode"
            + (f" for {action}" if action else ""))
    if mandatory and not confirm:
        raise ToolError(
            f"{permission} always requires explicit per-action approval, including in "
            "autonomous mode")
    return {
        "ok": True,
        "permission": permission,
        "effect": effect,
        "mode": policy["mode"],
        "mandatory_approval": mandatory,
        "confirmed": bool(confirm),
        "scope": policy["scope"],
    }


def status(project_path: str | None = None) -> dict:
    policy = get_policy(project_path)
    policy["operation"] = "read"
    return policy


def _looks_like_policy(payload: dict) -> bool:
    return isinstance(payload.get("permissions"), dict)


def validate_policy_file(project_path: str) -> dict:
    """Used by tests and diagnostics; never mutates."""
    project = require_path(project_path, kind="dir", label="project_path")
    path = _policy_path(project)
    if not os.path.isfile(path):
        return {"ok": True, "found": False, "path": path}
    if not is_within(project, path):
        raise ToolError("governance path escapes the project")
    try:
        payload = read_json(path)
    except (OSError, ValueError) as exc:
        return {"ok": False, "found": True, "path": path, "error": str(exc)}
    return {"ok": _looks_like_policy(payload), "found": True, "path": path,
            "mode": payload.get("mode")}
