"""V6 Phase 6 free-AI intelligence tests.

All provider requests are mocked or absent. No network call, credential, paid
request, asset download, model download or install is performed. Deterministic
results are labelled deterministic and are never presented as live model quality.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio.llm import (  # noqa: E402
    asset_research, capabilities, config as llm_config, free_policy,
    free_routing, intelligence, providers, quota,
)
from game_studio.agents import Orchestrator  # noqa: E402

import server  # noqa: E402


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="game-studio-v6p6-")
        self.addCleanup(self.temp.cleanup)
        self.home = os.path.join(self.temp.name, "studio-home")
        values = {
            "GAME_STUDIO_HOME": self.home,
            "GAME_STUDIO_LLM_PROVIDER": "",
            "GAME_STUDIO_LLM_MODEL": "",
            "GAME_STUDIO_LLM_BASE_URL": "",
            "GAME_STUDIO_LLM_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GROQ_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "GAME_STUDIO_LLM_LOCAL_ONLY": "",
            "GAME_STUDIO_LLM_MAX_REQUESTS": "",
            "GAME_STUDIO_LLM_MAX_REQUESTS_PER_DAY": "",
            "GAME_STUDIO_LLM_MAX_CONTEXT_CHARS": "",
            "GAME_STUDIO_LLM_MAX_TOKENS": "",
            "GAME_STUDIO_LLM_RETRIES": "",
            "GAME_STUDIO_LLM_BACKOFF": "",
        }
        self.env = mock.patch.dict(os.environ, values)
        self.env.start()
        self.addCleanup(self.env.stop)


class FreeCatalogTests(BaseCase):
    def test_catalog_is_evidence_backed_and_has_no_live_claim(self) -> None:
        report = free_policy.catalog()
        self.assertEqual(report["verification_date"], free_policy.VERIFICATION_DATE)
        self.assertEqual(report["network_calls"], 0)
        self.assertEqual(report["live_tests"]["performed"], 0)
        by_name = {item["provider"]: item for item in report["providers"]}
        self.assertEqual(set(by_name), {"gemini", "groq", "openrouter", "ollama"})
        for entry in by_name.values():
            self.assertIn(entry["status"], free_policy.FREE_STATUSES)
            self.assertTrue(entry["docs"])
            self.assertTrue(entry["verified_on"])

    def test_evidence_has_required_fields_and_no_secrets(self) -> None:
        report = free_policy.evidence()
        self.assertFalse(report["secrets_recorded"])
        for record in report["records"]:
            for key in ("provider", "documentation_urls", "verification_date",
                        "free_tier_status", "eligible_models", "rate_limits",
                        "capabilities", "restrictions", "authentication",
                        "live_test_authorized", "live_test_performed",
                        "verification_confidence"):
                self.assertIn(key, record)
            self.assertFalse(record["live_test_performed"])

    def test_gemini_free_eligibility_is_model_specific(self) -> None:
        self.assertTrue(free_policy.model_eligibility(
            "gemini", "gemini-3.8-flash")["eligible"])
        self.assertFalse(free_policy.model_eligibility(
            "gemini", "gemini-4-argon")["eligible"])
        self.assertTrue(free_policy.model_eligibility(
            "gemini", "gemini-4-argon")["reason"])

    def test_groq_documents_per_model_limits(self) -> None:
        entry = free_policy.provider_entry("groq")
        self.assertEqual(entry["status"], free_policy.FREE_LIMITED)
        for model, limits in entry["model_limits"].items():
            self.assertEqual(limits["rpd"], 1000)
            self.assertEqual(limits["rpm"], 30)
        self.assertTrue(free_policy.model_eligibility(
            "groq", "openai/gpt-oss-20b")["eligible"])
        self.assertFalse(free_policy.model_eligibility(
            "groq", "openai/gpt-oss-20b-paid")["eligible"])

    def test_openrouter_requires_free_suffix(self) -> None:
        self.assertTrue(free_policy.model_eligibility(
            "openrouter", "some/model:free")["eligible"])
        result = free_policy.model_eligibility("openrouter", "some/model")
        self.assertFalse(result["eligible"])
        self.assertIn(":free", result["reason"])

    def test_unknown_or_paid_provider_status_is_not_free(self) -> None:
        self.assertFalse(free_policy.is_free_status(free_policy.PAID))
        self.assertFalse(free_policy.is_free_status(free_policy.TRIAL_ONLY))
        self.assertFalse(free_policy.is_free_status(free_policy.UNKNOWN))
        self.assertEqual(free_policy.provider_status("openai"), free_policy.UNKNOWN)

    def test_catalog_makes_no_network_call(self) -> None:
        with mock.patch.object(providers, "http_request") as http:
            free_policy.catalog()
            free_policy.evidence()
        http.assert_not_called()


class FreeRoutingTests(BaseCase):
    def test_no_credentials_returns_deterministic_fallback(self) -> None:
        with mock.patch.object(free_routing.phase1_routing.shutil, "which",
                               return_value=None):
            result = free_routing.route("game_design_reasoning")
        self.assertEqual(result["mode"], "deterministic")
        self.assertIsNone(result["selected"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["network_calls"], 0)
        self.assertFalse(result["fallback_plan"]["paid_switch"])
        self.assertFalse(result["policy"]["paid_fallback"])
        self.assertTrue(all(c["free_status"] in free_policy.FREE_STATUSES
                            for c in result["candidates"]))

    def test_paid_provider_is_refused(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        result = free_routing.route("game_design_reasoning", provider="openai")
        self.assertEqual(result["mode"], "deterministic")
        self.assertIsNone(result["selected"])
        self.assertTrue(any("unknown" in blocker or "paid" in blocker
                            for blocker in result["candidates"][0]["blockers"]))
        self.assertFalse(result["fallback_plan"]["auto_switch"])

    def test_trial_only_and_paid_statuses_are_refused(self) -> None:
        os.environ["GROQ_API_KEY"] = "test-key-not-real"
        for status in (free_policy.TRIAL_ONLY, free_policy.PAID,
                       free_policy.UNKNOWN):
            with mock.patch.object(free_policy, "provider_status",
                                   return_value=status):
                result = free_routing.route(
                    "game_design_reasoning", provider="groq",
                    model="openai/gpt-oss-20b")
            self.assertEqual(result["mode"], "deterministic", status)
            self.assertTrue(any(status in blocker
                                for blocker in result["candidates"][0]["blockers"]))

    def test_openrouter_free_model_is_selected_but_paid_variant_is_not(self) -> None:
        os.environ["OPENROUTER_API_KEY"] = "test-key-not-real"
        free = free_routing.route("game_design_reasoning", provider="openrouter",
                                  model="some/model:free")
        self.assertEqual(free["mode"], "provider")
        self.assertEqual(free["selected"]["provider"], "openrouter")
        paid = free_routing.route("game_design_reasoning", provider="openrouter",
                                  model="some/model")
        self.assertEqual(paid["mode"], "deterministic")
        self.assertIn(":free", " ".join(paid["candidates"][0]["blockers"]))

    def test_gemini_and_groq_documented_free_models_are_selected(self) -> None:
        os.environ["GEMINI_API_KEY"] = "test-key-not-real"
        gemini = free_routing.route("game_design_reasoning", provider="gemini",
                                    model="gemini-3.8-flash")
        self.assertEqual(gemini["mode"], "provider")
        self.assertEqual(gemini["selected"]["free_status"], free_policy.FREE_LIMITED)
        os.environ["GROQ_API_KEY"] = "test-key-not-real"
        groq = free_routing.route("game_design_reasoning", provider="groq",
                                  model="openai/gpt-oss-120b")
        self.assertEqual(groq["mode"], "provider")

    def test_local_ollama_is_selected_when_runtime_exists(self) -> None:
        with mock.patch.object(free_routing.phase1_routing.shutil, "which",
                               return_value="C:/fake/ollama.exe"):
            result = free_routing.route("game_design_reasoning")
        self.assertEqual(result["mode"], "provider")
        self.assertEqual(result["selected"]["provider"], "ollama")
        self.assertEqual(result["selected"]["free_status"], free_policy.LOCAL_FREE)

    def test_exhausted_documented_quota_blocks_selection(self) -> None:
        os.environ["GROQ_API_KEY"] = "test-key-not-real"
        quota.record("groq", "openai/gpt-oss-20b", requests=1000)
        result = free_routing.route("game_design_reasoning", provider="groq",
                                    model="openai/gpt-oss-20b")
        self.assertEqual(result["mode"], "deterministic")
        self.assertTrue(any("allowance" in blocker
                            for blocker in result["candidates"][0]["blockers"]))

    def test_unknown_quota_is_not_treated_as_unlimited(self) -> None:
        state = quota.quota_state("gemini", "gemini-3.8-flash")
        self.assertIsNone(state["verified_daily_limit"])
        self.assertIsNone(state["remaining_today"])
        self.assertIsNone(state["exhausted"])
        decision = quota.can_request("gemini", "gemini-3.8-flash")
        self.assertEqual(decision["kind"], "quota_unknown_not_unlimited")
        self.assertFalse(quota.status()["policy"]["unknown_quota_is_unlimited"])

    def test_failure_classification_covers_required_cases(self) -> None:
        self.assertEqual(quota.failure_reason(status_code=429)["reason"],
                         "http_429_rate_limited")
        self.assertEqual(quota.failure_reason(status_code=401)["reason"],
                         "http_401_unauthorized")
        self.assertEqual(quota.failure_reason(status_code=403)["reason"],
                         "http_403_forbidden")
        self.assertEqual(quota.failure_reason(error_kind="timeout")["reason"],
                         "timeout")
        self.assertEqual(quota.failure_reason(error_kind="network")["reason"],
                         "network_failure")
        self.assertEqual(quota.failure_reason(error_kind="not_found")["reason"],
                         "invalid_model")
        self.assertEqual(quota.failure_reason(error_kind="deprecation")["reason"],
                         "deprecated")
        self.assertEqual(quota.failure_reason(error_kind="invalid_output")["reason"],
                         "malformed_output")

    def test_route_makes_no_network_call(self) -> None:
        with mock.patch.object(providers, "http_request") as http:
            free_routing.route("game_design_reasoning")
        http.assert_not_called()


class QuotaAndSecurityTests(BaseCase):
    def test_ledger_tracks_required_fields_and_redacts_secrets(self) -> None:
        quota.record("groq", "openai/gpt-oss-20b", input_tokens=12,
                     output_tokens=34, estimated_cost_usd=0.0,
                     verified_allowance=1000, remaining_allowance=999,
                     status="success")
        state = quota.quota_state("groq", "openai/gpt-oss-20b")
        self.assertEqual(state["requests_today"], 1)
        self.assertEqual(state["remaining_today"], 999)
        quota.record("groq", "openai/gpt-oss-20b", status="error",
                     fallback_reason="Authorization: Bearer sk-"
                                     "supersecretvalue1234567890")
        raw = json.dumps(quota.load_ledger())
        self.assertNotIn("supersecretvalue", raw)
        self.assertIn("[REDACTED]", raw)

    def test_record_outcome_reports_deterministic_fallback_without_paid_switch(self) -> None:
        result = free_routing.record_outcome(
            "groq", "openai/gpt-oss-20b", status="error", status_code=429)
        self.assertTrue(result["recorded"])
        self.assertEqual(result["failure"]["reason"], "http_429_rate_limited")
        self.assertEqual(result["fallback"], "deterministic")
        self.assertFalse(result["paid_fallback"])

    def test_quota_status_never_stores_credentials(self) -> None:
        report = quota.status()
        text = json.dumps(report).lower()
        self.assertNotIn("api_key", text)
        self.assertNotIn("bearer ", text)
        self.assertFalse(report["policy"]["secrets_stored"])


class IntelligenceTests(BaseCase):
    def setUp(self) -> None:
        super().setUp()
        self.design = intelligence.design(
            "Create a 3D jungle adventure where a monkey collects bananas.")

    def test_requirements_have_required_fields_and_stable_ids(self) -> None:
        proposal = intelligence.requirements(
            "Create a 3D jungle adventure where a monkey collects bananas.")
        ids = [item["id"] for item in proposal["requirements"]]
        self.assertEqual(len(ids), len(set(ids)))
        for item in proposal["requirements"]:
            for key in ("id", "description", "category", "priority",
                        "dependencies", "acceptance_criteria", "required_assets",
                        "target_engine", "verification_method", "status",
                        "provenance", "confidence"):
                self.assertIn(key, item)
            self.assertEqual(item["status"], "proposed")
            self.assertIn(item["provenance"],
                          ("user_requirement", "agent_recommendation",
                           "technical_dependency"))

    def test_expected_categories_are_covered(self) -> None:
        covered = {item["id"] for item in self.design["coverage"]}
        for expected in ("player_character", "character_rig_animations",
                         "jungle_terrain", "vegetation", "collectibles",
                         "collision", "camera", "player_controls", "score_system",
                         "objectives", "hud", "game_states", "performance",
                         "build_configuration", "tests"):
            self.assertIn(expected, covered)

    def test_contradiction_detection(self) -> None:
        proposal = intelligence.requirements("Create a 2D and 3D single player "
                                             "multiplayer game with a HUD but no UI.")
        kinds = {item["kind"] for item in proposal["contradictions"]}
        self.assertIn("dimension", kinds)
        self.assertIn("player_mode", kinds)

    def test_unsupported_and_blocked_detection(self) -> None:
        proposal = intelligence.requirements(
            "Create an AAA multiplayer open world with AI 3D models.")
        features = {item["feature"] for item in proposal["unsupported_features"]}
        self.assertIn("multiplayer", features)
        self.assertIn("aaa_scope", features)
        self.assertIn("ai_3d_generation", features)
        self.assertTrue(proposal["blocked_requirements"])

    def test_design_is_schema_valid_and_not_executable(self) -> None:
        self.assertTrue(self.design["validation"]["valid"])
        self.assertFalse(self.design["executable"])
        self.assertFalse(self.design["provenance"]["live_model_quality_claimed"])
        self.assertTrue(self.design["testing_requirements"])
        self.assertTrue(self.design["milestones"])

    def test_approval_boundary_keeps_decisions_separate(self) -> None:
        proposal = intelligence.requirements(
            "Create a 3D runner.",
            approved_decisions=[{"id": "D-1", "statement": "Use Unity 6"}])
        self.assertEqual(proposal["approved_decisions"][0]["approved"], True)
        self.assertNotIn(proposal["approved_decisions"][0]["statement"],
                         [item["description"] for item in proposal["requirements"]])

    def test_character_and_environment_specs_are_deterministic_not_ai(self) -> None:
        character = intelligence.character_spec_from_design(self.design)
        environment = intelligence.environment_spec_from_design(self.design)
        self.assertTrue(character["validation"]["valid"])
        self.assertTrue(environment["validation"]["valid"])
        self.assertFalse(character["ai_generated_asset"])
        self.assertFalse(environment["ai_generated_asset"])
        self.assertTrue(character["procedural_blender"])
        self.assertFalse(character["generation_performed"])
        self.assertFalse(environment["generation_performed"])

    def test_benchmark_is_deterministic_and_does_not_rank_live_models(self) -> None:
        report = intelligence.benchmark()
        self.assertEqual(report["evaluation_mode"], "deterministic")
        self.assertFalse(report["live_provider_quality"])
        self.assertIsNone(report["provider_ranking"])
        self.assertTrue(report["summary"]["all_reproducible"])
        self.assertTrue(report["summary"]["cost_policy_compliant"])
        self.assertFalse(report["summary"]["live_model_quality_measured"])


class AssetResearchTests(BaseCase):
    def test_categories_separate_free_from_paid(self) -> None:
        report = asset_research.catalog()
        self.assertEqual(report["asset_downloads"], 0)
        self.assertEqual(report["model_downloads"], 0)
        self.assertEqual(report["installs"], 0)
        by_category = report["by_category"]
        self.assertIn("pollinations_classic", by_category["free_hosted_api"])
        self.assertIn("stability_api", by_category["paid_service"])
        self.assertIn("triposr_local", by_category["open_source_local"])

    def test_no_asset_generation_is_claimed_available_now(self) -> None:
        report = asset_research.capabilities()
        self.assertFalse(report["asset_generation_performed"])
        self.assertTrue(report["procedural_blender_is_not_ai"])
        self.assertEqual(report["verified_free_hosted_available_now"], [])
        for capability in asset_research.CAPABILITIES:
            self.assertFalse(report["capabilities"][capability]["available_now"])

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            asset_research.find("teleportation")


class McpToolTests(BaseCase):
    def test_phase6_tools_have_handlers_and_schemas(self) -> None:
        names = {"llm_free_provider_catalog", "llm_free_quota_status",
                 "llm_free_route", "llm_game_requirements", "llm_game_design",
                 "llm_asset_generation_capabilities", "llm_ai_benchmark"}
        declared = {tool["name"] for tool in server.TOOLS}
        self.assertTrue(names <= declared)
        self.assertEqual(set(server.HANDLERS), declared)
        for tool in server.TOOLS:
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_handlers_return_labeled_results(self) -> None:
        catalog = server.tool_llm_free_provider_catalog({})
        self.assertEqual(catalog["network_calls"], 0)
        quota_status = server.tool_llm_free_quota_status({})
        self.assertFalse(quota_status["policy"]["paid_fallback"])
        route = server.tool_llm_free_route({"task": "game_design_reasoning"})
        self.assertIn(route["mode"], ("provider", "deterministic"))
        requirements = server.tool_llm_game_requirements(
            {"request": "Create a 2D platformer."})
        self.assertFalse(requirements["executable"])
        design = server.tool_llm_game_design(
            {"request": "Create a 3D jungle adventure where a monkey collects bananas.",
             "include_specs": True})
        self.assertTrue(design["validation"]["valid"])
        self.assertIn("character_spec", design)
        assets = server.tool_llm_asset_generation_capabilities({})
        self.assertFalse(assets["asset_generation_performed"])
        benchmark = server.tool_llm_ai_benchmark({})
        self.assertEqual(benchmark["evaluation_mode"], "deterministic")


class IntegrationTests(BaseCase):
    def test_orchestrator_free_only_stays_non_executable(self) -> None:
        orchestrator = Orchestrator(
            "Create a 3D jungle adventure where a monkey collects bananas.",
            use_provider=False, free_only=True)
        result = orchestrator.run()
        self.assertFalse(result["executable"])
        self.assertFalse(result["governance"]["writes_performed"])
        self.assertFalse(result["governance"]["engine_invoked"])
        self.assertFalse(result["governance"]["assets_generated"])
        modes = {item["mode"] for item in result["routing"].values()}
        self.assertTrue(modes <= {"provider", "deterministic"})
        for item in result["routing"].values():
            if item["selected"]:
                self.assertIn(item["selected"]["provider"],
                              free_routing.FREE_ROUTE_ORDER)

    def test_free_only_forces_allow_paid_off(self) -> None:
        orchestrator = Orchestrator("Create a 3D jungle adventure.",
                                    use_provider=False, allow_paid=True,
                                    free_only=True)
        self.assertFalse(orchestrator.allow_paid)
        self.assertTrue(orchestrator.free_only)

    def test_provider_capabilities_never_infer_asset_generation(self) -> None:
        for provider in llm_config.PROVIDERS:
            caps = capabilities.provider_profile(provider)["capabilities"]
            self.assertEqual(caps["image_generation"], capabilities.UNSUPPORTED)
            self.assertEqual(caps["texture_generation"], capabilities.UNSUPPORTED)
            self.assertEqual(caps["3d_mesh_generation"], capabilities.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
