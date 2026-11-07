"""V6 Phase 2 multi-agent coordinator.

Executes the specialist agents in dependency order with explicit concurrency,
bounded retries, cancellation and capability-aware provider routing. The result
is a consolidated, non-executable plan with traceable evidence. No engine,
Blender, asset or provider write is performed by this module.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time

from .. import understanding
from ..llm import config as llm_config
from ..llm import routing
from .contract import (
    AgentResult, BLOCKED, CANCELLED, COMPLETED, FAILED, PENDING, RUNNING,
)
from .context import ProjectContext
from .game_director import GameDirectorAgent
from .helpers import QUALITY_PROFILES, clean_values, excluded_values
from .registry import get_agent
from .workflow import TASK_BY_ID, TASK_DEFINITIONS, dependency_graph, parallel_groups

DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 4
MAX_RETRIES = 3


class Orchestrator:
    def __init__(self, request: str, *, engine: str | None = None,
                 platform: str | None = None, quality_target: str = "prototype",
                 concurrency: int = DEFAULT_CONCURRENCY, max_retries: int = 1,
                 provider_executor=None, use_provider: bool = False,
                 allow_paid: bool = False, installed_engines: list[str] | None = None,
                 approved_decisions: list[dict] | None = None,
                 cancel_event: threading.Event | None = None):
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(concurrency, int) or not 1 <= concurrency <= MAX_CONCURRENCY:
            raise ValueError(f"concurrency must be an integer between 1 and {MAX_CONCURRENCY}")
        if not isinstance(max_retries, int) or not 0 <= max_retries <= MAX_RETRIES:
            raise ValueError(f"max_retries must be between 0 and {MAX_RETRIES}")
        if quality_target not in QUALITY_PROFILES:
            raise ValueError(f"quality_target must be one of {list(QUALITY_PROFILES)}")
        self.request = request.strip()
        self.engine = (engine or "").strip().lower() or None
        self.platform = (platform or "").strip().lower() or None
        self.quality_target = quality_target
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.provider_executor = provider_executor
        self.use_provider = bool(use_provider)
        self.allow_paid = bool(allow_paid)
        self.installed_engines = [str(x).lower() for x in (installed_engines or [])]
        self.approved_decisions = approved_decisions or []
        self.cancel_event = cancel_event or threading.Event()
        self.context: ProjectContext | None = None
        self.results: dict[str, AgentResult] = {}
        self.routing_decisions: dict[str, dict] = {}
        self.brief: dict | None = None
        self._started = 0.0

    # -- lifecycle ---------------------------------------------------------
    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def create_brief(self) -> dict:
        director = GameDirectorAgent()
        analysis = understanding.analyze_request(
            self.request,
            installed_engines=self.installed_engines,
            known_engine=self.engine,
            known_platform=self.platform,
        )
        brief = director.create_brief(
            request=self.request,
            understanding=analysis,
            quality_target=self.quality_target,
            engine_hint=self.engine,
            installed_engines=self.installed_engines,
        )
        if self.platform and not brief.get("platform"):
            brief["platform"] = [self.platform]
        self.brief = brief
        return brief

    def build_plan(self) -> dict:
        return {
            "executable": False,
            "tasks": [
                {
                    "id": task["id"],
                    "agent": task["agent"],
                    "section": task["section"],
                    "dependencies": list(task["dependencies"]),
                    "description": task["description"],
                    "status": PENDING,
                }
                for task in TASK_DEFINITIONS
            ],
            "dependency_graph": dependency_graph(),
            "parallel_groups": parallel_groups(),
            "concurrency_limit": self.concurrency,
            "max_retries": self.max_retries,
        }

    # -- execution ---------------------------------------------------------
    def run(self) -> dict:
        self._started = time.perf_counter()
        if self.brief is None:
            self.create_brief()
        self.context = ProjectContext(
            self.request, brief=self.brief,
            approved_decisions=self.approved_decisions)

        for level in parallel_groups():
            if self.cancelled:
                self._mark_unstarted_cancelled()
                break
            ready: list[dict] = []
            for task_id in level:
                task = TASK_BY_ID[task_id]
                unmet = [dep for dep in task["dependencies"]
                         if self.results.get(dep) is None
                         or self.results[dep].status != COMPLETED]
                if unmet:
                    self.results[task_id] = self._blocked_result(
                        task, f"prerequisite task(s) not completed: {unmet}")
                    self.context.record_history(
                        task_id=task_id, agent=task["agent"], agent_version="1.0.0",
                        section=task["section"], status=BLOCKED,
                        note=f"blocked by {unmet}")
                else:
                    ready.append(task)
            if not ready:
                continue
            workers = min(self.concurrency, len(ready))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._run_task, task): task for task in ready}
                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    try:
                        self.results[task["id"]] = future.result()
                    except Exception as exc:  # defensive; agents already catch
                        self.results[task["id"]] = AgentResult(
                            agent=task["agent"], agent_version="1.0.0",
                            task_id=task["id"], status=FAILED,
                            error={"kind": "coordinator", "retryable": False,
                                   "message": f"{type(exc).__name__}: {exc}"},
                        )
                    result = self.results[task["id"]]
                    if result.status == COMPLETED:
                        self.context.record(
                            task_id=task["id"], agent=result.agent,
                            agent_version=result.agent_version,
                            section=task["section"], output=result.output or {},
                            evidence=result.evidence)
                    else:
                        self.context.record_history(
                            task_id=task["id"], agent=task["agent"],
                            agent_version="1.0.0", section=task["section"],
                            status=result.status, evidence=result.evidence,
                            note=(result.error or {}).get("message", ""))
        return self._report()

    def _run_task(self, task: dict) -> AgentResult:
        agent = get_agent(task["agent"])
        spec = agent.spec
        if self.cancelled:
            return self._cancelled_result(task)
        scoped = self.context.scoped(spec.required_context)
        estimated_chars = len(str(scoped))

        budget_error = self._budget_error(estimated_chars)
        if budget_error:
            return AgentResult(
                agent=spec.id, agent_version=spec.version, task_id=task["id"],
                status=FAILED,
                error={"kind": "budget-exceeded", "message": budget_error,
                       "retryable": False},
            )

        decision = routing.route(
            spec.task_category,
            required_capabilities=list(spec.required_capabilities),
            context_chars=estimated_chars,
            allow_paid=self.allow_paid,
        )
        self.routing_decisions[task["id"]] = {
            "task": task["id"],
            "mode": decision["mode"],
            "selected": decision["selected"],
            "required_capabilities": decision["required_capabilities"],
            "explanation": decision["explanation"],
            "network_calls": decision["network_calls"],
        }

        executor = self.provider_executor if self.use_provider else None
        attempts = 0
        while True:
            result = agent.run(
                task_id=task["id"], context=self.context,
                routing_decision=decision, executor=executor,
                attempt=attempts, retry_count=attempts)
            if (result.status == FAILED
                    and (result.error or {}).get("retryable")
                    and attempts < self.max_retries):
                attempts += 1
                continue
            break
        if self.cancelled and result.status != COMPLETED:
            return self._cancelled_result(task, retries=attempts)
        result.retry_count = attempts
        return result

    def _budget_error(self, estimated_chars: int) -> str | None:
        if not self.use_provider:
            return None
        cfg = llm_config.load_config()
        if int(cfg.get("max_requests") or 0) == 0:
            return "provider request budget is zero (GAME_STUDIO_LLM_MAX_REQUESTS)"
        if estimated_chars > int(cfg["max_context_chars"]):
            return (f"estimated agent context of {estimated_chars} chars exceeds the "
                    f"configured limit of {cfg['max_context_chars']}")
        return None

    def _blocked_result(self, task: dict, reason: str) -> AgentResult:
        return AgentResult(
            agent=task["agent"], agent_version="1.0.0", task_id=task["id"],
            status=BLOCKED,
            error={"kind": "prerequisite", "message": reason, "retryable": False},
            provider={"mode": "none", "live_verified": False},
        )

    def _cancelled_result(self, task: dict, retries: int = 0) -> AgentResult:
        return AgentResult(
            agent=task["agent"], agent_version="1.0.0", task_id=task["id"],
            status=CANCELLED,
            error={"kind": "cancelled", "message": "orchestration was cancelled",
                   "retryable": False},
            provider={"mode": "none", "live_verified": False},
            retry_count=retries,
        )

    def _mark_unstarted_cancelled(self) -> None:
        for task in TASK_DEFINITIONS:
            if task["id"] not in self.results:
                self.results[task["id"]] = self._cancelled_result(task)

    # -- consolidation -----------------------------------------------------
    def _report(self) -> dict:
        outputs = self.context.snapshot()["sections"] if self.context else {}
        conflicts = detect_conflicts(self.brief or {}, outputs,
                                     approved_decisions=self.approved_decisions)
        consolidated = outputs.get("consolidation")
        blocking = [item for item in conflicts if item.get("blocking")]
        failed = [tid for tid, res in self.results.items() if res.status == FAILED]
        blocked = [tid for tid, res in self.results.items() if res.status == BLOCKED]
        cancelled = [tid for tid, res in self.results.items()
                     if res.status == CANCELLED]

        if self.cancelled:
            status = CANCELLED
        elif failed:
            status = FAILED
        elif blocked or blocking:
            status = BLOCKED
        elif len(completed := [tid for tid, res in self.results.items()
                               if res.status == COMPLETED]) == len(TASK_DEFINITIONS):
            status = COMPLETED
        else:
            status = BLOCKED

        modes: dict[str, int] = {}
        for res in self.results.values():
            mode = (res.provider or {}).get("mode") or "none"
            modes[mode] = modes.get(mode, 0) + 1
        live_verified = bool(modes.get("live"))

        duration_ms = max(0, int((time.perf_counter() - self._started) * 1000))
        return {
            "ok": status == COMPLETED and not blocking,
            "status": status,
            "executable": False,
            "request": self.request,
            "brief": self.brief,
            "plan": self.build_plan(),
            "agent_runs": [self.results[task["id"]].to_dict()
                           for task in TASK_DEFINITIONS if task["id"] in self.results],
            "tasks": [{
                "id": task["id"],
                "agent": task["agent"],
                "section": task["section"],
                "dependencies": list(task["dependencies"]),
                "status": (self.results.get(task["id"]).status
                           if task["id"] in self.results else PENDING),
                "retry_count": (self.results.get(task["id"]).retry_count
                                if task["id"] in self.results else 0),
                "provider_mode": ((self.results.get(task["id"]).provider or {}).get("mode")
                                  if task["id"] in self.results else None),
            } for task in TASK_DEFINITIONS],
            "routing": self.routing_decisions,
            "outputs": outputs,
            "consolidated": consolidated,
            "conflicts": conflicts,
            "blocking_conflicts": blocking,
            "failed_tasks": failed,
            "blocked_tasks": blocked,
            "cancelled_tasks": cancelled,
            "approval_required": (consolidated or {}).get("approval_required") or [],
            "evidence_index": [ref for res in self.results.values()
                               for ref in res.evidence],
            "diagnostics": {
                "duration_ms": duration_ms,
                "agent_runs": len(self.results),
                "retries": sum(res.retry_count for res in self.results.values()),
                "concurrency_limit": self.concurrency,
                "provider_modes": modes,
                "live_verified": live_verified,
                "network_calls": 0 if not live_verified and "mocked" not in modes
                else None,
                "state_counts": _state_counts(self.results),
            },
            "provider_summary": {
                "mode": "deterministic" if set(modes) <= {"deterministic", "none"}
                else ("mocked" if modes.get("mocked") else "unknown"),
                "live_verified": live_verified,
                "note": ("No provider was contacted in deterministic mode. Mocked "
                         "executors are never live verification."),
            },
            "governance": {
                "executable": False,
                "writes_performed": False,
                "engine_invoked": False,
                "assets_generated": False,
                "requirement_status_changed": False,
            },
            "limitations": [
                "Phase 2 produces plans only; no game, asset, texture or animation exists.",
                "A completed agent run is not implementation or build verification.",
                "Provider attribution is deterministic unless an authorized live executor "
                "was supplied.",
            ],
        }


def _state_counts(results: dict[str, AgentResult]) -> dict:
    counts: dict[str, int] = {}
    for result in results.values():
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def detect_conflicts(brief: dict, outputs: dict,
                     approved_decisions: list[dict] | None = None) -> list[dict]:
    """Detect planning conflicts. Returns deduplicated, structured entries."""
    conflicts: list[dict] = []

    def add(entry: dict) -> None:
        if not any(existing.get("id") == entry.get("id") for existing in conflicts):
            conflicts.append(entry)

    for item in brief.get("conflicts") or []:
        add({
            "id": f"C-understanding-{len(conflicts) + 1}",
            "category": "requirements",
            "severity": "high",
            "message": str(item.get("message") if isinstance(item, dict) else item),
            "blocking": True,
            "requires_approval": True,
            "source_agents": ["game_director"],
            "status": "open",
        })

    mechanics = {str(x).lower() for x in brief.get("mechanics") or []}
    excluded = {str(x).lower() for x in excluded_values(brief)}
    for overlap in sorted(mechanics & excluded):
        add({
            "id": f"C-excluded-{overlap}",
            "category": "scope",
            "severity": "high",
            "message": f"Mechanic {overlap!r} is both required and excluded.",
            "blocking": True,
            "requires_approval": True,
            "source_agents": ["game_designer", "qa"],
            "status": "open",
        })

    architecture = outputs.get("architecture") or {}
    engine = architecture.get("engine") or {}
    if engine and not engine.get("installed"):
        add({
            "id": "C-engine-not-installed",
            "category": "engine",
            "severity": "high",
            "message": (f"Engine {engine.get('name')!r} is not detected; implementation "
                        "is blocked until an engine is verified."),
            "blocking": True,
            "requires_approval": True,
            "source_agents": ["technical_architect", "qa"],
            "status": "open",
        })

    character = outputs.get("character") or {}
    if character.get("capability_gaps"):
        add({
            "id": "C-character-pipeline",
            "category": "asset-pipeline",
            "severity": "medium",
            "message": "Character mesh/PBR/rig pipeline is not implemented in Phase 2.",
            "blocking": False,
            "requires_approval": True,
            "source_agents": ["character"],
            "status": "open",
        })

    environment = outputs.get("environment") or {}
    estimates = environment.get("estimates") or {}
    if estimates and not estimates.get("within_budget", False):
        add({
            "id": "C-environment-budget",
            "category": "performance",
            "severity": "high",
            "message": "Environment estimates exceed the approved performance budget.",
            "blocking": False,
            "requires_approval": True,
            "source_agents": ["environment", "technical_architect"],
            "status": "open",
        })

    for item in (outputs.get("qa") or {}).get("conflicts") or []:
        entry = dict(item) if isinstance(item, dict) else {}
        entry.setdefault("id", f"C-qa-{len(conflicts) + 1}")
        entry.setdefault("status", "open")
        entry.setdefault("source_agents", ["qa"])
        add(entry)

    for decision in approved_decisions or []:
        text = str(decision.get("statement") or decision.get("value") or "").lower()
        for overlap in sorted(excluded & {word for word in mechanics if word in text}):
            add({
                "id": f"C-decision-{overlap}",
                "category": "approved-decision",
                "severity": "high",
                "message": f"Approved decision conflicts with mechanic {overlap!r}.",
                "blocking": True,
                "requires_approval": True,
                "source_agents": ["game_director"],
                "status": "open",
            })

    for task_id, task in TASK_BY_ID.items():
        if task_id not in outputs:
            continue
        for dep in task["dependencies"]:
            if dep not in outputs:
                add({
                    "id": f"C-missing-prerequisite-{task_id}-{dep}",
                    "category": "dependency",
                    "severity": "high",
                    "message": f"Task {task_id!r} is missing prerequisite {dep!r}.",
                    "blocking": True,
                    "requires_approval": True,
                    "source_agents": ["game_director", "qa"],
                    "status": "open",
                })
    return conflicts


def orchestrate(request: str, **kwargs) -> dict:
    return Orchestrator(request, **kwargs).run()
