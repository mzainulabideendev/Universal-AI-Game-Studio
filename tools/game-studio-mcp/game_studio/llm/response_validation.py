"""Structural validation for model-produced game specifications.

A successful provider response is not proof of a usable game design. This module
parses, type-checks, and cross-checks the *content* of a response before anything
downstream may treat it as a specification.

Model output is untrusted data. Nothing here executes instructions found in the
response, fetches URLs, imports code, writes assets or calls a tool. It only
validates a JSON value and records what was found.

Validation layers
-----------------
1. JSON extraction (plain text or fenced block) and parsing.
2. Schema validation with the dependency-free Phase 1 validator.
3. Contradiction rules across fields.
4. Unsupported / unverified claim detection.
5. Confidence classification from measurable completeness.

Only layers 1-2 can make a payload ``schema_valid``. Contradictions and
unsupported claims are reported separately and never silently corrected.
"""

from __future__ import annotations

import json
from typing import Any

from . import schemas as llm_schemas
from . import config as llm_config

SCHEMA_VERSION = 1

_STR = {"type": "string", "maxLength": 4000}
_STR_LIST = {"type": "array", "items": {"type": "string", "maxLength": 2000},
             "maxItems": 80}
_MAYBE_STR_LIST = {"type": ["array", "string"], "maxItems": 80}

# The exact response contract requested from a provider in Phase 7E.
AI_GAME_SPEC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioAIGameSpec",
    "version": "1.0",
    "type": "object",
    "required": [
        "game_title", "genre", "target_platforms", "core_gameplay_loop",
        "player_mechanics", "camera_design", "environment_requirements",
        "collectibles", "hazards", "progression", "ui_requirements",
        "audio_requirements", "performance_targets", "technical_architecture",
        "asset_requirements", "acceptance_criteria", "risks",
        "unsupported_or_uncertain",
    ],
    "properties": {
        "game_title": {"type": "string", "minLength": 1, "maxLength": 120},
        "genre": _MAYBE_STR_LIST,
        "target_platforms": _MAYBE_STR_LIST,
        "core_gameplay_loop": _MAYBE_STR_LIST,
        "player_mechanics": _MAYBE_STR_LIST,
        "camera_design": _STR,
        "environment_requirements": _MAYBE_STR_LIST,
        "collectibles": _MAYBE_STR_LIST,
        "hazards": _MAYBE_STR_LIST,
        "progression": _MAYBE_STR_LIST,
        "ui_requirements": _MAYBE_STR_LIST,
        "audio_requirements": _MAYBE_STR_LIST,
        "performance_targets": {
            "type": "object",
            "required": ["target_fps"],
            "properties": {
                "target_fps": {"type": "integer", "minimum": 1, "maximum": 240},
                "quality_tier": {"type": "string", "maxLength": 80},
                "hardware": {"type": "string", "maxLength": 400},
                "notes": {"type": "string", "maxLength": 1000},
            },
        },
        "technical_architecture": _MAYBE_STR_LIST,
        "asset_requirements": _MAYBE_STR_LIST,
        "acceptance_criteria": _MAYBE_STR_LIST,
        "risks": _MAYBE_STR_LIST,
        "unsupported_or_uncertain": _MAYBE_STR_LIST,
        "engine": {"type": "string", "maxLength": 80},
        "dimension": {"type": "string", "maxLength": 20},
        "art_style": {"type": "string", "maxLength": 200},
        "summary": {"type": "string", "maxLength": 2000},
    },
}

LIST_FIELDS = (
    "genre", "target_platforms", "core_gameplay_loop", "player_mechanics",
    "environment_requirements", "collectibles", "hazards", "progression",
    "ui_requirements", "audio_requirements", "technical_architecture",
    "asset_requirements", "acceptance_criteria", "risks",
    "unsupported_or_uncertain",
)

SUPPORTED_ENGINES = ("unity", "unreal", "godot")
SUPPORTED_PLATFORMS = ("windows", "pc", "linux", "macos", "mac", "android",
                       "ios", "web", "webgl", "console")

# Features that Phase 3-5 did not implement. A model may mention them, but the
# result must be labelled for human review rather than treated as feasible.
UNSUPPORTED_CLAIMS = (
    ("multiplayer", "Multiplayer/networking is not implemented by the Phase 5 prototype."),
    ("multi-player", "Multiplayer/networking is not implemented by the Phase 5 prototype."),
    ("mmo", "An MMO scale is far outside the validated vertical slice."),
    ("netcode", "No networking layer exists in the validated build."),
    ("open world", "Streaming open-world tooling is not implemented."),
    ("ray tracing", "Ray tracing is not demonstrated by any measured build."),
    ("raytracing", "Ray tracing is not demonstrated by any measured build."),
    ("path tracing", "Path tracing is not demonstrated by any measured build."),
    ("nanite", "Nanite is an Unreal feature and is not available in the Unity build."),
    ("lumen", "Lumen is an Unreal feature and is not available in the Unity build."),
    ("metahuman", "MetaHuman is not part of this repository's asset pipeline."),
    ("photorealistic", "Photorealism is not supported by the procedural asset pipeline."),
    ("hundreds of", "Large content counts are unverified and need a budget check."),
    ("infinite", "Unbounded content or worlds are unverified."),
    ("machine learning", "No ML/NPC training pipeline is implemented."),
    ("neural", "No neural asset or behaviour pipeline is implemented."),
)

