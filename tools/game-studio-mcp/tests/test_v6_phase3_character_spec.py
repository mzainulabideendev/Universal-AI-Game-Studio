"""V6 Phase 3 character specification and capability tests (offline).

These tests never call Blender and never touch the network. They verify the
contract between the Phase 2 Character Agent and the Phase 3 asset pipeline.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import character_spec  # noqa: E402
from game_studio.agents.character import CharacterAgent  # noqa: E402

REQUEST = (
    "Create a stylized 3D jungle monkey character for a professional third-person "
    "adventure game. It should have expressive eyes, detailed facial features, brown "
    "fur coloration, realistic proportions for a stylized game character, a complete "
    "body, hands, feet, and a game-ready material setup. Prepare the character for "
    "idle, walk, run, and jump animations."
)


class QualityTierTests(unittest.TestCase):
    def test_tiers_are_measurably_different(self) -> None:
        specs = {tier: character_spec.build_character_spec(
            REQUEST, quality_tier=tier) for tier in ("low", "medium", "high")}
        resolutions = [spec["textures"]["resolution"] for spec in specs.values()]
        segments = [spec["geometry"]["sphere_segments"] for spec in specs.values()]
        bones = [spec["rigging"]["bone_count_target"] for spec in specs.values()]
        self.assertEqual(resolutions, sorted(resolutions))
        self.assertEqual(len(set(resolutions)), 3)
        self.assertEqual(segments, sorted(segments))
        self.assertEqual(len(set(segments)), 3)
        self.assertEqual(len(set(bones)), 3)

    def test_folder_tier_matches_spec_fields(self) -> None:
        for tier, expected in character_spec.QUALITY_TIERS.items():
            spec = character_spec.build_character_spec(REQUEST, quality_tier=tier)
            self.assertEqual(spec["textures"]["resolution"],
                             expected["texture_resolution"])
            self.assertEqual(spec["geometry"]["sphere_segments"],
                             expected["sphere_segments"])
            self.assertEqual(spec["rigging"]["bone_count_target"],
                             expected["bone_count"])
            self.assertEqual(character_spec.validate_character_spec(spec), [])

    def test_unknown_tier_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            character_spec.build_character_spec(REQUEST, quality_tier="ultra")


class SpecificationTests(unittest.TestCase):
    def test_request_is_parsed_honestly(self) -> None:
        spec = character_spec.build_character_spec(REQUEST)
        self.assertEqual(spec["character_type"], "primate")
        self.assertTrue(spec["limbs"]["tail"]["present"])
        self.assertEqual([a["name"] for a in spec["animations"]],
                         ["idle", "walk", "run", "jump"])
        self.assertEqual(spec["provenance"]["source"], "generated-locally")
        self.assertFalse(spec["capabilities"]["external_generation_used"])
        self.assertEqual(spec["provenance"]["external_assets"], [])
        self.assertEqual(spec["provenance"]["downloads"], [])

    def test_required_fields_and_schema(self) -> None:
        spec = character_spec.build_character_spec(REQUEST)
        for key in character_spec.CHARACTER_SPEC_SCHEMA["required"]:
            self.assertIn(key, spec)

    def test_tampered_tier_settings_fail_validation(self) -> None:
        spec = character_spec.build_character_spec(REQUEST, quality_tier="medium")
        tampered = copy.deepcopy(spec)
        tampered["textures"]["resolution"] = 4096
        self.assertTrue(any("textures.resolution" in error
                            for error in character_spec.validate_character_spec(tampered)))
        tampered = copy.deepcopy(spec)
        tampered["quality_tier"] = "cinematic"
        self.assertTrue(any("quality_tier" in error
                            for error in character_spec.validate_character_spec(tampered)))

    def test_unsupported_animation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            character_spec.build_character_spec(REQUEST, animations=["backflip"])

    def test_pbr_channels_report_absent_maps_honestly(self) -> None:
        spec = character_spec.build_character_spec(REQUEST)
        absent = spec["textures"]["maps_absent"]
        self.assertIn("ao", absent)
        self.assertIn("emission", absent)
        self.assertIn("opacity", absent)
        self.assertEqual(spec["textures"]["generation_method"],
                         "procedural-local-blender")
        for name in ("ao", "emission", "opacity"):
            self.assertNotIn(name, spec["textures"]["maps_generated"])

    def test_provenance_license_and_attribution(self) -> None:
        spec = character_spec.build_character_spec(REQUEST)
        provenance = spec["provenance"]
        self.assertEqual(provenance["license_id"], "project-original-1.0")
        self.assertFalse(provenance["attribution_required"])
        self.assertNotIn("CC", provenance["license"])

    def test_identifier_is_path_safe(self) -> None:
        spec = character_spec.build_character_spec(REQUEST, name="../../evil name")
        self.assertNotIn("..", spec["id"])
        self.assertNotIn("/", spec["id"])
        self.assertNotIn("\\", spec["id"])

    def test_non_object_specs_are_rejected(self) -> None:
        self.assertTrue(character_spec.validate_character_spec([]))
        self.assertTrue(character_spec.validate_character_spec(None))


class CapabilityTests(unittest.TestCase):
    def test_text_reasoning_is_supported_but_not_asset_generation(self) -> None:
        text = character_spec.check_capability("text_reasoning", "openai")
        self.assertEqual(text["state"], "supported")
        for capability in ("image_generation", "texture_generation",
                           "material_generation", "mesh_generation"):
            result = character_spec.check_capability(capability, "openai")
            self.assertEqual(result["state"], "unsupported")

    def test_provider_names_do_not_imply_generation_support(self) -> None:
        report = character_spec.provider_capability_report()
        for name, entry in report["providers"].items():
            self.assertIn(entry["image_generation"],
                          character_spec.CAPABILITY_STATES)
            self.assertNotEqual(entry["image_generation"], "supported")
        self.assertIn("image_generation", report["authorized_missing"])

    def test_meshy_is_known_but_paid_and_unauthorized(self) -> None:
        result = character_spec.check_capability("mesh_generation", "meshy")
        self.assertEqual(result["state"], "supported")
        self.assertTrue(result["paid"])
        self.assertFalse(result["authorized"])

    def test_unknown_capability_and_provider_raise(self) -> None:
        with self.assertRaises(ValueError):
            character_spec.check_capability("telepathy")
        with self.assertRaises(ValueError):
            character_spec.check_capability("mesh_generation", "not-a-provider")

    def test_image_analysis_is_not_claimed(self) -> None:
        result = character_spec.check_capability("image_analysis", "openai")
        self.assertEqual(result["state"], "unknown")


class AgentIntegrationTests(unittest.TestCase):
    def test_character_agent_emits_a_valid_asset_specification(self) -> None:
        output = CharacterAgent().deterministic_output({
            "brief": {
                "summary": "Jungle monkey third-person adventure",
                "quality_target": "standard",
                "characters": ["jungle monkey"],
                "mechanics": ["jump"],
            },
            "design": {"art_direction": "stylized brown fur"},
            "architecture": {},
        })
        character = output["characters"][0]
        spec = character["asset_specification"]
        self.assertEqual(character_spec.validate_character_spec(spec), [])
        self.assertEqual(spec["quality_tier"], "medium")
        self.assertEqual(spec["character_type"], "primate")
        self.assertIn("idle", [a["name"] for a in spec["animations"]])
        self.assertFalse(output["assets_generated"])
        self.assertFalse(output["textures_generated"])
        self.assertEqual(character["status"], "planned-not-generated")

    def test_quality_profiles_map_to_tiers(self) -> None:
        output = CharacterAgent().deterministic_output({
            "brief": {"summary": "hero", "quality_target": "prototype",
                      "characters": ["hero"]},
            "design": {}, "architecture": {},
        })
        spec = output["characters"][0]["asset_specification"]
        self.assertEqual(spec["quality_tier"], "low")

    def test_spec_from_agent_output(self) -> None:
        output = CharacterAgent().deterministic_output({
            "brief": {"summary": "jungle monkey", "characters": ["monkey"]},
            "design": {}, "architecture": {},
        })
        spec = character_spec.spec_from_agent_output(output, quality_tier="high")
        self.assertEqual(spec["quality_tier"], "high")
        self.assertEqual(character_spec.validate_character_spec(spec), [])

    def test_spec_from_empty_output_raises(self) -> None:
        with self.assertRaises(ValueError):
            character_spec.spec_from_agent_output({})
        with self.assertRaises(ValueError):
            character_spec.spec_from_agent_output({"summary": "x", "characters": []})


if __name__ == "__main__":
    unittest.main()
