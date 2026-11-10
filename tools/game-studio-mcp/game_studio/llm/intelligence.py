"""Structured game-design reasoning and requirement decomposition (Phase 6).

All output is deterministic, schema-validated and explicitly split into user
requirements, agent recommendations, assumptions, unsupported features, blocked
requirements and approved decisions. Nothing here calls a provider, generates an
asset, changes a project or marks a requirement verified.

The module deliberately reuses the existing Phase 1 deterministic understanding
engine (``game_studio.understanding``) so Phase 6 adds structure without
replacing proven parsing behaviour.
"""

from __future__ import annotations

import hashlib
import json

from .. import understanding
from . import asset_research
from . import free_routing
from . import schemas as llm_schemas

SCHEMA_VERSION = "1.0"

PRIORITIES = ("P0", "P1", "P2", "P3")
PROVENANCE = ("user_requirement", "agent_recommendation", "technical_dependency",
              "assumption", "approved_decision")
REQUIREMENT_STATUSES = ("proposed", "approved", "blocked", "unsupported")

REQUIREMENT_SCHEMA = {
    "type": "object",
    "required": ["id", "description", "category", "priority", "dependencies",
                 "acceptance_criteria", "required_assets", "target_engine",
                 "verification_method", "status", "provenance", "confidence"],
    "properties": {
        "id": {"type": "string", "minLength": 1, "maxLength": 40},
        "description": {"type": "string", "minLength": 3, "maxLength": 1200},
        "category": {"type": "string", "minLength": 1, "maxLength": 80},
        "priority": {"type": "string", "enum": list(PRIORITIES)},
        "dependencies": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "acceptance_criteria": {"type": "string", "minLength": 1, "maxLength": 1200},
        "required_assets": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "target_engine": {"type": "string", "minLength": 1, "maxLength": 40},
        "verification_method": {"type": "string", "minLength": 1, "maxLength": 300},
        "status": {"type": "string", "enum": list(REQUIREMENT_STATUSES)},
        "provenance": {"type": "string", "enum": list(PROVENANCE)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "classification": {"type": "string", "maxLength": 40},
        "source_text": {"type": "string", "maxLength": 4000},
    },
}

REQUIREMENTS_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "engine", "requirements", "contradictions",
                 "unsupported_features", "blocked_requirements",
                 "approved_decisions", "missing_information", "executable"],
    "properties": {
        "schema_version": {"type": "string"},
        "engine": {"type": "string"},
        "requirements": {"type": "array", "items": REQUIREMENT_SCHEMA,
                         "maxItems": 200},
        "contradictions": {"type": "array", "items": {"type": "object"},
                           "maxItems": 40},
        "unsupported_features": {"type": "array", "items": {"type": "object"},
                                 "maxItems": 40},
        "blocked_requirements": {"type": "array", "items": {"type": "object"},
                                 "maxItems": 40},
        "approved_decisions": {"type": "array", "items": {"type": "object"},
                               "maxItems": 40},
        "missing_information": {"type": "array", "items": {"type": "object"},
                                "maxItems": 40},
        "executable": {"type": "boolean"},
    },
}

