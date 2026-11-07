"""V6 Phase 3 character specification and capability model.

Pure, deterministic data structures. No Blender call and no network access
happens here. The specification is the contract between the Phase 2 Character
Agent and the Phase 3 Blender pipeline.
"""

from __future__ import annotations

import copy
import re

from .llm import capabilities as llm_capabilities
from .llm import config as llm_config
from .llm import schemas

SPEC_SCHEMA_VERSION = 1

# Real, measurable settings per tier. These values are applied to the Blender
# script, so the tiers differ in geometry and texture resolution, not labels.
QUALITY_TIERS = {
    "low": {
        "sphere_segments": 16,
        "ring_count": 8,
        "tail_segments": 5,
        "finger_count": 2,
        "texture_resolution": 256,
        "uv_angle_limit_deg": 60,
        "uv_island_margin": 0.01,
        "target_triangles": 8_000,
        "lod_levels": 2,
        "bone_count": 18,
        "animation_fps": 24,
    },
    "medium": {
        "sphere_segments": 24,
        "ring_count": 12,
        "tail_segments": 7,
        "finger_count": 3,
        "texture_resolution": 512,
        "uv_angle_limit_deg": 66,
        "uv_island_margin": 0.02,
        "target_triangles": 25_000,
        "lod_levels": 3,
        "bone_count": 22,
        "animation_fps": 30,
    },
    "high": {
        "sphere_segments": 32,
        "ring_count": 16,
        "tail_segments": 9,
        "finger_count": 4,
        "texture_resolution": 1024,
        "uv_angle_limit_deg": 70,
        "uv_island_margin": 0.025,
        "target_triangles": 60_000,
        "lod_levels": 4,
        "bone_count": 26,
        "animation_fps": 30,
    },
}

EXPORT_FORMATS = ("blend", "glb", "fbx")

ANIMATION_LIBRARY = {
    "idle": {"frames": 60, "loop": True},
    "walk": {"frames": 24, "loop": True},
    "run": {"frames": 18, "loop": True},
    "jump": {"frames": 30, "loop": False},
    "landing": {"frames": 20, "loop": False},
    "turn": {"frames": 24, "loop": True},
    "collect": {"frames": 30, "loop": False},
    "hit_reaction": {"frames": 20, "loop": False},
}

# PBR channels are declared per material. ``generated`` means a real image file
# is produced locally; ``constant`` means a numeric shader input (no image);
# ``absent`` is reported honestly rather than fabricated.
PBR_CHANNELS = ("base_color", "normal", "roughness", "metallic", "ao",
                "emission", "opacity")

