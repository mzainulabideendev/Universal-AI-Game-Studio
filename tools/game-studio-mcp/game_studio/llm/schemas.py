"""Versioned structured-output schemas and a dependency-free validator.

Only a deliberate JSON-schema subset is implemented (types, required,
properties, items, enum, ranges, array bounds). That is enough to reject
malformed or incomplete model output without shipping a schema library.

Invalid output is never accepted as a valid plan: the client asks the model to
repair it a bounded number of times, then falls back or fails explicitly.
"""

from __future__ import annotations

import json
import re

UNDERSTANDING_SCHEMA_VERSION = "1.1"
SPECIFICATION_SCHEMA_VERSION = "1.0"
REVIEW_SCHEMA_VERSION = "1.0"
AMBIGUITY_SCHEMA_VERSION = "1.0"
ENGINE_SCHEMA_VERSION = "1.0"
ARCHITECTURE_SCHEMA_VERSION = "1.0"
VALIDATION_SCHEMA_VERSION = "1.0"

_STRING = {"type": "string"}
_STRING_LIST = {"type": "array", "items": {"type": "string"}, "maxItems": 60}

_REQUIREMENT = {
    "type": "object",
    "required": ["id", "category", "statement", "classification"],
    "properties": {
        "id": {"type": "string", "minLength": 1, "maxLength": 40},
        "category": {"type": "string", "maxLength": 80},
        "statement": {"type": "string", "minLength": 3, "maxLength": 1200},
        "source_text": {"type": "string", "maxLength": 4000},
        "classification": {
            "type": "string",
            "enum": ["explicit", "implied", "technical", "optional", "unresolved",
                     "conflict", "excluded"],
        },
        "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
        "acceptance_test": {"type": "string", "maxLength": 1200},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "depends_on": {"type": "array", "items": {"type": "string"},
                       "maxItems": 20},
    },
}

_QUESTION = {
    "type": "object",
    "required": ["question", "why_it_matters"],
    "properties": {
        "question": {"type": "string", "maxLength": 500},
        "why_it_matters": {"type": "string", "maxLength": 800},
        "options": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "default": {"type": "string", "maxLength": 500},
    },
}

UNDERSTANDING_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioUnderstanding",
    "version": UNDERSTANDING_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "summary", "dimension", "platforms",
                 "genre", "requirements", "assumptions", "questions"],
    "properties": {
        "schema_version": {"type": "string"},
        "summary": {"type": "string", "minLength": 5, "maxLength": 2000},
        "genre": {"type": "string", "minLength": 2, "maxLength": 120},
        "subgenre": {"type": ["string", "null"], "maxLength": 120},
        "dimension": {"type": "string", "enum": ["2d", "2.5d", "3d"]},
        "platforms": {"type": "array", "items": {"type": "string"},
                      "minItems": 1, "maxItems": 12},
        "engine_recommendation": {
            "type": "object",
            "required": ["engine", "reason"],
            "properties": {
                "engine": {"type": "string", "enum": ["unity", "unreal", "godot"]},
                "reason": {"type": "string", "maxLength": 2000},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "art_direction": {"type": "string", "maxLength": 1000},
        "requirements": {"type": "array", "items": _REQUIREMENT,
                         "minItems": 1, "maxItems": 120},
        "core_loop": _STRING_LIST,
        "abilities": _STRING_LIST,
        "character": {"type": "object", "properties": {
            "type": {"type": "string"}, "description": {"type": "string"}}},
        "environment": {"type": "string", "maxLength": 2000},
        "animation_needs": _STRING_LIST,
        "physics_needs": _STRING_LIST,
        "ai_needs": _STRING_LIST,
        "ui_needs": _STRING_LIST,
        "audio_needs": _STRING_LIST,
        "save_system": {"type": ["string", "null"], "maxLength": 800},
        "performance_targets": _STRING_LIST,
        "exclusions": _STRING_LIST,
        "conflicts": {"type": "array", "maxItems": 30, "items": {
            "type": "object", "required": ["a", "b"],
            "properties": {"a": {"type": "string"}, "b": {"type": "string"},
                           "resolution": {"type": "string"}}}},
        "assumptions": {"type": "array", "items": {"type": "string"},
                        "maxItems": 30},
        "questions": {"type": "array", "maxItems": 20, "items": _QUESTION},
        "risks": _STRING_LIST,
        "technical_dependencies": _STRING_LIST,
        "language": {"type": ["string", "object"], "maxLength": 200},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "uncertainty": {"type": "array", "items": {"type": "string"},
                        "maxItems": 20},
    },
}

SPECIFICATION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioSpecificationAdditions",
    "version": SPECIFICATION_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "overview", "engine", "milestones",
                 "acceptance_criteria"],
    "properties": {
        "schema_version": {"type": "string"},
        "overview": {"type": "string", "minLength": 5, "maxLength": 4000},
        "engine": {"type": "object", "required": ["selected"],
                   "properties": {"selected": {
                       "type": "string", "enum": ["unity", "unreal", "godot"]}}},
        "art_direction": {"type": "string", "maxLength": 2000},
        "core_loop": _STRING_LIST,
        "milestones": {"type": "array", "minItems": 1, "maxItems": 20, "items": {
            "type": "object", "required": ["id", "name"],
            "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                           "gate": {"type": "string"}}}},
        "acceptance_criteria": {"type": "array", "minItems": 1, "maxItems": 60,
                                "items": {"type": "string"}},
        "risks": _STRING_LIST,
        "unresolved_questions": {"type": "array", "maxItems": 5,
                                 "items": {"type": "string"}},
        "technical_dependencies": _STRING_LIST,
    },
}

REVIEW_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioPlanReview",
    "version": REVIEW_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "verdict", "summary", "findings"],
    "properties": {
        "schema_version": {"type": "string"},
        "verdict": {"type": "string",
                    "enum": ["sound", "needs-changes", "blocked"]},
        "summary": {"type": "string", "maxLength": 2000},
        "findings": {"type": "array", "minItems": 1, "maxItems": 40, "items": {
            "type": "object",
            "required": ["severity", "area", "finding"],
            "properties": {
                "severity": {"type": "string",
                             "enum": ["blocker", "high", "medium", "low"]},
                "area": {"type": "string"},
                "finding": {"type": "string"},
                "recommendation": {"type": "string"},
                "requirement_id": {"type": "string"},
            }}},
        "assumptions": {"type": "array", "items": {"type": "string"}, "maxItems": 30},
        "questions": {"type": "array", "maxItems": 5, "items": {
            "type": "object", "required": ["question"],
            "properties": {"question": {"type": "string"},
                           "why_it_matters": {"type": "string"}}}},
    },
}