GAME_DESIGN_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "concept", "genre", "target_platform",
                 "core_gameplay_loop", "player_mechanics", "enemy_npc_requirements",
                 "environment_requirements", "character_requirements",
                 "animation_requirements", "uiux_requirements",
                 "audio_requirements", "physics_requirements",
                 "performance_targets", "asset_requirements",
                 "technical_constraints", "testing_requirements", "milestones",
                 "user_requirements", "recommendations", "assumptions",
                 "unsupported_features", "blocked_requirements",
                 "approved_decisions", "missing_information", "contradictions",
                 "executable"],
    "properties": {
        "schema_version": {"type": "string"},
        "concept": {"type": "string", "minLength": 1},
        "genre": {"type": "array", "items": {"type": "string"}},
        "target_platform": {"type": "array", "items": {"type": "string"}},
        "core_gameplay_loop": {"type": "string", "minLength": 1},
        "player_mechanics": {"type": "array", "items": {"type": "string"}},
        "enemy_npc_requirements": {"type": "array", "items": {"type": "string"}},
        "environment_requirements": {"type": "array", "items": {"type": "string"}},
        "character_requirements": {"type": "array", "items": {"type": "string"}},
        "animation_requirements": {"type": "array", "items": {"type": "string"}},
        "uiux_requirements": {"type": "array", "items": {"type": "string"}},
        "audio_requirements": {"type": "array", "items": {"type": "string"}},
        "physics_requirements": {"type": "array", "items": {"type": "string"}},
        "performance_targets": {"type": "object"},
        "asset_requirements": {"type": "array", "items": {"type": "string"}},
        "technical_constraints": {"type": "array", "items": {"type": "string"}},
        "testing_requirements": {"type": "array", "items": {"type": "string"}},
        "milestones": {"type": "array", "items": {"type": "object"}},
        "user_requirements": {"type": "array", "items": REQUIREMENT_SCHEMA},
        "recommendations": {"type": "array", "items": REQUIREMENT_SCHEMA},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "unsupported_features": {"type": "array", "items": {"type": "object"}},
        "blocked_requirements": {"type": "array", "items": {"type": "object"}},
        "approved_decisions": {"type": "array", "items": {"type": "object"}},
        "missing_information": {"type": "array", "items": {"type": "object"}},
        "contradictions": {"type": "array", "items": {"type": "object"}},
        "executable": {"type": "boolean"},
    },
}

# Coverage checklist for a complete game proposal. Missing items become agent
# recommendations, never user requirements.
REQUIRED_COVERAGE = (
    ("player_character", "Player character", "character",
     ("character", "player", "monkey", "hero", "avatar"), ["character mesh", "rig"]),
    ("character_rig_animations", "Character rig and animations", "animation",
     ("rig", "animation", "animator", "idle", "walk", "run"),
     ["skeleton rig", "idle/walk/run animations"]),
    ("jungle_terrain", "Terrain", "environment", ("terrain", "jungle", "ground"),
     ["terrain mesh", "terrain material"]),
    ("vegetation", "Vegetation", "environment", ("vegetation", "tree", "plant", "grass"),
     ["tree assets", "plant assets"]),
    ("collectibles", "Collectibles", "gameplay", ("collect", "banana", "pickup", "coin"),
     ["collectible mesh", "collectible material"]),
    ("collision", "Collision", "physics", ("collision", "collider", "physics"),
     ["collider setup"]),
    ("camera", "Camera", "gameplay", ("camera", "follow", "third-person"),
     ["camera rig"]),
    ("player_controls", "Player controls", "gameplay", ("control", "input", "movement"),
     ["input map"]),
    ("score_system", "Score system", "gameplay", ("score", "points", "counter"),
     ["score state"]),
    ("objectives", "Objectives", "gameplay", ("objective", "goal", "quest", "win"),
     ["objective state"]),
    ("hud", "HUD", "uiux", ("hud", "ui", "interface", "counter"),
     ["HUD canvas"]),
    ("game_states", "Game states", "technical", ("game state", "pause", "menu", "restart"),
     ["state machine"]),
    ("performance", "Performance target", "performance",
     ("performance", "fps", "frame", "draw call"), ["profiler capture"]),
    ("build_configuration", "Build configuration", "technical",
     ("build", "player settings", "scene list"), ["build settings"]),
    ("tests", "Tests", "qa", ("test", "verification", "acceptance"),
     ["automated test", "play-mode test"]),
)

_CATEGORY_ASSETS = {
    "character": ["character mesh", "rig", "materials"],
    "environment": ["environment mesh", "material", "collision"],
    "gameplay": ["gameplay system", "input map"],
    "system": ["system implementation"],
    "technical": ["configuration", "build settings"],
    "uiux": ["UI canvas", "fonts"],
}

_VERIFICATION = {
    "character": "Validate the generated spec, import into the engine and play the animation.",
    "environment": "Validate terrain/vegetation counts and run a play-mode traversal test.",
    "gameplay": "Play-mode acceptance test with observable success/failure.",
    "system": "Unit or play-mode test that exercises the system end to end.",
    "technical": "Build and inspect logs/artifacts; no success is claimed from configuration.",
    "uiux": "Play-mode test that verifies each required HUD element.",
    "performance": "Measure frame time on the documented hardware; report actual values.",
    "qa": "Run the automated suite and record the command, exit code and output.",
}

