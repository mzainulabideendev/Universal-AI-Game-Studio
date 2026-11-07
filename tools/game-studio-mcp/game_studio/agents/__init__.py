"""V6 Phase 2 specialized agent orchestration package."""

from __future__ import annotations

from .contract import AgentError, AgentResult, AgentSpec, STATES
from .coordinator import Orchestrator, detect_conflicts, orchestrate
from .registry import agents, get_agent, registry_report, specs
from .workflow import TASK_DEFINITIONS, dependency_graph, parallel_groups

__all__ = [
    "AgentError", "AgentResult", "AgentSpec", "STATES",
    "Orchestrator", "orchestrate", "detect_conflicts",
    "agents", "get_agent", "registry_report", "specs",
    "TASK_DEFINITIONS", "dependency_graph", "parallel_groups",
]