AMBIGUITY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioAmbiguityAnalysis",
    "version": AMBIGUITY_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "blocking", "ambiguities", "questions"],
    "properties": {
        "schema_version": {"type": "string"},
        "blocking": {"type": "boolean"},
        "summary": {"type": "string", "maxLength": 2000},
        "ambiguities": {"type": "array", "maxItems": 30, "items": {
            "type": "object",
            "required": ["area", "issue", "impact"],
            "properties": {
                "area": {"type": "string", "maxLength": 120},
                "issue": {"type": "string", "maxLength": 1200},
                "impact": {"type": "string",
                           "enum": ["architecture", "cost", "feasibility",
                                    "functionality", "polish"]},
                "requirement_id": {"type": "string", "maxLength": 40},
                "safe_default": {"type": "string", "maxLength": 800},
            }}},
        "questions": {"type": "array", "maxItems": 20, "items": _QUESTION},
        "assumptions": {"type": "array", "items": {"type": "string"},
                        "maxItems": 20},
    },
}

ENGINE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioEngineCompatibility",
    "version": ENGINE_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "recommendation", "candidates"],
    "properties": {
        "schema_version": {"type": "string"},
        "recommendation": {"type": "string",
                           "enum": ["unity", "unreal", "godot", "unresolved"]},
        "reason": {"type": "string", "maxLength": 3000},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "candidates": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
            "type": "object",
            "required": ["engine", "fit", "reason"],
            "properties": {
                "engine": {"type": "string",
                           "enum": ["unity", "unreal", "godot"]},
                "fit": {"type": "string",
                        "enum": ["strong", "partial", "poor"]},
                "reason": {"type": "string", "maxLength": 2000},
                "risks": {"type": "array", "items": {"type": "string"},
                          "maxItems": 15},
            }}},
        "platform_constraints": {"type": "array", "items": {"type": "string"},
                                 "maxItems": 20},
        "verification_needed": {"type": "array", "items": {"type": "string"},
                                "maxItems": 20},
    },
}