_UNSUPPORTED_RULES = (
    (("multiplayer", "online play", "netcode", "networking"),
     "multiplayer",
     "Phase 5 delivered a single-player slice; networking is not implemented or verified.",
     "unsupported"),
    (("open world", "massive open world", "hundreds of square"),
     "open_world",
     "An open-world production pipeline is outside the current verified scope.",
     "blocked"),
    (("aaa", "photorealistic aaa", "film quality"),
     "aaa_scope",
     "AAA scope, staffing and performance targets are not supported by this pipeline.",
     "unsupported"),
    (("ai texture", "ai-generated texture", "texture from ai", "ai normal map"),
     "ai_texture_generation",
     "No verified free texture/normal-map generator is integrated; Blender textures are procedural.",
     "unsupported"),
    (("ai 3d model", "ai-generated 3d", "text to 3d", "text-to-3d"),
     "ai_3d_generation",
     "No verified free hosted 3D generator is integrated; local options are not installed.",
     "unsupported"),
    (("ray tracing", "path traced", "path-traced"),
     "ray_tracing",
     "Ray tracing is not assumed to run on the documented integrated GPU.",
     "blocked"),
)


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(text))
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "item"


def _confidence(value: str | float | None) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return {"high": 0.85, "medium": 0.65, "low": 0.4,
            "unknown": 0.25}.get(str(value or "").lower(), 0.5)


def _assets_for(category: str) -> list[str]:
    return list(_CATEGORY_ASSETS.get(category, ["implementation"]))


def _normalise_requirement(item: dict, *, engine: str, index: int) -> dict:
    classification = str(item.get("classification") or "implied")
    provenance = ("user_requirement" if classification == "explicit"
                  else "technical_dependency" if classification == "technical"
                  else "agent_recommendation")
    category = str(item.get("category") or "system")
    priority = item.get("priority") if item.get("priority") in PRIORITIES else "P1"
    dependencies = [str(value) for value in (item.get("depends_on")
                                             or item.get("dependencies") or [])]
    return {
        "id": str(item.get("id") or f"R-{index:03d}"),
        "description": str(item.get("statement") or item.get("description")
                           or "Unspecified requirement"),
        "category": category,
        "priority": priority,
        "dependencies": dependencies,
        "acceptance_criteria": str(item.get("acceptance_test")
                                   or item.get("acceptance_criteria")
                                   or "An observable play-mode or build check passes."),
        "required_assets": list(item.get("required_assets") or _assets_for(category)),
        "target_engine": str(item.get("target_engine") or engine),
        "verification_method": str(
            item.get("verification_method")
            or _VERIFICATION.get(category, "Run the stated acceptance test and record evidence.")),
        "status": "proposed",
        "provenance": provenance,
        "confidence": _confidence(item.get("confidence")),
        "classification": classification,
        "source_text": str(item.get("source_text") or ""),
    }


def _coverage(requirements: list[dict], *, engine: str) -> tuple[list[dict], list[dict]]:
    added: list[dict] = []
    coverage: list[dict] = []
    next_index = len(requirements) + 1
    for key, label, category, keywords, assets in REQUIRED_COVERAGE:
        matched = None
        for requirement in requirements:
            haystack = (requirement["description"] + " " +
                        requirement["category"]).lower()
            if any(word in haystack for word in keywords):
                matched = requirement["id"]
                break
        if matched:
            coverage.append({"id": key, "label": label, "covered_by": matched})
            continue
        new_id = f"R-{next_index:03d}"
        next_index += 1
        requirement = {
            "id": new_id,
            "description": f"{label} is required for a complete, testable vertical slice.",
            "category": category,
            "priority": "P1",
            "dependencies": [],
            "acceptance_criteria": f"{label} is observable in a playable build or build artifact.",
            "required_assets": list(assets),
            "target_engine": engine,
            "verification_method": _VERIFICATION.get(
                category, "Run the stated acceptance test and record evidence."),
            "status": "proposed",
            "provenance": "agent_recommendation",
            "confidence": 0.6,
            "classification": "implied",
            "source_text": "generated coverage checklist",
        }
        added.append(requirement)
        coverage.append({"id": key, "label": label, "covered_by": new_id,
                         "added_as_recommendation": True})
    return added, coverage


