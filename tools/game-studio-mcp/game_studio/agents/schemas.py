"""JSON schemas for the Phase 2 agent contract and every agent output."""

from __future__ import annotations

_STR = {"type": "string"}
_STR_ARRAY = {"type": "array", "items": _STR}
_OBJ_ARRAY = {"type": "array", "items": {"type": "object"}}

AGENT_INPUT_SCHEMA = {
    "type": "object",
    "required": ["request", "context_sources"],
    "properties": {
        "request": _STR,
        "context_sources": {"type": "object"},
        "brief": {"type": "object"},
        "design": {"type": "object"},
        "architecture": {"type": "object"},
        "character": {"type": "object"},
        "environment": {"type": "object"},
        "gameplay": {"type": "object"},
        "uiux": {"type": "object"},
        "qa": {"type": "object"},
        "approved_decisions": {"type": "array"},
    },
}

BRIEF_SCHEMA = {
    "type": "object",
    "required": ["request", "summary", "genre", "dimension", "platform", "characters",
                 "environment", "mechanics", "exclusions", "requirements",
                 "assumptions", "conflicts", "quality_target"],
    "properties": {
        "request": _STR,
        "summary": _STR,
        "genre": _STR_ARRAY,
        "dimension": _STR_ARRAY,
        "platform": _STR_ARRAY,
        "characters": _STR_ARRAY,
        "environment": _STR_ARRAY,
        "mechanics": _STR_ARRAY,
        "exclusions": {"type": "array"},
        "requirements": {"type": "array"},
        "assumptions": _STR_ARRAY,
        "conflicts": {"type": "array"},
        "quality_target": _STR,
        "engine_hint": {"type": "string"},
    },
}

DESIGN_SCHEMA = {
    "type": "object",
    "required": ["summary", "genre", "dimension", "platform", "core_loop", "mechanics",
                 "objectives", "progression", "exclusions", "missing_requirements",
                 "acceptance_tests", "requirements_addressed", "assumptions", "risks"],
    "properties": {
        "summary": _STR,
        "genre": _STR_ARRAY,
        "dimension": _STR_ARRAY,
        "platform": _STR_ARRAY,
        "core_loop": _STR_ARRAY,
        "mechanics": _STR_ARRAY,
        "objectives": _STR_ARRAY,
        "progression": _STR_ARRAY,
        "exclusions": _STR_ARRAY,
        "missing_requirements": _STR_ARRAY,
        "acceptance_tests": _STR_ARRAY,
        "requirements_addressed": _STR_ARRAY,
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
    },
}

ARCHITECTURE_SCHEMA = {
    "type": "object",
    "required": ["summary", "engine", "architecture", "performance", "risks",
                 "requirements_addressed", "assumptions"],
    "properties": {
        "summary": _STR,
        "engine": {
            "type": "object",
            "required": ["name", "rationale", "installed", "supported_systems",
                         "unsupported_features"],
            "properties": {
                "name": _STR,
                "rationale": _STR,
                "installed": {"type": "boolean"},
                "supported_systems": _STR_ARRAY,
                "unsupported_features": _STR_ARRAY,
            },
        },
        "architecture": {
            "type": "object",
            "required": ["scenes", "systems", "dependencies"],
            "properties": {
                "scenes": _STR_ARRAY,
                "systems": _STR_ARRAY,
                "dependencies": _STR_ARRAY,
            },
        },
        "performance": {
            "type": "object",
            "required": ["quality_target", "budget"],
            "properties": {
                "quality_target": _STR,
                "budget": {"type": "object"},
            },
        },
        "risks": _STR_ARRAY,
        "requirements_addressed": _STR_ARRAY,
        "assumptions": _STR_ARRAY,
    },
}

CHARACTER_SCHEMA = {
    "type": "object",
    "required": ["summary", "characters", "assets_generated", "textures_generated",
                 "capability_gaps", "assumptions", "risks"],
    "properties": {
        "summary": _STR,
        "characters": {"type": "array", "items": {
            "type": "object",
            "required": ["name", "type", "geometry", "materials", "textures", "rig",
                         "lod", "status"],
            "properties": {
                "name": _STR,
                "type": _STR,
                "geometry": {"type": "object"},
                "materials": {"type": "array"},
                "textures": {"type": "object"},
                "rig": {"type": "object"},
                "lod": {"type": "object"},
                "asset_specification": {"type": "object"},
                "status": _STR,
            },
        }},
        "assets_generated": {"type": "boolean"},
        "textures_generated": {"type": "boolean"},
        "capability_gaps": _STR_ARRAY,
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
    },
}

