"""Character Agent: structured character/asset plan, never generated assets."""

from __future__ import annotations

from .. import character_spec
from .base import Agent
from .contract import AgentSpec
from .helpers import clean_values, has_exclusion, quality_profile, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, CHARACTER_SCHEMA

PBR_MAPS = ["base_color", "normal", "roughness", "metallic", "ambient_occlusion"]

# Phase 2 quality profiles mapped onto the Phase 3 executable tiers.
QUALITY_TIER_MAP = {"prototype": "low", "standard": "medium",
                    "high": "high", "cinematic": "high"}


def _asset_specification(name: str, brief: dict, design: dict, quality: str,
                         animations: list[str]) -> dict:
    """Build a real, validatable Phase 3 asset specification.

    This is a specification only. It records what the asset pipeline may build;
    it does not claim that any asset or texture exists.
    """
    description = " ".join(str(value) for value in (
        name, brief.get("summary") or brief.get("title") or "",
        " ".join(str(item) for item in brief.get("mechanics") or []),
        design.get("art_direction") if isinstance(design, dict) else "") if value)
    supported = [item for item in animations
                 if item.replace(" ", "_") in character_spec.ANIMATION_LIBRARY]
    if not supported:
        supported = ["idle", "walk", "run", "jump"]
    return character_spec.build_character_spec(
        description or f"{name} game character",
        name="".join(part.capitalize() for part in str(name).replace("_", " ").split())
        or "PlayerCharacter",
        quality_tier=QUALITY_TIER_MAP.get(quality, "medium"),
        animations=supported,
    )


class CharacterAgent(Agent):
    spec = AgentSpec(
        id="character",
        name="Character Agent",
        version="1.0.0",
        responsibility="Plan character geometry, UVs, PBR textures, rig and animations.",
        task_category="character_environment_planning",
        dependencies=("design", "architecture"),
        required_context=("brief", "design", "architecture"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=CHARACTER_SCHEMA,
        produces="character",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        design = input_data.get("design") or {}
        profile, quality = quality_profile(brief.get("quality_target"))
        names = clean_values(brief, "characters", ["player"])
        mechanics = set(clean_values(brief, "mechanics"))
        animations = ["idle", "walk", "run", "jump", "fall", "land", "interact"]
        if "combat" in mechanics and not has_exclusion(brief, "weapons", "combat"):
            animations.extend(["attack", "hit_reaction", "death"])
        if "climbing" in mechanics and not has_exclusion(brief, "climbing"):
            animations.append("climb")
        if "swimming" in mechanics and not has_exclusion(brief, "swimming"):
            animations.append("swim")

        characters = []
        for name in names:
            key = name.strip().lower()
            creature = any(word in key for word in ("monkey", "animal", "creature", "dog",
                                                     "cat", "beast"))
            asset_spec = _asset_specification(name, brief, design, quality, animations)
            characters.append({
                "name": name,
                "type": "creature" if creature else "humanoid",
                "geometry": {
                    "source": "Blender procedural or approved local asset",
                    "target_triangles": profile["character_triangles"],
                    "uv": "non-overlapping UV0 required; UV1 optional lightmap",
                    "uv_validation": "planned check for overlap and out-of-range UVs",
                },
                "materials": [{
                    "slot": "body",
                    "shader": "PBR metallic-roughness",
                    "status": "planned",
                    "texture_maps": list(PBR_MAPS),
                }],
                "textures": {
                    "maps": list(PBR_MAPS),
                    "resolution": 1024 if quality in ("prototype", "standard") else 2048,
                    "color_space": {"base_color": "sRGB", "normal": "linear",
                                    "roughness": "linear", "metallic": "linear",
                                    "ambient_occlusion": "linear"},
                    "status": "planned-not-generated",
                },
                "rig": {
                    "skeleton": "quadruped" if creature else "humanoid",
                    "bone_count_target": 28 if creature else 45,
                    "root_motion": "in-place clips; root motion disabled unless approved",
                    "animations": animations,
                    "status": "planned-not-generated",
                },
                "lod": {
                    "levels": profile["lod_levels"],
                    "reduction": ["100%", "60%", "30%", "15%"][:profile["lod_levels"]],
                    "status": "planned-not-generated",
                },
                "asset_specification": asset_spec,
                "status": "planned-not-generated",
            })

        gaps = [
            "Actual character meshes, UV layout, PBR textures and rigs are not generated by "
            "this agent; the asset_specification is an executable plan for the Phase 3 "
            "Blender pipeline.",
            "Texture baking, UV overlap validation and LOD generation happen in the Phase 3 "
            "pipeline, not in this agent.",
        ]
        if names:
            gaps.append("Character visual quality and animation playback remain unverified.")

        return {
            "summary": f"Planned {len(characters)} character asset set(s) with PBR maps, "
                       "rig and animation requirements. Nothing was generated.",
            "characters": characters,
            "assets_generated": False,
            "textures_generated": False,
            "capability_gaps": gaps,
            "requirements_addressed": requirement_ids(brief),
            "assumptions": [
                "Blender is available for later asset work; this agent made no Blender call.",
                "Animation clips will be authored or retargeted only in a later phase.",
            ],
            "risks": [
                "A material colour value would not prove a texture exists; Phase 3 must "
                "validate actual texture files and material references.",
            ],
        }