ARCHITECTURE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioArchitecturePlan",
    "version": ARCHITECTURE_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "summary", "systems", "milestones"],
    "properties": {
        "schema_version": {"type": "string"},
        "summary": {"type": "string", "minLength": 5, "maxLength": 4000},
        "core_experience": {"type": "string", "maxLength": 2000},
        "systems": {"type": "array", "minItems": 1, "maxItems": 40, "items": {
            "type": "object",
            "required": ["id", "name", "responsibility", "requirement_ids"],
            "properties": {
                "id": {"type": "string", "maxLength": 40},
                "name": {"type": "string", "maxLength": 160},
                "responsibility": {"type": "string", "maxLength": 1600},
                "requirement_ids": {"type": "array", "items": {"type": "string"},
                                    "maxItems": 30},
                "depends_on": {"type": "array", "items": {"type": "string"},
                               "maxItems": 30},
                "engine_notes": {"type": "string", "maxLength": 1200},
            }}},
        "dependency_edges": {"type": "array", "maxItems": 120, "items": {
            "type": "object", "required": ["from", "to"],
            "properties": {"from": {"type": "string"},
                           "to": {"type": "string"},
                           "reason": {"type": "string", "maxLength": 800}}}},
        "asset_plan": {"type": "array", "maxItems": 60, "items": {
            "type": "object", "required": ["asset", "purpose"],
            "properties": {
                "asset": {"type": "string"},
                "purpose": {"type": "string"},
                "source": {"type": "string",
                           "enum": ["existing", "blender", "meshy", "marketplace",
                                    "unknown"]},
            }}},
        "animation_plan": {"type": "array", "maxItems": 60, "items": {
            "type": "object", "required": ["clip", "purpose"],
            "properties": {"clip": {"type": "string"},
                           "purpose": {"type": "string"}}}},
        "milestones": {"type": "array", "minItems": 1, "maxItems": 20, "items": {
            "type": "object", "required": ["id", "name", "gate"],
            "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                           "gate": {"type": "string"}}}},
        "risks": {"type": "array", "items": {"type": "string"}, "maxItems": 30},
        "next_actions": {"type": "array", "items": {"type": "string"},
                         "maxItems": 20},
        "assumptions": {"type": "array", "items": {"type": "string"},
                        "maxItems": 20},
        "questions": {"type": "array", "maxItems": 5, "items": _QUESTION},
    },
}

VALIDATION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GameStudioPlanValidation",
    "version": VALIDATION_SCHEMA_VERSION,
    "type": "object",
    "required": ["schema_version", "verdict", "issues"],
    "properties": {
        "schema_version": {"type": "string"},
        "verdict": {"type": "string",
                    "enum": ["valid", "needs-changes", "blocked"]},
        "summary": {"type": "string", "maxLength": 2000},
        "issues": {"type": "array", "maxItems": 60, "items": {
            "type": "object",
            "required": ["severity", "area", "issue"],
            "properties": {
                "severity": {"type": "string",
                             "enum": ["blocker", "high", "medium", "low"]},
                "area": {"type": "string", "maxLength": 160},
                "issue": {"type": "string", "maxLength": 1200},
                "requirement_id": {"type": "string", "maxLength": 40},
                "fix": {"type": "string", "maxLength": 1200},
            }}},
        "verified_facts": {"type": "array", "items": {"type": "string"},
                           "maxItems": 30},
        "unverified_claims": {"type": "array", "items": {"type": "string"},
                              "maxItems": 30},
    },
}

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _type_ok(value, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return isinstance(value, _TYPES[expected])


def validate(instance: object, schema: dict, path: str = "$") -> list[str]:
    """Return a list of validation errors. Empty means valid."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(instance, option) for option in options):
            return [f"{path}: expected {'/'.join(options)}, got {type(instance).__name__}"]

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string is longer than {schema['maxLength']}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: exceeds {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance[:200]):
                errors.extend(validate(item, item_schema, f"{path}[{index}]"))

    if isinstance(instance, dict):
        for key in schema.get("required") or []:
            if key not in instance:
                errors.append(f"{path}: missing required field {key!r}")
        properties = schema.get("properties") or {}
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{path}.{key}"))
    return errors


def parse_json(text: str) -> object:
    """Extract a JSON value from plain text or a fenced code block."""
    if text is None:
        raise ValueError("empty model output")
    value = str(text).strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", value)
        value = re.sub(r"\s*```$", "", value).strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        return json.loads(value[start:end + 1])
    raise ValueError("model output contains no JSON object")


def schema_for(task: str) -> dict:
    return {
        "understanding": UNDERSTANDING_SCHEMA,
        "specification": SPECIFICATION_SCHEMA,
        "review": REVIEW_SCHEMA,
        "ambiguity": AMBIGUITY_SCHEMA,
        "engine": ENGINE_SCHEMA,
        "architecture": ARCHITECTURE_SCHEMA,
        "validation": VALIDATION_SCHEMA,
    }[task]


SCHEMA_VERSIONS = {
    "understanding": UNDERSTANDING_SCHEMA_VERSION,
    "specification": SPECIFICATION_SCHEMA_VERSION,
    "review": REVIEW_SCHEMA_VERSION,
    "ambiguity": AMBIGUITY_SCHEMA_VERSION,
    "engine": ENGINE_SCHEMA_VERSION,
    "architecture": ARCHITECTURE_SCHEMA_VERSION,
    "validation": VALIDATION_SCHEMA_VERSION,
}
