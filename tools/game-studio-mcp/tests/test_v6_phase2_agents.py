"""V6 Phase 2 agent contract and specialist agent tests.

All work here is deterministic and offline. Nothing in this file is a live
provider verification, a generated asset or a built game.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import understanding  # noqa: E402
from game_studio.agents import registry  # noqa: E402
from game_studio.agents.base import Agent  # noqa: E402
from game_studio.agents.character import CharacterAgent  # noqa: E402
from game_studio.agents.context import ProjectContext  # noqa: E402
from game_studio.agents.contract import (  # noqa: E402
    AgentError, AgentSpec, COMPLETED, FAILED, STATES,
    validate_agent_input, validate_agent_output,
)
from game_studio.agents.environment import EnvironmentAgent  # noqa: E402
from game_studio.agents.game_designer import GameDesignerAgent  # noqa: E402
from game_studio.agents.game_director import GameDirectorAgent  # noqa: E402
from game_studio.agents.gameplay import GameplayAgent  # noqa: E402
from game_studio.agents.qa import QAAgent  # noqa: E402
from game_studio.agents.technical_architect import TechnicalArchitectAgent  # noqa: E402
from game_studio.agents.uiux import UIUXAgent  # noqa: E402
from game_studio.agents.workflow import (  # noqa: E402
    dependency_graph, parallel_groups, validate_graph,
)
from game_studio.agents.schemas import BRIEF_SCHEMA  # noqa: E402
from game_studio.llm.schemas import validate as schemas_validate  # noqa: E402

REQUEST = (
    "Create a professional 3D jungle adventure game for Windows PC. The player "
    "controls a monkey that can run, jump, and collect bananas. Include a detailed "
    "jungle environment, character assets, follow camera, score HUD, and restart "
    "functionality."
)

ENV_VALUES = {
    "GAME_STUDIO_HOME": "",
    "GAME_STUDIO_LLM_PROVIDER": "",
    "GAME_STUDIO_LLM_MODEL": "",
    "GAME_STUDIO_LLM_BASE_URL": "",
    "GAME_STUDIO_LLM_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
    "GAME_STUDIO_LLM_LOCAL_ONLY": "",
}


def demo_brief(**overrides) -> dict:
    analysis = understanding.analyze_request(REQUEST, installed_engines=["unity"])
    brief = GameDirectorAgent().create_brief(
        request=REQUEST, understanding=analysis, quality_target="prototype",
        installed_engines=["unity"])
    brief.update(overrides)
    return brief


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="game-studio-v6p2a-")
        self.addCleanup(self.temp.cleanup)
        values = dict(ENV_VALUES)
        values["GAME_STUDIO_HOME"] = os.path.join(self.temp.name, "home")
        env = mock.patch.dict(os.environ, values)
        env.start()
        self.addCleanup(env.stop)

    def context_with_outputs(self, *sections: str) -> ProjectContext:
        brief = demo_brief()
        ctx = ProjectContext(REQUEST, brief=brief)
        if "design" in sections:
            self._record(ctx, "design", GameDesignerAgent(), "Design")
        if "architecture" in sections:
            self._record(ctx, "architecture", TechnicalArchitectAgent(), "Architecture")
        if "gameplay" in sections:
            self._record(ctx, "gameplay", GameplayAgent(), "Gameplay")
        return ctx

    def _record(self, ctx: ProjectContext, name: str, agent: Agent,
                task_id: str) -> None:
        result = agent.run(task_id=task_id, context=ctx)
        self.assertEqual(result.status, COMPLETED, result.error)
        ctx.record(task_id=task_id, agent=agent.spec.id,
                   agent_version=agent.spec.version, section=name,
                   output=result.output or {}, evidence=result.evidence)


class RegistryTests(BaseCase):
    def test_eight_typed_agents_are_registered(self) -> None:
        specs = registry.specs()
        self.assertEqual(len(specs), 8)
        self.assertEqual(set(specs), {
            "game_director", "game_designer", "technical_architect", "character",
            "environment", "gameplay", "uiux", "qa",
        })
        for spec in specs.values():
            self.assertIsInstance(spec, AgentSpec)
            self.assertTrue(spec.id and spec.name and spec.version)
            self.assertTrue(spec.responsibility)
            self.assertTrue(spec.task_category)
            self.assertTrue(spec.required_capabilities)
            self.assertEqual(spec.input_schema["type"], "object")
            self.assertEqual(spec.output_schema["type"], "object")
            self.assertIn(spec.produces, ("brief", "design", "architecture",
                                          "character", "environment", "gameplay",
                                          "uiux", "qa", "consolidation"))

    def test_agent_versions_and_required_context(self) -> None:
        for spec in registry.specs().values():
            self.assertRegex(spec.version, r"^\d+\.\d+\.\d+$")
            self.assertIn("brief", spec.required_context)
            self.assertEqual(len(spec.required_context),
                             len(set(spec.required_context)))

    def test_registry_report_is_valid_and_documents_states(self) -> None:
        report = registry.registry_report()
        self.assertTrue(report["ok"], report["workflow"]["graph_errors"])
        self.assertEqual(report["agent_count"], 8)
        self.assertEqual(report["states"], list(STATES))
        self.assertIn("not", report["note"].lower())

    def test_unknown_agent_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            registry.get_agent("nonexistent_agent")


class WorkflowTests(BaseCase):
    def test_dependency_graph_has_no_errors(self) -> None:
        self.assertEqual(validate_graph(), [])
        graph = dependency_graph()
        self.assertEqual(graph["design"]["depends_on"], [])
        self.assertEqual(graph["architecture"]["depends_on"], ["design"])
        self.assertIn("architecture", graph["character"]["depends_on"])
        self.assertEqual(graph["consolidation"]["depends_on"], ["qa"])

    def test_parallel_groups_are_stable_and_dependency_safe(self) -> None:
        groups = parallel_groups()
        self.assertEqual(groups, [["design"], ["architecture"],
                                  ["character", "environment", "gameplay"],
                                  ["uiux"], ["qa"], ["consolidation"]])
        seen: set[str] = set()
        for group in groups:
            for task_id in group:
                for dep in dependency_graph()[task_id]["depends_on"]:
                    self.assertIn(dep, seen, f"{task_id} ran before {dep}")
            seen.update(group)
        self.assertEqual(seen, set(dependency_graph()))

    def test_every_task_has_a_registered_agent(self) -> None:
        specs = registry.specs()
        for task_id, node in dependency_graph().items():
            self.assertIn(node["agent"], specs, task_id)
            self.assertTrue(node["section"])


class BriefTests(BaseCase):
    def test_brief_is_schema_valid_and_trustworthy(self) -> None:
        brief = demo_brief()
        self.assertEqual(validate_agent_input(GameDesignerAgent.spec, {
            "request": REQUEST, "context_sources": {}, "brief": brief}), [])
        self.assertEqual(schemas_validate(BRIEF_SCHEMA, brief), [])
        self.assertEqual(brief["characters"], ["monkey"])
        self.assertEqual(brief["environment"], ["jungle"])
        self.assertEqual(brief["dimension"], ["3d"])
        self.assertIn("pc", brief["platform"])
        self.assertIn("collectibles", brief["mechanics"])
        self.assertNotIn("executable", brief)
        self.assertTrue(brief["requirements"])
        self.assertTrue(all(item.get("id") for item in brief["requirements"]))

    def test_brief_rejects_malformed_understanding(self) -> None:
        with self.assertRaises(ValueError):
            GameDirectorAgent().create_brief(
                request=REQUEST, understanding={"summary": 5}, quality_target="prototype")

    def test_brief_quality_target_is_preserved(self) -> None:
        analysis = understanding.analyze_request(REQUEST, installed_engines=["unity"])
        brief = GameDirectorAgent().create_brief(
            request=REQUEST, understanding=analysis, quality_target="high",
            installed_engines=["unity"])
        self.assertEqual(brief["quality_target"], "high")


class ContractTests(BaseCase):
    def test_input_schema_rejects_missing_request(self) -> None:
        spec = GameDesignerAgent.spec
        errors = validate_agent_input(spec, {"context_sources": {}})
        self.assertTrue(any("request" in error for error in errors))

    def test_output_schema_rejects_malformed_payloads(self) -> None:
        spec = GameDesignerAgent.spec
        self.assertTrue(validate_agent_output(spec, ["not", "an", "object"]))
        self.assertTrue(validate_agent_output(spec, {"summary": "incomplete"}))

    def test_agent_rejects_invalid_executor_output(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())
        agent = GameDesignerAgent()
        result = agent.run(task_id="design", context=ctx,
                           executor=lambda spec, data, decision: {"summary": "only a summary"})
        self.assertEqual(result.status, FAILED)
        self.assertEqual((result.error or {})["kind"], "output-validation")
        self.assertTrue(result.output_validation)
        self.assertFalse(result.to_dict()["validation"]["output_valid"])

    def test_agent_rejects_non_object_executor_output(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())
        result = GameDesignerAgent().run(
            task_id="design", context=ctx,
            executor=lambda spec, data, decision: "free text reply")
        self.assertEqual(result.status, FAILED)
        self.assertTrue(any("JSON object" in error
                            for error in result.output_validation))

    def test_agent_maps_typed_error_without_success(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())

        def boom(spec, data, decision):
            raise AgentError("provider refused", kind="provider", retryable=True)

        result = GameDesignerAgent().run(task_id="design", context=ctx, executor=boom)
        self.assertEqual(result.status, FAILED)
        self.assertTrue((result.error or {})["retryable"])
        self.assertEqual((result.error or {})["kind"], "provider")

    def test_agent_maps_unexpected_exception(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())
        result = GameDesignerAgent().run(
            task_id="design", context=ctx,
            executor=lambda spec, data, decision: (_ for _ in ()).throw(
                RuntimeError("kaboom")))
        self.assertEqual(result.status, FAILED)
        self.assertEqual((result.error or {})["kind"], "internal")

    def test_mocked_executor_is_never_live_verification(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())
        output = GameDesignerAgent().deterministic_output(
            ctx.scoped(("brief",)))
        result = GameDesignerAgent().run(
            task_id="design", context=ctx,
            executor=lambda spec, data, decision: {"output": output,
                                                   "provider": "ollama",
                                                   "model": "local"},
            routing_decision={"mode": "provider",
                              "selected": {"provider": "ollama", "model": "local"},
                              "constraints": {"network_calls": 1}})
        self.assertEqual(result.status, COMPLETED)
        self.assertEqual(result.provider["mode"], "mocked")
        self.assertFalse(result.provider["live_verified"])
        self.assertNotEqual(result.provider.get("mode"), "live")


class ContextIsolationTests(BaseCase):
    def test_agents_receive_only_declared_sections(self) -> None:
        ctx = self.context_with_outputs("design", "architecture", "gameplay")
        design_view = ctx.scoped(GameDesignerAgent.spec.required_context)
        self.assertIn("brief", design_view)
        self.assertNotIn("architecture", design_view)
        self.assertNotIn("gameplay", design_view)
        qa_view = ctx.scoped(QAAgent.spec.required_context)
        self.assertIn("gameplay", qa_view)
        self.assertNotIn("character", qa_view)

    def test_scoped_copy_cannot_mutate_shared_context(self) -> None:
        ctx = self.context_with_outputs("design")
        view = ctx.scoped(("design",))
        view["design"]["summary"] = "tampered"
        self.assertNotEqual(ctx.get("design")["summary"], "tampered")
        self.assertIn("history", ctx.snapshot())

    def test_provenance_records_source_agent_and_version(self) -> None:
        ctx = self.context_with_outputs("design")
        provenance = ctx.snapshot()["provenance"]["design"]
        self.assertEqual(provenance["agent"], "game_designer")
        self.assertEqual(provenance["agent_version"], GameDesignerAgent.spec.version)
        self.assertEqual(provenance["task_id"], "Design")
        history = ctx.snapshot()["history"]
        self.assertEqual(history[-1]["agent"], "game_designer")

    def test_scoped_context_includes_approved_decisions(self) -> None:
        decisions = [{"id": "D-1", "statement": "Windows PC only"}]
        ctx = ProjectContext(REQUEST, brief=demo_brief(), approved_decisions=decisions)
        view = ctx.scoped(("brief",))
        self.assertEqual(view["approved_decisions"], decisions)


class AgentOutputTests(BaseCase):
    def run_agent(self, agent: Agent, task_id: str,
                  ctx: ProjectContext) -> dict:
        result = agent.run(task_id=task_id, context=ctx)
        self.assertEqual(result.status, COMPLETED, result.error)
        self.assertEqual(result.output_validation, [])
        self.assertTrue(result.evidence)
        self.assertEqual(result.provider["mode"], "deterministic")
        self.assertFalse(result.provider["live_verified"])
        self.assertGreaterEqual(result.duration_ms, 0)
        return result.output

    def test_game_designer_output(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())
        output = self.run_agent(GameDesignerAgent(), "design", ctx)
        self.assertEqual(schemas_validate(output, GameDesignerAgent.spec.output_schema), [])
        self.assertTrue(output["core_loop"])
        self.assertTrue(output["acceptance_tests"])
        self.assertIn("collectibles", output["mechanics"])
        self.assertTrue(output["requirements_addressed"])

    def test_technical_architect_prefers_detected_unity(self) -> None:
        ctx = self.context_with_outputs("design")
        output = self.run_agent(TechnicalArchitectAgent(), "architecture", ctx)
        self.assertEqual(output["engine"]["name"], "unity")
        self.assertTrue(output["engine"]["installed"])
        self.assertIn("Level_Jungle", output["architecture"]["scenes"])
        self.assertLessEqual(output["performance"]["budget"]["max_draw_calls"], 300)
        self.assertTrue(output["engine"]["unsupported_features"] == [])

    def test_technical_architect_marks_undetected_engine(self) -> None:
        brief = demo_brief(installed_engines=[])
        ctx = ProjectContext(REQUEST, brief=brief)
        self._record(ctx, "design", GameDesignerAgent(), "Design")
        output = self.run_agent(TechnicalArchitectAgent(), "architecture", ctx)
        self.assertFalse(output["engine"]["installed"])
        self.assertTrue(any("not detected" in risk for risk in output["risks"]))

    def test_character_plan_never_claims_generation(self) -> None:
        ctx = self.context_with_outputs("design")
        self._record(ctx, "architecture", TechnicalArchitectAgent(), "Architecture")
        output = self.run_agent(CharacterAgent(), "character", ctx)
        self.assertFalse(output["assets_generated"])
        self.assertFalse(output["textures_generated"])
        character = output["characters"][0]
        self.assertEqual(character["name"], "monkey")
        self.assertEqual(character["status"], "planned-not-generated")
        self.assertEqual(character["textures"]["status"], "planned-not-generated")
        self.assertIn("normal", character["textures"]["maps"])
        self.assertEqual(character["rig"]["status"], "planned-not-generated")
        self.assertTrue(output["capability_gaps"])

    def test_character_excludes_swimming_animation(self) -> None:
        brief = demo_brief(
            mechanics=["jumping", "collectibles", "score", "swimming"],
            exclusions=[{"category": "mechanic", "value": "swimming"}])
        ctx = ProjectContext(REQUEST, brief=brief)
        self._record(ctx, "design", GameDesignerAgent(), "Design")
        self._record(ctx, "architecture", TechnicalArchitectAgent(), "Architecture")
        output = self.run_agent(CharacterAgent(), "character", ctx)
        animations = output["characters"][0]["rig"]["animations"]
        self.assertNotIn("swim", animations)
        self.assertIn("jump", animations)

    def test_environment_plan_respects_budget_and_is_not_generated(self) -> None:
        ctx = self.context_with_outputs("design")
        self._record(ctx, "architecture", TechnicalArchitectAgent(), "Architecture")
        output = self.run_agent(EnvironmentAgent(), "environment", ctx)
        self.assertFalse(output["generated"])
        self.assertEqual(output["environment"], "jungle")
        self.assertTrue(output["estimates"]["within_budget"])
        self.assertFalse(output["water"]["present"])
        self.assertTrue(output["performance_risks"])

    def test_gameplay_plan_has_systems_and_tests(self) -> None:
        ctx = self.context_with_outputs("design")
        self._record(ctx, "architecture", TechnicalArchitectAgent(), "Architecture")
        output = self.run_agent(GameplayAgent(), "gameplay", ctx)
        ids = {system["id"] for system in output["systems"]}
        self.assertIn("player-movement", ids)
        self.assertIn("follow-camera", ids)
        self.assertIn("restart", ids)
        for system in output["systems"]:
            self.assertTrue(system["acceptance_tests"])
        self.assertIn("collect-banana", {item["id"] for item in output["interactions"]})
        self.assertIn("planned, not executed", " ".join(output["risks"]))

    def test_uiux_plan_covers_hud_and_restart_flow(self) -> None:
        ctx = self.context_with_outputs("design", "gameplay")
        output = self.run_agent(UIUXAgent(), "uiux", ctx)
        screens = {screen["id"] for screen in output["screens"]}
        self.assertTrue({"main_menu", "game_hud", "pause", "game_over",
                         "settings"} <= screens)
        self.assertTrue(any("score" in item.lower() for item in output["hud"]))
        self.assertTrue(output["accessibility"])

    def test_qa_never_reports_verified_implementation(self) -> None:
        ctx = self.context_with_outputs("design", "architecture", "gameplay")
        self._record(ctx, "character", CharacterAgent(), "Character")
        self._record(ctx, "environment", EnvironmentAgent(), "Environment")
        self._record(ctx, "uiux", UIUXAgent(), "UIUX")
        output = self.run_agent(QAAgent(), "qa", ctx)
        self.assertEqual(output["verification_status"], "not-verified")
        self.assertEqual(output["coverage"]["missing"], [])
        self.assertEqual(output["coverage"]["addressed"],
                         output["coverage"]["requirements_total"])
        self.assertTrue(output["checks"])
        self.assertTrue(any(item["category"] == "asset-pipeline"
                            for item in output["conflicts"]))
        self.assertIn("not implementation verification", " ".join(output["risks"]))

    def test_director_consolidation_is_non_executable(self) -> None:
        ctx = self.context_with_outputs("design", "architecture", "gameplay")
        self._record(ctx, "character", CharacterAgent(), "Character")
        self._record(ctx, "environment", EnvironmentAgent(), "Environment")
        self._record(ctx, "uiux", UIUXAgent(), "UIUX")
        self._record(ctx, "qa", QAAgent(), "QA")
        output = self.run_agent(GameDirectorAgent(), "consolidation", ctx)
        self.assertFalse(output["executable"])
        self.assertEqual(output["implementation_status"], "planned-not-implemented")
        self.assertIn("dependency_graph", output)
        self.assertIn("parallel_groups", output)
        self.assertTrue(output["approval_required"])
        self.assertTrue(any("not a playable game" in risk.lower()
                            for risk in output["risks"]))


class FailureHandlingTests(BaseCase):
    def test_missing_output_is_a_validation_error(self) -> None:
        self.assertTrue(validate_agent_output(CharacterAgent.spec, None))
        ctx = ProjectContext(REQUEST, brief=None)
        view = ctx.scoped(CharacterAgent.spec.required_context)
        self.assertNotIn("design", view)
        self.assertEqual(view["request"], REQUEST)

    def test_empty_output_is_rejected_not_coerced(self) -> None:
        ctx = ProjectContext(REQUEST, brief=demo_brief())
        result = GameDesignerAgent().run(
            task_id="design", context=ctx,
            executor=lambda spec, data, decision: {})
        self.assertEqual(result.status, FAILED)
        self.assertTrue(result.output_validation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
