"""V6 Phase 2 coordinator tests.

Every provider interaction in this file is mocked, offline and explicitly
labelled. No live provider, engine, Blender or paid request is exercised.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio.agents import registry  # noqa: E402
from game_studio.agents.contract import (  # noqa: E402
    AgentError, BLOCKED, CANCELLED, COMPLETED, FAILED,
)
from game_studio.agents.coordinator import (  # noqa: E402
    Orchestrator, detect_conflicts, orchestrate,
)
from game_studio.agents.workflow import TASK_DEFINITIONS  # noqa: E402

import server  # noqa: E402

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
    "GAME_STUDIO_LLM_MAX_REQUESTS": "",
    "GAME_STUDIO_LLM_MAX_CONTEXT_CHARS": "",
    "GAME_STUDIO_LLM_MAX_REQUESTS_PER_DAY": "",
}


def deterministic_executor(calls: list[dict] | None = None):
    """Return a mocked executor that produces each agent's deterministic output."""

    def executor(spec, data, decision):
        if calls is not None:
            calls.append({"agent": spec.id, "input": data, "decision": decision})
        output = registry.get_agent(spec.id).deterministic_output(data)
        return {"output": output, "mode": "mocked",
                "provider": "mock-provider", "model": "mock-model"}

    return executor


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="game-studio-v6p2c-")
        self.addCleanup(self.temp.cleanup)
        values = dict(ENV_VALUES)
        values["GAME_STUDIO_HOME"] = os.path.join(self.temp.name, "home")
        env = mock.patch.dict(os.environ, values)
        env.start()
        self.addCleanup(env.stop)

    def run_orchestrator(self, **kwargs) -> dict:
        params = {"installed_engines": ["unity"], "concurrency": 2}
        params.update(kwargs)
        return Orchestrator(REQUEST, **params).run()


class PlanTests(BaseCase):
    def test_plan_is_non_executable_and_dependency_ordered(self) -> None:
        plan = Orchestrator(REQUEST, installed_engines=["unity"]).build_plan()
        self.assertFalse(plan["executable"])
        self.assertEqual(len(plan["tasks"]), 8)
        self.assertEqual(plan["concurrency_limit"], 2)
        self.assertEqual(plan["parallel_groups"][0], ["design"])
        self.assertEqual(plan["parallel_groups"][-1], ["consolidation"])
        self.assertTrue(all(task["status"] == "pending" for task in plan["tasks"]))

    def test_invalid_construction_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Orchestrator("")
        with self.assertRaises(ValueError):
            Orchestrator(REQUEST, concurrency=0)
        with self.assertRaises(ValueError):
            Orchestrator(REQUEST, concurrency=5)
        with self.assertRaises(ValueError):
            Orchestrator(REQUEST, max_retries=4)
        with self.assertRaises(ValueError):
            Orchestrator(REQUEST, quality_target="ultra")

    def test_task_assignment_matches_registry(self) -> None:
        specs = registry.specs()
        plan = Orchestrator(REQUEST).build_plan()
        for task in plan["tasks"]:
            self.assertIn(task["agent"], specs)
            self.assertTrue(task["description"])


