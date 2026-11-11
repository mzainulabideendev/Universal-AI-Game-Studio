"""V6 Phase 7 real-AI validation tests (offline only).

No live provider request, credential, download or install is performed here.
The one mocked "live" case replaces the provider adapter, so the test suite
never opens a socket. Anything produced by a fixture is labelled as a fixture
and never presented as live model quality.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from game_studio.llm import (  # noqa: E402
    config as llm_config,
    free_policy,
    game_spec_pipeline,
    provider_validation,
    providers,
    quality_evaluation,
    response_validation,
    schemas as llm_schemas,
)
from game_studio import character_spec, environment_spec  # noqa: E402

import server  # noqa: E402


def fixture_payload() -> dict:
    return {
        "game_title": "Jungle Banana Run",
        "genre": ["third-person action adventure", "platformer"],
        "target_platforms": ["Windows", "Android"],
        "core_gameplay_loop": [
            "Explore the jungle trail",
            "Collect bananas to fill the objective counter",
            "Avoid hazard volumes and respawn at the last checkpoint",
            "Reach the destination zone to complete the level",
        ],
        "player_mechanics": ["Run and turn", "Jump and land", "Collect", "Interact"],
        "camera_design": "Third-person follow camera with a spring arm and obstacle pull-in.",
        "environment_requirements": [
            "Tropical jungle biome with a defined trail",
            "Cliffs, river and foliage dressing",
            "Directional sunlight with a warm ambient fill",
        ],
        "collectibles": ["Banana pickup with a trigger collider"],
        "hazards": ["Spike pit", "River current volume"],
        "progression": ["Spawn area", "Mid-route checkpoint", "Destination zone"],
        "ui_requirements": ["HUD banana counter", "Pause menu", "Level complete panel"],
        "audio_requirements": ["Footstep SFX", "Collect chime", "Ambient jungle loop"],
        "performance_targets": {
            "target_fps": 60,
            "quality_tier": "low",
            "hardware": "Integrated GPU, 8 GB RAM",
            "notes": "Keep draw calls bounded and reuse materials.",
        },
        "technical_architecture": [
            "Unity character controller with rigidbody-free movement",
            "Trigger colliders for collectibles and hazards",
            "Single additive scene with baked lighting",
        ],
        "asset_requirements": [
            "Monkey character mesh with a 24-bone rig and idle/walk/run/jump animations",
            "Jungle terrain tiles, tree and bush props, river plane and rock clusters",
            "Banana prop with a stylized material",
            "PBR base color and roughness textures for terrain and props",
            "Footstep and collect audio clips",
            "HUD font, banana icon and menu panel",
        ],
        "acceptance_criteria": [
            "Collecting a banana increments the HUD counter within 1 frame",
            "The player reaches the destination zone and the level completes within 10 seconds of arrival",
            "Frame rate stays at or above 60 fps for 30 seconds on the reference hardware",
            "All 10 bananas can be collected in one run",
        ],
        "risks": ["Android thermal throttling", "Touch input mapping is not yet specified"],
        "unsupported_or_uncertain": ["Android build pipeline has not been validated in this repository"],
        "engine": "unity",
        "dimension": "3d",
        "art_style": "stylized low-poly",
        "summary": "A short third-person jungle collection level for Windows and Android.",
    }


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="game-studio-v6p7-")
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

    def configure_dummy_credential(self) -> None:
        patcher = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-not-real"})
        patcher.start()
        self.addCleanup(patcher.stop)


class ReadinessTests(BaseCase):
    def test_readiness_is_offline_and_reports_missing_credential(self) -> None:
        report = provider_validation.readiness()
        self.assertTrue(report["ok"])
        self.assertEqual(report["network_calls"], 0)
        self.assertFalse(report["credential"]["configured"])
        self.assertFalse(report["credential"]["value_exposed"])
        self.assertFalse(report["ready"])
        self.assertIn("no credential configured", " ".join(report["blockers"]))
        self.assertEqual(report["adapter"], "GeminiProvider")
        self.assertEqual(report["free_status"], "free_limited")
        self.assertIs(report["model_eligibility"]["eligible"], True)
        json.dumps(report)

    def test_readiness_unknown_provider_is_not_ready(self) -> None:
        report = provider_validation.readiness("acme-ai")
        self.assertFalse(report["ok"])
        self.assertFalse(report["ready"])
        self.assertEqual(report["network_calls"], 0)

    def test_readiness_rejects_paid_model_and_paid_provider(self) -> None:
        paid_model = provider_validation.readiness("gemini", "gemini-4-argon")
        self.assertFalse(paid_model["ready"])
        self.assertIs(paid_model["model_eligibility"]["eligible"], False)
        paid_provider = provider_validation.readiness("openai")
        self.assertFalse(paid_provider["ok"])
        self.assertFalse(paid_provider["ready"])
        self.assertIn("free-provider catalog", " ".join(paid_provider["blockers"]))

    def test_configured_credential_is_detected_but_not_exposed(self) -> None:
        self.configure_dummy_credential()
        report = provider_validation.readiness()
        self.assertTrue(report["credential"]["configured"])
        self.assertNotIn("test-key-not-real", json.dumps(report))

    def test_exhausted_quota_blocks_readiness(self) -> None:
        exhausted = {
            "provider": "gemini", "model": "gemini-3.8-flash",
            "status": "free_limited", "free": True, "requests_today": 250,
            "verified_daily_limit": 250, "remaining_today": 0,
            "exhausted": True, "quota_known": True, "reason": "limit reached",
        }
        with mock.patch.object(provider_validation.quota, "quota_state",
                               return_value=exhausted):
            report = provider_validation.readiness()
        self.assertFalse(report["ready"])
        self.assertIn("quota", " ".join(report["blockers"]).lower())


class PlanTests(BaseCase):
    def test_plan_makes_no_request_and_records_limits(self) -> None:
        plan = provider_validation.plan_live_validation()
        self.assertEqual(plan["network_calls"], 0)
        self.assertFalse(plan["live_request_performed"])
        self.assertFalse(plan["executable_now"])
        self.assertEqual(plan["request"]["retries"], 0)
        self.assertFalse(plan["request"]["provider_fallback"])
        self.assertFalse(plan["request"]["project_files_sent"])
        self.assertEqual(plan["quota_impact"]["requests"], 1)
        self.assertEqual(plan["credential"]["status"],
                         "BLOCKED_CREDENTIAL_NOT_CONFIGURED")
        self.assertEqual(plan["authorization"]["status"], "NOT_AUTHORIZED")
        self.assertEqual(len(plan["request"]["request_sha256"]), 64)
        self.assertEqual(plan["data_handling"]["controlled_test_idea_only"], True)

    def test_plan_hash_is_stable_and_changes_with_the_request(self) -> None:
        first = provider_validation.plan_live_validation()
        second = provider_validation.plan_live_validation()
        self.assertEqual(first["request"]["request_sha256"],
                         second["request"]["request_sha256"])
        changed = provider_validation.plan_live_validation(
            provider_validation.CONTROLLED_TEST_IDEA + " Add a timer.")
        self.assertNotEqual(first["request"]["request_sha256"],
                            changed["request"]["request_sha256"])

    def test_plan_uses_corrected_gemini_generation_config(self) -> None:
        plan = provider_validation.plan_live_validation()
        request = plan["request"]
        # Gemini 3.6+ silently ignores temperature; Phase 7 must omit it.
        self.assertNotIn("temperature", request["generation_config"])
        self.assertIsNone(request["temperature"])
        self.assertTrue(request["temperature_omitted"])
        self.assertTrue(request["temperature_omission_reason"])
        self.assertEqual(request["generation_config"],
                         {"max_output_tokens": 2048,
                          "response_mime_type": "application/json"})
        self.assertTrue(request["json_mode"])
        self.assertEqual(request["max_output_tokens"], 2048)
        self.assertEqual(request["retries"], 0)
        self.assertFalse(request["provider_fallback"])
        self.assertEqual(plan["model"], "gemini-3.8-flash")
        self.assertEqual(plan["model_verification"]["model_id"],
                         "gemini-3.8-flash")
        self.assertTrue(plan["model_verification"]["model_code_verified"])
        self.assertIn("ai.google.dev", plan["model_verification"]
                      ["generate_content_reference"])

    def test_plan_hash_reflects_temperature_removal(self) -> None:
        plan = provider_validation.plan_live_validation()
        request = plan["request"]
        canonical = json.dumps({
            "provider": plan["provider"],
            "model": plan["model"],
            "system": request["system_prompt"],
            "user": request["user_prompt"],
            "max_output_tokens": request["max_output_tokens"],
            "response_mime_type": "application/json",
            "retries": 0,
            "fallback": False,
        }, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(request["request_sha256"], expected)

    def test_plan_enforces_input_and_output_bounds(self) -> None:
        with self.assertRaises(ValueError):
            provider_validation.plan_live_validation("x" * 4001)
        with self.assertRaises(ValueError):
            provider_validation.plan_live_validation(max_output_tokens=8)
        with self.assertRaises(ValueError):
            provider_validation.plan_live_validation(timeout=2)

    def test_audit_record_contains_no_secret_material(self) -> None:
        record = provider_validation.audit_record(
            provider_validation.plan_live_validation())
        text = json.dumps(record)
        self.assertNotIn("api_key", text)
        self.assertNotIn("Authorization", text)
        self.assertEqual(record["network_calls"], 0)
        self.assertFalse(record["live_request_performed"])


class GeminiBodyTests(BaseCase):
    def _adapter(self, *, model: str = "gemini-3.8-flash"):
        return providers.GeminiProvider({
            "provider": "gemini",
            "model": model,
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "test-key-not-real",
            "local_provider": False,
            "key_required": True,
        })

    def _run(self, adapter, **kwargs):
        captured = {}

        def fake_request(url, *, headers, body, timeout, **extra):
            captured["url"] = url
            captured["body"] = body
            return {"payload": {
                "candidates": [{"content": {"parts": [{"text": "{}"}]},
                                "finishReason": "STOP"}],
                "usageMetadata": {"totalTokenCount": 1},
            }}

        with mock.patch.object(providers, "_request", fake_request):
            adapter.complete([{"role": "user", "content": "hi"}], **kwargs)
        return captured

    def test_none_temperature_is_omitted_from_body(self) -> None:
        captured = self._run(self._adapter(), temperature=None,
                             max_tokens=2048, json_mode=True,
                             system="system instructions")
        generation = captured["body"]["generationConfig"]
        self.assertNotIn("temperature", generation)
        self.assertEqual(generation,
                         {"maxOutputTokens": 2048,
                          "responseMimeType": "application/json"})
        self.assertIn("systemInstruction", captured["body"])

    def test_explicit_temperature_is_still_forwarded_when_requested(self) -> None:
        captured = self._run(self._adapter(), temperature=0.2, max_tokens=64)
        self.assertEqual(captured["body"]["generationConfig"]["temperature"], 0.2)


class GatedExecutionTests(BaseCase):
    def _authorization(self, plan: dict) -> dict:
        return {
            "approved": True,
            "approved_by": "unit-test",
            "provider": plan["provider"],
            "model": plan["model"],
            "request_sha256": plan["request"]["request_sha256"],
        }

    def test_execution_refuses_without_authorization(self) -> None:
        result = provider_validation.execute_live_validation()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "BLOCKED_AUTHORIZATION_MISSING")
        self.assertEqual(result["network_calls"], 0)

    def test_execution_refuses_wrong_hash(self) -> None:
        plan = provider_validation.plan_live_validation()
        authorization = self._authorization(plan)
        authorization["request_sha256"] = "0" * 64
        result = provider_validation.execute_live_validation(
            authorization=authorization)
        self.assertEqual(result["status"], "AUTHORIZATION_REQUEST_MISMATCH")
        self.assertEqual(result["network_calls"], 0)

    def test_execution_refuses_without_credential(self) -> None:
        plan = provider_validation.plan_live_validation()
        result = provider_validation.execute_live_validation(
            authorization=self._authorization(plan))
        self.assertEqual(result["status"], "BLOCKED_CREDENTIAL_NOT_CONFIGURED")
        self.assertEqual(result["network_calls"], 0)

    def test_mocked_adapter_success_is_validated_and_recorded(self) -> None:
        self.configure_dummy_credential()

        class FakeAdapter:
            def complete(self, messages, **kwargs):
                self.kwargs = kwargs
                return {
                    "text": json.dumps(fixture_payload()),
                    "usage": {"prompt_tokens": 120, "completion_tokens": 480,
                              "total_tokens": 600},
                    "model": "gemini-3.8-flash",
                    "raw_meta": {"finish_reason": "STOP"},
                }

        adapter = FakeAdapter()
        with mock.patch.object(provider_validation.llm_providers, "build",
                               return_value=adapter):
            plan = provider_validation.plan_live_validation()
            result = provider_validation.execute_live_validation(
                authorization=self._authorization(plan))
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["status"], "LIVE_REQUEST_COMPLETED")
        self.assertEqual(result["network_calls"], 1)
        self.assertEqual(result["retries"], 0)
        self.assertTrue(result["schema_validation"]["valid"])
        self.assertEqual(result["usage"]["total_tokens"], 600)
        self.assertEqual(result["usage"]["source"], "provider")
        self.assertEqual(adapter.kwargs["max_tokens"], 2048)
        self.assertTrue(adapter.kwargs["json_mode"])
        self.assertIsNone(adapter.kwargs["temperature"])
        self.assertFalse(result["secrets_recorded"])
        self.assertEqual(result["quota_after"]["requests_today"], 1)

    def test_mocked_adapter_error_is_not_retried(self) -> None:
        self.configure_dummy_credential()

        class FailingAdapter:
            calls = 0

            def complete(self, messages, **kwargs):
                FailingAdapter.calls += 1
                raise providers.ProviderError("rate limited", kind="rate_limit",
                                              retryable=True, status=429)

        with mock.patch.object(provider_validation.llm_providers, "build",
                               return_value=FailingAdapter()):
            plan = provider_validation.plan_live_validation()
            result = provider_validation.execute_live_validation(
                authorization=self._authorization(plan))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "LIVE_REQUEST_FAILED")
        self.assertEqual(FailingAdapter.calls, 1)
        self.assertEqual(result["error"]["kind"], "rate_limit")
        self.assertFalse(result["error"]["retry_attempted"])
        self.assertTrue(result["fallback_used"])


class ResponseValidationTests(BaseCase):
    def test_malformed_and_non_object_output_is_invalid(self) -> None:
        broken = response_validation.validate_text("{not json", source="fixture")
        self.assertFalse(broken["schema_valid"])
        self.assertTrue(broken["errors"])
        scalar = response_validation.extract_json("[1, 2, 3]")
        self.assertFalse(scalar["ok"])

    def test_fixture_passes_schema(self) -> None:
        report = response_validation.validate_game_spec(
            fixture_payload(), source="offline_fixture")
        self.assertTrue(report["schema_valid"], report["errors"])
        self.assertEqual(report["missing_fields"], [])
        self.assertEqual(report["confidence"]["label"], "high")

    def test_missing_required_field_is_reported(self) -> None:
        payload = fixture_payload()
        payload.pop("audio_requirements")
        report = response_validation.validate_game_spec(payload)
        self.assertFalse(report["schema_valid"])
        self.assertIn("audio_requirements", report["missing_fields"])

    def test_wrong_type_is_rejected(self) -> None:
        payload = fixture_payload()
        payload["performance_targets"] = {"target_fps": "sixty"}
        report = response_validation.validate_game_spec(payload)
        self.assertFalse(report["schema_valid"])
        self.assertTrue(any("target_fps" in item or "performance_targets" in item
                            for item in report["errors"]))

    def test_contradiction_and_unsupported_claims_are_flagged(self) -> None:
        payload = fixture_payload()
        payload["dimension"] = "2d and 3d"
        payload["core_gameplay_loop"].append("Add online multiplayer and netcode")
        report = response_validation.validate_game_spec(payload)
        kinds = {item["kind"] for item in report["contradictions"]}
        self.assertIn("dimension", kinds)
        claims = {item["claim"] for item in report["unsupported_claims"]}
        self.assertIn("multiplayer", claims)
        self.assertTrue(all(item["auto_accepted"] is False
                            for item in report["unsupported_claims"]))

    def test_ambiguous_acceptance_criteria_are_flagged(self) -> None:
        payload = fixture_payload()
        payload["acceptance_criteria"].append("The level should feel fun and polished")
        report = response_validation.validate_game_spec(payload)
        self.assertTrue(report["ambiguous_requirements"])

    def test_secret_redaction(self) -> None:
        secret = "sk-" + "A" * 24
        redacted = response_validation.redact_payload(
            {"note": f"key={secret}", "nested": [f"Bearer abcdefghijklmnop"]})
        text = json.dumps(redacted)
        self.assertNotIn(secret, text)
        self.assertIn("[REDACTED]", text)


class QualityEvaluationTests(BaseCase):
    def test_rubric_has_ten_categories_and_a_bounded_total(self) -> None:
        report = quality_evaluation.evaluate(fixture_payload(),
                                             source="offline_fixture")
        self.assertEqual(len(report["scores"]), 10)
        self.assertEqual(report["max_score"], 100)
        self.assertGreaterEqual(report["total_score"], 0)
        self.assertLessEqual(report["total_score"], 100)
        self.assertTrue(report["requires_human_review"])
        self.assertFalse(report["human_approved"])
        self.assertFalse(report["general_intelligence_claimed"])
        for category in report["scores"]:
            self.assertIn("method", category)
            self.assertIn("evidence", category)
            self.assertLessEqual(category["score"], category["max"])

    def test_good_fixture_scores_higher_than_a_minimal_payload(self) -> None:
        strong = quality_evaluation.evaluate(fixture_payload())
        minimal = quality_evaluation.evaluate({
            "game_title": "Empty",
            "genre": [],
            "target_platforms": [],
            "core_gameplay_loop": [],
            "player_mechanics": [],
            "camera_design": "",
            "environment_requirements": [],
            "collectibles": [],
            "hazards": [],
            "progression": [],
            "ui_requirements": [],
            "audio_requirements": [],
            "performance_targets": {},
            "technical_architecture": [],
            "asset_requirements": [],
            "acceptance_criteria": [],
            "risks": [],
            "unsupported_or_uncertain": [],
        })
        self.assertGreater(strong["total_score"], minimal["total_score"])
        self.assertEqual(minimal["grade"], "not_usable")


class SpecificationPipelineTests(BaseCase):
    def test_requirement_ids_are_stable_and_never_verified(self) -> None:
        idea = ("Create a third-person 3D jungle game where a monkey collects "
                "bananas and reaches a destination.")
        first = game_spec_pipeline.build_specification(idea)
        second = game_spec_pipeline.build_specification(idea)
        ids_a = [item["requirement_id"] for item in first["requirements"]]
        ids_b = [item["requirement_id"] for item in second["requirements"]]
        self.assertEqual(ids_a, ids_b)
        self.assertEqual(len(ids_a), len(set(ids_a)))
        for item in first["requirements"]:
            self.assertEqual(item["implementation_status"], "not_implemented")
            self.assertFalse(item["human_approved"])
            self.assertEqual(item["status"], "proposed")
            self.assertTrue(item["requirement_id"].startswith("REQ-"))
            for key in ("description", "category", "priority", "dependencies",
                        "acceptance_criteria", "required_assets", "target_engine",
                        "target_platforms", "verification_method", "provenance",
                        "confidence", "unsupported_assumptions"):
                self.assertIn(key, item)

    def test_ai_payload_changes_source_but_not_status(self) -> None:
        idea = "Create a third-person 3D jungle adventure for Windows and Android."
        spec = game_spec_pipeline.build_specification(
            idea, ai_payload=fixture_payload(), platforms=["windows", "android"])
        self.assertEqual(spec["source"], "ai_provider")
        self.assertTrue(spec["response_validation"]["schema_valid"])
        self.assertTrue(all(item["source"] == "ai_provider"
                            for item in spec["requirements"]))
        self.assertTrue(all(item["implementation_status"] == "not_implemented"
                            for item in spec["requirements"]))
        self.assertFalse(spec["ai_generated_asset"])
        self.assertFalse(spec["executable"])

    def test_invalid_ai_payload_is_refused(self) -> None:
        payload = fixture_payload()
        payload.pop("game_title")
        with self.assertRaises(ValueError):
            game_spec_pipeline.build_specification("A jungle game", ai_payload=payload)

    def test_spec_validation_rejects_tampering(self) -> None:
        spec = game_spec_pipeline.build_specification("A small jungle game")
        spec["requirements"][0]["implementation_status"] = "verified"
        spec["approval"]["approved"] = True
        spec["generation_plan"]["steps"][0]["executed"] = True
        report = game_spec_pipeline.validate_spec(spec)
        self.assertFalse(report["valid"])
        joined = " ".join(report["errors"])
        self.assertIn("verified", joined)
        self.assertIn("approval", joined)
        self.assertIn("executed", joined)

    def test_bridges_use_existing_phase3_and_phase4_builders(self) -> None:
        spec = game_spec_pipeline.build_specification(
            "Create a stylized 3D jungle game where a monkey collects bananas.")
        character = spec["bridges"]["character"]
        environment = spec["bridges"]["environment"]
        gameplay = spec["bridges"]["gameplay"]
        self.assertEqual(character_spec.validate_character_spec(character["spec"]), [])
        self.assertEqual(environment_spec.validate_environment_spec(environment["spec"]), [])
        for bridge in (character, environment, gameplay):
            self.assertFalse(bridge["ai_generated_asset"])
            self.assertFalse(bridge["phase5_project_modified"])
        self.assertFalse(gameplay["generated"])
        self.assertFalse(gameplay["build_started"])
        self.assertEqual(gameplay["phase5_interfaces"]["missing"], [])
        self.assertTrue(spec["bridges"]["character"]["requirement_ids"])
        self.assertIn("Assets/V6/Scripts/Player/PlayerMovement.cs",
                      gameplay["phase5_interfaces"]["interfaces"])

    def test_generation_plan_is_preview_only(self) -> None:
        spec = game_spec_pipeline.build_specification("A small jungle game")
        plan = spec["generation_plan"]
        self.assertFalse(plan["executable"])
        self.assertFalse(plan["executed"])
        self.assertFalse(plan["human_approved"])
        self.assertFalse(plan["asset_generation_performed"])
        self.assertFalse(plan["build_started"])
        self.assertTrue(plan["steps"])
        self.assertTrue(all(step["executed"] is False for step in plan["steps"]))
        self.assertTrue(all(step["requires_approval"] for step in plan["steps"]))


class McpIntegrationTests(BaseCase):
    def test_tool_and_handler_parity(self) -> None:
        declared = [tool["name"] for tool in server.TOOLS]
        handlers = list(server.HANDLERS)
        self.assertEqual(len(declared), 107)
        self.assertEqual(len(set(declared)), 107)
        self.assertEqual(set(declared), set(handlers))
        self.assertTrue(all(tool["inputSchema"]["type"] == "object"
                            for tool in server.TOOLS))

    def test_new_tools_are_offline_and_safe(self) -> None:
        readiness = server.tool_llm_provider_readiness({"provider": "gemini"})
        self.assertEqual(readiness["network_calls"], 0)
        plan = server.tool_llm_provider_validate({"mode": "plan"})
        self.assertEqual(plan["network_calls"], 0)
        self.assertIn("audit_record", plan)
        refusal = server.tool_llm_provider_validate({"mode": "execute"})
        self.assertEqual(refusal["network_calls"], 0)

    def test_spec_and_quality_tools_round_trip(self) -> None:
        spec = server.tool_llm_game_spec_generate(
            {"idea": "Create a 3D jungle game where a monkey collects bananas."})
        validation = server.tool_llm_game_spec_validate({"spec": spec})
        self.assertTrue(validation["ok"])
        quality = server.tool_llm_game_quality_evaluate({"spec": spec})
        self.assertEqual(len(quality["scores"]), 10)
        preview = server.tool_llm_generation_plan_preview(
            {"idea": "Create a 3D jungle game where a monkey collects bananas."})
        self.assertFalse(preview["executed"])


class PreservationTests(BaseCase):
    def test_protected_artifacts_match_phase6_evidence(self) -> None:
        evidence = json.loads(
            (REPO / "reports" / "v6-phase6-audit.json").read_text(encoding="utf-8"))
        preservation = evidence["preservation"]
        for group in ("v4", "v5"):
            for relative, record in preservation[group].items():
                path = REPO / relative
                self.assertTrue(path.is_file(), relative)
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(actual, record["expected"], relative)

    def test_free_policy_still_refuses_paid_and_unknown(self) -> None:
        self.assertFalse(free_policy.is_free_status("paid"))
        self.assertFalse(free_policy.is_free_status("unknown"))
        self.assertFalse(free_policy.model_eligibility(
            "gemini", "gemini-4-argon")["eligible"])
        self.assertFalse(free_policy.model_eligibility(
            "unknown-provider", "anything")["eligible"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