def _contradictions(text: str, analysis: dict) -> list[dict]:
    lowered = text.lower()
    found = []
    for conflict in analysis.get("conflicts") or []:
        found.append({
            "id": f"C-{len(found) + 1:02d}",
            "kind": "parsed_conflict",
            "statement": str(conflict.get("statement") or conflict),
            "severity": "material",
            "source": "deterministic parser",
        })
    rules = (
        (("2d", "2-d"), ("3d", "3-d"), "dimension",
         "The request mentions both 2D and 3D presentation."),
        (("single player", "single-player"), ("multiplayer", "multi-player"),
         "player_mode", "Single-player and multiplayer are both requested."),
        (("no ui", "no hud"), ("hud", "ui"), "ui",
         "A HUD/UI is both excluded and required."),
        (("no audio", "no sound"), ("music", "sound", "audio"), "audio",
         "Audio is both excluded and required."),
        (("free",), ("paid api", "subscription"), "billing",
         "The request mixes free-only expectations with paid services."),
    )
    for left, right, kind, message in rules:
        if any(token in lowered for token in left) and any(token in lowered for token in right):
            found.append({
                "id": f"C-{len(found) + 1:02d}",
                "kind": kind,
                "statement": message,
                "severity": "material",
                "source": "phase6 contradiction rules",
                "requires_user_decision": True,
            })
    return found


def _unsupported(text: str) -> list[dict]:
    lowered = text.lower()
    found = []
    for keywords, feature, reason, status in _UNSUPPORTED_RULES:
        if any(keyword in lowered for keyword in keywords):
            found.append({
                "id": f"U-{len(found) + 1:02d}",
                "feature": feature,
                "reason": reason,
                "status": status,
                "evidence": "Phase 6 asset/provider research and Phase 5 scope",
            })
    return found


def _approved(approved_decisions: list[dict] | None) -> list[dict]:
    decisions = []
    for index, item in enumerate(approved_decisions or [], start=1):
        if not isinstance(item, dict):
            continue
        decisions.append({
            "id": str(item.get("id") or f"D-{index:03d}"),
            "statement": str(item.get("statement") or item.get("decision") or ""),
            "approved": True,
            "source": "user_approved_input",
        })
    return decisions


def requirements(request: str, *, engine: str = "unity",
                 approved_decisions: list[dict] | None = None) -> dict:
    """Decompose a game idea into structured, traceable requirements."""
    text = (request or "").strip()
    if not text:
        raise ValueError("request text is required")
    if len(text) > 20_000:
        raise ValueError("request text is too long (max 20000 characters)")
    analysis = understanding.analyze_request(text)
    raw = []
    for bucket in ("explicit", "implied", "technical_dependencies",
                   "optional_enhancements"):
        raw.extend(analysis["requirements"].get(bucket) or [])
    normalised = [_normalise_requirement(item, engine=engine, index=index)
                  for index, item in enumerate(raw, start=1)]
    additions, coverage = _coverage(normalised, engine=engine)
    all_requirements = normalised + additions

    contradictions = _contradictions(text, analysis)
    unsupported = _unsupported(text)
    blocked = [
        {"requirement_id": item["id"], "reason": feature["reason"],
         "feature": feature["feature"], "status": feature["status"]}
        for item in all_requirements
        for feature in unsupported
        if feature["feature"].replace("_", " ") in item["description"].lower()
    ]
    if not blocked:
        blocked = [{"requirement_id": None, "feature": feature["feature"],
                    "reason": feature["reason"], "status": feature["status"]}
                   for feature in unsupported]

    result = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "request": text,
        "engine": engine,
        "requirements": all_requirements,
        "coverage": coverage,
        "contradictions": contradictions,
        "unsupported_features": unsupported,
        "blocked_requirements": blocked,
        "approved_decisions": _approved(approved_decisions),
        "missing_information": list(analysis.get("unresolved") or []),
        "summary": analysis.get("summary"),
        "language": analysis.get("language"),
        "confidence": analysis.get("confidence"),
        "provenance": {
            "parser": "game_studio.understanding",
            "phase": 6,
            "user_requirement_count": sum(
                1 for item in all_requirements
                if item["provenance"] == "user_requirement"),
            "recommendation_count": sum(
                1 for item in all_requirements
                if item["provenance"] != "user_requirement"),
        },
        "executable": False,
        "note": ("Proposal only. Requirements are not approved or verified; no engine, "
                 "Blender, asset or provider action was performed."),
    }
    result["validation"] = validate_requirements(result)
    if not result["validation"]["valid"]:
        raise ValueError("generated requirement proposal failed schema validation: "
                         + "; ".join(result["validation"]["errors"][:5]))
    return result