AMBIGUITY_MARKERS = (
    "fun", "engaging", "polished", "good", "nice", "better", "smooth",
    "immersive", "cinematic", "high quality", "a lot", "many", "some",
)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalise(payload: dict) -> dict:
    """Return a copy with list-like fields coerced to arrays of strings.

    Normalisation is recorded by the caller. It never invents content: a missing
    or malformed field stays empty or malformed and is still reported.
    """
    result = dict(payload)
    for field in LIST_FIELDS:
        if field in result:
            result[field] = _as_list(result.get(field))
    return result


def extract_json(text: object) -> dict:
    """Extract one JSON object without executing or trusting its content."""
    if text is None:
        return {"ok": False, "error": "empty provider output", "payload": None}
    try:
        payload = llm_schemas.parse_json(str(text))
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"invalid JSON: {exc}", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "provider output is not a JSON object",
                "payload": None}
    return {"ok": True, "error": None, "payload": payload}


def _scan_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False).lower()


def contradictions(payload: dict) -> list[dict]:
    """Deterministic cross-field contradiction checks."""
    found: list[dict] = []
    text = _scan_text(payload)
    dimension = str(payload.get("dimension") or "").lower()
    if ("2d" in dimension or "2d" in text) and ("3d" in dimension or "3d" in text):
        found.append({"id": "C-01", "kind": "dimension",
                      "statement": "The response references both 2D and 3D presentation.",
                      "requires_human_decision": True})
    if "single-player" in text or "single player" in text:
        if "multiplayer" in text or "multi-player" in text:
            found.append({"id": f"C-{len(found) + 1:02d}", "kind": "player_mode",
                          "statement": "Single-player and multiplayer are both required.",
                          "requires_human_decision": True})
    if "no audio" in text and _as_list(payload.get("audio_requirements")):
        found.append({"id": f"C-{len(found) + 1:02d}", "kind": "audio",
                      "statement": "Audio is excluded and also required.",
                      "requires_human_decision": True})
    if "no ui" in text or "no hud" in text:
        if _as_list(payload.get("ui_requirements")):
            found.append({"id": f"C-{len(found) + 1:02d}", "kind": "ui",
                          "statement": "UI is excluded and also required.",
                          "requires_human_decision": True})
    platforms = [item.lower() for item in _as_list(payload.get("target_platforms"))]
    unknown = [item for item in platforms
               if not any(word in item for word in SUPPORTED_PLATFORMS)]
    if platforms and unknown:
        found.append({"id": f"C-{len(found) + 1:02d}", "kind": "platform",
                      "statement": f"Unrecognised target platform(s): {unknown}",
                      "requires_human_decision": True})
    engine = str(payload.get("engine") or "").lower()
    if engine and engine not in SUPPORTED_ENGINES:
        found.append({"id": f"C-{len(found) + 1:02d}", "kind": "engine",
                      "statement": f"Engine {engine!r} is not one of {list(SUPPORTED_ENGINES)}.",
                      "requires_human_decision": True})
    performance = payload.get("performance_targets") or {}
    fps = performance.get("target_fps") if isinstance(performance, dict) else None
    if isinstance(fps, int) and fps > 120:
        found.append({"id": f"C-{len(found) + 1:02d}", "kind": "performance",
                      "statement": f"A {fps} FPS target is not supported by any "
                                   "measured build and must be justified.",
                      "requires_human_decision": True})
    if not _as_list(payload.get("collectibles")) and "collect" in text:
        found.append({"id": f"C-{len(found) + 1:02d}", "kind": "collectibles",
                      "statement": "The loop mentions collecting but no collectible is specified.",
                      "requires_human_decision": True})
    return found


def unsupported_claims(payload: dict) -> list[dict]:
    """Flag claims about capabilities this project has not implemented."""
    text = _scan_text(payload)
    found: list[dict] = []
    for marker, reason in UNSUPPORTED_CLAIMS:
        if marker in text:
            found.append({
                "id": f"U-{len(found) + 1:02d}",
                "claim": marker,
                "reason": reason,
                "status": "requires_human_review",
                "auto_accepted": False,
            })
    return found


