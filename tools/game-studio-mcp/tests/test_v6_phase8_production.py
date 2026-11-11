"""V6 Phase 8 production-readiness integration tests (offline only).

These tests exercise the existing Phase 0-7 implementation end to end with
deterministic inputs and mocked boundaries. No provider, credential, socket,
download, install, engine or build is used.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import character_spec, environment_spec, manifest, util  # noqa: E402
from game_studio.agents.coordinator import Orchestrator  # noqa: E402
from game_studio.agents.workflow import (  # noqa: E402
    dependency_graph, parallel_groups, validate_graph,
)
from game_studio.llm import (  # noqa: E402
    bounded_http, free_policy, game_spec_pipeline, intelligence, quota,
    response_validation,
)
from game_studio.llm import config as llm_config  # noqa: E402

import server  # noqa: E402

JUNGLE = ("Create a stylized 3D jungle adventure where a monkey collects "
          "bananas and reaches a temple.")
OPEN_WORLD = ("Create a 3D open world RPG with quests, inventory, combat "
              "and multiplayer.")
PUBLIC_IP = "93.184.216.34"


def fixture_payload() -> dict:
    """Small deterministic provider-shaped payload used only as a fixture."""
    design = intelligence.design(JUNGLE)
    return game_spec_pipeline.payload_from_design(design)


class SpecificationWorkflowTests(unittest.TestCase):
    def test_complete_natural_language_to_specification_workflow(self) -> None:
        spec = game_spec_pipeline.build_specification(JUNGLE)
        self.assertTrue(spec["ok"])
        self.assertEqual(spec["source"], "deterministic")
        self.assertTrue(spec["validation"]["valid"], spec["validation"]["errors"])
        self.assertGreaterEqual(len(spec["requirements"]), 20)
        self.assertEqual(len(spec["requirements"]),
                         len({item["requirement_id"] for item in spec["requirements"]}))
        self.assertEqual(spec["approval"]["status"], "HUMAN_REVIEW_REQUIRED")
        self.assertFalse(spec["approval"]["approved"])
        self.assertFalse(spec["executable"])
        self.assertFalse(spec["ai_generated_asset"])
        self.assertFalse(spec["generation_performed"])
        self.assertFalse(spec["phase5_project_modified"])
        self.assertEqual(spec["provenance"]["network_calls"], 0)
        self.assertFalse(spec["provenance"]["human_approved"])

        plan = spec["generation_plan"]
        self.assertFalse(plan["executable"])
        self.assertFalse(plan["executed"])
        self.assertFalse(plan["human_approved"])
        self.assertTrue(all(step["requires_approval"] for step in plan["steps"]))
        self.assertTrue(all(step["executed"] is False for step in plan["steps"]))
        declared = {tool["name"] for tool in server.TOOLS}
        for step in plan["steps"]:
            if step.get("tool"):
                self.assertIn(step["tool"], declared)

        self.assertEqual(set(spec["bridges"]), {"character", "environment", "gameplay"})
        self.assertEqual(
            character_spec.validate_character_spec(spec["bridges"]["character"]["spec"]), [])
        self.assertEqual(
            environment_spec.validate_environment_spec(spec["bridges"]["environment"]["spec"]), [])

    def test_multi_feature_requirements_are_unique_and_stable(self) -> None:
        first = game_spec_pipeline.build_specification(OPEN_WORLD)
        second = game_spec_pipeline.build_specification(OPEN_WORLD)
        ids_a = [item["requirement_id"] for item in first["requirements"]]
        ids_b = [item["requirement_id"] for item in second["requirements"]]
        self.assertTrue(ids_a)
        self.assertEqual(len(ids_a), len(set(ids_a)))
        self.assertEqual(ids_a, ids_b)
        self.assertTrue(first["validation"]["valid"])

    def test_provider_payload_provenance_is_explicit(self) -> None:
        payload = fixture_payload()
        spec = game_spec_pipeline.build_specification(JUNGLE, ai_payload=payload)
        self.assertEqual(spec["source"], "ai_provider")
        self.assertTrue(spec["response_validation"]["schema_valid"])
        provenance = spec["provenance"]
        self.assertIn("ai_provider", provenance["design_source"])
        self.assertTrue(provenance["provider_payload_used_for_design"])
        self.assertEqual(provenance["requirements_extraction"], "deterministic")
        self.assertIn("deterministic parser", provenance["requirements_source"])
        self.assertNotIn("provider payload validated by response_validation",
                         provenance["requirements_source"])
        self.assertTrue(all(item["extraction_source"].startswith("game_studio.understanding")
                            for item in spec["requirements"]))
        self.assertEqual(spec["provenance"]["network_calls"], 0)

    def test_requirement_dependencies_resolve_and_unknown_are_rejected(self) -> None:
        spec = game_spec_pipeline.build_specification(OPEN_WORLD)
        known = {item["requirement_id"] for item in spec["requirements"]}
        known.update(str(item["id"]) for item in spec["requirements"])
        for item in spec["requirements"]:
            for dependency in item["dependencies"]:
                self.assertIn(dependency, known)

        tampered = json.loads(json.dumps(spec))
        tampered["requirements"][0]["dependencies"] = ["REQ-DOES-NOT-EXIST"]
        report = game_spec_pipeline.validate_spec(tampered)
        self.assertFalse(report["valid"])
        self.assertIn("unknown id", " ".join(report["errors"]))

    def test_agent_orchestration_respects_dependency_order(self) -> None:
        result = Orchestrator(JUNGLE, installed_engines=["unity"]).run()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["executable"])
        self.assertEqual(len(result["tasks"]), len(dependency_graph()))
        self.assertEqual(validate_graph(), [])
        groups = parallel_groups()
        seen: set[str] = set()
        for group in groups:
            for task_id in group:
                self.assertTrue(set(dependency_graph()[task_id]["depends_on"]) <= seen)
            seen.update(group)
        self.assertEqual(seen, set(dependency_graph()))

    def test_gameplay_bridge_maps_to_real_phase5_interfaces(self) -> None:
        spec = game_spec_pipeline.build_specification(OPEN_WORLD)
        gameplay = spec["bridges"]["gameplay"]
        self.assertEqual(gameplay["phase5_interfaces"]["missing"], [])
        self.assertEqual(set(gameplay["phase5_interfaces"]["interfaces"]),
                         set(game_spec_pipeline.PHASE5_INTERFACES))
        for relative in game_spec_pipeline.PHASE5_INTERFACES:
            self.assertTrue((game_spec_pipeline.PHASE5_ROOT / relative).is_file())
        features = {item["feature"] for item in gameplay["unsupported_features"]}
        self.assertIn("multiplayer", features)
        self.assertIn("open_world", features)
        self.assertFalse(gameplay["generated"])
        self.assertFalse(gameplay["build_started"])
        self.assertFalse(gameplay["phase5_project_modified"])

    def test_invalid_provider_payload_is_refused(self) -> None:
        payload = fixture_payload()
        payload.pop("game_title")
        with self.assertRaises(ValueError):
            game_spec_pipeline.build_specification(JUNGLE, ai_payload=payload)

    def test_approval_boundary_cannot_be_bypassed(self) -> None:
        spec = game_spec_pipeline.build_specification(JUNGLE)
        spec["approval"]["approved"] = True
        spec["generation_plan"]["steps"][0]["executed"] = True
        report = game_spec_pipeline.validate_spec(spec)
        self.assertFalse(report["valid"])
        self.assertIn("approval", " ".join(report["errors"]))
        self.assertIn("executed", " ".join(report["errors"]))


class ProviderSafetyTests(unittest.TestCase):
    def test_free_only_eligibility_rejects_paid_and_paid_openrouter_variants(self) -> None:
        self.assertIs(free_policy.model_eligibility("gemini", "gemini-3.8-flash")["eligible"], True)
        self.assertIs(free_policy.model_eligibility("gemini", "gemini-4-argon")["eligible"], False)
        self.assertIs(free_policy.model_eligibility(
            "openrouter", "example/model")["eligible"], False)
        self.assertIs(free_policy.model_eligibility(
            "openrouter", "example/model:free")["eligible"], True)
        self.assertIsNone(free_policy.model_eligibility("unknown-provider", "x")["eligible"])

    def test_unknown_quota_is_not_unlimited_and_no_paid_fallback(self) -> None:
        decision = quota.can_request("gemini", "gemini-3.8-flash")
        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["quota_known"])
        self.assertIsNone(decision["remaining_today"])
        self.assertEqual(decision["kind"], "quota_unknown_not_unlimited")
        self.assertIn("not treated as unlimited", decision["reason"])
        self.assertIs(free_policy.is_free_status(free_policy.PAID), False)
        self.assertIs(free_policy.is_free_status(free_policy.TRIAL_ONLY), False)
        self.assertIs(free_policy.is_free_status(free_policy.UNKNOWN), False)

    def test_secret_redaction_and_manifest_secret_rejection(self) -> None:
        secret = "sk-" + "a" * 24
        redacted = llm_config.redact(f"provider failed with api_key={secret}")
        self.assertNotIn(secret, redacted)
        with self.assertRaises(util.ToolError):
            manifest._check_no_secrets({"api_key": "should-not-be-stored"})
        with self.assertRaises(util.ToolError):
            manifest._check_no_secrets({"note": f"token={secret}"})


class SecurityReliabilityTests(unittest.TestCase):
    def test_ssrf_private_ranges_and_path_traversal_are_blocked(self) -> None:
        private_cases = ("100.64.0.1", "fc00::1", "fe80::1", "::ffff:127.0.0.1")
        for address in private_cases:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            with mock.patch.object(util.socket, "getaddrinfo",
                                   return_value=[(family, socket.SOCK_STREAM, 6, "",
                                                  (address, 443, 0, 0))]):
                with self.assertRaises(util.ToolError):
                    util._validate_url("https://example.invalid/")
        with mock.patch.object(util.socket, "getaddrinfo",
                               return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                                              (PUBLIC_IP, 443))]):
            parsed = util._validate_url("https://example.invalid/")
        self.assertEqual(parsed.hostname, "example.invalid")
        with self.assertRaises(util.ToolError):
            util.safe_join(str(ROOT), "../escape.txt")

    def test_commands_run_without_a_shell(self) -> None:
        completed = mock.Mock(returncode=0, stdout="ok", stderr="")
        with mock.patch.object(util.subprocess, "run", return_value=completed) as run:
            result = util.run_command(["python", "-c", "print(1)"])
        self.assertTrue(result["ok"])
        kwargs = run.call_args.kwargs
        self.assertFalse(kwargs.get("shell", False))

    def test_partial_or_truncated_body_is_never_parsed_as_json(self) -> None:
        payload, parsed = bounded_http._decode_payload(
            b'{"candidates": [', {"Content-Type": "application/json"}, True)
        self.assertIsInstance(payload, str)
        self.assertFalse(parsed)
        payload, parsed = bounded_http._decode_payload(
            b'{"broken":', {"Content-Type": "application/json"}, False)
        self.assertIsInstance(payload, str)
        self.assertFalse(parsed)
        payload, parsed = bounded_http._decode_payload(
            b'{"ok": true}', {"Content-Type": "application/json"}, False)
        self.assertEqual(payload, {"ok": True})
        self.assertTrue(parsed)

    def test_bounded_transport_rejects_private_addresses(self) -> None:
        with self.assertRaises(Exception) as caught:
            bounded_http._reject_private([(socket.AF_INET, "127.0.0.1")])
        self.assertEqual(caught.exception.kind, "blocked_private_address")


class PlatformParityTests(unittest.TestCase):
    def test_mcp_tool_handler_parity(self) -> None:
        declared = [tool["name"] for tool in server.TOOLS]
        handlers = list(server.HANDLERS)
        self.assertEqual(len(declared), 107)
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(len(declared), len(handlers))
        self.assertEqual(set(declared), set(handlers))
        self.assertTrue(all(tool.get("inputSchema", {}).get("type") == "object"
                            for tool in server.TOOLS))

    def test_protected_v4_and_v5_artifacts_match_phase0_hashes(self) -> None:
        baseline = json.loads(
            (REPO / "reports" / "v6-phase0-baseline.json").read_text(encoding="utf-8"))
        checkpoint = baseline["v4_checkpoint"]
        self.assertTrue(checkpoint["commit_exists"])
        for relative, record in checkpoint["files"].items():
            actual = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, record["sha256"], relative)
        for relative, record in baseline["v5_checkpoint"]["artifacts"].items():
            actual = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, record["sha256"], relative)

    def test_phase_reports_parse_and_remain_passing(self) -> None:
        for name in ("v6-phase5-audit.json", "v6-phase6-audit.json",
                     "v6-phase7-audit.json"):
            payload = json.loads((REPO / "reports" / name).read_text(encoding="utf-8"))
            self.assertTrue(payload["all_criteria_passed"], name)
            self.assertIn(payload["verdict"], ("PASS", "PASS_AUTOMATED"), name)


if __name__ == "__main__":
    unittest.main()
