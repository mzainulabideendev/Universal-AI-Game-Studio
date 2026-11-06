"""Deterministic MCP execution-plan generation.

The LLM may recommend *what* should happen. This module decides *which existing
MCP tool* would perform an approved step, and it never executes anything.

Design rules:

* only tools that exist in the Game Studio MCP server may appear;
* no free-form shell command, script or URL is generated;
* paid/credit operations are explicitly marked and blocked by default;
* every write, editor run and build carries its confirmation requirement;
* the plan is data, so a client can show it to the user before anything runs.

``executable`` is always ``False``: a plan is not an action.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..util import ToolError

PLAN_SCHEMA_VERSION = "1.0"

# capability -> tool name, risk class and default confirmation requirement.
TOOL_CATALOG: dict[str, dict] = {
    "inspect_project": {"tool": "inspect_game_project", "risk": "read",
                        "confirm": False, "cost": "free"},
    "inspect_engine": {"tool": "inspect_engine_capabilities", "risk": "read",
                       "confirm": False, "cost": "free"},
    "select_engine": {"tool": "select_game_engine", "risk": "write",
                      "confirm": True, "cost": "free"},
    "init_manifest": {"tool": "init_project_manifest", "risk": "write",
                      "confirm": True, "cost": "free"},
    "track_progress": {"tool": "track_project_progress", "risk": "read",
                       "confirm": False, "cost": "free"},
    "compare_requirements": {"tool": "compare_project_against_requirements",
                             "risk": "read", "confirm": False, "cost": "free"},
    "search_assets": {"tool": "search_assets", "risk": "read",
                      "confirm": False, "cost": "free"},
    "download_asset": {"tool": "download_polyhaven_asset", "risk": "external",
                       "confirm": True, "cost": "free"},
    "blender_blockout": {"tool": "blender_create_environment_blockout",
                         "risk": "local-process", "confirm": True, "cost": "free"},
    "blender_validate": {"tool": "blender_validate_asset", "risk": "read",
                         "confirm": False, "cost": "free"},
    "blender_export": {"tool": "blender_export_asset", "risk": "write",
                       "confirm": True, "cost": "free"},
    "meshy_generate": {"tool": "meshy_text_to_3d", "risk": "paid",
                       "confirm": True, "cost": "paid"},
    "meshy_rig": {"tool": "meshy_rig_character", "risk": "paid",
                  "confirm": True, "cost": "paid"},
    "meshy_animate": {"tool": "meshy_create_animation", "risk": "paid",
                      "confirm": True, "cost": "paid"},
    "inspect_animation": {"tool": "inspect_animation_rig", "risk": "read",
                          "confirm": False, "cost": "free"},
    "retarget_map": {"tool": "create_animation_retarget_map", "risk": "read",
                     "confirm": False, "cost": "free"},
    "check_animation": {"tool": "check_animation_compatibility", "risk": "read",
                        "confirm": False, "cost": "free"},
    "stage_asset": {"tool": "stage_asset_for_engine", "risk": "write",
                    "confirm": True, "cost": "free"},
    "verify_import": {"tool": "verify_staged_import", "risk": "read",
                      "confirm": False, "cost": "free"},
    "unity_refresh": {"tool": "unity_batch_refresh", "risk": "engine-run",
                      "confirm": True, "cost": "free"},
    "unity_tests": {"tool": "unity_run_tests", "risk": "engine-run",
                    "confirm": True, "cost": "free"},
    "unity_build": {"tool": "unity_build", "risk": "engine-run",
                    "confirm": True, "cost": "free"},
    "godot_import": {"tool": "godot_batch_import", "risk": "engine-run",
                     "confirm": True, "cost": "free"},
    "godot_build": {"tool": "godot_build", "risk": "engine-run",
                    "confirm": True, "cost": "free"},
    "unreal_status": {"tool": "unreal_status", "risk": "read",
                      "confirm": False, "cost": "free"},
    "engine_build": {"tool": "engine_build", "risk": "engine-run",
                     "confirm": True, "cost": "free"},
}

ALLOWED_TOOLS = frozenset(item["tool"] for item in TOOL_CATALOG.values())

# Keys an LLM must never smuggle into a step: these would turn a plan into an
# arbitrary execution surface.
FORBIDDEN_KEYS = frozenset({
    "command", "cmd", "shell", "powershell", "bash", "script", "code",
    "exec", "execute", "run", "url", "endpoint", "raw",
})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _step(step_id: str, phase: str, capability: str, reason: str,
          *, requirement_ids: list[str] | None = None,
          blocked: bool = False, blocked_reason: str | None = None) -> dict:
    entry = TOOL_CATALOG.get(capability)
    if entry is None:
        raise ToolError(f"unknown execution capability: {capability}")
    requires_paid_approval = entry["cost"] == "paid"
    return {
        "id": step_id,
        "phase": phase,
        "capability": capability,
        "tool": entry["tool"],
        "reason": reason,
        "requirement_ids": requirement_ids or [],
        "risk": entry["risk"],
        "requires_confirm": bool(entry["confirm"]),
        "cost": entry["cost"],
        "requires_paid_approval": requires_paid_approval,
        "allowed_by_default": not blocked and not requires_paid_approval,
        "blocked": blocked,
        "blocked_reason": blocked_reason,
        "executed": False,
    }


def _requirement_ids(spec: dict, *categories: str) -> list[str]:
    wanted = {category.lower() for category in categories}
    result = []
    for item in spec.get("requirements") or []:
        if str(item.get("category") or "").lower() in wanted:
            result.append(str(item.get("id")))
    return result


def build_execution_plan(specification: dict, *, understanding: dict | None = None,
                         include_paid_options: bool = True) -> dict:
    """Map an approved specification onto governed MCP tool steps."""
    if not isinstance(specification, dict):
        raise ToolError("specification must be an object")
    engine = (specification.get("engine") or {}).get("selected")
    has_characters = bool(specification.get("characters"))
    mechanics = set()
    if isinstance(understanding, dict):
        value = understanding.get("mechanics")
        if isinstance(value, list):
            mechanics.update(str(item).lower() for item in value)
    animation_categories = ("animation", "gameplay", "movement")
    anim_ids = _requirement_ids(specification, *animation_categories)

    available = []
    blocked = []
    paid = []

    def add(step: dict) -> None:
        if step["blocked"]:
            blocked.append(step)
        elif step["requires_paid_approval"]:
            paid.append(step)
        else:
            available.append(step)

    # Phase 0: ground truth and memory.
    add(_step("P0-inspect", "ground-truth", "inspect_project",
              "Read the real project before writing anything."))
    add(_step("P0-engine", "ground-truth", "inspect_engine",
              "Confirm which engine features are actually implemented."))
    if not engine:
        add(_step("P0-select", "ground-truth", "select_engine",
                  "No engine is approved yet; implementation cannot start.",
                  blocked=True,
                  blocked_reason="engine is unresolved in the specification"))
    add(_step("P0-manifest", "ground-truth", "init_manifest",
              "Persist the approved requirements so progress is auditable.",
              requirement_ids=_requirement_ids(specification)))

    # Phase 1: assets and animation dependencies.
    add(_step("P1-search", "assets", "search_assets",
              "Find licensed candidates before generating new assets."))
    add(_step("P1-download", "assets", "download_asset",
              "Download only explicitly approved, licence-checked assets."))
    add(_step("P1-blockout", "assets", "blender_blockout",
              "Block out the environment to validate layout and scale."))
    add(_step("P1-validate", "assets", "blender_validate",
              "Validate triangles, UVs, transforms and rigs before import."))

    if include_paid_options:
        add(_step("P1-meshy", "assets", "meshy_generate",
                  "Optional paid generation for a missing character or prop.",
                  requirement_ids=_requirement_ids(specification, "character",
                                                   "environment")))
    if has_characters:
        if include_paid_options:
            add(_step("P1-rig", "animation", "meshy_rig",
                      "Optional paid rigging if no suitably licensed rig exists.",
                      requirement_ids=anim_ids))
            add(_step("P1-animate", "animation", "meshy_animate",
                      "Optional paid animation if the required clips are missing.",
                      requirement_ids=anim_ids))
        add(_step("P1-inspect-anim", "animation", "inspect_animation",
                  "Inspect the real rig and clips before referencing states.",
                  requirement_ids=anim_ids))
        add(_step("P1-retarget", "animation", "retarget_map",
                  "Produce a bone map; correctness still needs playback testing.",
                  requirement_ids=anim_ids))
        add(_step("P1-check-anim", "animation", "check_animation",
                  "Report compatibility gaps instead of assuming retargeting works.",
                  requirement_ids=anim_ids))

    # Phase 2: engine integration and verification.
    add(_step("P2-stage", "engine", "stage_asset",
              "Stage validated assets inside the project with a hash record.",
              requirement_ids=_requirement_ids(specification, "technical")))
    add(_step("P2-verify-import", "engine", "verify_import",
              "Verify the import artefact exists; visual playback still needs a check."))
    if engine == "unity":
        add(_step("P2-refresh", "engine", "unity_refresh",
                  "Refresh the Unity asset database in batch mode."))
        add(_step("P2-tests", "engine", "unity_tests",
                  "Run the project's automated tests and parse results."))
        add(_step("P2-build", "engine", "unity_build",
                  "Produce a real player build and verify the artefact."))
    elif engine == "godot":
        add(_step("P2-refresh", "engine", "godot_import",
                  "Import the project headlessly."))
        add(_step("P2-build", "engine", "godot_build",
                  "Export a real build using a configured preset."))
    elif engine == "unreal":
        add(_step("P2-status", "engine", "unreal_status",
                  "Unreal automation is staged-only; confirm the real editor state."))
        add(_step("P2-build", "engine", "engine_build",
                  "Build only if the adapter reports a real implementation.",
                  blocked=True,
                  blocked_reason="Unreal build automation is not implemented; "
                                 "do not claim a build"))
    else:
        add(_step("P2-build", "engine", "engine_build",
                  "No verified engine selected.", blocked=True,
                  blocked_reason="engine is unresolved"))

    # Phase 3: evidence and acceptance.
    add(_step("P3-compare", "evidence", "compare_requirements",
              "Re-check every requirement against real evidence."))
    add(_step("P3-progress", "evidence", "track_progress",
              "Report coverage and remaining P0/P1 gaps honestly."))

    all_steps = available + paid + blocked
    return {
        "ok": True,
        "schema_version": PLAN_SCHEMA_VERSION,
        "generated_at": _now(),
        "executable": False,
        "note": ("This is a plan, not an execution. Every step must still pass the "
                 "governance permission check and its own confirm gate. Paid steps are "
                 "blocked until the user explicitly approves spending."),
        "engine": engine,
        "steps": all_steps,
        "counts": {
            "total": len(all_steps),
            "available": len(available),
            "paid_requires_approval": len(paid),
            "blocked": len(blocked),
        },
        "allowed_tools": sorted(ALLOWED_TOOLS),
        "constraints": [
            "no arbitrary shell or filesystem operation is generated",
            "only tools registered in the Game Studio MCP may appear",
            "paid generation is never auto-approved",
            "a plan does not prove implementation",
        ],
    }


def validate_execution_plan(plan: dict) -> list[str]:
    """Return structural and safety errors. Empty means acceptable."""
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    if plan.get("executable") is not False:
        errors.append("plan.executable must be false; plans never execute directly")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("plan.steps must be a non-empty array")
        return errors
    for index, step in enumerate(steps):
        path = f"steps[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{path}: must be an object")
            continue
        for key in FORBIDDEN_KEYS & set(step):
            errors.append(f"{path}: forbidden execution key {key!r}")
        tool = step.get("tool")
        if tool not in ALLOWED_TOOLS:
            errors.append(f"{path}: tool {tool!r} is not in the MCP allow-list")
        for required in ("id", "phase", "reason"):
            if not step.get(required):
                errors.append(f"{path}: missing {required}")
        if step.get("cost") == "paid" and not step.get("requires_paid_approval"):
            errors.append(f"{path}: paid steps must require explicit approval")
        if step.get("requires_confirm") is not True and step.get("risk") in (
                "write", "external", "local-process", "engine-run", "paid"):
            errors.append(f"{path}: risky step must require confirmation")
        if step.get("executed") is not False:
            errors.append(f"{path}: a generated plan must not claim execution")
    return errors


def plan_from_parameters(*, specification: dict, understanding: dict | None = None,
                         include_paid_options: bool = True) -> dict:
    """Build and validate a plan in one call."""
    plan = build_execution_plan(specification, understanding=understanding,
                                include_paid_options=include_paid_options)
    errors = validate_execution_plan(plan)
    plan["validation"] = {"ok": not errors, "errors": errors}
    if errors:
        raise ToolError("execution plan failed validation: " + "; ".join(errors[:5]))
    return plan
