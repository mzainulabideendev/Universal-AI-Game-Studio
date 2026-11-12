"""Idea -> requirements -> design -> validated specification -> reviewable plan.

This is the Phase 7 bridge between the Phase 6 intelligence layer and the Phase
3/4/5 delivery interfaces. It is intentionally *specification only*:

- No character, environment, texture or animation is generated.
- The Phase 5 Unity project is inspected read-only at most.
- No engine build is started.
- Every output is labelled ``proposal``, ``executable=False`` and
  ``ai_generated_asset=False``.
- Requirements proposed by a model are never marked implemented or verified.

The same functions accept either the deterministic Phase 6 design or a
schema-validated provider payload. The caller must pass the correct ``source``
label; nothing upgrades a proposal to verified on its own.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import intelligence
from . import response_validation as rv

SCHEMA_VERSION = 1
PHASE5_ROOT = Path(__file__).resolve().parents[4] / "validation" / "unity-jungle-v6"

PHASE5_INTERFACES = (
    "Assets/V6/Scripts/Player/PlayerMovement.cs",
    "Assets/V6/Scripts/Player/PlayerInputHandler.cs",
    "Assets/V6/Scripts/Player/GroundDetector.cs",
    "Assets/V6/Scripts/Player/PlayerCollisionHandler.cs",
    "Assets/V6/Scripts/Collectibles/Collectible.cs",
    "Assets/V6/Scripts/Collectibles/CollectibleManager.cs",
    "Assets/V6/Scripts/Camera/CameraFollowController.cs",
    "Assets/V6/Scripts/Core/GameStateController.cs",
    "Assets/V6/Scripts/Core/LevelManager.cs",
    "Assets/V6/Scripts/Core/ObjectiveManager.cs",
    "Assets/V6/Scripts/Core/CheckpointManager.cs",
    "Assets/V6/Scripts/Core/DestinationZone.cs",
)

PLAYER_CONTROLS = (
    "Move with WASD / left stick",
    "Camera follows the player with a limited orbit",
    "Jump with Space / south button",
    "Interact with E / west button",
    "Pause with Escape, restart with R",
)


def _stable_id(*parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8"))
    return "REQ-" + digest.hexdigest()[:10].upper()


def _normalise_requirement(item: dict, *, engine: str,
                           source: str) -> dict:
    description = str(item.get("description") or "Unspecified requirement")
    requirement_id = _stable_id(engine, item.get("category"), description.lower())
    return {
        "requirement_id": requirement_id,
        "id": str(item.get("id") or requirement_id),
        "description": description,
        "category": str(item.get("category") or "system"),
        "priority": str(item.get("priority") or "P1"),
        "dependencies": list(item.get("dependencies") or []),
        "acceptance_criteria": str(item.get("acceptance_criteria")
                                   or "An observable play-mode or build check passes."),
        "required_assets": list(item.get("required_assets") or []),
        "target_engine": str(item.get("target_engine") or engine),
        "target_platforms": list(item.get("target_platforms") or []),
        "verification_method": str(item.get("verification_method")
                                   or "Run the stated acceptance test and record evidence."),
        "provenance": str(item.get("provenance") or "agent_recommendation"),
        "confidence": item.get("confidence") if item.get("confidence") is not None else 0.5,
        "implementation_status": "not_implemented",
        "human_approved": False,
        "unsupported_assumptions": list(item.get("unsupported_assumptions") or []),
        "source": source,
        "extraction_source": "game_studio.understanding deterministic parser",
        "status": "proposed",
    }


def requirements_from_idea(idea: str, *, engine: str = "unity",
                           platforms: list[str] | None = None,
                           source: str = "deterministic") -> dict:
    """Decompose an idea into stable, traceable, non-approved requirements.

    The deterministic parser can emit the same statement twice (for example an
    optional feature mentioned in two keyword lists). Requirement IDs are a
    hash of engine, category and description, so duplicates would otherwise
    collapse into one ID and fail specification validation. Keep the first
    occurrence and preserve source order.
    """
    proposal = intelligence.requirements(idea, engine=engine)
    requirements: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in proposal["requirements"]:
        key = (str(item.get("category") or "system").lower(),
               str(item.get("description") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        requirements.append(
            _normalise_requirement(item, engine=engine, source=source))
    platform_values = list(platforms or [])
    for item in requirements:
        item["target_platforms"] = list(platform_values)
    unsupported = proposal.get("unsupported_features") or []
    for item in requirements:
        lowered = item["description"].lower()
        item["unsupported_assumptions"] = [
            feature["feature"] for feature in unsupported
            if feature["feature"].replace("_", " ") in lowered
        ]
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "engine": engine,
        "request": proposal["request"],
        "requirements": requirements,
        "coverage": proposal["coverage"],
        "contradictions": proposal["contradictions"],
        "unsupported_features": unsupported,
        "blocked_requirements": proposal["blocked_requirements"],
        "missing_information": proposal["missing_information"],
        "validation": proposal["validation"],
        "counts": {
            "total": len(requirements),
            "user_requirement": sum(1 for item in requirements
                                    if item["provenance"] == "user_requirement"),
            "recommendation": sum(1 for item in requirements
                                  if item["provenance"] != "user_requirement"),
            "blocked": len(proposal["blocked_requirements"]),
        },
        "executable": False,
        "human_approved": False,
        "note": ("Proposal only. Requirement IDs are stable across runs; none is "
                 "implemented, verified or human-approved."),
    }


def ai_payload_to_design(payload: dict, *, engine: str = "unity") -> dict:
    """Map a validated provider response into the Phase 6 design shape.

    This does not make the response verified. It only lets the existing Phase 3/4
    spec builders consume it without duplicating their logic.
    """
    platforms = rv._as_list(payload.get("target_platforms"))
    environment = rv._as_list(payload.get("environment_requirements"))
    mechanics = rv._as_list(payload.get("player_mechanics"))
    collectibles = rv._as_list(payload.get("collectibles"))
    progression = rv._as_list(payload.get("progression"))
    loop = " ".join(rv._as_list(payload.get("core_gameplay_loop")))
    concept = " ".join(
        [str(payload.get("game_title") or "Untitled"),
         str(payload.get("summary") or ""),
         " ".join(environment), loop]).strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "request": concept,
        "concept": concept or "Untitled game proposal",
        "genre": rv._as_list(payload.get("genre")),
        "dimension": [str(payload.get("dimension") or "3d")],
        "target_platform": platforms,
        "art_style": [str(payload.get("art_style") or "stylized")],
        "quality_target": "prototype",
        "core_gameplay_loop": loop,
        "player_mechanics": mechanics,
        "environment_requirements": environment,
        "character_requirements": [
            "Player character described by the approved specification"],
        "animation_requirements": ["idle", "walk", "run", "jump", "landing"],
        "uiux_requirements": rv._as_list(payload.get("ui_requirements")),
        "audio_requirements": rv._as_list(payload.get("audio_requirements")),
        "physics_requirements": ["character collision", "collectible trigger",
                                 "terrain/ground contact"],
        "performance_targets": dict(payload.get("performance_targets") or {}),
        "asset_requirements": rv._as_list(payload.get("asset_requirements")),
        "technical_constraints": [
            f"Target engine: {engine}",
            "Procedural Blender assets are not AI-generated assets.",
            "No paid provider may be used under free-only policy.",
        ],
        "testing_requirements": rv._as_list(payload.get("acceptance_criteria")),
        "milestones": [],
        "user_requirements": [],
        "recommendations": [],
        "assumptions": [],
        "unsupported_features": [],
        "blocked_requirements": [],
        "approved_decisions": [],
        "missing_information": [],
        "contradictions": [],
        "provenance": {"mode": "ai_provider", "live_model_quality_claimed": False},
        "executable": False,
    }


def payload_from_design(design: dict, *, engine: str = "unity") -> dict:
    """Express a deterministic Phase 6 design in the Phase 7 response contract.

    This lets the same rubric score offline fixtures and provider responses
    without pretending the deterministic output came from a model.
    """
    performance = design.get("performance_targets") or {}
    loop = design.get("core_gameplay_loop")
    if isinstance(loop, str):
        loop = [loop]
    return {
        "game_title": str(design.get("concept")
                          or design.get("request")
                          or "Untitled game specification")[:120],
        "genre": rv._as_list(design.get("genre")),
        "target_platforms": rv._as_list(design.get("target_platform")),
        "core_gameplay_loop": rv._as_list(loop),
        "player_mechanics": rv._as_list(design.get("player_mechanics")),
        "camera_design": "Third-person follow camera with collision handling",
        "environment_requirements": rv._as_list(
            design.get("environment_requirements")),
        "collectibles": rv._as_list(design.get("collectibles")),
        "hazards": rv._as_list(design.get("hazards")),
        "progression": rv._as_list(design.get("milestones")
                                   or design.get("progression")),
        "ui_requirements": rv._as_list(design.get("uiux_requirements")),
        "audio_requirements": rv._as_list(design.get("audio_requirements")),
        "performance_targets": dict(performance) if isinstance(performance, dict) else {},
        "technical_architecture": rv._as_list(design.get("technical_constraints")),
        "asset_requirements": rv._as_list(design.get("asset_requirements")),
        "acceptance_criteria": rv._as_list(design.get("testing_requirements")),
        "risks": ["Feasibility is untested until a build and measurement run happen."],
        "unsupported_or_uncertain": rv._as_list(design.get("unsupported_features")),
        "engine": engine,
        "dimension": (design.get("dimension") or ["3d"])[0]
        if isinstance(design.get("dimension"), list) else str(design.get("dimension") or "3d"),
        "art_style": ", ".join(rv._as_list(design.get("art_style"))) or "stylized",
        "summary": str(design.get("concept") or "")[:2000],
    }


def feasibility(spec: dict) -> dict:
    """Deterministic, labelled feasibility assessment. Never claims validation."""
    engine = str(spec.get("engine") or "").lower()
    platforms = [item.lower() for item in spec.get("target_platforms") or []]
    checks: list[dict] = []
    if engine in ("unity", "unreal", "godot"):
        checks.append({
            "item": "engine", "value": engine, "status": "supported_engineering_target",
            "reason": "An adapter exists in this repository, but a build is not run in Phase 7.",
        })
    else:
        checks.append({
            "item": "engine", "value": engine or None, "status": "unsupported",
            "reason": "No adapter exists for this engine.",
        })
    for platform in platforms:
        if platform in ("windows", "pc"):
            checks.append({
                "item": "platform", "value": platform,
                "status": "demonstrated_by_existing_build",
                "reason": ("A real Unity 6000.6.2f1 Windows build exists from Phase 5; "
                           "Phase 7 did not rebuild it."),
            })
        elif platform in ("android", "ios", "web", "webgl", "linux", "macos", "mac"):
            checks.append({
                "item": "platform", "value": platform,
                "status": "requires_unverified_setup",
                "reason": ("No build for this platform was produced or measured in "
                           "Phases 1-6; module/SDK setup and a new build are required."),
            })
        else:
            checks.append({
                "item": "platform", "value": platform, "status": "unverified",
                "reason": "Platform is not part of any measured build.",
            })
    performance = spec.get("performance_targets") or {}
    if isinstance(performance, dict) and performance.get("target_fps"):
        checks.append({
            "item": "performance", "value": performance.get("target_fps"),
            "status": "target_only_not_measured",
            "reason": "A measured FPS from a different build does not validate this target.",
        })
    return {
        "checks": checks,
        "verified": False,
        "measurements_performed": False,
        "note": ("Feasibility is an engineering assessment based on existing adapters "
                 "and previous evidence. It is not a build result."),
    }


def quality_payload(spec: dict) -> dict:
    """Build the rubric view of a specification without altering its provenance.

    The extra ``requirements`` array carries the pipeline's stable IDs so the
    traceability category can be scored. It is an evaluation view, not part of
    the provider response.
    """
    payload = dict(spec.get("ai_payload")
                   or payload_from_design(spec.get("design") or {},
                                          engine=spec.get("engine") or "unity"))
    payload["requirements"] = [
        {"id": item.get("requirement_id"),
         "provenance": item.get("provenance"),
         "acceptance_criteria": item.get("acceptance_criteria")}
        for item in spec.get("requirements") or [] if isinstance(item, dict)
    ]
    return payload


def _phase5_interfaces() -> dict:
    present = {}
    for relative in PHASE5_INTERFACES:
        path = PHASE5_ROOT / relative
        present[relative] = path.is_file()
    return {
        "root": "validation/unity-jungle-v6",
        "read_only": True,
        "modified": False,
        "interfaces": present,
        "missing": [key for key, value in present.items() if not value],
    }


def bridge_character(spec: dict, *, quality_tier: str = "medium") -> dict:
    design = spec.get("design") or {}
    bridged = intelligence.character_spec_from_design(
        design, quality_tier=quality_tier, target_engine=spec.get("engine"))
    requirement_ids = [
        item["requirement_id"] for item in spec.get("requirements") or []
        if "character" in (item.get("category", "") + " " + item.get("description", "")).lower()
        or any("character" in asset.lower() or "rig" in asset.lower()
               for asset in item.get("required_assets") or [])
    ]
    return {
        "ok": True,
        "phase3_interface": "game_studio.character_spec.build_character_spec",
        "requirement_ids": requirement_ids,
        "spec": bridged["spec"],
        "validation": bridged["validation"],
        "provenance": {
            "source": spec.get("source"),
            "phase": 7,
            "requirement_ids": requirement_ids,
        },
        "ai_generated_asset": False,
        "procedural_blender": True,
        "generation_performed": False,
        "phase5_project_modified": False,
        "note": "Specification only. No mesh, texture or animation was generated.",
    }


def bridge_environment(spec: dict, *, quality_tier: str = "medium") -> dict:
    design = spec.get("design") or {}
    bridged = intelligence.environment_spec_from_design(
        design, quality_tier=quality_tier, target_engine=spec.get("engine"))
    requirement_ids = [
        item["requirement_id"] for item in spec.get("requirements") or []
        if "environment" in (item.get("category", "") + " " + item.get("description", "")).lower()
    ]
    return {
        "ok": True,
        "phase4_interface": "game_studio.environment_spec.build_environment_spec",
        "requirement_ids": requirement_ids,
        "spec": bridged["spec"],
        "validation": bridged["validation"],
        "provenance": {
            "source": spec.get("source"),
            "phase": 7,
            "requirement_ids": requirement_ids,
        },
        "ai_generated_asset": False,
        "procedural_blender": True,
        "generation_performed": False,
        "phase5_project_modified": False,
        "note": "Specification only. No terrain, prop or texture was generated.",
    }


def bridge_gameplay(spec: dict) -> dict:
    payload = spec.get("ai_payload") or {}
    design = spec.get("design") or {}
    collectibles = rv._as_list(payload.get("collectibles")) or ["Collectible item"]
    hazards = rv._as_list(payload.get("hazards")) or [
        "Environmental hazard described by the approved specification"]
    objectives = rv._as_list(payload.get("progression")) or [
        "Reach the destination after completing the collection objective"]
    acceptance = rv._as_list(payload.get("acceptance_criteria")) or list(
        design.get("testing_requirements") or [])
    requirement_ids = [
        item["requirement_id"] for item in spec.get("requirements") or []
        if any(word in (item.get("category", "") + " " + item.get("description", "")).lower()
               for word in ("gameplay", "player", "ui", "camera", "physics", "system"))
    ]
    return {
        "ok": True,
        "phase5_interface": "read-only inspection of validation/unity-jungle-v6",
        "requirement_ids": requirement_ids,
        "player_controls": list(PLAYER_CONTROLS),
        "physics_requirements": [
            "Character controller with gravity and ground detection",
            "Trigger colliders for collectibles",
            "Destination trigger for level completion",
        ],
        "collectibles": collectibles,
        "hazards": hazards,
        "objectives": objectives,
        "checkpoints": ["Spawn checkpoint", "Mid-route checkpoint",
                        "Destination/level-complete checkpoint"],
        "camera": [str(payload.get("camera_design")
                       or "Third-person follow camera with collision")],
        "ui": rv._as_list(payload.get("ui_requirements")) or [
            "HUD showing objective counter"],
        "game_states": ["Boot", "MainMenu", "Playing", "Paused", "LevelComplete"],
        "acceptance_tests": acceptance,
        "phase5_interfaces": _phase5_interfaces(),
        "unsupported_features": list(spec.get("unsupported_features") or []),
        "blocked_requirements": list(spec.get("blocked_requirements") or []),
        "provenance": {
            "source": spec.get("source"),
            "phase": 7,
            "requirement_ids": requirement_ids,
        },
        "ai_generated_asset": False,
        "generated": False,
        "phase5_project_modified": False,
        "build_started": False,
        "note": "Gameplay specification only. No scene, script or build was written.",
    }


def build_generation_plan(spec: dict) -> dict:
    """Preview the future execution plan without executing any step."""
    design = spec.get("design") or {}
    engine = spec.get("engine") or "unity"
    steps = [
        {"id": "G1", "step": "Human approves the specification and requirement set",
         "tool": None, "requires_approval": True, "executed": False},
        {"id": "G2", "step": "Generate the character from the Phase 3 spec",
         "tool": "character_generate_asset", "requires_approval": True, "executed": False},
        {"id": "G3", "step": "Generate the environment from the Phase 4 spec",
         "tool": "environment_generate_asset", "requires_approval": True, "executed": False},
        {"id": "G4", "step": f"Integrate assets and gameplay in a {engine} project",
         "tool": "unity_build" if engine == "unity" else "engine_build",
         "requires_approval": True, "executed": False},
        {"id": "G5", "step": "Run engine tests and record evidence",
         "tool": "unity_run_tests" if engine == "unity" else "engine_build",
         "requires_approval": True, "executed": False},
        {"id": "G6", "step": "Build, launch and capture the player",
         "tool": "unity_build" if engine == "unity" else "engine_build",
         "requires_approval": True, "executed": False},
    ]
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "engine": engine,
        "steps": steps,
        "requirements_covered": [item["requirement_id"]
                                 for item in spec.get("requirements") or []],
        "executable": False,
        "executed": False,
        "human_approved": False,
        "asset_generation_performed": False,
        "build_started": False,
        "ai_generated_asset": False,
        "design_quality_target": (design.get("quality_target") or "prototype"),
        "note": ("Preview only. Every step requires explicit human approval and a "
                 "separate authorised run; this document is not an executable plan."),
    }


def validate_spec(spec: object) -> dict:
    """Validate pipeline-level structure and traceability, not game quality."""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return {"valid": False, "errors": ["specification must be an object"]}
    for key in ("schema_version", "source", "engine", "requirements",
                "approval", "generation_plan", "design"):
        if key not in spec:
            errors.append(f"missing field {key!r}")
    requirements = spec.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append("requirements must be a non-empty array")
    else:
        seen: set[str] = set()
        identifiers: set[str] = set()
        for index, item in enumerate(requirements):
            if not isinstance(item, dict):
                errors.append(f"requirements[{index}] is not an object")
                continue
            for key in ("requirement_id", "description", "category", "priority",
                        "dependencies", "acceptance_criteria", "required_assets",
                        "target_engine", "verification_method", "provenance",
                        "implementation_status", "human_approved"):
                if key not in item:
                    errors.append(f"requirements[{index}] missing {key!r}")
            identifier = item.get("requirement_id")
            if identifier in seen:
                errors.append(f"duplicate requirement_id {identifier!r}")
            seen.add(identifier)
            identifiers.add(str(identifier))
            if item.get("id"):
                identifiers.add(str(item["id"]))
            if item.get("implementation_status") in (
                    "verified", "implemented", "completed", "approved"):
                errors.append(f"requirements[{index}] cannot be implemented or "
                              "verified without recorded evidence and human approval")
            if item.get("human_approved") is True:
                errors.append(f"requirements[{index}] cannot be pre-approved")
        for index, item in enumerate(requirements):
            if not isinstance(item, dict):
                continue
            for dependency in item.get("dependencies") or []:
                if str(dependency) not in identifiers:
                    errors.append(f"requirements[{index}] depends on unknown id "
                                  f"{dependency!r}")
    approval = spec.get("approval")
    if isinstance(approval, dict):
        if approval.get("approved") is True:
            errors.append("approval must not be granted by the pipeline")
        if approval.get("status") != "HUMAN_REVIEW_REQUIRED":
            errors.append("approval.status must be HUMAN_REVIEW_REQUIRED")
    plan = spec.get("generation_plan")
    if isinstance(plan, dict):
        if plan.get("executable") is not False:
            errors.append("generation_plan.executable must be false")
        if plan.get("human_approved") is True:
            errors.append("generation_plan cannot be pre-approved")
        if plan.get("build_started") is True:
            errors.append("generation_plan.build_started must be false")
        if plan.get("asset_generation_performed") is True:
            errors.append("generation_plan.asset_generation_performed must be false")
        if any(step.get("executed") for step in plan.get("steps") or []):
            errors.append("no generation step may be marked executed")
    provenance = spec.get("provenance")
    if isinstance(provenance, dict) and provenance.get("human_approved") is True:
        errors.append("provenance.human_approved must remain false before approval")
    for key in ("generation_performed", "phase5_project_modified"):
        if spec.get(key) is True:
            errors.append(f"{key} must be false for a specification")
    if spec.get("ai_generated_asset") is not False:
        errors.append("ai_generated_asset must be false")
    if spec.get("executable") is not False:
        errors.append("specification must not be executable")
    return {"valid": not errors, "errors": errors}


def build_specification(idea: str, *, engine: str = "unity",
                        platforms: list[str] | None = None,
                        quality_tier: str = "medium",
                        ai_payload: dict | None = None,
                        include_bridges: bool = True) -> dict:
    """Build a reviewable specification from an idea or a validated response."""
    if not isinstance(idea, str) or not idea.strip():
        raise ValueError("idea must be a non-empty string")
    if len(idea) > 20_000:
        raise ValueError("idea is too long (max 20000 characters)")

    source = "ai_provider" if ai_payload is not None else "deterministic"
    validation = None
    if ai_payload is not None:
        validation = rv.validate_game_spec(ai_payload, source="ai_provider")
        if not validation["schema_valid"]:
            raise ValueError("provider payload failed schema validation: "
                             + "; ".join(validation["errors"][:5]))
        normalised = validation["normalised"]
        design = ai_payload_to_design(normalised, engine=engine)
        design["validation"] = {"valid": True, "errors": []}
        design["provenance"] = {"mode": "ai_provider"}
        platforms = platforms or rv._as_list(normalised.get("target_platforms"))
        structured = requirements_from_idea(idea, engine=engine,
                                            platforms=platforms, source=source)
    else:
        design = intelligence.design(idea, engine=engine,
                                     platform=(platforms or [None])[0])
        structured = requirements_from_idea(idea, engine=engine,
                                            platforms=platforms, source=source)

    requirements = structured["requirements"]
    spec = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "phase": "V6 Phase 7 - idea to specification",
        "request": idea,
        "source": source,
        "engine": engine,
        "target_platforms": list(platforms or []),
        "quality_tier": quality_tier,
        "design": design,
        "ai_payload": ai_payload,
        "response_validation": validation,
        "requirements": requirements,
        "coverage": structured["coverage"],
        "contradictions": structured["contradictions"],
        "unsupported_features": structured["unsupported_features"],
        "blocked_requirements": structured["blocked_requirements"],
        "missing_information": structured["missing_information"],
        "feasibility": feasibility({"engine": engine,
                                    "target_platforms": platforms or [],
                                    "performance_targets": design.get("performance_targets")}),
        "approval": {
            "required": True,
            "status": "HUMAN_REVIEW_REQUIRED",
            "approved": False,
            "approved_by": None,
            "what_must_be_approved": [
                "Engine, dimension, art direction and scope",
                "Requirement set and priorities",
                "Character, environment and gameplay specifications",
                "Any future asset generation or build run",
            ],
        },
        "provenance": {
            "pipeline": "game_studio.llm.game_spec_pipeline",
            "source": source,
            "design_source": ("ai_provider payload validated by response_validation"
                              if source == "ai_provider"
                              else "game_studio.llm.intelligence deterministic design"),
            "requirements_source": ("game_studio.understanding deterministic parser "
                                    "(provably offline; not generated by the provider)"),
            "requirements_extraction": "deterministic",
            "provider_payload_used_for_design": source == "ai_provider",
            "checked_at": None,
            "human_approved": False,
            "network_calls": 0,
        },
        "executable": False,
        "ai_generated_asset": False,
        "generation_performed": False,
        "phase5_project_modified": False,
        "note": ("Proposal only. A valid specification is not proof of a playable game "
                 "and does not execute or generate anything."),
    }
    if include_bridges:
        spec["bridges"] = {
            "character": bridge_character(spec, quality_tier=quality_tier),
            "environment": bridge_environment(spec, quality_tier=quality_tier),
            "gameplay": bridge_gameplay(spec),
        }
    spec["generation_plan"] = build_generation_plan(spec)
    spec["validation"] = validate_spec(spec)
    if not spec["validation"]["valid"]:
        raise ValueError("generated specification failed validation: "
                         + "; ".join(spec["validation"]["errors"][:5]))
    spec["provenance"]["checked_at"] = None
    return spec


def summary(payload: dict) -> dict:
    """Compact, stable summary suitable for reports and comparisons."""
    return json.loads(json.dumps({
        "source": payload.get("source"),
        "engine": payload.get("engine"),
        "requirements": len(payload.get("requirements") or []),
        "bridges": sorted((payload.get("bridges") or {}).keys()),
        "validation": payload.get("validation"),
        "approval": (payload.get("approval") or {}).get("status"),
        "executable": payload.get("executable"),
        "ai_generated_asset": payload.get("ai_generated_asset"),
    }, sort_keys=True))