DEFAULT_MATERIALS = (
    {
        "name": "M_Monkey_Fur",
        "role": "fur",
        "base_color": [0.32, 0.19, 0.10, 1.0],
        "roughness": 0.78,
        "metallic": 0.0,
        "textured": True,
        "channels": {
            "base_color": "generated",
            "roughness": "generated",
            "normal": "generated",
            "metallic": "constant",
            "ao": "absent",
            "emission": "absent",
            "opacity": "absent",
        },
        "color_spaces": {"base_color": "sRGB", "roughness": "Non-Color",
                         "normal": "Non-Color"},
    },
    {
        "name": "M_Monkey_Skin",
        "role": "face_hands_feet",
        "base_color": [0.55, 0.38, 0.25, 1.0],
        "roughness": 0.62,
        "metallic": 0.0,
        "textured": False,
        "channels": {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": {},
    },
    {
        "name": "M_Monkey_EyeWhite",
        "role": "eyes",
        "base_color": [0.92, 0.89, 0.82, 1.0],
        "roughness": 0.25,
        "metallic": 0.0,
        "textured": False,
        "channels": {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": {},
    },
    {
        "name": "M_Monkey_Iris",
        "role": "eyes",
        "base_color": [0.35, 0.18, 0.04, 1.0],
        "roughness": 0.3,
        "metallic": 0.0,
        "textured": False,
        "channels": {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": {},
    },
    {
        "name": "M_Monkey_Pupil",
        "role": "eyes",
        "base_color": [0.02, 0.02, 0.02, 1.0],
        "roughness": 0.2,
        "metallic": 0.0,
        "textured": False,
        "channels": {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": {},
    },
    {
        "name": "M_Monkey_Nose",
        "role": "face",
        "base_color": [0.16, 0.10, 0.08, 1.0],
        "roughness": 0.45,
        "metallic": 0.0,
        "textured": False,
        "channels": {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": {},
    },
    {
        "name": "M_Monkey_InnerEar",
        "role": "ears",
        "base_color": [0.62, 0.35, 0.30, 1.0],
        "roughness": 0.7,
        "metallic": 0.0,
        "textured": False,
        "channels": {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": {},
    },
)

CHARACTER_SPEC_SCHEMA = {
    "type": "object",
    "required": [
        "schema_version", "id", "name", "description", "character_type",
        "quality_tier", "proportions", "head", "limbs", "clothing",
        "accessories", "surface_details", "geometry", "materials", "textures",
        "uv", "rigging", "animations", "export", "provenance", "capabilities",
    ],
    "properties": {
        "schema_version": {"type": "integer"},
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "character_type": {"type": "string"},
        "quality_tier": {"type": "string", "enum": list(QUALITY_TIERS)},
        "style": {"type": "string"},
        "proportions": {"type": "object"},
        "head": {"type": "object"},
        "limbs": {"type": "object"},
        "clothing": {"type": "array"},
        "accessories": {"type": "array"},
        "surface_details": {"type": "array"},
        "geometry": {"type": "object"},
        "materials": {"type": "array"},
        "textures": {"type": "object"},
        "uv": {"type": "object"},
        "rigging": {"type": "object"},
        "animations": {"type": "array"},
        "export": {"type": "object"},
        "provenance": {"type": "object"},
        "capabilities": {"type": "object"},
    },
}

ASSET_CAPABILITIES = (
    "text_reasoning", "image_generation", "texture_generation",
    "image_to_texture", "material_generation", "mesh_generation",
    "image_analysis",
)

CAPABILITY_STATES = ("supported", "unsupported", "unknown")


def _provider_support_matrix() -> dict:
    """Explicit matrix. Never inferred from a provider name.

    The repository ships text-generation adapters only. No image, texture or
    material generation endpoint is implemented. Meshy is a dedicated 3D
    adapter that spends credits and therefore requires separate authorization.
    """
    matrix = {}
    for provider in llm_config.PROVIDERS:
        matrix[provider] = {
            "text_reasoning": "supported",
            "image_generation": "unsupported",
            "texture_generation": "unsupported",
            "image_to_texture": "unsupported",
            "material_generation": "unsupported",
            "mesh_generation": "unsupported",
            "image_analysis": "unknown",
            "basis": ("Phase 1 text adapter only; no image/texture/material "
                      "endpoint is implemented in this repository."),
        }
    matrix["meshy"] = {
        "text_reasoning": "unsupported",
        "image_generation": "unsupported",
        "texture_generation": "unknown",
        "image_to_texture": "unknown",
        "material_generation": "unsupported",
        "mesh_generation": "supported",
        "image_analysis": "unknown",
        "basis": ("Dedicated Meshy text-to-3D adapter exists. Calls spend credits, "
                  "require a configured key and explicit approval, and are not "
                  "used in Phase 3."),
        "paid": True,
        "authorized": False,
    }
    return matrix


def asset_provider_capabilities() -> dict:
    matrix = _provider_support_matrix()
    supported_by_local = {
        "mesh_generation": "procedural-blender",
        "texture_generation": "procedural-blender-images",
        "material_generation": "blender-pbr-node-graph",
        "image_analysis": "not-implemented",
    }
    return {
        "schema_version": SPEC_SCHEMA_VERSION,
        "providers": matrix,
        "capability_states": list(CAPABILITY_STATES),
        "local_tools": supported_by_local,
        "authorized_external_generators": [],
        "note": ("No LLM provider is treated as an image or 3D generator. Phase 3 "
                 "uses local Blender execution and reports missing capabilities."),
    }


def check_capability(capability: str, provider: str | None = None) -> dict:
    if capability not in ASSET_CAPABILITIES:
        raise ValueError(f"unknown asset capability {capability!r}")
    matrix = _provider_support_matrix()
    if provider is None:
        states = {name: entry[capability] for name, entry in matrix.items()}
        supported = [name for name, state in states.items()
                     if state == "supported" and not name == "meshy"]
        return {
            "capability": capability,
            "states": states,
            "supported_providers": supported,
            "externally_authorized": False,
            "usable_without_approval": bool(supported),
            "note": ("A supported text capability does not imply image, texture or "
                     "3D generation support."),
        }
    if provider not in matrix:
        raise ValueError(f"unknown provider {provider!r}")
    entry = matrix[provider]
    return {
        "capability": capability,
        "provider": provider,
        "state": entry[capability],
        "basis": entry.get("basis"),
        "paid": entry.get("paid", False),
        "authorized": entry.get("authorized", False),
    }


def quality_settings(tier: str | None) -> tuple[dict, str]:
    key = (tier or "medium").strip().lower()
    if key not in QUALITY_TIERS:
        raise ValueError(f"quality_tier must be one of {list(QUALITY_TIERS)}")
    return copy.deepcopy(QUALITY_TIERS[key]), key


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "character"


def _infer_character_type(description: str) -> str:
    text = (description or "").lower()
    if any(word in text for word in ("monkey", "ape", "chimpanzee", "gorilla")):
        return "primate"
    if any(word in text for word in ("human", "person", "hero", "soldier")):
        return "humanoid"
    if any(word in text for word in ("robot", "android", "mech")):
        return "mechanical"
    if any(word in text for word in ("animal", "creature", "beast", "dog", "cat")):
        return "creature"
    return "stylized_humanoid"


def _requested_animations(description: str) -> list[str]:
    text = (description or "").lower()
    requested = [name for name in ANIMATION_LIBRARY if name in text]
    if not requested:
        requested = ["idle", "walk", "run", "jump"]
    return requested


def build_character_spec(description: str, *, name: str = "JungleMonkey",
                         quality_tier: str = "medium",
                         animations: list[str] | None = None,
                         target_engine: str = "unity",
                         include_tail: bool | None = None,
                         seed: int = 20261107) -> dict:
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description must be a non-empty string")
    tier, tier_key = quality_settings(quality_tier)
    text = description.lower()
    character_type = _infer_character_type(description)
    animations = list(animations or _requested_animations(description))
    unknown = [item for item in animations if item not in ANIMATION_LIBRARY]
    if unknown:
        raise ValueError(f"unsupported animations: {unknown}")
    if include_tail is None:
        include_tail = character_type == "primate" or "tail" in text

    height = 1.25 if character_type == "primate" else 1.8
    materials = copy.deepcopy(list(DEFAULT_MATERIALS))
    if "brown" in text or "fur" in text:
        materials[0]["base_color"] = [0.32, 0.19, 0.10, 1.0]
        materials[0]["surface_note"] = "brown fur coloration from the request"

    spec = {
        "schema_version": SPEC_SCHEMA_VERSION,
        "id": f"char-{_slug(name)}-{tier_key}",
        "name": name,
        "description": description.strip(),
        "character_type": character_type,
        "quality_tier": tier_key,
        "style": "stylized-realistic" if "stylized" in text else "stylized",
        "proportions": {
            "height_m": height,
            "torso_scale": [0.34, 0.26, 0.46],
            "head_radius_m": 0.26 if character_type == "primate" else 0.22,
            "arm_length_m": 0.62 if character_type == "primate" else 0.70,
            "leg_length_m": 0.52 if character_type == "primate" else 0.85,
            "realistic_proportions": "realistic" in text or "professional" in text,
        },
        "head": {
            "head_shape": "rounded with brow ridge and muzzle",
            "eyes": {
                "count": 2,
                "expressive": "expressive eyes" in text or "eye" in text,
                "iris": True,
                "pupil": True,
            },
            "mouth": {"present": True, "style": "subtle stylized line"},
            "ears": {"count": 2, "shape": "rounded monkey ears",
                     "inner_ear_material": "M_Monkey_InnerEar"},
            "nose": {"present": True, "material": "M_Monkey_Nose"},
            "facial_features": ["brow ridge", "muzzle", "eye sockets"],
        },
        "limbs": {
            "arms": 2,
            "legs": 2,
            "hands": {"count": 2, "finger_count": tier["finger_count"],
                      "thumb": True},
            "feet": {"count": 2, "toe_count": 3},
            "tail": {
                "present": bool(include_tail),
                "segments": tier["tail_segments"] if include_tail else 0,
            },
        },
        "clothing": [],
        "accessories": [],
        "surface_details": ["procedural fur colour variation",
                            "muzzle wrinkles", "nose and inner-ear colour breaks"],
        "geometry": {
            "generator": "procedural-blender-primitives",
            "sphere_segments": tier["sphere_segments"],
            "ring_count": tier["ring_count"],
            "tail_segments": tier["tail_segments"] if include_tail else 0,
            "finger_count": tier["finger_count"],
            "target_triangles": tier["target_triangles"],
            "lod_levels": tier["lod_levels"],
            "complexity": tier_key,
            "measurable_difference": {
                "low_to_medium": "more sphere and tail segments, more fingers",
                "medium_to_high": "more geometry detail and 2x texture resolution",
            },
        },
        "materials": materials,
        "textures": {
            "resolution": tier["texture_resolution"],
            "format": "PNG",
            "generation_method": "procedural-local-blender",
            "maps_generated": ["base_color", "roughness", "normal"],
            "maps_constant": ["metallic"],
            "maps_absent": {
                "ao": "no physically measured ambient occlusion was computed",
                "emission": "not required by the character description",
                "opacity": "character is fully opaque",
            },
            "color_spaces": {"base_color": "sRGB", "roughness": "Non-Color",
                             "normal": "Non-Color"},
        },
        "uv": {
            "method": "smart_project",
            "angle_limit_deg": tier["uv_angle_limit_deg"],
            "island_margin": tier["uv_island_margin"],
            "require_uv_layer": True,
            "require_coverage": True,
        },
        "rigging": {
            "required": True,
            "skeleton": "quadruped-adapted biped",
            "bone_count_target": tier["bone_count"],
            "skinning": "automatic weights with validated fallback",
            "animation_fps": tier["animation_fps"],
            "bone_groups": ["root", "pelvis", "spine", "chest", "neck", "head",
                            "arm.L", "arm.R", "hand.L", "hand.R", "leg.L",
                            "leg.R", "foot.L", "foot.R", "tail"],
            "export_animation": True,
        },
        "animations": [
            {
                "name": animation,
                "frames": ANIMATION_LIBRARY[animation]["frames"],
                "fps": tier["animation_fps"],
                "loop": ANIMATION_LIBRARY[animation]["loop"],
                "generation": "procedural-keyframes",
            }
            for animation in animations
        ],
        "export": {
            "target_engine": (target_engine or "unity").lower(),
            "formats": list(EXPORT_FORMATS),
            "units": "meters",
            "forward_axis": "-Z",
            "up_axis": "Y",
            "require_reimport": True,
        },
        "provenance": {
            "source": "generated-locally",
            "generation_method": "procedural-blender",
            "creator": "Universal AI Game Studio",
            "license": "Original project asset (no third-party content)",
            "license_id": "project-original-1.0",
            "attribution_required": False,
            "external_assets": [],
            "downloads": [],
            "blender_executed": True,
            "seed": seed,
        },
        "capabilities": {
            "required": ["mesh_generation", "texture_generation",
                         "material_generation"],
            "provider_checks": {
                capability: check_capability(capability)
                for capability in ("mesh_generation", "texture_generation",
                                   "material_generation", "image_generation")
            },
            "external_generation_used": False,
            "local_generation_used": "blender",
            "missing_capabilities": [
                "AI image generation provider not configured/authorized",
                "AI 3D mesh generation provider not authorized (Meshy paid)",
            ],
        },
    }
    return spec


def validate_character_spec(spec: object) -> list[str]:
    if not isinstance(spec, dict):
        return ["$: character specification must be a JSON object"]
    errors = schemas.validate(spec, CHARACTER_SPEC_SCHEMA)
    if errors:
        return errors
    tier = spec["quality_tier"]
    if tier not in QUALITY_TIERS:
        errors.append(f"$.quality_tier: unknown tier {tier!r}")
    expected = QUALITY_TIERS[tier]
    if spec["textures"]["resolution"] != expected["texture_resolution"]:
        errors.append("$.textures.resolution: does not match the declared tier")
    if spec["geometry"]["sphere_segments"] != expected["sphere_segments"]:
        errors.append("$.geometry.sphere_segments: does not match the declared tier")
    if spec["rigging"]["bone_count_target"] != expected["bone_count"]:
        errors.append("$.rigging.bone_count_target: does not match the declared tier")
    if not spec["animations"]:
        errors.append("$.animations: at least one animation requirement is required")
    for animation in spec["animations"]:
        if animation["name"] not in ANIMATION_LIBRARY:
            errors.append(f"$.animations: unsupported animation {animation['name']!r}")
    if spec["provenance"]["source"] == "external" and not spec["provenance"].get("license"):
        errors.append("$.provenance.license: external assets require a license")
    return errors


def spec_from_agent_output(output: dict, *, quality_tier: str = "medium",
                           target_engine: str = "unity") -> dict:
    """Adapt the Phase 2 Character Agent output into an executable spec."""
    if not isinstance(output, dict) or not output.get("summary"):
        raise ValueError("character agent output is missing a summary")
    characters = output.get("characters") or []
    if not characters:
        raise ValueError("character agent output contains no characters")
    first = characters[0]
    name = str(first.get("name") or "JungleMonkey")
    description = " ".join(str(value) for value in (
        name, first.get("type", ""), output.get("summary", "")))
    return build_character_spec(
        description, name=name.title().replace(" ", "") or "JungleMonkey",
        quality_tier=quality_tier, target_engine=target_engine)


def provider_capability_report() -> dict:
    """Summary used by MCP and audit output."""
    matrix = asset_provider_capabilities()
    missing = []
    for capability in ("image_generation", "texture_generation",
                       "material_generation", "mesh_generation"):
        entries = matrix["providers"]
        if not any(entry[capability] == "supported" and entry.get("authorized")
                   for entry in entries.values()):
            missing.append(capability)
    return {
        "schema_version": SPEC_SCHEMA_VERSION,
        **matrix,
        "authorized_missing": missing,
        "llm_capability_keys": list(llm_capabilities.CAPABILITY_KEYS),
    }
