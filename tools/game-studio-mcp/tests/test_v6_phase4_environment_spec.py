"""V6 Phase 4 environment specification and profile tests (offline).

No Blender process and no network access. These tests verify the contract
between the Phase 2 Environment Agent and the Phase 4 generation pipeline.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import environment_spec  # noqa: E402
from game_studio.agents.environment import EnvironmentAgent  # noqa: E402

REQUEST = (
    "Create a detailed stylized 3D tropical jungle adventure environment for a "
    "third-person monkey game. Include natural hilly terrain, dense tropical "
    "vegetation, tall trees, grass, ferns, rocks, roots, fallen logs, a flowing "
    "river with river banks, natural sunlight, atmospheric depth, and a clear "
    "playable route."
)


class ProfileTests(unittest.TestCase):
    def test_all_profiles_exist_and_levels_are_honest(self) -> None:
        self.assertEqual(len(environment_spec.ENVIRONMENT_PROFILES), 6)
        tropical = environment_spec.ENVIRONMENT_PROFILES["tropical_jungle"]
        self.assertEqual(tropical["implemented_level"], "full")
        self.assertTrue(tropical["river"])
        for key, profile in environment_spec.ENVIRONMENT_PROFILES.items():
            if key == "tropical_jungle":
                continue
            self.assertEqual(profile["implemented_level"], "partial", key)

    def test_profile_report_separates_full_and_partial(self) -> None:
        report = environment_spec.profile_report()
        self.assertEqual(report["fully_implemented"], ["tropical_jungle"])
        self.assertEqual(len(report["partial_profiles"]), 5)
        self.assertIn("daylight", report["lighting_presets"])
        self.assertEqual(report["quality_tiers"]["low"]["terrain_segments"], 33)

    def test_profile_inference(self) -> None:
        self.assertEqual(environment_spec.infer_profile("a tropical jungle"),
                         "tropical_jungle")
        self.assertEqual(environment_spec.infer_profile("dense rainforest"),
                         "dense_rainforest")
        self.assertEqual(environment_spec.infer_profile("a mountain jungle"),
                         "mountain_jungle")
        self.assertEqual(environment_spec.infer_profile("jungle ruins"),
                         "jungle_ruins")
        self.assertEqual(environment_spec.infer_profile("a forest clearing"),
                         "forest_clearing")

    def test_lighting_inference(self) -> None:
        self.assertEqual(environment_spec.infer_lighting("sunset glow"), "sunset")
        self.assertEqual(environment_spec.infer_lighting("morning mist"), "morning")
        self.assertEqual(environment_spec.infer_lighting("overcast rain"), "overcast")
        self.assertEqual(environment_spec.infer_lighting("natural sunlight"), "daylight")

    def test_unknown_profile_and_lighting_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            environment_spec.build_environment_spec(REQUEST, profile="volcano")
        with self.assertRaises(ValueError):
            environment_spec.build_environment_spec(REQUEST, lighting="midnight")


class QualityTierTests(unittest.TestCase):
    def test_tiers_are_measurably_different(self) -> None:
        specs = {tier: environment_spec.build_environment_spec(
            REQUEST, quality_tier=tier) for tier in ("low", "medium", "high")}
        segments = [spec["terrain"]["segments"] for spec in specs.values()]
        trees = [spec["vegetation"]["counts"]["trees"] for spec in specs.values()]
        textures = [spec["textures"]["resolution"] for spec in specs.values()]
        budgets = [spec["performance"]["target_triangles"] for spec in specs.values()]
        for values in (segments, trees, textures, budgets):
            self.assertEqual(values, sorted(values))
            self.assertEqual(len(set(values)), 3)

    def test_folder_settings_match_declared_tier(self) -> None:
        for tier, expected in environment_spec.QUALITY_TIERS.items():
            spec = environment_spec.build_environment_spec(
                REQUEST, quality_tier=tier)
            self.assertEqual(spec["terrain"]["segments"],
                             expected["terrain_segments"])
            self.assertEqual(spec["textures"]["resolution"],
                             expected["texture_resolution"])
            self.assertEqual(spec["performance"]["target_triangles"],
                             expected["target_triangles"])
            self.assertEqual(environment_spec.validate_environment_spec(spec), [])

    def test_unknown_tier_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            environment_spec.build_environment_spec(REQUEST, quality_tier="ultra")


class SpecificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = environment_spec.build_environment_spec(REQUEST)

    def test_spec_is_valid_and_complete(self) -> None:
        self.assertEqual(environment_spec.validate_environment_spec(self.spec), [])
        for key in environment_spec.ENVIRONMENT_SPEC_SCHEMA["required"]:
            self.assertIn(key, self.spec)

    def test_spec_is_deterministic(self) -> None:
        again = environment_spec.build_environment_spec(REQUEST)
        self.assertEqual(self.spec, again)

    def test_seed_is_recorded_and_does_not_change_layout(self) -> None:
        other = environment_spec.build_environment_spec(REQUEST, seed=7)
        self.assertEqual(other["provenance"]["seed"], 7)
        self.assertEqual(other["layout"], self.spec["layout"])
        self.assertEqual(other["id"], self.spec["id"])

    def test_terrain_and_layout_are_inside_bounds(self) -> None:
        terrain = self.spec["terrain"]
        self.assertGreater(terrain["size_x_m"], 0)
        self.assertGreater(terrain["amplitude_m"], 0)
        spawn = self.spec["layout"]["spawn"]
        self.assertLessEqual(abs(spawn["x"]), terrain["size_x_m"] / 2)
        self.assertLessEqual(abs(spawn["y"]), terrain["size_y_m"] / 2)
        self.assertGreaterEqual(len(self.spec["layout"]["route"]), 2)
        self.assertEqual([p["order"] for p in self.spec["layout"]["route"]],
                         list(range(len(self.spec["layout"]["route"]))))

    def test_river_metadata_is_honest_about_physics(self) -> None:
        water = self.spec["water"]
        self.assertTrue(water["present"])
        self.assertGreater(water["width_m"], 0)
        self.assertIn("visual-only", water["physics"])
        self.assertIn("swimming", water["physics"])

    def test_material_channels_are_declared(self) -> None:
        ground = self.spec["materials"][0]
        self.assertEqual(ground["name"], "M_Env_Ground")
        self.assertEqual(ground["channels"]["base_color"], "generated")
        self.assertEqual(ground["channels"]["normal"], "generated")
        self.assertEqual(ground["channels"]["ao"], "absent")
        self.assertEqual(ground["channels"]["opacity"], "absent")
        self.assertEqual(ground["color_spaces"]["normal"], "Non-Color")
        names = {material["name"] for material in self.spec["materials"]}
        for expected in ("M_Env_Water", "M_Env_Bark", "M_Env_Rock", "M_Env_Stone",
                         "M_Env_Grass", "M_Env_Wood"):
            self.assertIn(expected, names)

    def test_provenance_declares_no_external_or_ai_assets(self) -> None:
        provenance = self.spec["provenance"]
        self.assertFalse(provenance["ai_generated"])
        self.assertEqual(provenance["external_assets"], [])
        self.assertEqual(provenance["downloads"], [])
        self.assertEqual(provenance["source"], "generated-locally")
        self.assertTrue(provenance["license"])

    def test_collision_and_navigation_metadata(self) -> None:
        collision = self.spec["collision"]
        self.assertTrue(collision["terrain_collider"])
        self.assertTrue(collision["river_boundary"])
        self.assertIn("metadata", collision["navigation"])
        self.assertIn("no navmesh", collision["navigation"])

    def test_invalid_spec_is_rejected(self) -> None:
        broken = copy.deepcopy(self.spec)
        broken["terrain"]["segments"] += 1
        errors = environment_spec.validate_environment_spec(broken)
        self.assertTrue(any("segments" in error for error in errors))
        self.assertTrue(environment_spec.validate_environment_spec("nope"))

    def test_empty_description_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            environment_spec.build_environment_spec("   ")


class AgentIntegrationTests(unittest.TestCase):
    def test_phase2_environment_agent_output_becomes_an_executable_spec(self) -> None:
        agent = EnvironmentAgent()
        output = agent.deterministic_output({
            "brief": {"environment": ["forest"], "quality_target": "medium"},
            "architecture": {"performance": {"budget": {"max_draw_calls": 240}}},
        })
        self.assertFalse(output["generated"])
        spec = environment_spec.spec_from_agent_output(
            output, quality_tier="medium")
        self.assertEqual(environment_spec.validate_environment_spec(spec), [])
        self.assertEqual(spec["quality_tier"], "medium")
        self.assertEqual(spec["export"]["target_engine"], "unity")
        self.assertEqual(spec["character"]["asset_path"],
                         "validation/v6-character-pipeline/JungleMonkey.glb")

    def test_agent_output_requires_a_summary(self) -> None:
        with self.assertRaises(ValueError):
            environment_spec.spec_from_agent_output({"environment": "jungle"})


if __name__ == "__main__":
    unittest.main()
