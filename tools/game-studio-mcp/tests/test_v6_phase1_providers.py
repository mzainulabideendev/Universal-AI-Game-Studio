"""V6 Phase 1 provider architecture tests.

Every provider request in this file is mocked. No network call, paid request,
Ollama install, model download or real credential is used. Tests never claim
that a mocked response is live provider verification.
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

from game_studio import secrets  # noqa: E402
from game_studio.llm import (  # noqa: E402
    capabilities, catalog, config as llm_config, providers, routing,
)
from game_studio.util import ToolError  # noqa: E402

import server  # noqa: E402


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="game-studio-v6p1-")
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

    def provider_cfg(self, name: str, *, key: str | None = "test-key-not-real",
                     model: str = "model-x") -> dict:
        return {
            "provider": name,
            "model": model,
            "base_url": {
                "openai": "https://api.openai.com/v1",
                "openai_compatible": "https://example.test/v1",
                "anthropic": "https://api.anthropic.com/v1",
                "gemini": "https://generativelanguage.googleapis.com/v1beta",
                "ollama": "http://127.0.0.1:11434",
            }[name],
            "api_key": key,
            "local_provider": name == "ollama",
            "key_required": name != "ollama",
        }


class CapabilityModelTests(BaseCase):
    def test_states_are_tri_state(self) -> None:
        self.assertEqual(set(capabilities.STATES),
                         {"supported", "unsupported", "unknown"})

    def test_provider_report_is_honest_about_unimplemented_features(self) -> None:
        report = capabilities.capability_report()
        self.assertEqual(report["network_calls"], 0)
        self.assertIsNone(report["live_verified"])
        by_name = {item["provider"]: item for item in report["providers"]}
        self.assertEqual(set(by_name), set(llm_config.PROVIDERS))
        for provider in by_name.values():
            caps = provider["capabilities"]
            self.assertEqual(caps["text_generation"], capabilities.SUPPORTED)
            self.assertEqual(caps["tool_calling"], capabilities.UNSUPPORTED)
            self.assertEqual(caps["vision"], capabilities.UNSUPPORTED)
            self.assertEqual(caps["streaming"], capabilities.UNSUPPORTED)
            self.assertEqual(caps["embeddings"], capabilities.UNSUPPORTED)
        self.assertEqual(by_name["anthropic"]["capabilities"]["structured_output"],
                         capabilities.UNSUPPORTED)
        self.assertEqual(by_name["openai"]["capabilities"]["structured_output"],
                         capabilities.SUPPORTED)

    def test_model_capabilities_default_to_unknown(self) -> None:
        model = capabilities.unknown_model_capabilities()
        for name in capabilities.MODEL_CAPABILITY_KEYS:
            self.assertEqual(model[name], capabilities.UNKNOWN)
        self.assertEqual(model["context_window"],
                         {"state": capabilities.UNKNOWN, "value": None})

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            capabilities.provider_profile("not-a-provider")


class ProviderDiscoveryTests(BaseCase):
    def test_openai_style_model_list_is_get_and_normalised(self) -> None:
        captured = {}

        def fake_http(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {"ok": True, "status": 200, "payload": {
                "data": [{"id": "model-a", "created": 1, "owned_by": "org"},
                         {"id": "model-b"}]}}

        with mock.patch.object(providers, "http_request", side_effect=fake_http):
            result = providers.build(self.provider_cfg("openai_compatible")).list_models()

        self.assertEqual(captured["method"], "GET")
        self.assertTrue(captured["url"].endswith("/models"))
        self.assertEqual(result["count"], 2)
        self.assertEqual([m["id"] for m in result["models"]], ["model-a", "model-b"])
        self.assertFalse(result["capability_metadata_exposed"])
        for model in result["models"]:
            self.assertEqual(model["capabilities"]["tool_calling"],
                             capabilities.UNKNOWN)

    def test_anthropic_uses_documented_models_endpoint_and_auth_header(self) -> None:
        captured = {}

        def fake_http(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {"ok": True, "status": 200, "payload": {
                "data": [{"id": "claude-x", "display_name": "Claude X",
                          "type": "model"}]}}

        with mock.patch.object(providers, "http_request", side_effect=fake_http):
            result = providers.build(self.provider_cfg("anthropic")).list_models()

        self.assertTrue(captured["url"].endswith("/models?limit=100"))
        self.assertEqual(captured["headers"].real_headers().get("x-api-key"),
                         "test-key-not-real")
        self.assertEqual(result["models"][0]["name"], "Claude X")
        self.assertEqual(result["models"][0]["capabilities"]["structured_output"],
                         capabilities.UNKNOWN)

    def test_gemini_documented_metadata_sets_only_supported_fields(self) -> None:
        def fake_http(url, **kwargs):
            return {"ok": True, "status": 200, "payload": {"models": [
                {"name": "models/gemini-x", "displayName": "Gemini X",
                 "inputTokenLimit": 1000,
                 "supportedGenerationMethods": ["generateContent"]},
            ]}}

        with mock.patch.object(providers, "http_request", side_effect=fake_http):
            result = providers.build(self.provider_cfg("gemini")).list_models()

        model = result["models"][0]
        self.assertEqual(model["id"], "gemini-x")
        self.assertEqual(model["capabilities"]["text_generation"],
                         capabilities.SUPPORTED)
        self.assertEqual(model["capabilities"]["context_window"],
                         {"state": "supported", "value": 1000})
        self.assertEqual(model["capabilities"]["vision"], capabilities.UNKNOWN)
        self.assertEqual(model["capabilities"]["tool_calling"], capabilities.UNKNOWN)

    def test_ollama_uses_loopback_tags_and_never_assumes_capabilities(self) -> None:
        captured = {}

        def fake_http(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {"ok": True, "status": 200, "payload": {"models": [
                {"name": "llama3.1:latest", "model": "llama3.1:latest",
                 "modified_at": "2026-01-01", "size": 10,
                 "details": {"family": "llama", "parameter_size": "8B"}},
            ]}}

        with mock.patch.object(providers, "http_request", side_effect=fake_http):
            result = providers.build(self.provider_cfg("ollama", key=None)).list_models()

        self.assertTrue(captured["url"].endswith("/api/tags"))
        self.assertTrue(captured["allow_local"])
        model = result["models"][0]
        self.assertEqual(model["id"], "llama3.1:latest")
        self.assertEqual(model["capabilities"]["structured_output"],
                         capabilities.UNKNOWN)
        self.assertFalse(result["capability_metadata_exposed"])

    def test_unknown_listing_shape_is_an_error_not_a_fake_success(self) -> None:
        with mock.patch.object(providers, "http_request",
                               return_value={"ok": True, "status": 200,
                                             "payload": {"unexpected": []}}):
            with self.assertRaises(providers.ProviderError) as caught:
                providers.build(self.provider_cfg("openai")).list_models()
        self.assertEqual(caught.exception.kind, "invalid_response")


class DiscoveryWorkflowTests(BaseCase):
    def test_hosted_discovery_without_credential_makes_no_request(self) -> None:
        with mock.patch.object(providers, "http_request") as http:
            result = catalog.discover_models("openai", confirm=True)
        http.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "unavailable")
        self.assertIn("credential", result["remediation"].lower())
        self.assertTrue(result["deterministic_fallback"]["available"])

    def test_discovery_requires_confirmation_before_any_request(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        with mock.patch.object(providers, "http_request") as http:
            with self.assertRaises(ToolError):
                catalog.discover_models("openai", confirm=False)
        http.assert_not_called()

    def test_auth_failure_is_reported_without_secret_leak(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        with mock.patch.object(providers, "http_request", return_value={
                "ok": False, "status": 401,
                "payload": {"error": {"message": "bad sk-abcdefghijklmnop"}}}):
            result = catalog.discover_models("openai", confirm=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "auth")
        self.assertNotIn("sk-abcdefghijklmnop", json.dumps(result))
        self.assertIn("credential", result["remediation"].lower())

    def test_ollama_unavailable_explains_without_installing(self) -> None:
        with mock.patch.object(providers, "http_request", return_value={
                "ok": False, "status": None, "error": "connection refused"}):
            result = catalog.discover_models("ollama", confirm=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["reachable"])
        self.assertEqual(result["mode"], "unavailable")
        self.assertIn("ollama", result)
        self.assertFalse(result["ollama"]["started"])
        self.assertIn("ollama", result["remediation"].lower())

    def test_successful_mocked_listing_is_labelled_live_but_is_test_only(self) -> None:
        os.environ["GEMINI_API_KEY"] = "test-key-not-real"
        with mock.patch.object(providers, "http_request", return_value={
                "ok": True, "status": 200,
                "payload": {"models": [{"name": "models/gemini-x",
                                        "supportedGenerationMethods": ["generateContent"]}]}}):
            result = catalog.discover_models("gemini", confirm=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "live")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["models"][0]["capabilities"]["tool_calling"],
                         capabilities.UNKNOWN)


class ConfigurationAndSecretTests(BaseCase):
    def test_provider_selection_is_private_config_without_credentials(self) -> None:
        result = llm_config.save_provider_selection(
            "ollama", model="llama3.1", base_url="http://127.0.0.1:11434",
            confirm=True)
        self.assertTrue(result["ok"])
        path = os.path.join(self.home, "llm.json")
        self.assertTrue(os.path.isfile(path))
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(stored["provider"], "ollama")
        self.assertEqual(stored["model"], "llama3.1")
        self.assertNotIn("api_key", stored)
        self.assertNotIn("test-key", json.dumps(stored))

    def test_hosted_http_endpoint_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            llm_config.save_provider_selection(
                "openai", base_url="http://api.example.test/v1", confirm=True)

    def test_unknown_provider_selection_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            llm_config.save_provider_selection("nope", confirm=True)

    def test_provider_config_does_not_reuse_another_providers_endpoint(self) -> None:
        llm_config.save_provider_selection(
            "ollama", model="local-model", base_url="http://127.0.0.1:11434",
            confirm=True)
        os.environ["GAME_STUDIO_LLM_BASE_URL"] = "https://custom.example/v1"
        os.environ["GAME_STUDIO_LLM_PROVIDER"] = "ollama"
        cfg = llm_config.provider_config("openai")
        self.assertEqual(cfg["provider"], "openai")
        self.assertEqual(cfg["base_url"], "https://api.openai.com/v1")

    def test_credential_is_stored_privately_and_never_returned(self) -> None:
        result = server.tool_llm_configure_credential({
            "provider": "openai", "api_key": "sk-phase1-secret-value",
            "confirm": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["api_key"], "[REDACTED]")
        self.assertNotIn("sk-phase1-secret-value", json.dumps(result))
        path = secrets.llm_key_file()
        self.assertTrue(os.path.isfile(path))
        self.assertIn("sk-phase1-secret-value",
                      Path(path).read_text(encoding="utf-8"))
        self.assertEqual(secrets.load_local_llm_key("openai"),
                         "sk-phase1-secret-value")
        self.assertEqual(llm_config.provider_config("openai")["key_source"],
                         "local-file")

    def test_environment_overrides_local_credential(self) -> None:
        secrets.save_llm_key("openai", "sk-local-secret-value")
        os.environ["OPENAI_API_KEY"] = "sk-env-secret-value"
        self.assertEqual(llm_config.provider_config("openai")["api_key"],
                         "sk-env-secret-value")
        self.assertEqual(secrets.llm_key_source("openai"), "OPENAI_API_KEY")

    def test_clearing_credential_updates_status(self) -> None:
        secrets.save_llm_key("openai", "sk-local-secret-value")
        result = server.tool_llm_configure_credential({
            "provider": "openai", "action": "clear", "confirm": True})
        self.assertTrue(result["removed"])
        self.assertIsNone(secrets.load_local_llm_key("openai"))
        self.assertFalse(llm_config.provider_config("openai")["api_key"])

    def test_credential_configuration_requires_confirmation(self) -> None:
        with self.assertRaises(ToolError):
            server.tool_llm_configure_credential({
                "provider": "openai", "api_key": "sk-phase1-secret-value"})


class RoutingTests(BaseCase):
    def test_missing_ollama_runtime_is_not_selected_automatically(self) -> None:
        with mock.patch.object(routing.shutil, "which", return_value=None):
            result = routing.route("game_design_reasoning")
        self.assertEqual(result["mode"], "deterministic")
        self.assertIsNone(result["selected"])
        ollama = next(c for c in result["candidates"] if c["provider"] == "ollama")
        self.assertIn("not installed", " ".join(ollama["blockers"]))
        self.assertFalse(result["live_verified"])
        self.assertEqual(result["network_calls"], 0)

    def test_installed_local_ollama_is_preferred_without_a_credential(self) -> None:
        with mock.patch.object(routing.shutil, "which",
                               return_value="C:/fake/ollama.exe"):
            result = routing.route("game_design_reasoning")
        self.assertEqual(result["mode"], "provider")
        self.assertEqual(result["selected"]["provider"], "ollama")
        self.assertEqual(result["selected"]["kind"], "local")
        self.assertFalse(result["live_verified"])
        self.assertEqual(result["network_calls"], 0)

    def test_known_unsupported_capability_blocks_every_provider(self) -> None:
        result = routing.route("asset_analysis", required_capabilities=["vision"])
        self.assertEqual(result["mode"], "deterministic")
        self.assertIsNone(result["selected"])
        for candidate in result["candidates"]:
            self.assertIn("required capability 'vision' is unsupported",
                          candidate["blockers"])

    def test_unknown_capability_is_labelled_or_rejected_when_required(self) -> None:
        relaxed = routing.route("code_generation",
                                required_capabilities=["context_window"])
        ollama = next(c for c in relaxed["candidates"] if c["provider"] == "ollama")
        self.assertIn("'context_window' is unknown",
                      " ".join(ollama["warnings"]))
        strict = routing.route("code_generation",
                               required_capabilities=["context_window"],
                               require_known=True)
        self.assertEqual(strict["mode"], "deterministic")

    def test_hosted_provider_is_never_selected_without_allow_paid(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        result = routing.route("game_design_reasoning", provider="openai")
        self.assertEqual(result["mode"], "deterministic")
        self.assertIsNone(result["selected"])
        self.assertIn("allow_paid is false",
                      " ".join(result["explanation"]))
        self.assertFalse(result["fallback_plan"]["auto_switch"])
        self.assertFalse(result["fallback_plan"]["paid_switch"])

    def test_explicit_approval_allows_a_hosted_provider(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        result = routing.route("game_design_reasoning", provider="openai",
                               allow_paid=True)
        self.assertEqual(result["mode"], "provider")
        self.assertEqual(result["selected"]["provider"], "openai")
        self.assertTrue(result["constraints"]["max_tokens_per_request"] > 0)

    def test_anthropic_is_rejected_for_structured_output_task(self) -> None:
        os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
        result = routing.route("game_design_reasoning", provider="anthropic",
                               allow_paid=True)
        self.assertEqual(result["mode"], "deterministic")
        self.assertIn("structured_output",
                      " ".join(result["candidates"][0]["blockers"]))

    def test_model_not_in_discovered_list_is_rejected(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        result = routing.route(
            "game_design_reasoning", provider="openai", model="missing-model",
            allow_paid=True,
            discovered={"openai": [{"id": "other-model"}]})
        self.assertEqual(result["mode"], "deterministic")
        self.assertIn("not present in the discovered model list",
                      " ".join(result["candidates"][0]["blockers"]))

    def test_context_budget_is_enforced(self) -> None:
        result = routing.route("code_generation", provider="ollama",
                               context_chars=10_000_000)
        self.assertEqual(result["mode"], "deterministic")
        self.assertIn("context", " ".join(result["candidates"][0]["blockers"]).lower())

    def test_output_token_budget_is_enforced(self) -> None:
        result = routing.route("code_generation", provider="ollama",
                               max_tokens=999_999)
        self.assertEqual(result["mode"], "deterministic")

    def test_unknown_task_without_capabilities_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            routing.route("not-a-task")

    def test_invalid_capability_name_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            routing.route("code_generation", required_capabilities=["telepathy"])

    def test_routing_matrix_contacts_nothing(self) -> None:
        matrix = routing.routing_matrix()
        self.assertEqual(matrix["network_calls"], 0)
        self.assertEqual(len(matrix["rows"]), len(capabilities.TASK_CATEGORIES))


class ToolRegistrationTests(BaseCase):
    def test_phase1_tools_are_registered_with_handlers_and_schemas(self) -> None:
        names = [tool["name"] for tool in server.TOOLS]
        for name in ("llm_provider_capabilities", "llm_list_models", "llm_route",
                     "llm_configure_provider", "llm_configure_credential"):
            self.assertIn(name, names)
            self.assertIn(name, server.HANDLERS)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(server.TOOLS), len(server.HANDLERS))
        for tool in server.TOOLS:
            self.assertEqual(tool["inputSchema"].get("type"), "object")

    def test_capability_tool_makes_no_network_call(self) -> None:
        with mock.patch.object(providers, "http_request") as http:
            result = server.tool_llm_provider_capabilities({})
        http.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["network_calls"], 0)

    def test_route_tool_makes_no_network_call(self) -> None:
        with mock.patch.object(providers, "http_request") as http:
            result = server.tool_llm_route({"task": "code_generation"})
        http.assert_not_called()
        self.assertEqual(result["network_calls"], 0)


if __name__ == "__main__":
    unittest.main()