class ExecutionTests(BaseCase):
    def test_full_deterministic_demo_completes_every_task(self) -> None:
        report = self.run_orchestrator()
        self.assertEqual(report["status"], COMPLETED)
        self.assertTrue(report["ok"])
        self.assertFalse(report["executable"])
        self.assertEqual([task["status"] for task in report["tasks"]],
                         [COMPLETED] * 8)
        self.assertEqual(report["outputs"]["architecture"]["engine"]["name"], "unity")
        self.assertEqual(report["provider_summary"]["mode"], "deterministic")
        self.assertFalse(report["provider_summary"]["live_verified"])
        self.assertGreaterEqual(report["diagnostics"]["duration_ms"], 0)
        self.assertEqual(report["diagnostics"]["state_counts"], {"completed": 8})
        self.assertFalse(report["governance"]["writes_performed"])
        self.assertFalse(report["governance"]["assets_generated"])
        self.assertFalse(report["governance"]["engine_invoked"])
        self.assertFalse(report["governance"]["requirement_status_changed"])

    def test_outputs_are_passed_between_agents_in_dependency_order(self) -> None:
        calls: list[dict] = []
        report = self.run_orchestrator(
            use_provider=True, provider_executor=deterministic_executor(calls))
        self.assertEqual(report["status"], COMPLETED)
        order = [call["agent"] for call in calls]
        self.assertEqual(len(order), 8)
        self.assertLess(order.index("game_designer"), order.index("technical_architect"))
        self.assertLess(order.index("technical_architect"), order.index("character"))
        self.assertLess(order.index("gameplay"), order.index("uiux"))
        self.assertLess(order.index("uiux"), order.index("qa"))
        self.assertLess(order.index("qa"), order.index("game_director"))

        architect = next(call for call in calls if call["agent"] == "technical_architect")
        self.assertIn("design", architect["input"])
        self.assertTrue(architect["input"]["design"]["core_loop"])

        qa_call = next(call for call in calls if call["agent"] == "qa")
        for section in ("design", "architecture", "character", "environment",
                        "gameplay", "uiux"):
            self.assertIn(section, qa_call["input"], section)

    def test_concurrency_limit_is_enforced(self) -> None:
        lock = threading.Lock()
        active = 0
        peak = 0

        def executor(spec, data, decision):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            output = registry.get_agent(spec.id).deterministic_output(data)
            return {"output": output, "mode": "mocked"}

        report = self.run_orchestrator(
            use_provider=True, provider_executor=executor, concurrency=2)
        self.assertEqual(report["status"], COMPLETED)
        self.assertEqual(report["diagnostics"]["concurrency_limit"], 2)
        self.assertLessEqual(peak, 2)
        self.assertGreaterEqual(peak, 1)

    def test_single_worker_runs_strictly_sequentially(self) -> None:
        lock = threading.Lock()
        active = 0
        peak = 0

        def executor(spec, data, decision):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return {"output": registry.get_agent(spec.id).deterministic_output(data),
                    "mode": "mocked"}

        report = self.run_orchestrator(
            use_provider=True, provider_executor=executor, concurrency=1)
        self.assertEqual(report["status"], COMPLETED)
        self.assertEqual(peak, 1)

    def test_use_provider_false_never_calls_the_executor(self) -> None:
        def forbidden(spec, data, decision):
            raise AssertionError("executor must not be called when use_provider is false")

        report = self.run_orchestrator(provider_executor=forbidden, use_provider=False)
        self.assertEqual(report["status"], COMPLETED)
        self.assertEqual(report["provider_summary"]["mode"], "deterministic")

    def test_deterministic_fallback_when_provider_requested_without_executor(self) -> None:
        report = self.run_orchestrator(use_provider=True, provider_executor=None)
        self.assertEqual(report["status"], COMPLETED)
        self.assertEqual(report["provider_summary"]["mode"], "deterministic")
        self.assertFalse(report["provider_summary"]["live_verified"])

    def test_orchestrate_helper_returns_a_report(self) -> None:
        report = orchestrate(REQUEST, installed_engines=["unity"])
        self.assertEqual(report["status"], COMPLETED)