def validate_requirements(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be an object"]}
    errors = llm_schemas.validate(payload, REQUIREMENTS_SCHEMA)
    ids = []
    for index, item in enumerate(payload.get("requirements") or []):
        if not isinstance(item, dict):
            continue
        if item.get("id") in ids:
            errors.append(f"requirements[{index}].id is duplicated: {item.get('id')!r}")
        ids.append(item.get("id"))
        for dependency in item.get("dependencies") or []:
            if dependency not in ids and dependency not in [
                    other.get("id") for other in payload.get("requirements") or []
                    if isinstance(other, dict)]:
                errors.append(
                    f"requirements[{index}] depends on unknown id {dependency!r}")
    return {"valid": not errors, "errors": errors}


def design(request: str, *, engine: str = "unity", platform: str | None = None,
           dimension: str | None = None, art_style: str | None = None,
           quality_target: str = "prototype",
           approved_decisions: list[dict] | None = None) -> dict:
    """Produce a schema-validated, clearly labelled game-design proposal."""
    proposal = requirements(request, engine=engine,
                            approved_decisions=approved_decisions)
    analysis = understanding.analyze_request(request)
    view = analysis["understanding"]
    genres = list(view.get("game_genre") or ["adventure"])
    dimensions = list(view.get("dimension") or ([dimension] if dimension else ["3d"]))
    platforms = list(view.get("target_platform") or ([platform] if platform else ["pc"]))
    mechanics = list(view.get("mechanics") or ["movement"])
    characters = list(view.get("characters") or ["player character"])
    environment = list(view.get("environment") or ["environment"])
    style = list(view.get("visual_style") or ([art_style] if art_style else ["stylized"]))

    loop = (f"Explore the {environment[0]} as the {characters[0]}, use "
            f"{', '.join(mechanics[:3])} to achieve the objective, and repeat with "
            "increasing challenge.")
    design_payload = {
        "schema_version": SCHEMA_VERSION,
        "request": request,
        "concept": analysis.get("summary") or request,
        "genre": genres,
        "dimension": dimensions,
        "target_platform": platforms,
        "art_style": style,
        "quality_target": quality_target,
        "core_gameplay_loop": loop,
        "player_mechanics": mechanics,
        "enemy_npc_requirements": (
            ["At least one hostile or neutral NPC with state-driven behaviour."]
            if any(word in request.lower() for word in ("enemy", "fighting", "combat",
                                                        "monster", "chase"))
            else ["No NPC is required by the user; treat any NPC as an optional agent recommendation."]),
        "environment_requirements": [f"{environment[0]} environment with playable layout",
                                     "collision-aware traversal and spawn points"],
        "character_requirements": [f"{characters[0]} with a species-appropriate rig",
                                   "LOD and material set suitable for the target platform"],
        "animation_requirements": ["idle", "walk", "run", "jump", "landing"],
        "uiux_requirements": ["HUD showing objective and score",
                              "start/pause/restart game states"],
        "audio_requirements": ["audio is not required by this proposal; adding it needs approval"],
        "physics_requirements": ["character collision", "collectible trigger",
                                 "terrain/ground contact"],
        "performance_targets": {
            "target_fps": 60,
            "quality_tier": quality_target,
            "hardware": "AMD Ryzen 5 4500U / 16 GB RAM / integrated Radeon graphics",
            "measured": False,
            "note": "Target only; no performance was measured in Phase 6.",
        },
        "asset_requirements": sorted({
            asset for item in proposal["requirements"]
            for asset in item["required_assets"]}),
        "technical_constraints": [
            f"Target engine: {engine}",
            "Procedural Blender assets are not AI-generated assets.",
            "No paid provider or unverified free asset service may be used.",
        ],
        "testing_requirements": [
            "Automated unit tests for requirement decomposition",
            "Play-mode test for controls, collision, collectibles and HUD",
            "Build/test evidence recorded before any completion claim",
        ],
        "milestones": [
            {"id": "M1", "name": "Design approval", "status": "pending"},
            {"id": "M2", "name": "Playable greybox", "status": "pending"},
            {"id": "M3", "name": "Character and environment integration", "status": "pending"},
            {"id": "M4", "name": "Gameplay and HUD", "status": "pending"},
            {"id": "M5", "name": "Tests and build verification", "status": "pending"},
        ],
        "user_requirements": [item for item in proposal["requirements"]
                              if item["provenance"] == "user_requirement"],
        "recommendations": [item for item in proposal["requirements"]
                            if item["provenance"] != "user_requirement"],
        "assumptions": [
            "The user has not approved an engine change or paid service.",
            "The documented mid-range laptop is the performance target.",
        ],
        "unsupported_features": proposal["unsupported_features"],
        "blocked_requirements": proposal["blocked_requirements"],
        "approved_decisions": proposal["approved_decisions"],
        "missing_information": proposal["missing_information"],
        "contradictions": proposal["contradictions"],
        "coverage": proposal["coverage"],
        "requirements_summary": {
            "total": len(proposal["requirements"]),
            "user": len([item for item in proposal["requirements"]
                         if item["provenance"] == "user_requirement"]),
            "recommendations": len([item for item in proposal["requirements"]
                                    if item["provenance"] != "user_requirement"]),
        },
        "provenance": {
            "mode": "deterministic",
            "provider": None,
            "live_model_quality_claimed": False,
            "network_calls": 0,
        },
        "executable": False,
        "note": ("Design proposal only. It is not an approved specification and it "
                 "performs no generation, build or engine operation."),
    }
    errors = llm_schemas.validate(design_payload, GAME_DESIGN_SCHEMA)
    design_payload["validation"] = {"valid": not errors, "errors": errors}
    if errors:
        raise ValueError("generated design failed schema validation: "
                         + "; ".join(errors[:5]))
    return design_payload


def character_spec_from_design(design_payload: dict, *,
                               quality_tier: str = "medium",
                               target_engine: str | None = None) -> dict:
    """Bridge a design proposal into a Phase 3 character spec (no generation)."""
    from .. import character_spec

    if not isinstance(design_payload, dict) or not design_payload.get("concept"):
        raise ValueError("design payload is missing a concept")
    engine = target_engine or design_payload.get("technical_constraints", ["unity"])[0]
    engine_key = "unity" if "unity" in str(engine).lower() else str(engine).lower()
    characters = design_payload.get("character_requirements") or ["player character"]
    description = " ".join(str(value) for value in characters)
    if any(word in (design_payload.get("concept") or "").lower()
           for word in ("monkey", "primate", "ape")):
        description += " monkey primate tail"
    animations = [name for name in ("idle", "walk", "run", "jump", "landing")
                  if name in " ".join(design_payload.get("animation_requirements") or [])]
    spec = character_spec.build_character_spec(
        description, name="PlayerCharacter", quality_tier=quality_tier,
        animations=animations or None, target_engine=engine_key)
    return {
        "ok": True,
        "source": "phase6_design",
        "spec": spec,
        "validation": {"valid": not character_spec.validate_character_spec(spec),
                       "errors": character_spec.validate_character_spec(spec)},
        "ai_generated_asset": False,
        "procedural_blender": True,
        "generation_performed": False,
        "note": ("This is a specification for the deterministic Blender pipeline. No "
                 "mesh or texture was generated and none is AI-generated."),
    }


def environment_spec_from_design(design_payload: dict, *,
                                 quality_tier: str = "medium",
                                 target_engine: str | None = None,
                                 character_path: str | None = None) -> dict:
    """Bridge a design proposal into a Phase 4 environment spec (no generation)."""
    from .. import environment_spec

    if not isinstance(design_payload, dict) or not design_payload.get("concept"):
        raise ValueError("design payload is missing a concept")
    engine = target_engine or design_payload.get("technical_constraints", ["unity"])[0]
    engine_key = "unity" if "unity" in str(engine).lower() else str(engine).lower()
    environment = " ".join([
        design_payload.get("concept") or "",
        " ".join(design_payload.get("environment_requirements") or []),
        " ".join(design_payload.get("genre") or []),
    ])
    spec = environment_spec.build_environment_spec(
        environment, name="GameLevel", quality_tier=quality_tier,
        target_engine=engine_key, character_path=character_path)
    return {
        "ok": True,
        "source": "phase6_design",
        "spec": spec,
        "validation": {"valid": not environment_spec.validate_environment_spec(spec),
                       "errors": environment_spec.validate_environment_spec(spec)},
        "ai_generated_asset": False,
        "procedural_blender": True,
        "generation_performed": False,
        "note": ("This is a specification for the deterministic Blender pipeline. No "
                 "terrain or texture was generated and none is AI-generated."),
    }


BENCHMARK_IDEAS = (
    ("simple_2d", "Create a simple 2D platformer where a cat collects fish."),
    ("endless_runner_3d", "Create a 3D endless runner where a robot dodges obstacles."),
    ("jungle_adventure", "Create a 3D jungle adventure where a monkey collects bananas."),
    ("chess", "Create a chess game with an AI opponent and a move history panel."),
    ("fighting", "Create a 3D fighting game with two characters and a health bar."),
    ("open_world", "Create an open world exploration game with hundreds of quests."),
)


def benchmark(ideas: tuple[tuple[str, str], ...] | None = None) -> dict:
    """Deterministic, labelled benchmark. Never claims live model quality."""
    entries = []
    for name, prompt in (ideas or BENCHMARK_IDEAS):
        first = requirements(prompt)
        second = requirements(prompt)
        digest = hashlib.sha256(json.dumps(first["requirements"],
                                           sort_keys=True).encode()).hexdigest()
        repeat = hashlib.sha256(json.dumps(second["requirements"],
                                           sort_keys=True).encode()).hexdigest()
        covered = len([item for item in first["coverage"]
                       if item.get("covered_by")])
        route = free_routing.route("game_design_reasoning")
        entries.append({
            "id": name,
            "input": prompt,
            "requirement_count": len(first["requirements"]),
            "user_requirement_count": first["provenance"]["user_requirement_count"],
            "coverage_items": len(first["coverage"]),
            "coverage_present": covered,
            "schema_valid": first["validation"]["valid"],
            "contradiction_count": len(first["contradictions"]),
            "unsupported_count": len(first["unsupported_features"]),
            "blocked_count": len(first["blocked_requirements"]),
            "cost_policy_mode": route["mode"],
            "paid_fallback": route["fallback_plan"]["paid_switch"],
            "deterministic_fallback_available": True,
            "reproducible": digest == repeat,
            "output_sha256": digest,
        })
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "evaluation_mode": "deterministic",
        "live_provider_quality": False,
        "provider_ranking": None,
        "note": ("This benchmark measures schema validity, decomposition coverage, "
                 "determinism and cost-policy compliance. It does not measure or rank "
                 "live model quality."),
        "ideas": entries,
        "summary": {
            "ideas": len(entries),
            "schema_valid": all(item["schema_valid"] for item in entries),
            "all_reproducible": all(item["reproducible"] for item in entries),
            "cost_policy_compliant": all(item["paid_fallback"] is False
                                         for item in entries),
            "live_model_quality_measured": False,
        },
    }