ENVIRONMENT_SCHEMA = {
    "type": "object",
    "required": ["summary", "environment", "terrain", "vegetation", "structures",
                 "water", "lighting", "weather", "atmosphere", "materials",
                 "estimates", "performance_risks", "dependencies", "generated",
                 "assumptions", "risks"],
    "properties": {
        "summary": _STR,
        "environment": _STR,
        "terrain": {"type": "object"},
        "vegetation": {"type": "array"},
        "structures": {"type": "array"},
        "water": {"type": "object"},
        "lighting": {"type": "object"},
        "weather": {"type": "object"},
        "atmosphere": {"type": "object"},
        "materials": _STR_ARRAY,
        "estimates": {"type": "object"},
        "performance_risks": _STR_ARRAY,
        "dependencies": _STR_ARRAY,
        "generated": {"type": "boolean"},
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
    },
}

GAMEPLAY_SCHEMA = {
    "type": "object",
    "required": ["summary", "controls", "movement", "physics", "interactions",
                 "camera", "scoring", "progression", "systems", "acceptance_tests",
                 "exclusions", "assumptions", "risks"],
    "properties": {
        "summary": _STR,
        "controls": {"type": "array"},
        "movement": {"type": "object"},
        "physics": {"type": "object"},
        "interactions": {"type": "array"},
        "camera": {"type": "object"},
        "scoring": {"type": "object"},
        "progression": {"type": "object"},
        "systems": {"type": "array", "items": {
            "type": "object",
            "required": ["id", "name", "reusable", "acceptance_tests"],
            "properties": {
                "id": _STR,
                "name": _STR,
                "reusable": {"type": "boolean"},
                "acceptance_tests": _STR_ARRAY,
            },
        }},
        "acceptance_tests": _STR_ARRAY,
        "exclusions": _STR_ARRAY,
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
    },
}

UIUX_SCHEMA = {
    "type": "object",
    "required": ["summary", "screens", "hud", "settings", "accessibility",
                 "navigation", "dependencies", "assumptions", "risks"],
    "properties": {
        "summary": _STR,
        "screens": {"type": "array", "items": {
            "type": "object",
            "required": ["id", "purpose", "widgets", "navigation"],
            "properties": {
                "id": _STR,
                "purpose": _STR,
                "widgets": _STR_ARRAY,
                "navigation": _STR_ARRAY,
            },
        }},
        "hud": _STR_ARRAY,
        "settings": _STR_ARRAY,
        "accessibility": _STR_ARRAY,
        "navigation": _STR_ARRAY,
        "dependencies": _STR_ARRAY,
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
    },
}

QA_SCHEMA = {
    "type": "object",
    "required": ["summary", "checks", "coverage", "test_plan",
                 "evidence_requirements", "conflicts", "verification_status",
                 "assumptions", "risks"],
    "properties": {
        "summary": _STR,
        "checks": {"type": "array", "items": {
            "type": "object",
            "required": ["id", "category", "status", "evidence", "remediation"],
            "properties": {
                "id": _STR,
                "category": _STR,
                "status": _STR,
                "evidence": _STR,
                "remediation": _STR,
            },
        }},
        "coverage": {
            "type": "object",
            "required": ["requirements_total", "addressed", "missing"],
            "properties": {
                "requirements_total": {"type": "integer"},
                "addressed": {"type": "integer"},
                "missing": _STR_ARRAY,
            },
        },
        "test_plan": {"type": "array"},
        "evidence_requirements": _STR_ARRAY,
        "conflicts": {"type": "array"},
        "verification_status": {"type": "string", "enum": ["not-verified"]},
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
    },
}

DIRECTOR_SCHEMA = {
    "type": "object",
    "required": ["summary", "project", "milestones", "workstreams",
                 "dependency_graph", "parallel_groups", "conflicts",
                 "open_questions", "approval_required", "executable",
                 "implementation_status", "assumptions", "risks",
                 "requirements_addressed"],
    "properties": {
        "summary": _STR,
        "project": {"type": "object"},
        "milestones": {"type": "array"},
        "workstreams": {"type": "array"},
        "dependency_graph": {"type": "object"},
        "parallel_groups": {"type": "array"},
        "conflicts": {"type": "array"},
        "open_questions": _STR_ARRAY,
        "approval_required": {"type": "array"},
        "executable": {"type": "boolean", "enum": [False]},
        "implementation_status": _STR,
        "assumptions": _STR_ARRAY,
        "risks": _STR_ARRAY,
        "requirements_addressed": _STR_ARRAY,
    },
}