class ProviderAttributionTests(BaseCase):
    def test_mocked_executor_is_labelled_mocked_not_live(self) -> None:
        report = self.run_orchestrator(
            use_provider=True, provider_executor=deterministic_executor())
        self.assertEqual(report["status"], COMPLETED)
        self.assertEqual(report["provider_summary"]["mode"], "mocked")
        self.assertFalse(report["provider_summary"]["live_verified"])
        self.assertFalse(report["diagnostics"]["live_verified"])
        for run in report["agent_runs"]:
            self.assertEqual(run["provider"]["mode"], "mocked")
            self.assertFalse(run["provider"]["live_verified"])

    def test_routing_uses_phase1_capabilities_and_no_network(self) -> None:
        report = self.run_orchestrator()
        self.assertEqual(len(report["routing"]), 8)
        for task_id, decision in report["routing"].items():
            self.assertIn(decision["mode"], ("provider", "deterministic"))
            self.assertTrue(decision["required_capabilities"])
            self.assertIn("explanation", decision)
            self.assertEqual(decision["network_calls"], 0)
        self.assertEqual(report["provider_summary"]["mode"], "deterministic")

    def test_provider_failure_is_reported_without_success(self) -> None:
        calls = {"count": 0}

        def failing(spec, data, decision):
            calls["count"] += 1
            raise AgentError("provider rejected the request", kind="provider",
                             retryable=False)

        report = self.run_orchestrator(
            use_provider=True, provider_executor=failing, max_retries=2)
        self.assertEqual(report["status"], FAILED)
        self.assertFalse(report["ok"])
        self.assertIn("design", report["failed_tasks"])
        self.assertIn("architecture", report["blocked_tasks"])
        self.assertEqual(calls["count"], 1)
        self.assertFalse(report["provider_summary"]["live_verified"])

    def test_secrets_are_not_present_in_report(self) -> None:
        secret = "sk-live-super-secret-value-123"
        with mock.patch.dict(os.environ, {"GAME_STUDIO_LLM_API_KEY": secret,
                                          "OPENAI_API_KEY": secret}):
            report = self.run_orchestrator(
                use_provider=True, provider_executor=deterministic_executor(),
                allow_paid=True)
        payload = json.dumps(report)
        self.assertNotIn(secret, payload)
        self.assertNotIn("api_key", payload)


class RetryAndCancellationTests(BaseCase):
    def test_retryable_failure_is_retried_within_limit(self) -> None:
        calls = {"count": 0}

        def flaky(spec, data, decision):
            calls["count"] += 1
            raise AgentError("temporary transport failure", kind="provider",
                             retryable=True)

        report = self.run_orchestrator(
            use_provider=True, provider_executor=flaky, max_retries=2)
        self.assertEqual(report["status"], FAILED)
        design = next(task for task in report["tasks"] if task["id"] == "design")
        self.assertEqual(design["status"], FAILED)
        self.assertEqual(design["retry_count"], 2)
        self.assertEqual(calls["count"], 3)
        self.assertEqual(report["diagnostics"]["retries"], 2)

    def test_retry_recovers(self) -> None:
        calls = {"count": 0}

        def recovering(spec, data, decision):
            calls["count"] += 1
            if spec.id == "game_designer" and calls["count"] == 1:
                raise AgentError("one transient failure", kind="provider",
                                 retryable=True)
            return {"output": registry.get_agent(spec.id).deterministic_output(data),
                    "mode": "mocked"}

        report = self.run_orchestrator(
            use_provider=True, provider_executor=recovering, max_retries=1)
        self.assertEqual(report["status"], COMPLETED)
        design = next(task for task in report["tasks"] if task["id"] == "design")
        self.assertEqual(design["retry_count"], 1)

    def test_retries_are_not_attempted_when_limit_is_zero(self) -> None:
        calls = {"count": 0}

        def flaky(spec, data, decision):
            calls["count"] += 1
            raise AgentError("retryable but disallowed", kind="provider",
                             retryable=True)

        report = self.run_orchestrator(
            use_provider=True, provider_executor=flaky, max_retries=0)
        self.assertEqual(report["status"], FAILED)
        self.assertEqual(calls["count"], 1)

    def test_cancel_before_run_marks_everything_cancelled(self) -> None:
        orchestrator = Orchestrator(REQUEST, installed_engines=["unity"])
        orchestrator.cancel()
        report = orchestrator.run()
        self.assertEqual(report["status"], CANCELLED)
        self.assertFalse(report["ok"])
        self.assertEqual(report["diagnostics"]["state_counts"],
                         {"cancelled": 8})
        self.assertEqual(len(report["cancelled_tasks"]), 8)

    def test_cancel_during_run_stops_remaining_tasks(self) -> None:
        orchestrator = Orchestrator(REQUEST, installed_engines=["unity"],
                                    max_retries=0)
        orchestrator.use_provider = True

        def executor(spec, data, decision):
            orchestrator.cancel()
            return {"output": registry.get_agent(spec.id).deterministic_output(data),
                    "mode": "mocked"}

        orchestrator.provider_executor = executor
        report = orchestrator.run()
        self.assertEqual(report["status"], CANCELLED)
        self.assertFalse(report["ok"])
        self.assertTrue(report["cancelled_tasks"])
        self.assertEqual(report["diagnostics"]["state_counts"].get(COMPLETED), 1)

    def test_dependent_tasks_are_blocked_when_a_prerequisite_fails(self) -> None:
        def failing_design(spec, data, decision):
            if spec.id == "game_designer":
                raise AgentError("cannot design", kind="provider", retryable=False)
            return {"output": registry.get_agent(spec.id).deterministic_output(data),
                    "mode": "mocked"}

        report = self.run_orchestrator(
            use_provider=True, provider_executor=failing_design)
        self.assertEqual(report["status"], FAILED)
        statuses = {task["id"]: task["status"] for task in report["tasks"]}
        self.assertEqual(statuses["design"], FAILED)
        self.assertEqual(statuses["architecture"], BLOCKED)
        self.assertEqual(report["diagnostics"]["state_counts"].get(BLOCKED), 7)

    def test_dependency_failure_prevents_dependent_execution(self) -> None:
        seen: list[str] = []

        def executor(spec, data, decision):
            seen.append(spec.id)
            if spec.id == "technical_architect":
                raise AgentError("engine planning failed", kind="provider")
            return {"output": registry.get_agent(spec.id).deterministic_output(data),
                    "mode": "mocked"}

        report = self.run_orchestrator(
            use_provider=True, provider_executor=executor)
        self.assertEqual(report["status"], FAILED)
        self.assertNotIn("character", seen)
        self.assertNotIn("environment", seen)
        self.assertNotIn("gameplay", seen)
        self.assertNotIn("uiux", seen)
        self.assertNotIn("qa", seen)