def ambiguous_requirements(payload: dict) -> list[dict]:
    """Find acceptance criteria that cannot be verified as written."""
    found: list[dict] = []
    for index, item in enumerate(_as_list(payload.get("acceptance_criteria"))):
        lowered = item.lower()
        markers = [marker for marker in AMBIGUITY_MARKERS if marker in lowered]
        if markers and not any(word in lowered for word in
                               ("ms", "fps", "count", "within", "at least",
                                "equals", "returns", "passes", "reaches")):
            found.append({
                "id": f"A-{index + 1:02d}",
                "criterion": item,
                "markers": markers,
                "reason": "The criterion uses subjective language without a measurable check.",
                "requires_human_decision": True,
            })
    return found


def missing_fields(payload: dict) -> list[str]:
    missing = [key for key in AI_GAME_SPEC_SCHEMA["required"] if key not in payload]
    empty = [key for key in ("game_title", "core_gameplay_loop", "player_mechanics",
                             "target_platforms", "acceptance_criteria")
             if key in payload and not _as_list(payload.get(key))
             and not str(payload.get(key) or "").strip()]
    return missing + empty


def confidence(payload: dict, *, errors: list[str],
               contradiction_count: int) -> dict:
    total = len(AI_GAME_SPEC_SCHEMA["required"])
    present = total - len(missing_fields(payload))
    coverage = round(present / total, 3) if total else 0.0
    if errors:
        label = "low"
    elif contradiction_count or coverage < 0.85:
        label = "medium"
    else:
        label = "high"
    return {
        "label": label,
        "required_field_coverage": coverage,
        "schema_errors": len(errors),
        "contradictions": contradiction_count,
        "note": ("Confidence is a structural completeness signal, not a judgement "
                 "that the design is good or feasible."),
    }


def validate_game_spec(payload: object, *, source: str = "unknown") -> dict:
    """Validate a parsed game specification and return labelled findings."""
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "schema_valid": False,
            "source": source,
            "errors": ["payload must be a JSON object"],
            "warnings": [],
            "missing_fields": list(AI_GAME_SPEC_SCHEMA["required"]),
            "contradictions": [],
            "unsupported_claims": [],
            "ambiguous_requirements": [],
            "confidence": {"label": "low", "required_field_coverage": 0.0},
            "provenance": {"validator": "game_studio.llm.response_validation",
                           "validated_as": source},
        }

    normalised = normalise(payload)
    errors = llm_schemas.validate(normalised, AI_GAME_SPEC_SCHEMA)
    missing = missing_fields(normalised)
    contradiction_list = contradictions(normalised)
    unsupported = unsupported_claims(normalised)
    ambiguous = ambiguous_requirements(normalised)
    warnings: list[str] = []
    if unsupported:
        warnings.append("The response claims capabilities this project has not implemented.")
    if contradiction_list:
        warnings.append("The response contains internal contradictions.")
    if ambiguous:
        warnings.append("Some acceptance criteria are not measurable as written.")

    return {
        "ok": not errors,
        "schema_valid": not errors,
        "source": source,
        "errors": errors,
        "warnings": warnings,
        "missing_fields": missing,
        "contradictions": contradiction_list,
        "unsupported_claims": unsupported,
        "ambiguous_requirements": ambiguous,
        "normalised": normalised,
        "confidence": confidence(normalised, errors=errors,
                                  contradiction_count=len(contradiction_list)),
        "provenance": {
            "validator": "game_studio.llm.response_validation",
            "schema": AI_GAME_SPEC_SCHEMA["title"],
            "schema_version": AI_GAME_SPEC_SCHEMA["version"],
            "validated_as": source,
            "untrusted_input": True,
            "actions_executed": False,
        },
    }


def validate_text(text: object, *, source: str = "unknown") -> dict:
    """Convenience wrapper: extract JSON from text, then validate it."""
    extracted = extract_json(text)
    if not extracted["ok"]:
        return {
            "ok": False,
            "schema_valid": False,
            "source": source,
            "errors": [extracted["error"]],
            "warnings": [],
            "missing_fields": list(AI_GAME_SPEC_SCHEMA["required"]),
            "contradictions": [],
            "unsupported_claims": [],
            "ambiguous_requirements": [],
            "confidence": {"label": "low", "required_field_coverage": 0.0},
            "provenance": {"validator": "game_studio.llm.response_validation",
                           "validated_as": source, "untrusted_input": True},
        }
    result = validate_game_spec(extracted["payload"], source=source)
    result["json_extracted"] = True
    return result


def redact_payload(payload: object) -> object:
    """Redact credential-looking substrings from evidence before persisting it."""
    if isinstance(payload, str):
        return llm_config.redact(payload)
    if isinstance(payload, dict):
        return {key: redact_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload
