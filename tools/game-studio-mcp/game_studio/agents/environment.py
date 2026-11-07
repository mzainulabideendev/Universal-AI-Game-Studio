"""Environment Agent: structured environment plan, never generated content."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import clean_values, quality_profile, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, ENVIRONMENT_SCHEMA


class EnvironmentAgent(Agent):
    spec = AgentSpec(
        id="environment",
        name="Environment Agent",
        version="1.0.0",
        responsibility="Plan terrain, vegetation, structures, water, lighting and atmosphere.",
        task_category="character_environment_planning",
        dependencies=("design", "architecture"),
        required_context=("brief", "design", "architecture"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=ENVIRONMENT_SCHEMA,
        produces="environment",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        architecture = input_data.get("architecture") or {}
        profile, quality = quality_profile(brief.get("quality_target"))
        biome = (clean_values(brief, "environment", ["forest"])[0]).lower()
        budget = (architecture.get("performance") or {}).get("budget") or profile
        max_draw = int(budget.get("max_draw_calls") or profile["max_draw_calls"])
        texture_budget = int(budget.get("texture_budget_mb")
                             or profile["texture_budget_mb"])

        props = min(profile["environment_props"], max_draw // 2)
        estimate_draws = min(max_draw, 40 + props)
        estimate_texture_mb = min(texture_budget, 24 + props // 4)

        return {
            "summary": f"Planned a {biome} environment at {quality} quality within the "
                       f"{max_draw} draw-call budget.",
            "environment": biome,
            "terrain": {
                "approach": "deterministic procedural heightmap with hand-authored landmarks",
                "size_meters": 200,
                "material_layers": ["grass", "soil", "rock"],
                "collision": "terrain collider with simplified slopes",
            },
            "vegetation": [
                {"type": "canopy_trees", "count": props // 3, "lod": True},
                {"type": "ferns", "count": props // 2, "lod": True},
                {"type": "ground_cover", "count": props, "lod": True},
            ],
            "structures": [
                {"type": "ruins", "count": 2, "purpose": "landmark and traversal"},
                {"type": "wooden_platforms", "count": 6, "purpose": "jump routes"},
            ],
            "water": {"present": False, "reason": "not requested; swimming is excluded"},
            "lighting": {
                "directional_sun": True, "shadows": quality != "prototype",
                "ambient": "skybox gradient", "reflection_probes": quality in ("high",
                                                                              "cinematic"),
            },
            "weather": {"enabled": False, "reason": "weather was not requested"},
            "atmosphere": {"fog": True, "skybox": "procedural jungle sky",
                           "post_processing": quality in ("standard", "high",
                                                          "cinematic")},
            "materials": ["grass", "soil", "mud", "stone", "wood", "foliage"],
            "estimates": {
                "draw_calls": estimate_draws,
                "texture_mb": estimate_texture_mb,
                "max_draw_calls": max_draw,
                "texture_budget_mb": texture_budget,
                "within_budget": (estimate_draws <= max_draw
                                  and estimate_texture_mb <= texture_budget),
            },
            "performance_risks": [
                "Foliage overdraw is the main integrated-GPU risk; use LODs and limited "
                "shadow casters.",
                "Verify draw calls in a real build; these values are estimates, not "
                "measurements.",
            ],
            "dependencies": [
                "Terrain and foliage generation belongs to Phase 4.",
                "Texture and material pipeline belongs to Phase 3.",
                "The selected engine must exist before import.",
            ],
            "generated": False,
            "requirements_addressed": requirement_ids(brief),
            "assumptions": [
                "Environment size and prop counts are planning defaults based on the "
                "requested quality target.",
            ],
            "risks": [
                "No terrain, vegetation, material or lighting was created in Phase 2.",
                "Performance estimates are not measurements and must be validated later.",
            ],
        }