class BudgetTests(BaseCase):
    def test_zero_request_budget_blocks_provider_work(self) -> None:
        with mock.patch.dict(os.environ, {"GAME_STUDIO_LLM_MAX_REQUESTS": "0"}):
            report = self.run_orchestrator(
                use_provider=True, provider_executor=deterministic_executor())
        self.assertEqual(report["status"], FAILED)
        self.assertTrue(report["failed_tasks"])
        budget_errors = [run for run in report["agent_runs"]
                         if (run["error"] or {}).get("kind") == "budget-exceeded"]
        self.assertTrue(budget_errors)
        self.assertIn("budget", budget_errors[0]["error"]["message"])

    def test_context_budget_is_enforced(self) -> None:
        long_request = REQUEST + (" extra detail" * 800)
        with mock.patch.dict(os.environ,
                             {"GAME_STUDIO_LLM_MAX_CONTEXT_CHARS": "4000"}):
            report = Orchestrator(
                long_request, installed_engines=["unity"], use_provider=True,
                provider_executor=deterministic_executor()).run()
        self.assertEqual(report["status"], FAILED)
        design = next(run for run in report["agent_runs"] if run["task_id"] == "design")
        self.assertEqual(design["error"]["kind"], "budget-exceeded")
        self.assertIn("exceeds the configured limit", design["error"]["message"])

    def test_budget_checks_do_not_apply_to_deterministic_mode(self) -> None:
        with mock.patch.dict(os.environ, {"GAME_STUDIO_LLM_MAX_REQUESTS": "0",
                                          "GAME_STUDIO_LLM_MAX_CONTEXT_CHARS": "4000"}):
            report = self.run_orchestrator(use_provider=False)
        self.assertEqual(report["status"], COMPLETED)


