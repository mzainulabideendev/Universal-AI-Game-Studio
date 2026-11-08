#!/usr/bin/env python3
"""Universal AI Game Studio MCP server (stdio, dependency-free).

The server exposes real tools for detection, Blender automation, Meshy tasks,
licensed asset search, animation inspection and engine staging/build commands.
Tools that need credentials or extra confirmation return explicit errors rather
than simulated successes.

Run:
    python tools/game-studio-mcp/server.py

Configure your MCP client to start that command with the desired environment
variables (MESHY_API_KEY, SKETCHFAB_TOKEN, optional BLENDER_EXE, GAME_STUDIO_HOME).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback

from game_studio import SERVER_NAME, SERVER_VERSION, PROTOCOL_VERSION
from game_studio import (
    animations, assets, blender, character_pipeline, character_spec, config, detect,
    engines, environment_pipeline, environment_spec, governance, manifest, meshy,
    operations, projects, secrets, specification, understanding, verification,
)
from game_studio.llm import config as llm_config
from game_studio.llm import capabilities as llm_capabilities
from game_studio.llm import catalog as llm_catalog
from game_studio.llm import reasoning as llm_reasoning
from game_studio.llm import routing as llm_routing
from game_studio.llm.client import LLMError
from game_studio.agents import Orchestrator as AgentOrchestrator
from game_studio.agents.helpers import QUALITY_PROFILES
from game_studio.util import ToolError, now_iso

MAX_TEXT = 200_000
LOG_PREFIX = "[universal-game-studio]"
_write_lock = threading.Lock()


def log(message: str) -> None:
    print(f"{LOG_PREFIX} {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# argument helpers
# --------------------------------------------------------------------------
def _str(args: dict, key: str, *, required: bool = False, default: str | None = None,
         max_length: int = 4096) -> str | None:
    value = args.get(key, default)
    if value is None:
        if required:
            raise ToolError(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise ToolError(f"{key} is required")
    if len(value) > max_length:
        raise ToolError(f"{key} must be at most {max_length} characters")
    return value or None


def _int(args: dict, key: str, *, default: int | None = None,
         minimum: int | None = None, maximum: int | None = None) -> int | None:
    value = args.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ToolError(f"{key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ToolError(f"{key} must be at most {maximum}")
    return value


def _float(args: dict, key: str, *, default: float | None = None,
           minimum: float | None = None, maximum: float | None = None) -> float | None:
    value = args.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError(f"{key} must be a number")
    value = float(value)
    if minimum is not None and value < minimum:
        raise ToolError(f"{key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ToolError(f"{key} must be at most {maximum}")
    return value


def _bool(args: dict, key: str, *, default: bool = False) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise ToolError(f"{key} must be a boolean")
    return value


def _list(args: dict, key: str) -> list | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ToolError(f"{key} must be an array")
    return value


def _obj(args: dict, key: str, *, required: bool = False) -> dict | None:
    value = args.get(key)
    if value is None:
        if required:
            raise ToolError(f"{key} is required")
        return None
    if not isinstance(value, dict):
        raise ToolError(f"{key} must be an object")
    return value


# --------------------------------------------------------------------------
# studio tools
# --------------------------------------------------------------------------
def tool_studio_info(args: dict) -> dict:
    cfg = config.load_config()
    return {
        "ok": True,
        "server": {"name": SERVER_NAME, "version": SERVER_VERSION,
                   "protocol": PROTOCOL_VERSION, "generated_at": now_iso()},
        "platform": detect.platform_name() if hasattr(detect, "platform_name") else os.name,
        "config_path": config.config_path(),
        "audit_path": config.audit_path(),
        "download_root": cfg.get("download_root"),
        "selected_engine": cfg.get("selected_engine"),
        "selected_engine_path": cfg.get("selected_engine_path"),
        "integrations": {
            "meshy": {"configured": bool(secrets.meshy_key_source()),
                      "source": secrets.meshy_key_source(),
                      "env": "MESHY_API_KEY",
                      "setup_tool": "meshy_setup_guide"},
            "sketchfab": {"configured": bool(os.environ.get("SKETCHFAB_TOKEN")),
                          "env": "SKETCHFAB_TOKEN"},
            "blender": {"configured": bool(blender.resolve_blender())},
        },
        "secrets_note": "Credential values are never stored in the config or returned by tools.",
        "confirmation_model": {
            "confirm_required": [
                "Meshy generation, rigging and animation tasks (credits)",
                "Poly Haven downloads and asset staging (writes files)",
                "Unity batch refresh, tests, builds and editor commands",
                "Godot import and export",
                "blender_run_python (arbitrary code)",
            ],
            "overwrite_requires": "confirm_overwrite=true on export/render/stage when the target exists",
        },
    }


def tool_detect_system(args: dict) -> dict:
    return {"ok": True, **detect.inspect_system()}


def tool_detect_game_engines(args: dict) -> dict:
    discover_projects = _bool(args, "discover_projects", default=True)
    roots = _list(args, "roots")
    return detect.detect_game_engines(discover=discover_projects, roots=roots)


def tool_list_available_engines(args: dict) -> dict:
    return engines.list_available_engines()


def tool_select_game_engine(args: dict) -> dict:
    return engines.select_engine(
        _str(args, "engine", required=True),
        engine_path=_str(args, "engine_path"),
        persist=_bool(args, "persist", default=True),
    )


def tool_inspect_engine_capabilities(args: dict) -> dict:
    return engines.inspect_engine_capabilities(_str(args, "engine"))


def tool_inspect_game_project(args: dict) -> dict:
    return projects.inspect_game_project(
        _str(args, "project_path", required=True),
        include_editor_status=_bool(args, "include_editor_status", default=False),
    )


def tool_configure_studio(args: dict) -> dict:
    updates: dict = {}
    for key in ("selected_engine", "selected_engine_path", "blender_exe", "unity_exe",
                "unreal_editor_cmd", "godot_exe", "download_root"):
        value = _str(args, key)
        if value is not None:
            updates[key] = value
    if "project_roots" in args:
        roots = _list(args, "project_roots")
        updates["project_roots"] = [str(root) for root in (roots or [])]
    if "allow_overwrite" in args:
        updates["allow_overwrite"] = _bool(args, "allow_overwrite")
    if not updates:
        raise ToolError("provide at least one configuration value to change")
    try:
        saved = config.save_config(updates)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    config.audit("studio.configure", tool="configure_studio",
                 details={"keys": sorted(updates)})
    return {
        "ok": True,
        "config_path": config.config_path(),
        "updated_keys": sorted(updates),
        "config": {key: saved.get(key) for key in
                   ("selected_engine", "selected_engine_path", "project_roots",
                    "blender_exe", "unity_exe", "unreal_editor_cmd", "godot_exe",
                    "download_root", "allow_overwrite")},
    }


def tool_list_studio_projects(args: dict) -> dict:
    roots = _list(args, "roots")
    found = detect.discover_projects(roots)
    return {"ok": True, "count": len(found), "projects": found,
            "roots": roots or config.load_config().get("project_roots")}


def tool_read_studio_audit(args: dict) -> dict:
    limit = _int(args, "limit", default=50, minimum=1, maximum=1000)
    records = config.read_audit(limit or 50)
    return {"ok": True, "count": len(records), "records": records,
            "path": config.audit_path()}


# --------------------------------------------------------------------------
# Request understanding, specification and project memory
# --------------------------------------------------------------------------
def _installed_engines(args: dict) -> list[str] | None:
    explicit = _list(args, "installed_engines")
    if explicit is not None:
        return [str(item).lower() for item in explicit
                if str(item).lower() in engines.ENGINES]
    if _bool(args, "detect_environment", default=False):
        return engines.list_available_engines().get("available", [])
    return None


def tool_analyze_game_request(args: dict) -> dict:
    request = _str(args, "request", required=True, max_length=20_000)
    result = understanding.analyze_request(
        request or "",
        installed_engines=_installed_engines(args),
        known_engine=_str(args, "engine") or config.load_config().get("selected_engine"),
        known_platform=_str(args, "platform"),
    )
    # Internal convenience keys are not part of the public contract.
    result.pop("_concepts", None)
    result.pop("_matched", None)
    config.audit("request.analyzed", tool="analyze_game_request",
                 details={"characters": result["understanding"]["characters"],
                          "genre": result["understanding"]["game_genre"],
                          "requirement_count": result["counts"]["all"]})
    return result


def tool_create_game_specification(args: dict) -> dict:
    request = _str(args, "request", required=True, max_length=20_000)
    spec = specification.create_specification(
        request=request,
        project_name=_str(args, "project_name"),
        engine=_str(args, "engine"),
        platform=_str(args, "platform"),
        dimension=_str(args, "dimension"),
        art_style=_str(args, "art_style"),
        scope=_str(args, "scope"),
        installed_engines=_installed_engines(args),
        known_engine=config.load_config().get("selected_engine"),
        approved=_bool(args, "approved"),
    )
    config.audit("specification.created", tool="create_game_specification",
                 details={"spec_id": spec["spec_id"],
                          "engine": spec["engine"]["selected"],
                          "requirements": len(spec["requirements"])})
    return spec


def tool_init_project_manifest(args: dict) -> dict:
    spec = args.get("spec")
    if not isinstance(spec, dict):
        raise ToolError("spec must be the object returned by create_game_specification")
    confirm = _bool(args, "confirm")
    _authorize(args, "create_files", action="write project manifest", confirm=confirm)
    result = manifest.init_manifest(
        _str(args, "project_path", required=True) or "",
        spec,
        confirm=confirm,
        overwrite=_bool(args, "overwrite"),
    )
    config.audit("manifest.initialized", tool="init_project_manifest",
                 details={"project": result.get("project_id"),
                          "revision": result.get("revision")})
    return result


def tool_get_project_manifest(args: dict) -> dict:
    return manifest.load_manifest_view(_str(args, "project_path", required=True) or "")


def tool_update_requirement_status(args: dict) -> dict:
    evidence = _list(args, "evidence")
    confirm = _bool(args, "confirm")
    _authorize(args, "edit_files", action="update requirement status", confirm=confirm)
    result = manifest.update_requirement_status(
        _str(args, "project_path", required=True) or "",
        _str(args, "requirement_id", required=True) or "",
        _str(args, "status", required=True) or "",
        evidence=evidence,
        note=_str(args, "note", max_length=4000),
        confirm=confirm,
    )
    config.audit("requirement.status", tool="update_requirement_status",
                 details={"project": result.get("requirement_id"),
                          "status": result.get("current")})
    return result


def tool_record_project_decision(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    _authorize(args, "edit_files", action="record project decision", confirm=confirm)
    result = manifest.record_decision(
        _str(args, "project_path", required=True) or "",
        topic=_str(args, "topic", required=True) or "",
        decision=_str(args, "decision", required=True) or "",
        rationale=_str(args, "rationale", max_length=4000),
        source=_str(args, "source", default="user") or "user",
        approved=_bool(args, "approved"),
        confirm=confirm,
    )
    config.audit("decision.recorded", tool="record_project_decision",
                 details={"topic": result["decision"]["topic"]})
    return result


def tool_track_project_progress(args: dict) -> dict:
    return manifest.track_progress(_str(args, "project_path", required=True) or "")


def tool_compare_requirements(args: dict) -> dict:
    return manifest.compare_project_against_requirements(
        _str(args, "project_path", required=True) or "",
        inspect_project=_bool(args, "inspect_project", default=True),
    )


# --------------------------------------------------------------------------
# Execution modes, permissions and operations
# --------------------------------------------------------------------------
def _project_arg(args: dict) -> str | None:
    value = _str(args, "project_path")
    return value or None


def _authorize(args: dict, permission: str, *, action: str,
               confirm: bool | None = None) -> dict:
    return governance.authorize(
        permission,
        project_path=_project_arg(args),
        confirm=_bool(args, "confirm") if confirm is None else confirm,
        action=action,
    )


def tool_get_execution_mode(args: dict) -> dict:
    return governance.status(_project_arg(args))


def tool_set_execution_mode(args: dict) -> dict:
    return governance.set_mode(
        _str(args, "mode", required=True) or "",
        project_path=_project_arg(args),
        confirm=_bool(args, "confirm"),
    )


def tool_set_permission(args: dict) -> dict:
    return governance.set_permission(
        _str(args, "permission", required=True) or "",
        _str(args, "effect", required=True) or "",
        project_path=_project_arg(args),
        confirm=_bool(args, "confirm"),
        reason=_str(args, "reason", max_length=1000),
    )


def tool_list_operations(args: dict) -> dict:
    return operations.list_operations(
        limit=_int(args, "limit", default=50, minimum=1, maximum=200) or 50,
        include_terminal=_bool(args, "include_terminal", default=True),
    )


def tool_get_operation(args: dict) -> dict:
    return operations.get_operation(_str(args, "operation_id", required=True) or "")


def tool_cancel_operation(args: dict) -> dict:
    return operations.request_cancel(
        _str(args, "operation_id", required=True) or "",
        confirm=_bool(args, "confirm"),
        reason=_str(args, "reason", max_length=1000),
    )


def tool_cleanup_operation(args: dict) -> dict:
    return operations.cleanup_operation(
        _str(args, "operation_id", required=True) or "",
        confirm=_bool(args, "confirm"),
        temp_dir=_str(args, "temp_dir"),
    )


def tool_operation_status(args: dict) -> dict:
    return operations.status()


def tool_recover_operations(args: dict) -> dict:
    return operations.recover_interrupted()


# --------------------------------------------------------------------------
# Evidence verification
# --------------------------------------------------------------------------
def tool_inspect_requirement_evidence(args: dict) -> dict:
    return verification.inspect_requirement_evidence(
        _str(args, "project_path", required=True) or "",
        requirement_id=_str(args, "requirement_id"),
    )


def tool_run_requirement_verification(args: dict) -> dict:
    command = _list(args, "command")
    if command is not None and not all(isinstance(part, str) for part in command):
        raise ToolError("command must be an array of strings")
    return verification.run_requirement_verification(
        _str(args, "project_path", required=True) or "",
        _str(args, "requirement_id", required=True) or "",
        command=[str(part) for part in command] if command is not None else None,
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=900, minimum=10, maximum=7200) or 900,
        apply_status=_bool(args, "apply_status", default=True),
    )


# --------------------------------------------------------------------------
# LLM reasoning
# --------------------------------------------------------------------------
def tool_llm_status(args: dict) -> dict:
    return llm_reasoning.status()


def tool_llm_understand_request(args: dict) -> dict:
    try:
        return llm_reasoning.understand_request(
            _str(args, "request", required=True, max_length=20_000) or "",
            engine=_str(args, "engine"),
            platform=_str(args, "platform"),
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_generate_specification(args: dict) -> dict:
    try:
        return llm_reasoning.generate_specification(
            _str(args, "request", required=True, max_length=20_000) or "",
            engine=_str(args, "engine"),
            platform=_str(args, "platform"),
            dimension=_str(args, "dimension"),
            art_style=_str(args, "art_style"),
            scope=_str(args, "scope"),
            project_name=_str(args, "project_name"),
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            approved=_bool(args, "approved"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_analyze_ambiguities(args: dict) -> dict:
    try:
        return llm_reasoning.analyze_ambiguities(
            _str(args, "request", required=True, max_length=20_000) or "",
            understanding_data=_obj(args, "understanding"),
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_engine_compatibility(args: dict) -> dict:
    try:
        return llm_reasoning.reason_about_engine_compatibility(
            _str(args, "request", required=True, max_length=20_000) or "",
            engine=_str(args, "engine"),
            platform=_str(args, "platform"),
            understanding_data=_obj(args, "understanding"),
            installed_engines=_list(args, "installed_engines"),
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_plan_architecture(args: dict) -> dict:
    try:
        return llm_reasoning.plan_game_architecture(
            _str(args, "request", required=True, max_length=20_000) or "",
            understanding_data=_obj(args, "understanding"),
            specification_data=_obj(args, "specification"),
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_validate_plan(args: dict) -> dict:
    try:
        return llm_reasoning.validate_generated_plan(
            _obj(args, "plan", required=True) or {},
            request=_str(args, "request", max_length=20_000),
            understanding_data=_obj(args, "understanding"),
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            use_llm=_bool(args, "use_llm"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_build_execution_plan(args: dict) -> dict:
    return llm_reasoning.build_execution_plan(
        _obj(args, "specification", required=True) or {},
        understanding_data=_obj(args, "understanding"),
        include_paid_options=_bool(args, "include_paid_options", default=True),
    )


def tool_llm_trace_requirements(args: dict) -> dict:
    return llm_reasoning.trace_requirements(
        _obj(args, "understanding", required=True) or {},
        specification_data=_obj(args, "specification"),
        project_path=_project_arg(args),
    )


def tool_llm_test_provider(args: dict) -> dict:
    return llm_reasoning.verify_provider(
        confirm=_bool(args, "confirm"),
        project_path=_project_arg(args),
    )


def tool_llm_review_plan(args: dict) -> dict:
    plan = args.get("plan")
    if not isinstance(plan, dict):
        raise ToolError("plan must be an object")
    try:
        return llm_reasoning.review_plan(
            plan,
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_game_director(args: dict) -> dict:
    try:
        return llm_reasoning.game_director_plan(
            _str(args, "request", required=True, max_length=20_000) or "",
            project_path=_project_arg(args),
            confirm=_bool(args, "confirm"),
            include_project_content=_bool(args, "include_project_content"),
            operation_id=_str(args, "operation_id"),
        )
    except LLMError as exc:
        raise ToolError(str(exc)) from exc


def tool_llm_provider_capabilities(args: dict) -> dict:
    return llm_capabilities.capability_report()


def tool_llm_list_models(args: dict) -> dict:
    provider = _str(args, "provider") or llm_config.load_config()["provider"]
    return llm_catalog.discover_models(
        provider,
        confirm=_bool(args, "confirm"),
        project_path=_project_arg(args),
    )


def tool_llm_route(args: dict) -> dict:
    try:
        return llm_routing.route(
            _str(args, "task", required=True) or "",
            required_capabilities=_list(args, "required_capabilities") or None,
            context_chars=_int(args, "context_chars", minimum=0),
            provider=_str(args, "provider"),
            model=_str(args, "model"),
            allow_paid=_bool(args, "allow_paid"),
            require_known=_bool(args, "require_known"),
            discovered=_obj(args, "discovered"),
            max_tokens=_int(args, "max_tokens", minimum=1),
        )
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"routing failed: {llm_config.redact(str(exc))}") from exc


def tool_llm_configure_provider(args: dict) -> dict:
    return llm_config.save_provider_selection(
        _str(args, "provider", required=True) or "",
        model=_str(args, "model"),
        base_url=_str(args, "base_url"),
        confirm=_bool(args, "confirm"),
    )


def tool_llm_configure_credential(args: dict) -> dict:
    provider = _str(args, "provider", required=True) or ""
    action = (_str(args, "action") or "set").strip().lower()
    if action not in ("set", "clear"):
        raise ToolError("action must be 'set' or 'clear'")
    if not _bool(args, "confirm"):
        raise ToolError("Configuring a credential writes a private local secret; "
                        "pass confirm=true")
    if action == "clear":
        removed = secrets.clear_llm_key(provider)
        config.audit("llm.clear_credential", tool="llm_configure_credential",
                     details={"provider": provider, "removed": removed})
        return {
            "ok": True,
            "provider": provider,
            "action": "clear",
            "removed": removed,
            "credential_configured": bool(
                llm_config.provider_config(provider).get("api_key")),
            "note": ("An environment variable can still provide this credential; "
                     "only the private local file entry was removed."),
        }
    api_key = args.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ToolError("api_key is required when action='set'")
    saved = secrets.save_llm_key(provider, api_key)
    config.audit("llm.configure_credential", tool="llm_configure_credential",
                 details={"provider": saved["provider"], "source": saved["source"]})
    cfg = llm_config.provider_config(provider)
    return {
        "ok": True,
        "provider": saved["provider"],
        "action": "set",
        "source": saved["source"],
        "saved": True,
        "credential_configured": True,
        "api_key": "[REDACTED]",
        "note": ("The key is stored in the private machine-local secrets file and is "
                 "never returned. Reachability is not claimed until a real test request "
                 "succeeds."),
        "active_provider": cfg["provider"],
    }


def tool_orchestrate_game_plan(args: dict) -> dict:
    request = _str(args, "request", required=True, max_length=20_000) or ""
    installed = _list(args, "installed_engines")
    if installed is None:
        try:
            detected = engines.list_available_engines()
            installed = detected.get("available") or []
        except Exception:
            installed = []
    quality = _str(args, "quality_target") or "prototype"
    if quality not in QUALITY_PROFILES:
        raise ToolError(f"quality_target must be one of {list(QUALITY_PROFILES)}")
    approved = _list(args, "approved_decisions") or []
    if any(not isinstance(item, dict) for item in approved):
        raise ToolError("approved_decisions must be an array of objects")
    try:
        orchestrator = AgentOrchestrator(
            request,
            engine=_str(args, "engine"),
            platform=_str(args, "platform"),
            quality_target=quality,
            concurrency=_int(args, "concurrency", default=2, minimum=1,
                             maximum=4) or 2,
            max_retries=_int(args, "max_retries", default=1, minimum=0,
                             maximum=3) or 0,
            installed_engines=[str(x) for x in installed],
            approved_decisions=approved,
            use_provider=False,
        )
        return orchestrator.run()
    except ValueError as exc:
        raise ToolError(str(exc)) from exc



# --------------------------------------------------------------------------
# Blender tools
# --------------------------------------------------------------------------
def tool_blender_info(args: dict) -> dict:
    return blender.blender_info(_str(args, "blender_exe"))


def tool_blender_inspect(args: dict) -> dict:
    return blender.inspect_blend(_str(args, "blend_file", required=True),
                                 _int(args, "max_objects", default=500, minimum=1,
                                      maximum=5000) or 500)


def tool_blender_validate(args: dict) -> dict:
    return blender.validate_blend(_str(args, "blend_file", required=True),
                                  _int(args, "max_triangles", default=150_000,
                                       minimum=1) or 150_000)


def tool_blender_export(args: dict) -> dict:
    _authorize(args, "run_blender", action="export Blender asset")
    return blender.export_blend(
        _str(args, "blend_file", required=True),
        _str(args, "output", required=True),
        _str(args, "format", default="glb") or "glb",
        selected_only=_bool(args, "selected_only"),
        apply_transforms=_bool(args, "apply_transforms", default=True),
        scale=_float(args, "scale", default=1.0, minimum=0.0001) or 1.0,
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_import(args: dict) -> dict:
    _authorize(args, "run_blender", action="import into Blender")
    return blender.import_to_blend(
        _str(args, "source", required=True),
        save_blend=_str(args, "save_blend"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_render(args: dict) -> dict:
    _authorize(args, "run_blender", action="render Blender preview")
    return blender.render_preview(
        _str(args, "blend_file", required=True),
        _str(args, "output_png", required=True),
        width=_int(args, "width", default=640, minimum=16, maximum=4096) or 640,
        height=_int(args, "height", default=360, minimum=16, maximum=4096) or 360,
        frame=_int(args, "frame"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_environment(args: dict) -> dict:
    _authorize(args, "run_blender", action="create Blender environment blockout")
    return blender.create_environment_blockout(
        _str(args, "preset", default="jungle") or "jungle",
        seed=_int(args, "seed", default=1337) or 1337,
        size=_float(args, "size", default=100.0, minimum=5.0, maximum=2000.0) or 100.0,
        segments=_int(args, "segments", default=64, minimum=16, maximum=256) or 64,
        tree_count=_int(args, "tree_count", default=60, minimum=0, maximum=5000) or 0,
        rock_count=_int(args, "rock_count", default=25, minimum=0, maximum=5000) or 0,
        water_level=_float(args, "water_level", default=0.0) or 0.0,
        include_water=_bool(args, "include_water", default=True),
        save_blend=_str(args, "save_blend"),
        export_glb=_str(args, "export_glb"),
        render_png=_str(args, "render_png"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_blender_run_python(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    _authorize(args, "run_blender", action="run arbitrary Blender Python", confirm=confirm)
    _authorize(args, "execute_process", action="run arbitrary Blender Python",
               confirm=confirm)
    return blender.run_python(
        _str(args, "code", required=True, max_length=100_000) or "",
        blend_file=_str(args, "blend_file"),
        save=_bool(args, "save"),
        confirm=confirm,
        timeout=_int(args, "timeout", default=900, minimum=10, maximum=7200) or 900,
    )


# --------------------------------------------------------------------------
# Character asset pipeline
# --------------------------------------------------------------------------
def tool_character_generate(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    if not confirm:
        raise ToolError("character generation runs Blender and writes files; pass confirm=true")
    _authorize(args, "run_blender", action="generate a Blender character asset",
               confirm=confirm)
    description = _str(args, "description", required=True, max_length=8000) or ""
    quality_tier = (_str(args, "quality_tier", default="medium") or "medium").lower()
    if quality_tier not in character_spec.QUALITY_TIERS:
        raise ToolError(
            f"quality_tier must be one of {list(character_spec.QUALITY_TIERS)}")
    animations = _list(args, "animations")
    name = _str(args, "name", default="JungleMonkey") or "JungleMonkey"
    target_engine = _str(args, "target_engine", default="unity") or "unity"
    output_dir = _str(args, "output_dir", required=True) or ""
    try:
        spec = character_spec.build_character_spec(
            description, name=name, quality_tier=quality_tier,
            animations=[str(item) for item in animations] if animations else None,
            target_engine=target_engine,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return character_pipeline.run_pipeline(
        spec, output_dir,
        timeout=_int(args, "timeout", default=1200, minimum=60, maximum=7200) or 1200,
        blender_exe=_str(args, "blender_exe"),
        preview_size=_int(args, "preview_size", default=720, minimum=128,
                          maximum=2048) or 720,
    )


def tool_character_capabilities(args: dict) -> dict:
    return character_spec.provider_capability_report()


# --------------------------------------------------------------------------
# Environment generation pipeline
# --------------------------------------------------------------------------
def tool_environment_generate(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    if not confirm:
        raise ToolError(
            "environment generation runs Blender and writes files; pass confirm=true")
    _authorize(args, "run_blender", action="generate a Blender environment",
               confirm=confirm)
    description = _str(args, "description", required=True, max_length=8000) or ""
    quality_tier = (_str(args, "quality_tier", default="medium") or "medium").lower()
    profile = _str(args, "profile")
    if profile and profile.lower() not in environment_spec.ENVIRONMENT_PROFILES:
        raise ToolError(
            f"profile must be one of {list(environment_spec.ENVIRONMENT_PROFILES)}")
    name = _str(args, "name", default="JungleLevel") or "JungleLevel"
    target_engine = _str(args, "target_engine", default="unity") or "unity"
    output_dir = _str(args, "output_dir", required=True) or ""
    try:
        spec = environment_spec.build_environment_spec(
            description, name=name, quality_tier=quality_tier,
            profile=profile.lower() if profile else None,
            lighting=_str(args, "lighting"),
            target_engine=target_engine,
            character_path=_str(args, "character_path"),
            seed=_int(args, "seed", default=20261108) or 20261108,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return environment_pipeline.run_pipeline(
        spec, output_dir,
        timeout=_int(args, "timeout", default=1200, minimum=60, maximum=7200) or 1200,
        blender_exe=_str(args, "blender_exe"),
        preview_size=_int(args, "preview_size", default=640, minimum=128,
                          maximum=2048),
        character_root=_str(args, "project_path"),
    )


def tool_environment_profiles(args: dict) -> dict:
    return environment_spec.profile_report()


# --------------------------------------------------------------------------
# Meshy tools
# --------------------------------------------------------------------------
def tool_meshy_balance(args: dict) -> dict:
    return meshy.balance()


def tool_meshy_setup(args: dict) -> dict:
    return meshy.setup_guide()


def tool_meshy_configure(args: dict) -> dict:
    return meshy.configure_api_key(
        _str(args, "api_key", required=True, max_length=secrets.MAX_KEY_LENGTH) or "",
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_clear(args: dict) -> dict:
    return meshy.clear_api_key()


def tool_meshy_text_to_3d(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    _authorize(args, "paid_generation", action="Meshy text-to-3D", confirm=confirm)
    return meshy.create_text_to_3d(
        _str(args, "prompt", default="") or "",
        mode=_str(args, "mode", default="preview") or "preview",
        preview_task_id=_str(args, "preview_task_id"),
        ai_model=_str(args, "ai_model"),
        target_polycount=_int(args, "target_polycount", minimum=100, maximum=300_000),
        should_remesh=args.get("should_remesh") if isinstance(args.get("should_remesh"), bool) else None,
        pose_mode=_str(args, "pose_mode"),
        target_formats=_list(args, "target_formats"),
        enable_pbr=_bool(args, "enable_pbr", default=True),
        texture_resolution=_str(args, "texture_resolution"),
        texture_prompt=_str(args, "texture_prompt"),
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_rig(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    _authorize(args, "paid_generation", action="Meshy rigging", confirm=confirm)
    return meshy.create_rigging(
        input_task_id=_str(args, "input_task_id"),
        model_url=_str(args, "model_url"),
        height_meters=_float(args, "height_meters", default=1.7, minimum=0.2,
                             maximum=10.0) or 1.7,
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_animation_library(args: dict) -> dict:
    action_ids = _list(args, "action_ids")
    if action_ids is not None:
        action_ids = [int(i) for i in action_ids]
    return meshy.animation_library(
        search=_str(args, "search"),
        category=_str(args, "category"),
        action_ids=action_ids,
    )


def tool_meshy_create_animation(args: dict) -> dict:
    action_ids = _list(args, "action_ids")
    if action_ids is not None:
        action_ids = [int(i) for i in action_ids]
    confirm = _bool(args, "confirm")
    _authorize(args, "paid_generation", action="Meshy animation", confirm=confirm)
    return meshy.create_animation(
        rig_task_id=_str(args, "rig_task_id", required=True) or "",
        action_id=_int(args, "action_id"),
        action_ids=action_ids,
        motion_task_id=_str(args, "motion_task_id"),
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_task_status(args: dict) -> dict:
    return meshy.get_task(
        _str(args, "task_id", required=True) or "",
        _str(args, "task_type", required=True) or "",
    )


def tool_meshy_cancel(args: dict) -> dict:
    return meshy.cancel_task(
        _str(args, "task_id", required=True) or "",
        _str(args, "task_type", required=True) or "",
        confirm=_bool(args, "confirm"),
    )


def tool_meshy_wait(args: dict) -> dict:
    timeout_seconds = _int(args, "timeout_seconds", default=120, minimum=0,
                           maximum=1800) or 0
    record = operations.start_operation(
        "meshy-wait", "wait for Meshy task",
        metadata={"task_id": _str(args, "task_id")}, timeout_seconds=timeout_seconds)
    result: dict = {"ok": False, "error": "Meshy wait did not return a result"}
    try:
        result = meshy.wait_for_task(
            _str(args, "task_id", required=True) or "",
            _str(args, "task_type", required=True) or "",
            timeout_seconds=timeout_seconds,
            poll_seconds=_float(args, "poll_seconds", default=5.0, minimum=1.0,
                                maximum=60.0) or 5.0,
            operation_id=record["id"],
        )
    finally:
        operations.finish_operation(record["id"], result)
    result["operation_id"] = record["id"]
    return result


def tool_meshy_download(args: dict) -> dict:
    _authorize(args, "download_assets", action="download Meshy output")
    return meshy.download_output(
        _str(args, "task_id", required=True) or "",
        _str(args, "task_type", required=True) or "",
        _str(args, "output_key", required=True) or "",
        _str(args, "destination", required=True) or "",
    )


def tool_meshy_generate(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    _authorize(args, "paid_generation", action="Meshy asset generation", confirm=confirm)
    return meshy.generate_asset(
        _str(args, "prompt", required=True) or "",
        refine=_bool(args, "refine"),
        wait=_bool(args, "wait", default=True),
        timeout_seconds=_int(args, "timeout_seconds", default=180, minimum=0,
                             maximum=1800) or 0,
        ai_model=_str(args, "ai_model"),
        target_polycount=_int(args, "target_polycount", minimum=100, maximum=300_000),
        pose_mode=_str(args, "pose_mode"),
        enable_pbr=_bool(args, "enable_pbr", default=True),
        texture_resolution=_str(args, "texture_resolution"),
        confirm=_bool(args, "confirm"),
    )


# --------------------------------------------------------------------------
# Asset tools
# --------------------------------------------------------------------------
def tool_asset_providers(args: dict) -> dict:
    return assets.providers()


def tool_asset_search(args: dict) -> dict:
    return assets.search_assets(
        _str(args, "query", required=True) or "",
        kind=_str(args, "kind", default="model") or "model",
        provider=_str(args, "provider", default="auto") or "auto",
        limit=_int(args, "limit", default=20, minimum=1, maximum=60) or 20,
        max_polycount=_int(args, "max_polycount", minimum=1),
    )


def tool_asset_download(args: dict) -> dict:
    confirm = _bool(args, "confirm")
    _authorize(args, "download_assets", action="download Poly Haven asset",
               confirm=confirm)
    return assets.download_polyhaven(
        _str(args, "asset_id", required=True) or "",
        fmt=_str(args, "format", default="glb") or "glb",
        resolution=_str(args, "resolution", default="2k") or "2k",
        destination_dir=_str(args, "destination_dir"),
        confirm=_bool(args, "confirm"),
        max_bytes=_int(args, "max_bytes", default=512 * 1024 * 1024, minimum=1) or
        512 * 1024 * 1024,
    )


def tool_asset_license(args: dict) -> dict:
    return assets.inspect_asset_license(
        _str(args, "provider", required=True) or "",
        asset_id=_str(args, "asset_id"),
    )


def tool_asset_validate(args: dict) -> dict:
    return assets.validate_asset_file(
        _str(args, "path", required=True) or "",
        max_triangles=_int(args, "max_triangles", minimum=1),
    )


def tool_asset_manifest(args: dict) -> dict:
    paths = _list(args, "paths")
    if not paths:
        raise ToolError("paths must contain at least one file")
    return assets.asset_manifest([str(p) for p in paths], _str(args, "destination"))


# --------------------------------------------------------------------------
# Animation tools
# --------------------------------------------------------------------------
def tool_animation_inspect(args: dict) -> dict:
    return animations.inspect_rig(_str(args, "path", required=True) or "")


def tool_animation_retarget_map(args: dict) -> dict:
    return animations.create_retarget_map(
        _str(args, "character_path", required=True) or "",
        _str(args, "animation_path", required=True) or "",
        destination=_str(args, "destination"),
    )


def tool_animation_compatibility(args: dict) -> dict:
    return animations.check_compatibility(
        _str(args, "character_path", required=True) or "",
        _str(args, "animation_path", required=True) or "",
    )


def tool_animation_sources(args: dict) -> dict:
    return animations.list_animation_sources()


# --------------------------------------------------------------------------
# Engine tools
# --------------------------------------------------------------------------
def tool_engine_stage(args: dict) -> dict:
    _authorize(args, "modify_engine_project", action="stage asset into engine project")
    return engines.stage_asset(
        _str(args, "source", required=True) or "",
        _str(args, "project_path", required=True) or "",
        engine=_str(args, "engine"),
        relative_path=_str(args, "relative_path"),
        confirm=_bool(args, "confirm"),
        confirm_overwrite=_bool(args, "confirm_overwrite"),
    )


def tool_engine_verify(args: dict) -> dict:
    return engines.verify_staged_import(
        _str(args, "project_path", required=True) or "",
        _str(args, "relative_path", required=True) or "",
    )


def tool_engine_build(args: dict) -> dict:
    _authorize(args, "build_game", action="build a game player")
    return engines.engine_build(
        _str(args, "engine", required=True) or "",
        _str(args, "project_path", required=True) or "",
        target=_str(args, "target"),
        output_path=_str(args, "output_path"),
        preset=_str(args, "preset"),
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unity_status(args: dict) -> dict:
    return engines.unity_editor_status()


def tool_unity_commands(args: dict) -> dict:
    return engines.unity_list_commands(_str(args, "project_path", required=True) or "")


def tool_unity_run_command(args: dict) -> dict:
    arguments = _list(args, "arguments")
    _authorize(args, "execute_process", action="run Unity editor command")
    _authorize(args, "modify_engine_project", action="run Unity editor command")
    return engines.unity_run_command(
        _str(args, "project_path", required=True) or "",
        _str(args, "command", required=True) or "",
        [str(a) for a in (arguments or [])],
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=300, minimum=5, maximum=3600) or 300,
    )


def tool_unity_refresh(args: dict) -> dict:
    _authorize(args, "execute_process", action="run Unity batch refresh")
    return engines.unity_batch_refresh(
        _str(args, "project_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unity_tests(args: dict) -> dict:
    _authorize(args, "execute_process", action="run Unity tests")
    return engines.unity_run_tests(
        _str(args, "project_path", required=True) or "",
        mode=_str(args, "mode", default="EditMode") or "EditMode",
        test_filter=_str(args, "filter"),
        output=_str(args, "output"),
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unity_build(args: dict) -> dict:
    _authorize(args, "build_game", action="build a Unity player")
    return engines.unity_build(
        _str(args, "project_path", required=True) or "",
        target=_str(args, "target", required=True) or "",
        output_path=_str(args, "output_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
        allow_dirty_build=_bool(args, "allow_dirty_build"),
    )


def tool_godot_import(args: dict) -> dict:
    _authorize(args, "modify_engine_project", action="run Godot headless import")
    return engines.godot_batch_import(
        _str(args, "project_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_godot_build(args: dict) -> dict:
    _authorize(args, "build_game", action="build a Godot export")
    return engines.godot_build(
        _str(args, "project_path", required=True) or "",
        preset=_str(args, "preset", required=True) or "",
        output_path=_str(args, "output_path", required=True) or "",
        confirm=_bool(args, "confirm"),
        timeout=_int(args, "timeout", default=engines.DEFAULT_TIMEOUT, minimum=30,
                     maximum=7200) or engines.DEFAULT_TIMEOUT,
    )


def tool_unreal_status(args: dict) -> dict:
    return engines.unreal_stage_only(_str(args, "project_path", required=True) or "")


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------
def _tool(name: str, description: str, properties: dict | None = None,
          required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = required
    return {"name": name, "description": description, "inputSchema": schema}


PROJECT_PATH = {"type": "string", "description": "Absolute path to the game project"}
ENGINE_ENUM = {"type": "string", "enum": list(engines.ENGINES)}
CONFIRM = {"type": "boolean", "default": False,
           "description": "Explicit approval for a write, credit spend or editor run"}
OPERATION_ID = {"type": "string",
                "description": "Operation id used to check cancellation before/while "
                               "waiting for provider retries"}
OVERWRITE = {"type": "boolean", "default": False,
             "description": "Allow replacing an existing target file"}

TOOLS = [
    # studio
    _tool("studio_info", "Report server version, config location, selected engine and which "
          "credentialed integrations are configured. Never returns secret values."),
    _tool("detect_system", "Inspect OS, CPU, memory, GPUs and disk space."),
    _tool("detect_game_engines", "Detect Unity, Unreal and Godot installations and optionally "
          "discover game projects under configured roots.", {
              "discover_projects": {"type": "boolean", "default": True},
              "roots": {"type": "array", "items": {"type": "string"},
                        "description": "Optional roots; defaults to configured project_roots"},
          }),
    _tool("list_available_engines", "List engines with detection state, adapter capabilities and "
          "the current selection."),
    _tool("select_game_engine", "Persist the engine the user wants to work in. Requires a "
          "verified installation.", {
              "engine": ENGINE_ENUM,
              "engine_path": {"type": "string",
                              "description": "Optional explicit editor/CLI path"},
              "persist": {"type": "boolean", "default": True},
          }, ["engine"]),
    _tool("inspect_engine_capabilities", "Show exactly which engine operations are implemented, "
          "verified, or unavailable in this environment.", {
              "engine": ENGINE_ENUM,
          }),
    _tool("inspect_game_project", "Inspect a Unity/Unreal/Godot project: version, packages, render "
          "pipeline, scenes, missing scripts and warnings.", {
              "project_path": PROJECT_PATH,
              "include_editor_status": {"type": "boolean", "default": False},
          }, ["project_path"]),
    _tool("configure_studio", "Persist machine-local studio settings (tool paths, project roots, "
          "download root). Credentials are not accepted here.", {
              "selected_engine": ENGINE_ENUM,
              "selected_engine_path": {"type": "string"},
              "project_roots": {"type": "array", "items": {"type": "string"}},
              "blender_exe": {"type": "string"},
              "unity_exe": {"type": "string"},
              "unreal_editor_cmd": {"type": "string"},
              "godot_exe": {"type": "string"},
              "download_root": {"type": "string"},
              "allow_overwrite": {"type": "boolean"},
          }),
    _tool("list_studio_projects", "Discover game projects under the provided or configured roots.", {
        "roots": {"type": "array", "items": {"type": "string"}},
    }),
    _tool("read_studio_audit", "Read the append-only audit log of write/generation actions.", {
        "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 1000},
    }),
    # blender
    _tool("blender_info", "Probe the real Blender executable and report version and addons.", {
        "blender_exe": {"type": "string"},
    }),
    _tool("blender_inspect_blend", "Inspect objects, meshes, UVs, materials, armatures, actions and "
          "missing images in a .blend file.", {
              "blend_file": {"type": "string"},
              "max_objects": {"type": "integer", "default": 500, "minimum": 1, "maximum": 5000},
          }, ["blend_file"]),
    _tool("blender_validate_asset", "Validate a .blend for engine import (triangles, UVs, transforms, "
          "textures, armature, bounds).", {
              "blend_file": {"type": "string"},
              "max_triangles": {"type": "integer", "default": 150000, "minimum": 1},
          }, ["blend_file"]),
    _tool("blender_export_asset", "Export a .blend to glb/gltf/fbx/obj/stl/usdz and return a hash.", {
        "blend_file": {"type": "string"},
        "output": {"type": "string"},
        "format": {"type": "string", "enum": ["glb", "gltf", "fbx", "obj", "stl", "usdz"],
                   "default": "glb"},
        "selected_only": {"type": "boolean", "default": False},
        "apply_transforms": {"type": "boolean", "default": True},
        "scale": {"type": "number", "default": 1.0},
        "project_path": PROJECT_PATH,
        "confirm_overwrite": OVERWRITE,
        "confirm": CONFIRM,
    }, ["blend_file", "output"]),
    _tool("blender_import_asset", "Import fbx/glb/gltf/obj/blend/usd into a fresh Blender scene and "
          "optionally save a .blend.", {
              "source": {"type": "string"},
              "save_blend": {"type": "string"},
              "project_path": PROJECT_PATH,
              "confirm_overwrite": OVERWRITE,
              "confirm": CONFIRM,
          }, ["source"]),
    _tool("blender_render_preview", "Render a PNG preview of a .blend for visual verification.", {
        "blend_file": {"type": "string"},
        "output_png": {"type": "string"},
        "width": {"type": "integer", "default": 640, "minimum": 16, "maximum": 4096},
        "height": {"type": "integer", "default": 360, "minimum": 16, "maximum": 4096},
        "frame": {"type": ["integer", "null"]},
        "project_path": PROJECT_PATH,
        "confirm_overwrite": OVERWRITE,
        "confirm": CONFIRM,
    }, ["blend_file", "output_png"]),
    _tool("blender_create_environment_blockout", "Generate a procedural terrain blockout "
          "(jungle/forest/desert/alpine) with trees, rocks, water, sun and camera. This is a "
          "blockout, not production environment art.", {
              "preset": {"type": "string", "enum": ["jungle", "forest", "desert", "alpine"],
                         "default": "jungle"},
              "seed": {"type": "integer", "default": 1337},
              "size": {"type": "number", "default": 100.0, "minimum": 5, "maximum": 2000},
              "segments": {"type": "integer", "default": 64, "minimum": 16, "maximum": 256},
              "tree_count": {"type": "integer", "default": 60, "minimum": 0, "maximum": 5000},
              "rock_count": {"type": "integer", "default": 25, "minimum": 0, "maximum": 5000},
              "water_level": {"type": "number", "default": 0.0},
              "include_water": {"type": "boolean", "default": True},
              "save_blend": {"type": "string"},
              "export_glb": {"type": "string"},
              "render_png": {"type": "string"},
              "project_path": PROJECT_PATH,
              "confirm_overwrite": OVERWRITE,
              "confirm": CONFIRM,
          }),
    _tool("blender_run_python", "Execute arbitrary Blender Python in background mode. Requires "
          "explicit confirm=true; set __mcp_result to return data.", {
              "code": {"type": "string"},
              "blend_file": {"type": "string"},
              "save": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
              "timeout": {"type": "integer", "default": 900, "minimum": 10, "maximum": 7200},
          }, ["code"]),
    # character asset pipeline
    _tool("character_generate_asset", "Generate a real procedural character in Blender: "
          "geometry, UVs, PBR materials/textures, armature, skin weights, keyframed actions, "
          ".blend/.glb/.fbx export, GLB re-import validation and a rendered preview. This is a "
          "stylized procedural prototype, not AI-generated or production character art. "
          "Requires confirm=true.", {
              "description": {"type": "string", "maxLength": 8000,
                              "description": "Natural-language character request."},
              "name": {"type": "string", "maxLength": 80, "default": "JungleMonkey"},
              "quality_tier": {"type": "string", "enum": ["low", "medium", "high"],
                               "default": "medium"},
              "animations": {"type": "array", "items": {"type": "string"}},
              "target_engine": {"type": "string", "enum": ["unity", "godot", "unreal"],
                                "default": "unity"},
              "output_dir": {"type": "string"},
              "preview_size": {"type": "integer", "default": 720, "minimum": 128,
                               "maximum": 2048},
              "timeout": {"type": "integer", "default": 1200, "minimum": 60, "maximum": 7200},
              "blender_exe": {"type": "string"},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
          }, ["description", "output_dir", "confirm"]),
    _tool("character_capabilities", "Report which asset capabilities (text, image, texture, "
          "material, mesh, image-to-texture, image analysis) each provider supports, explicitly "
          "separating configured text adapters from unauthorized image/3D generators."),
    # environment generation pipeline
    _tool("environment_generate_asset", "Generate a real procedural tropical jungle environment "
          "in Blender: terrain, vegetation, rocks, props, river with banks, PBR ground textures, "
          "lighting/atmosphere, collision and spawn metadata, Phase 3 character integration, "
          ".blend/.glb/.gltf/.fbx export, GLB re-import validation and preview renders. This is a "
          "stylized procedural prototype, not hand-authored or AI-generated production art. "
          "Requires confirm=true.", {
              "description": {"type": "string", "maxLength": 8000,
                              "description": "Natural-language environment request."},
              "name": {"type": "string", "maxLength": 80, "default": "JungleLevel"},
              "quality_tier": {"type": "string", "enum": ["low", "medium", "high"],
                               "default": "medium"},
              "profile": {"type": "string", "enum": list(environment_spec.ENVIRONMENT_PROFILES)},
              "lighting": {"type": "string", "enum": list(environment_spec.LIGHTING_PRESETS)},
              "target_engine": {"type": "string", "enum": ["unity", "godot", "unreal"],
                                "default": "unity"},
              "character_path": {"type": "string"},
              "seed": {"type": "integer", "default": 20261108},
              "output_dir": {"type": "string"},
              "preview_size": {"type": "integer", "default": 640, "minimum": 128,
                               "maximum": 2048},
              "timeout": {"type": "integer", "default": 1200, "minimum": 60, "maximum": 7200},
              "blender_exe": {"type": "string"},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
          }, ["description", "output_dir", "confirm"]),
    _tool("environment_profiles", "Report the reusable environment profiles (with honest "
          "implementation levels), quality tiers, lighting presets and tier settings."),
    # meshy
    _tool("meshy_setup_guide", "Explain how to create a Meshy API key, where to store it, how "
          "to rotate it, and whether one is currently configured. Never returns the key."),
    _tool("meshy_configure_api_key", "Validate a Meshy API key against the balance endpoint, "
          "then save it in the studio's private config directory outside the repository. "
          "Requires confirm=true. The environment variable MESHY_API_KEY overrides it.", {
              "api_key": {"type": "string", "maxLength": 512,
                          "description": "The Meshy key. It is validated and stored locally; "
                                         "tools never return it."},
              "confirm": CONFIRM,
          }, ["api_key", "confirm"]),
    _tool("meshy_clear_api_key", "Delete the locally saved Meshy key. An environment variable "
          "cannot be removed by this tool and still takes precedence."),
    _tool("meshy_balance", "Read the Meshy credit balance. Requires a configured API key."),
    _tool("meshy_text_to_3d", "Create a Meshy text-to-3D preview or refine task. Spends credits; "
          "requires confirm=true.", {
              "prompt": {"type": "string", "maxLength": 800},
              "mode": {"type": "string", "enum": ["preview", "refine"], "default": "preview"},
              "preview_task_id": {"type": "string"},
              "ai_model": {"type": "string"},
              "target_polycount": {"type": "integer", "minimum": 100, "maximum": 300000},
              "should_remesh": {"type": ["boolean", "null"]},
              "pose_mode": {"type": "string"},
              "target_formats": {"type": "array", "items": {"type": "string"}},
              "enable_pbr": {"type": "boolean", "default": True},
              "texture_resolution": {"type": "string", "enum": ["2k", "4k", "8k"]},
              "texture_prompt": {"type": "string"},
              "confirm": CONFIRM,
          }, ["confirm"]),
    _tool("meshy_rig_character", "Rig a humanoid model through Meshy. Spends credits; confirm=true.", {
        "input_task_id": {"type": "string"},
        "model_url": {"type": "string", "description": "Public https model URL"},
        "height_meters": {"type": "number", "default": 1.7, "minimum": 0.2, "maximum": 10},
        "confirm": CONFIRM,
    }, ["confirm"]),
    _tool("meshy_animation_library", "Search Meshy's animation library (read-only).", {
        "search": {"type": "string"},
        "category": {"type": "string"},
        "action_ids": {"type": "array", "items": {"type": "integer"}},
    }),
    _tool("meshy_create_animation", "Apply library actions or a motion task to a Meshy rig. Spends "
          "credits; confirm=true.", {
              "rig_task_id": {"type": "string"},
              "action_id": {"type": "integer"},
              "action_ids": {"type": "array", "items": {"type": "integer"}},
              "motion_task_id": {"type": "string"},
              "confirm": CONFIRM,
          }, ["rig_task_id", "confirm"]),
    _tool("meshy_task_status", "Read one Meshy task's status, progress, error and output URLs.", {
        "task_id": {"type": "string"},
        "task_type": {"type": "string",
                      "enum": ["text-to-3d", "rigging", "animation"]},
    }, ["task_id", "task_type"]),
    _tool("meshy_wait_for_task", "Poll a Meshy task until it finishes or the timeout is reached.", {
        "task_id": {"type": "string"},
        "task_type": {"type": "string",
                      "enum": ["text-to-3d", "rigging", "animation"]},
        "timeout_seconds": {"type": "integer", "default": 120, "minimum": 0, "maximum": 1800},
        "poll_seconds": {"type": "number", "default": 5, "minimum": 1, "maximum": 60},
    }, ["task_id", "task_type"]),
    _tool("meshy_cancel_task", "Report and apply Meshy cancellation only where the documented API "
          "supports it. This adapter has no cancel endpoint, so it explicitly reports that a "
          "remote task was NOT cancelled rather than faking it.", {
              "task_id": {"type": "string"},
              "task_type": {"type": "string",
                            "enum": ["text-to-3d", "rigging", "animation"]},
              "confirm": CONFIRM,
          }, ["task_id", "task_type", "confirm"]),
    _tool("meshy_download_output", "Download a finished Meshy output to a local path and hash it.", {
        "task_id": {"type": "string"},
        "task_type": {"type": "string",
                      "enum": ["text-to-3d", "rigging", "animation"]},
        "output_key": {"type": "string", "description": "Key from meshy_task_status output_urls"},
        "destination": {"type": "string"},
    }, ["task_id", "task_type", "output_key", "destination"]),
    _tool("meshy_generate_asset", "Create a preview and optionally refine it in one call. Spends "
          "credits; confirm=true.", {
              "prompt": {"type": "string", "maxLength": 800},
              "refine": {"type": "boolean", "default": False},
              "wait": {"type": "boolean", "default": True},
              "timeout_seconds": {"type": "integer", "default": 180, "minimum": 0,
                                  "maximum": 1800},
              "ai_model": {"type": "string"},
              "target_polycount": {"type": "integer", "minimum": 100, "maximum": 300000},
              "pose_mode": {"type": "string"},
              "enable_pbr": {"type": "boolean", "default": True},
              "texture_resolution": {"type": "string", "enum": ["2k", "4k", "8k"]},
              "confirm": CONFIRM,
          }, ["prompt", "confirm"]),
    # assets
    _tool("list_asset_providers", "Show which asset providers have real automated search/download "
          "and which are manual-only, with license notes."),
    _tool("search_assets", "Search licensed assets. Poly Haven is keyless; Sketchfab needs "
          "SKETCHFAB_TOKEN. Manual-only providers are reported, never simulated.", {
              "query": {"type": "string"},
              "kind": {"type": "string",
                       "enum": ["model", "texture", "hdri", "character", "environment", "animation"],
                       "default": "model"},
              "provider": {"type": "string",
                           "enum": ["auto", "polyhaven", "sketchfab", "meshy", "mixamo",
                                    "kenney", "opengameart", "unity_asset_store", "fab"],
                           "default": "auto"},
              "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 60},
              "max_polycount": {"type": "integer", "minimum": 1},
          }, ["query"]),
    _tool("download_polyhaven_asset", "Download a CC0 Poly Haven asset with dependencies, verify "
          "MD5 and write provenance.json. confirm=true.", {
              "asset_id": {"type": "string"},
              "format": {"type": "string", "default": "glb"},
              "resolution": {"type": "string", "default": "2k"},
              "destination_dir": {"type": "string"},
              "max_bytes": {"type": "integer", "default": 536870912, "minimum": 1},
              "confirm": CONFIRM,
          }, ["asset_id", "confirm"]),
    _tool("inspect_asset_license", "Read provider/asset license information. Sketchfab and "
          "manual-only providers require per-asset human review.", {
              "provider": {"type": "string"},
              "asset_id": {"type": "string"},
          }, ["provider"]),
    _tool("validate_asset_file", "Validate glTF/GLB/OBJ/STL/FBX/BLEND/image files and report "
          "triangles, UVs, textures, animations and issues.", {
              "path": {"type": "string"},
              "max_triangles": {"type": "integer", "minimum": 1},
          }, ["path"]),
    _tool("create_asset_manifest", "Hash files and write an asset manifest with sizes and extensions.", {
        "paths": {"type": "array", "items": {"type": "string"}},
        "destination": {"type": "string"},
    }, ["paths"]),
    # animations
    _tool("inspect_animation_rig", "Classify a GLB/glTF rig (humanoid/quadruped/generic), list "
          "joints, clips and durations.", {
              "path": {"type": "string"},
          }, ["path"]),
    _tool("create_animation_retarget_map", "Build a bone-name retarget map between a character and "
          "an animated file, optionally writing JSON.", {
              "character_path": {"type": "string"},
              "animation_path": {"type": "string"},
              "destination": {"type": "string"},
          }, ["character_path", "animation_path"]),
    _tool("check_animation_compatibility", "Check whether an animation's skeleton is compatible "
          "with a character skeleton.", {
              "character_path": {"type": "string"},
              "animation_path": {"type": "string"},
          }, ["character_path", "animation_path"]),
    _tool("list_animation_sources", "List animation sources with their real availability and "
          "manual-only limitations."),
    # engines
    _tool("stage_asset_for_engine", "Copy an asset into a Unity/Unreal/Godot project and record "
          "provenance. Staging is not import. Requires confirm=true.", {
              "source": {"type": "string"},
              "project_path": PROJECT_PATH,
              "engine": ENGINE_ENUM,
              "relative_path": {"type": "string",
                                "description": "Destination relative to Assets/, Content/ or the "
                                               "Godot project root"},
              "confirm": CONFIRM,
              "confirm_overwrite": OVERWRITE,
          }, ["source", "project_path", "confirm"]),
    _tool("verify_staged_import", "Check real import evidence for a staged asset (.meta, .import, "
          "import cache) without claiming visual or runtime correctness.", {
              "project_path": PROJECT_PATH,
              "relative_path": {"type": "string"},
          }, ["project_path", "relative_path"]),
    _tool("engine_build", "Build a player through the engine CLI. Requires confirm=true. A produced "
          "artifact is not proof the game runs.", {
              "engine": ENGINE_ENUM,
              "project_path": PROJECT_PATH,
              "target": {"type": "string", "description": "Unity build target"},
              "preset": {"type": "string", "description": "Godot export preset"},
              "output_path": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["engine", "project_path", "output_path", "confirm"]),
    _tool("unity_editor_status", "Show live Unity Editor connections through the Unity CLI."),
    _tool("unity_list_commands", "List Editor Pipeline commands registered by an open Unity editor.", {
        "project_path": PROJECT_PATH,
    }, ["project_path"]),
    _tool("unity_run_command", "Run a registered Unity Editor Pipeline command. Can modify the "
          "project; requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "command": {"type": "string"},
              "arguments": {"type": "array", "items": {"type": "string"}},
              "timeout": {"type": "integer", "default": 300, "minimum": 5, "maximum": 3600},
              "confirm": CONFIRM,
          }, ["project_path", "command", "confirm"]),
    _tool("unity_batch_refresh", "Run Unity batch import (-quit -batchmode -nographics) and report "
          "the log. Requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "confirm"]),
    _tool("unity_run_tests", "Run Unity EditMode/PlayMode tests and parse the NUnit report. Requires "
          "confirm=true.", {
              "project_path": PROJECT_PATH,
              "mode": {"type": "string", "enum": ["EditMode", "PlayMode"], "default": "EditMode"},
              "filter": {"type": "string"},
              "output": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "confirm"]),
    _tool("unity_build", "Build a Unity player with the Unity CLI and verify artifacts exist. "
          "Requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "target": {"type": "string"},
              "output_path": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "allow_dirty_build": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
          }, ["project_path", "target", "output_path", "confirm"]),
    _tool("godot_batch_import", "Run Godot headless import and check the .godot import cache. "
          "Requires confirm=true.", {
              "project_path": PROJECT_PATH,
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "confirm"]),
    _tool("godot_build", "Export a Godot project with an existing export preset. Requires "
          "confirm=true.", {
              "project_path": PROJECT_PATH,
              "preset": {"type": "string"},
              "output_path": {"type": "string"},
              "timeout": {"type": "integer", "default": 1800, "minimum": 30, "maximum": 7200},
              "confirm": CONFIRM,
          }, ["project_path", "preset", "output_path", "confirm"]),
    _tool("unreal_status", "Inspect an Unreal project and state the staged-only automation limits.", {
        "project_path": PROJECT_PATH,
    }, ["project_path"]),
    # understanding, specification and project memory
    _tool("analyze_game_request", "Turn a free-form game request (English, Roman Urdu, Urdu or "
          "mixed) into a traceable requirement set. Separates explicit requirements from "
          "implied, technical, optional and unresolved items; reports conflicts, exclusions "
          "and only the questions that materially change implementation. Read-only.", {
              "request": {"type": "string", "maxLength": 20000,
                          "description": "The user's words, unedited"},
              "engine": {"type": "string", "description": "Known/selected engine to reduce "
                                                         "unnecessary questions"},
              "platform": {"type": "string", "description": "Known target platform"},
              "installed_engines": {"type": "array", "items": {"type": "string"},
                                    "description": "Optional list of verified installs"},
              "detect_environment": {"type": "boolean", "default": False,
                                     "description": "Run engine detection (slower) instead of "
                                                    "supplying installed_engines"},
          }, ["request"]),
    _tool("create_game_specification", "Create an engine-aware project specification: overview, "
          "character/environment/animation plans, classified requirements, dependency graph, "
          "milestones and acceptance tests. Defaults are labelled assumptions and the result "
          "stays awaiting approval unless approved=true. Writes nothing.", {
              "request": {"type": "string", "maxLength": 20000},
              "project_name": {"type": "string"},
              "engine": {"type": "string", "enum": list(engines.ENGINES),
                         "description": "User override after answering the engine question"},
              "platform": {"type": "string",
                           "enum": list(specification.PERFORMANCE_TARGETS)},
              "dimension": {"type": "string", "enum": ["2d", "2.5d", "3d"]},
              "art_style": {"type": "string"},
              "scope": {"type": "string"},
              "installed_engines": {"type": "array", "items": {"type": "string"}},
              "detect_environment": {"type": "boolean", "default": False},
              "approved": {"type": "boolean", "default": False},
          }, ["request"]),
    _tool("init_project_manifest", "Persist an approved specification and its requirement "
          "traceability in <project>/.game-studio/manifest.json. Writes a file; requires "
          "confirm=true. Never stores credentials.", {
              "project_path": PROJECT_PATH,
              "spec": {"type": "object", "description": "Output of create_game_specification"},
              "overwrite": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
          }, ["project_path", "spec", "confirm"]),
    _tool("get_project_manifest", "Load the persisted project manifest after a restart: spec, "
          "requirement statuses, decisions, questions, errors and recent history. Read-only.", {
              "project_path": PROJECT_PATH,
          }, ["project_path"]),
    _tool("update_requirement_status", "Record a requirement status with evidence. implemented "
          "needs evidence; tested needs test/playtest evidence; verified needs "
          "test/build/playtest/inspection evidence and no missing evidence files. Requires "
          "confirm=true.", {
              "project_path": PROJECT_PATH,
              "requirement_id": {"type": "string"},
              "status": {"type": "string", "enum": list(manifest.STATUSES)},
              "evidence": {"type": "array", "items": {
                  "type": "object",
                  "properties": {
                      "kind": {"type": "string", "enum": list(manifest.EVIDENCE_KINDS)},
                      "reference": {"type": "string"},
                      "note": {"type": "string"},
                  },
                  "required": ["kind", "reference"],
              }},
              "note": {"type": "string"},
              "confirm": CONFIRM,
          }, ["project_path", "requirement_id", "status", "confirm"]),
    _tool("record_project_decision", "Append a technical/design decision with rationale and "
          "whether it was user-approved, and clear a matching pending question. Requires "
          "confirm=true.", {
              "project_path": PROJECT_PATH,
              "topic": {"type": "string"},
              "decision": {"type": "string"},
              "rationale": {"type": "string"},
              "source": {"type": "string",
                         "enum": ["user", "ai-default", "ai-recommendation", "external"],
                         "default": "user"},
              "approved": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
          }, ["project_path", "topic", "decision", "confirm"]),
    _tool("track_project_progress", "Summarise requirement coverage, milestone gates and the "
          "next P0/P1 actions from the persisted manifest. Read-only.", {
              "project_path": PROJECT_PATH,
          }, ["project_path"]),
    _tool("compare_project_against_requirements", "Re-check the manifest against the real "
          "project: detects the engine, checks evidence files still exist and flags requirements "
          "claimed done without qualifying evidence. Never upgrades a status automatically.", {
              "project_path": PROJECT_PATH,
              "inspect_project": {"type": "boolean", "default": True},
          }, ["project_path"]),
    # execution modes, permissions and operations
    _tool("get_execution_mode", "Show the effective execution mode, permission matrix, budgets "
          "and policy path for a project (or the global fallback). Read-only.", {
              "project_path": PROJECT_PATH,
          }),
    _tool("set_execution_mode", "Persist guided, balanced or autonomous mode per project. A mode "
          "is not a permission grant: paid generation, uploads and deletion always require "
          "per-action approval. Requires confirm=true.", {
              "mode": {"type": "string", "enum": list(governance.MODES)},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
          }, ["mode", "confirm"]),
    _tool("set_permission", "Set one granular permission to allow, ask or deny. paid_generation, "
          "upload_content and delete_files cannot be set to allow. Requires confirm=true.", {
              "permission": {"type": "string", "enum": list(governance.PERMISSIONS)},
              "effect": {"type": "string", "enum": list(governance.EFFECTS)},
              "project_path": PROJECT_PATH,
              "reason": {"type": "string", "maxLength": 1000},
              "confirm": CONFIRM,
          }, ["permission", "effect", "confirm"]),
    _tool("list_operations", "List persisted long-running operations and their states. Use this "
          "to find an operation id before cancelling.", {
              "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
              "include_terminal": {"type": "boolean", "default": True},
          }),
    _tool("get_operation", "Read one persisted operation record including cancellation state "
          "and result.", {
              "operation_id": {"type": "string"},
          }, ["operation_id"]),
    _tool("cancel_operation", "Request cancellation of a long-running operation. Local process "
          "trees are terminated and confirmed by the OS. Remote provider work is reported "
          "cancelled only if the provider confirms it. Requires confirm=true.", {
              "operation_id": {"type": "string"},
              "reason": {"type": "string", "maxLength": 1000},
              "confirm": CONFIRM,
          }, ["operation_id", "confirm"]),
    _tool("cleanup_operation", "Delete a finished operation record and its studio temp directory. "
          "Refuses active operations and paths outside the studio temp root. Requires "
          "confirm=true.", {
              "operation_id": {"type": "string"},
              "temp_dir": {"type": "string"},
              "confirm": CONFIRM,
          }, ["operation_id", "confirm"]),
    _tool("operation_status", "Summarise the operations registry and cancellation capabilities."),
    _tool("recover_operations", "Mark operations that were active when the server stopped as "
          "interrupted. Never retries them automatically."),
    # evidence verification
    _tool("inspect_requirement_evidence", "For each requirement show the original user wording, "
          "implementation files, tests, acceptance test, recorded verification runs and gaps. "
          "Read-only; never upgrades a status.", {
              "project_path": PROJECT_PATH,
              "requirement_id": {"type": "string"},
          }, ["project_path"]),
    _tool("run_requirement_verification", "Run a caller-supplied validation command (argv, no "
          "shell) in the project, capture output/timestamps/hashes, compare with the previous "
          "run and upgrade to tested only on exit code 0. Requires execute_process permission "
          "and confirm=true.", {
              "project_path": PROJECT_PATH,
              "requirement_id": {"type": "string"},
              "command": {"type": "array", "items": {"type": "string"},
                          "description": "Argv array, e.g. [\"python\",\"-m\",\"unittest\"]"},
              "timeout": {"type": "integer", "default": 900, "minimum": 10,
                          "maximum": 7200},
              "apply_status": {"type": "boolean", "default": True},
              "confirm": CONFIRM,
          }, ["project_path", "requirement_id", "confirm"]),
    # LLM reasoning
    _tool("llm_status", "Report LLM provider configuration, budgets, privacy controls, provider "
          "matrix and fallback behaviour. Never returns credentials."),
    _tool("llm_understand_request", "Use the configured LLM to understand a natural-language game "
          "request (English, Roman Urdu, Urdu or mixed) and return schema-validated structured "
          "requirements. Falls back to the deterministic parser and labels it. Sends text to the "
          "provider, so it requires external_api permission and confirm=true.", {
              "request": {"type": "string", "maxLength": 20000},
              "engine": {"type": "string"},
              "platform": {"type": "string"},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["request", "confirm"]),
    _tool("llm_generate_specification", "Hybrid specification: LLM understanding/recommendations "
          "plus the deterministic dependency graph, milestones and acceptance tests. Nothing is "
          "marked implemented. Requires confirm=true for the provider request.", {
              "request": {"type": "string", "maxLength": 20000},
              "project_name": {"type": "string"},
              "engine": {"type": "string", "enum": list(engines.ENGINES)},
              "platform": {"type": "string"},
              "dimension": {"type": "string", "enum": ["2d", "2.5d", "3d"]},
              "art_style": {"type": "string"},
              "scope": {"type": "string"},
              "project_path": PROJECT_PATH,
              "approved": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["request", "confirm"]),
    _tool("llm_analyze_ambiguities", "Ask only material clarification questions (maximum five) "
          "and return ambiguities with safe defaults where possible. Falls back to the "
          "deterministic unresolved/conflict analysis and labels it.", {
              "request": {"type": "string", "maxLength": 20000},
              "understanding": {"type": "object",
                                "description": "Optional prior understanding object"},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["request", "confirm"]),
    _tool("llm_engine_compatibility", "Reason about Unity/Unreal/Godot compatibility for the "
          "request and platform. A recommendation is never treated as an installed or verified "
          "engine; pass detected installations separately.", {
              "request": {"type": "string", "maxLength": 20000},
              "engine": {"type": "string", "enum": list(engines.ENGINES)},
              "platform": {"type": "string"},
              "understanding": {"type": "object"},
              "installed_engines": {"type": "array", "items": {"type": "string"}},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["request", "confirm"]),
    _tool("llm_plan_architecture", "Design systems, dependencies, asset/animation plans and "
          "milestones grounded in requirement ids. Returns a proposal, never implementation "
          "evidence.", {
              "request": {"type": "string", "maxLength": 20000},
              "understanding": {"type": "object"},
              "specification": {"type": "object"},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["request", "confirm"]),
    _tool("llm_validate_plan", "Validate a plan structurally (coverage, dependencies, "
          "acceptance tests, traceability, execution-plan safety) and optionally add an LLM "
          "review. The deterministic verdict cannot be upgraded by the model.", {
              "plan": {"type": "object"},
              "request": {"type": "string", "maxLength": 20000},
              "understanding": {"type": "object"},
              "project_path": PROJECT_PATH,
              "use_llm": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["plan"]),
    _tool("llm_build_execution_plan", "Map an approved specification onto governed MCP tool "
          "steps. Deterministic, read-only planning: never executes anything, never emits a "
          "shell command, and marks paid steps as requiring explicit approval.", {
              "specification": {"type": "object"},
              "understanding": {"type": "object"},
              "include_paid_options": {"type": "boolean", "default": True},
          }, ["specification"]),
    _tool("llm_trace_requirements", "Build a requirement trace map from understanding to "
          "specification and manifest. Copies status only when the manifest records it.", {
              "understanding": {"type": "object"},
              "specification": {"type": "object"},
              "project_path": PROJECT_PATH,
          }, ["understanding"]),
    _tool("llm_test_provider", "Send one small real request to the configured provider to prove "
          "reachability. Requires confirm=true; refuses hosted providers in local-only mode. "
          "Failure is reported, never simulated.", {
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
          }, ["confirm"]),
    _tool("llm_review_plan", "Ask the configured LLM to review a plan for feasibility, gaps and "
          "unapproved assumptions. Returns advice only. Requires confirm=true.", {
              "plan": {"type": "object"},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["plan", "confirm"]),
    _tool("llm_game_director_plan", "AI Game Director: combine LLM understanding with real "
          "project/manifest evidence to produce a grounded, structured roadmap. Project content "
          "is never sent unless explicitly requested and allowed. Requires confirm=true.", {
              "request": {"type": "string", "maxLength": 20000},
              "project_path": PROJECT_PATH,
              "include_project_content": {"type": "boolean", "default": False},
              "confirm": CONFIRM,
              "operation_id": OPERATION_ID,
          }, ["request", "confirm"]),
    _tool("llm_provider_capabilities", "Report adapter-level capability states for every "
          "provider (supported/unsupported/unknown), task categories, limitations and the "
          "rule that model names are never treated as capability evidence. No network calls."),
    _tool("llm_list_models", "List models from one provider using its documented discovery "
          "endpoint. Performs one real read-only request, so it requires confirm=true. "
          "Capabilities stay unknown unless the provider exposes documented metadata. "
          "Ollama is never installed or started.", {
              "provider": {"type": "string",
                           "enum": list(llm_config.PROVIDERS)},
              "project_path": PROJECT_PATH,
              "confirm": CONFIRM,
          }, ["confirm"]),
    _tool("llm_route", "Select a provider/model for a task category and required "
          "capabilities. Refuses known-unsupported capabilities, labels unknown ones, "
          "honours budgets and never silently switches to a paid provider. No network calls.", {
              "task": {"type": "string",
                       "enum": list(llm_capabilities.TASK_CATEGORIES)},
              "required_capabilities": {"type": "array",
                                        "items": {"type": "string",
                                                  "enum": list(
                                                      llm_capabilities.CAPABILITY_KEYS)}},
              "context_chars": {"type": "integer", "minimum": 0},
              "max_tokens": {"type": "integer", "minimum": 1},
              "provider": {"type": "string", "enum": list(llm_config.PROVIDERS)},
              "model": {"type": "string"},
              "allow_paid": {"type": "boolean", "default": False,
                             "description": "Explicit approval to consider hosted providers"},
              "require_known": {"type": "boolean", "default": False,
                                "description": "Reject unknown capabilities instead of "
                                               "labelling them unverified"},
              "discovered": {"type": "object",
                             "description": "Optional provider -> model entries from "
                                            "llm_list_models for model checks"},
          }, ["task"]),
    _tool("llm_configure_provider", "Persist the machine-local provider selection, model and "
          "endpoint. Never stores a credential. Requires confirm=true.", {
              "provider": {"type": "string", "enum": list(llm_config.PROVIDERS)},
              "model": {"type": "string"},
              "base_url": {"type": "string"},
              "confirm": CONFIRM,
          }, ["provider", "confirm"]),
    _tool("llm_configure_credential", "Store or clear a provider credential in the private "
          "machine-local secrets file. The value is never returned, logged or written to "
          "project files. Requires confirm=true. Does not perform a paid request.", {
              "provider": {"type": "string", "enum": list(llm_config.PROVIDERS)},
              "api_key": {"type": "string",
                          "description": "Credential value; redacted from every response"},
              "action": {"type": "string", "enum": ["set", "clear"], "default": "set"},
              "confirm": CONFIRM,
          }, ["provider", "confirm"]),
    _tool("orchestrate_game_plan", "Run the V6 Phase 2 typed multi-agent orchestration "
          "deterministically: Game Director, Game Designer, Technical Architect, "
          "Character, Environment, Gameplay, UI/UX and QA plan a project with a "
          "dependency graph, conflict detection and evidence. Produces a "
          "non-executable plan only; no provider, engine, Blender or asset write "
          "occurs and nothing is generated.", {
              "request": {"type": "string", "minLength": 1, "maxLength": 20000,
                          "description": "Original game request, unedited"},
              "engine": {"type": "string",
                         "description": "Optional engine hint; only honoured if detected"},
              "platform": {"type": "string"},
              "quality_target": {"type": "string",
                                 "enum": list(QUALITY_PROFILES),
                                 "default": "prototype"},
              "concurrency": {"type": "integer", "minimum": 1, "maximum": 4,
                              "default": 2,
                              "description": "Maximum concurrently running agents"},
              "max_retries": {"type": "integer", "minimum": 0, "maximum": 3,
                              "default": 1},
              "installed_engines": {"type": "array", "items": {"type": "string"},
                                    "description": "Defaults to locally detected "
                                                   "engines"},
              "approved_decisions": {"type": "array", "items": {"type": "object"},
                                     "description": "Approved project decisions the "
                                                    "director must not override"},
          }, ["request"]),
]

HANDLERS = {
    "studio_info": tool_studio_info,
    "detect_system": tool_detect_system,
    "detect_game_engines": tool_detect_game_engines,
    "list_available_engines": tool_list_available_engines,
    "select_game_engine": tool_select_game_engine,
    "inspect_engine_capabilities": tool_inspect_engine_capabilities,
    "inspect_game_project": tool_inspect_game_project,
    "configure_studio": tool_configure_studio,
    "list_studio_projects": tool_list_studio_projects,
    "read_studio_audit": tool_read_studio_audit,
    "blender_info": tool_blender_info,
    "blender_inspect_blend": tool_blender_inspect,
    "blender_validate_asset": tool_blender_validate,
    "blender_export_asset": tool_blender_export,
    "blender_import_asset": tool_blender_import,
    "blender_render_preview": tool_blender_render,
    "blender_create_environment_blockout": tool_blender_environment,
    "blender_run_python": tool_blender_run_python,
    "character_generate_asset": tool_character_generate,
    "character_capabilities": tool_character_capabilities,
    "environment_generate_asset": tool_environment_generate,
    "environment_profiles": tool_environment_profiles,
    "meshy_balance": tool_meshy_balance,
    "meshy_setup_guide": tool_meshy_setup,
    "meshy_configure_api_key": tool_meshy_configure,
    "meshy_clear_api_key": tool_meshy_clear,
    "meshy_text_to_3d": tool_meshy_text_to_3d,
    "meshy_rig_character": tool_meshy_rig,
    "meshy_animation_library": tool_meshy_animation_library,
    "meshy_create_animation": tool_meshy_create_animation,
    "meshy_task_status": tool_meshy_task_status,
    "meshy_wait_for_task": tool_meshy_wait,
    "meshy_cancel_task": tool_meshy_cancel,
    "meshy_download_output": tool_meshy_download,
    "meshy_generate_asset": tool_meshy_generate,
    "list_asset_providers": tool_asset_providers,
    "search_assets": tool_asset_search,
    "download_polyhaven_asset": tool_asset_download,
    "inspect_asset_license": tool_asset_license,
    "validate_asset_file": tool_asset_validate,
    "create_asset_manifest": tool_asset_manifest,
    "inspect_animation_rig": tool_animation_inspect,
    "create_animation_retarget_map": tool_animation_retarget_map,
    "check_animation_compatibility": tool_animation_compatibility,
    "list_animation_sources": tool_animation_sources,
    "stage_asset_for_engine": tool_engine_stage,
    "verify_staged_import": tool_engine_verify,
    "engine_build": tool_engine_build,
    "unity_editor_status": tool_unity_status,
    "unity_list_commands": tool_unity_commands,
    "unity_run_command": tool_unity_run_command,
    "unity_batch_refresh": tool_unity_refresh,
    "unity_run_tests": tool_unity_tests,
    "unity_build": tool_unity_build,
    "godot_batch_import": tool_godot_import,
    "godot_build": tool_godot_build,
    "unreal_status": tool_unreal_status,
    "analyze_game_request": tool_analyze_game_request,
    "create_game_specification": tool_create_game_specification,
    "init_project_manifest": tool_init_project_manifest,
    "get_project_manifest": tool_get_project_manifest,
    "update_requirement_status": tool_update_requirement_status,
    "record_project_decision": tool_record_project_decision,
    "track_project_progress": tool_track_project_progress,
    "compare_project_against_requirements": tool_compare_requirements,
    "get_execution_mode": tool_get_execution_mode,
    "set_execution_mode": tool_set_execution_mode,
    "set_permission": tool_set_permission,
    "list_operations": tool_list_operations,
    "get_operation": tool_get_operation,
    "cancel_operation": tool_cancel_operation,
    "cleanup_operation": tool_cleanup_operation,
    "operation_status": tool_operation_status,
    "recover_operations": tool_recover_operations,
    "inspect_requirement_evidence": tool_inspect_requirement_evidence,
    "run_requirement_verification": tool_run_requirement_verification,
    "llm_status": tool_llm_status,
    "llm_understand_request": tool_llm_understand_request,
    "llm_generate_specification": tool_llm_generate_specification,
    "llm_analyze_ambiguities": tool_llm_analyze_ambiguities,
    "llm_engine_compatibility": tool_llm_engine_compatibility,
    "llm_plan_architecture": tool_llm_plan_architecture,
    "llm_validate_plan": tool_llm_validate_plan,
    "llm_build_execution_plan": tool_llm_build_execution_plan,
    "llm_trace_requirements": tool_llm_trace_requirements,
    "llm_test_provider": tool_llm_test_provider,
    "llm_review_plan": tool_llm_review_plan,
    "llm_game_director_plan": tool_llm_game_director,
    "llm_provider_capabilities": tool_llm_provider_capabilities,
    "llm_list_models": tool_llm_list_models,
    "llm_route": tool_llm_route,
    "llm_configure_provider": tool_llm_configure_provider,
    "llm_configure_credential": tool_llm_configure_credential,
    "orchestrate_game_plan": tool_orchestrate_game_plan,
}


# --------------------------------------------------------------------------
# MCP transport
# --------------------------------------------------------------------------
def text_result(payload: object, is_error: bool = False) -> dict:
    text = json.dumps(payload, indent=2, default=str)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n... [truncated]"
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _error(message: str, **extra) -> dict:
    return {"ok": False, "error": message, "generated_at": now_iso(), **extra}


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": (req.get("params") or {}).get(
                    "protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Real game-studio tools. Start with analyze_game_request on the user's "
                    "unedited words, then create_game_specification; persist the approved plan "
                    "with init_project_manifest. Read studio_info and detect_game_engines before "
                    "engine work. Never claim an asset is imported or a build is verified without "
                    "evidence. Paid Meshy calls and all project writes require explicit approval."
                ),
            },
        }
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(_error(f"unknown tool: {name}"), True)}
        if not isinstance(arguments, dict):
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(_error("arguments must be an object"), True)}
        try:
            payload = handler(arguments)
            ok = bool(payload.get("ok", True)) if isinstance(payload, dict) else True
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(payload, not ok)}
        except ToolError as exc:
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(_error(str(exc), tool=name), True)}
        except Exception as exc:  # keep the transport alive, log the trace to stderr
            log(f"{name} failed: {exc}")
            traceback.print_exc(file=sys.stderr)
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": text_result(
                        _error(f"unexpected failure in {name}: {exc}", tool=name), True)}
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": req_id, "result": {key: []}}
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    log(f"starting {SERVER_NAME} {SERVER_VERSION}")
    try:
        recovered = operations.recover_interrupted()
        if recovered.get("count"):
            log(f"marked {recovered['count']} interrupted operation(s) from a previous run")
    except Exception as exc:  # never block startup on registry recovery
        log(f"operation recovery skipped: {exc}")

    def write_response(responses: object) -> None:
        with _write_lock:
            sys.stdout.write(json.dumps(responses, default=str) + "\n")
            sys.stdout.flush()

    def run_async(request: dict) -> None:
        # tools/call runs on a worker thread so cancel_operation can be serviced
        # while a long Blender/engine/LLM call is still blocking.
        try:
            response = handle(request)
        except Exception as exc:  # pragma: no cover - defensive
            log(f"async tool call crashed: {exc}")
            response = {"jsonrpc": "2.0", "id": request.get("id"),
                        "error": {"code": -32603, "message": "internal error"}}
        if response is not None:
            write_response(response)

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"invalid JSON: {exc}")
            continue
        if isinstance(request, list):
            for item in request:
                if not isinstance(item, dict):
                    continue
                if item.get("method") == "tools/call":
                    threading.Thread(target=run_async, args=(item,), daemon=True).start()
                else:
                    response = handle(item)
                    if response is not None:
                        write_response(response)
        elif isinstance(request, dict):
            if request.get("method") == "tools/call":
                threading.Thread(target=run_async, args=(request,), daemon=True).start()
            else:
                response = handle(request)
                if response is not None:
                    write_response(response)


if __name__ == "__main__":
    main()
