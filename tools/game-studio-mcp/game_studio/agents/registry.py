"""Agent registry for V6 Phase 2."""

from __future__ import annotations

from .character import CharacterAgent
from .contract import AgentSpec, STATES
from .environment import EnvironmentAgent
from .game_designer import GameDesignerAgent
from .game_director import GameDirectorAgent
from .gameplay import GameplayAgent
from .qa import QAAgent
from .technical_architect import TechnicalArchitectAgent
from .uiux import UIUXAgent
from .workflow import dependency_graph, parallel_groups, validate_graph

_AGENT_CLASSES = (
    GameDirectorAgent,
    GameDesignerAgent,
    TechnicalArchitectAgent,
    CharacterAgent,
    EnvironmentAgent,
    GameplayAgent,
    UIUXAgent,
    QAAgent,
)


def agents() -> dict[str, object]:
    return {cls.spec.id: cls() for cls in _AGENT_CLASSES}


def specs() -> dict[str, AgentSpec]:
    return {cls.spec.id: cls.spec for cls in _AGENT_CLASSES}


def get_agent(agent_id: str):
    instances = agents()
    if agent_id not in instances:
        raise KeyError(f"unknown agent {agent_id!r}")
    return instances[agent_id]


def registry_report() -> dict:
    errors = validate_graph()
    return {
        "ok": not errors,
        "schema_version": 1,
        "phase": "V6 Phase 2 - agent orchestration",
        "agent_count": len(_AGENT_CLASSES),
        "agents": [spec.describe() for spec in specs().values()],
        "workflow": {
            "dependency_graph": dependency_graph(),
            "parallel_groups": parallel_groups(),
            "graph_errors": errors,
        },
        "states": list(STATES),
        "note": ("All agents are planning modules. A completed agent run is not "
                 "implementation, texture, animation or build verification."),
    }