class ConflictTests(BaseCase):
    def brief(self, **overrides) -> dict:
        from game_studio import understanding
        from game_studio.agents.game_director import GameDirectorAgent
        analysis = understanding.analyze_request(REQUEST, installed_engines=["unity"])
        brief = GameDirectorAgent().create_brief(
            request=REQUEST, understanding=analysis, quality_target="prototype",
            installed_engines=["unity"])
        brief.update(overrides)
        return brief

    def test_engine_not_installed_is_blocking(self) -> None:
        conflicts = detect_conflicts(
            self.brief(),
            {"architecture": {"engine": {"name": "unreal", "installed": False}}})
        entry = next(c for c in conflicts if c["id"] == "C-engine-not-installed")
        self.assertTrue(entry["blocking"])
        self.assertTrue(entry["requires_approval"])

    def test_required_and_excluded_mechanic_conflict(self) -> None:
        brief = self.brief(mechanics=["swimming", "collectibles"],
                           exclusions=[{"value": "swimming"}])
        conflicts = detect_conflicts(brief, {})
        self.assertTrue(any(c["id"] == "C-excluded-swimming" for c in conflicts))

    def test_approved_decision_conflict_is_not_overridden(self) -> None:
        brief = self.brief(mechanics=["swimming"],
                           exclusions=[{"value": "swimming"}])
        conflicts = detect_conflicts(
            brief, {}, approved_decisions=[
                {"id": "D-1", "statement": "Swimming is explicitly approved as a core mechanic."}])
        entry = next(c for c in conflicts if c["id"] == "C-decision-swimming")
        self.assertTrue(entry["blocking"])
        self.assertEqual(entry["category"], "approved-decision")

    def test_missing_prerequisite_is_detected(self) -> None:
        conflicts = detect_conflicts(
            self.brief(), {"architecture": {"engine": {"name": "unity",
                                                       "installed": True}}})
        self.assertTrue(any(c["id"] == "C-missing-prerequisite-architecture-design"
                            for c in conflicts))

    def test_environment_budget_conflict_is_detected(self) -> None:
        conflicts = detect_conflicts(
            self.brief(),
            {"environment": {"estimates": {"within_budget": False}}})
        entry = next(c for c in conflicts if c["id"] == "C-environment-budget")
        self.assertTrue(entry["requires_approval"])
        self.assertFalse(entry["blocking"])

    def test_character_pipeline_gap_is_reported(self) -> None:
        conflicts = detect_conflicts(
            self.brief(), {"character": {"capability_gaps": ["no meshes"]}})
        entry = next(c for c in conflicts if c["id"] == "C-character-pipeline")
        self.assertFalse(entry["blocking"])
        self.assertTrue(entry["requires_approval"])

    def test_conflict_ids_are_deduplicated(self) -> None:
        brief = self.brief()
        outputs = {
            "architecture": {"engine": {"name": "unity", "installed": True}},
            "qa": {"conflicts": [
                {"id": "C-character-pipeline", "category": "asset-pipeline",
                 "severity": "medium", "message": "duplicate", "blocking": False},
                {"id": "C-character-pipeline", "category": "asset-pipeline",
                 "severity": "medium", "message": "duplicate", "blocking": False},
            ]},
        }
        conflicts = detect_conflicts(brief, outputs)
        ids = [conflict["id"] for conflict in conflicts]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_engine_blocks_end_to_end_without_installed_engines(self) -> None:
        report = self.run_orchestrator(installed_engines=[])
        self.assertEqual(report["status"], BLOCKED)
        self.assertFalse(report["ok"])
        self.assertTrue(any(c["id"] == "C-engine-not-installed"
                            for c in report["blocking_conflicts"]))
        self.assertFalse(report["executable"])

    def test_open_conflicts_keep_plan_non_executable(self) -> None:
        report = self.run_orchestrator()
        self.assertFalse(report["executable"])
        self.assertIsNotNone(report["consolidated"])
        self.assertFalse(report["consolidated"]["executable"])
        self.assertTrue(report["conflicts"])
        self.assertTrue(report["approval_required"])


class EvidenceAndGovernanceTests(BaseCase):
    def test_evidence_refs_are_traceable_to_agents(self) -> None:
        report = self.run_orchestrator()
        evidence = report["evidence_index"]
        self.assertEqual(len(evidence), 8)
        for ref in evidence:
            self.assertTrue(ref["ref"].startswith("agent://"))
            self.assertIn(ref["source_agent"], registry.specs())
        history = report["outputs"] and report.get("brief") is not None
        self.assertTrue(history)
        for run in report["agent_runs"]:
            self.assertEqual(run["agent"], run["evidence"][0]["source_agent"])
            self.assertIn("output_valid", run["validation"])
            self.assertTrue(run["validation"]["output_valid"])
            self.assertEqual(run["validation"]["input_valid"], True)

    def test_governance_reports_no_writes(self) -> None:
        report = self.run_orchestrator()
        governance = report["governance"]
        self.assertEqual(governance, {
            "executable": False,
            "writes_performed": False,
            "engine_invoked": False,
            "assets_generated": False,
            "requirement_status_changed": False,
        })
        for run in report["agent_runs"]:
            output = run["output"] or {}
            if "assets_generated" in output:
                self.assertFalse(output["assets_generated"])
            if "textures_generated" in output:
                self.assertFalse(output["textures_generated"])
            if "generated" in output:
                self.assertFalse(output["generated"])

    def test_limitations_are_explicit(self) -> None:
        report = self.run_orchestrator()
        text = " ".join(report["limitations"]).lower()
        self.assertIn("plans only", text)
        self.assertIn("not implementation", text)


class McpIntegrationTests(BaseCase):
    def test_tool_and_handler_parity(self) -> None:
        names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(server.HANDLERS))
        self.assertEqual(len(names), 92)
        self.assertIn("orchestrate_game_plan", names)

    def test_orchestrate_tool_schema_is_strict(self) -> None:
        tool = next(t for t in server.TOOLS if t["name"] == "orchestrate_game_plan")
        schema = tool["inputSchema"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["request"])
        self.assertEqual(schema["properties"]["concurrency"]["maximum"], 4)
        self.assertEqual(schema["properties"]["concurrency"]["minimum"], 1)
        self.assertIn("request", schema["properties"])

    def test_orchestrate_tool_runs_deterministically(self) -> None:
        result = server.tool_orchestrate_game_plan(
            {"request": REQUEST, "installed_engines": ["unity"]})
        self.assertEqual(result["status"], COMPLETED)
        self.assertFalse(result["executable"])
        self.assertEqual(result["provider_summary"]["mode"], "deterministic")
        self.assertEqual(len(result["tasks"]), 8)

    def test_orchestrate_tool_validates_arguments(self) -> None:
        from game_studio.util import ToolError
        with self.assertRaises(ToolError):
            server.tool_orchestrate_game_plan({})
        with self.assertRaises(ToolError):
            server.tool_orchestrate_game_plan({"request": REQUEST,
                                               "quality_target": "ultra"})
        with self.assertRaises(ToolError):
            server.tool_orchestrate_game_plan({"request": REQUEST,
                                               "approved_decisions": ["bad"]})
        with self.assertRaises(ToolError):
            server.tool_orchestrate_game_plan({"request": REQUEST,
                                               "concurrency": 9})


class RegressionTests(BaseCase):
    def test_v4_checkpoint_files_are_unchanged(self) -> None:
        import hashlib
        baseline = json.loads((ROOT.parents[1] / "reports" /
                               "v6-phase0-baseline.json").read_text(encoding="utf-8"))
        files = baseline["v4_checkpoint"]["files"]
        self.assertTrue(files)
        for relative, expected in files.items():
            path = ROOT.parents[1] / relative
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, expected["sha256"], relative)
        self.assertTrue(baseline["v4_checkpoint"]["preserved"])

    def test_v5_artifacts_are_unchanged(self) -> None:
        import hashlib
        baseline = json.loads((ROOT.parents[1] / "reports" /
                               "v6-phase0-baseline.json").read_text(encoding="utf-8"))
        artifacts = baseline["v5_checkpoint"]["artifacts"]
        self.assertTrue(artifacts)
        for relative, expected in artifacts.items():
            if not expected.get("exists"):
                continue
            path = ROOT.parents[1] / relative
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, expected["sha256"], relative)

    def test_phase1_audit_evidence_is_preserved(self) -> None:
        audit = json.loads((ROOT.parents[1] / "reports" /
                            "v6-phase1-audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["mcp"]["tools"], 89)
        self.assertEqual(audit["mcp"]["handlers"], 89)
        self.assertEqual(audit["mcp"]["missing_handlers"], [])
        self.assertEqual(audit["tests"]["result"], "OK")

    def test_workflow_definition_has_eight_unique_tasks(self) -> None:
        ids = [task["id"] for task in TASK_DEFINITIONS]
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
