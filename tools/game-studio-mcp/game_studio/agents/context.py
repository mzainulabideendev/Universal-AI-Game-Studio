"""Controlled shared project context for the Phase 2 agents.

Agents receive only the sections declared in their ``required_context``. Every
section records the producing agent, version and task id so outputs remain
traceable. Mutating an agent's view never mutates the shared context.
"""

from __future__ import annotations

import copy


class ProjectContext:
    def __init__(self, request: str, *, brief: dict | None = None,
                 approved_decisions: list[dict] | None = None):
        self.request = request
        self.sections: dict[str, dict] = {}
        self.provenance: dict[str, dict] = {}
        self.history: list[dict] = []
        if brief is not None:
            self.sections["brief"] = copy.deepcopy(brief)
            self.provenance["brief"] = {
                "agent": "game_director",
                "agent_version": "1.0.0",
                "task_id": "brief",
            }
        self.approved_decisions = copy.deepcopy(approved_decisions or [])

    def record(self, *, task_id: str, agent: str, agent_version: str,
               section: str, output: dict, evidence: list[dict] | None = None,
               status: str = "completed") -> None:
        self.sections[section] = copy.deepcopy(output)
        self.provenance[section] = {
            "agent": agent,
            "agent_version": agent_version,
            "task_id": task_id,
            "status": status,
        }
        self.history.append({
            "task_id": task_id,
            "agent": agent,
            "agent_version": agent_version,
            "section": section,
            "status": status,
            "evidence": copy.deepcopy(evidence or []),
        })

    def scoped(self, required_context: tuple[str, ...] | list[str], *,
               include_request: bool = True) -> dict:
        """Return only the declared sections, as deep copies."""
        view: dict = {}
        if include_request:
            view["request"] = self.request
        for name in required_context:
            if name in self.sections:
                view[name] = copy.deepcopy(self.sections[name])
        if self.approved_decisions:
            view["approved_decisions"] = copy.deepcopy(self.approved_decisions)
        view["context_sources"] = {
            name: copy.deepcopy(self.provenance.get(name, {}))
            for name in required_context if name in self.sections
        }
        return view

    def get(self, section: str) -> dict | None:
        value = self.sections.get(section)
        return copy.deepcopy(value) if value is not None else None

    def record_history(self, *, task_id: str, agent: str, agent_version: str,
                       section: str, status: str,
                       evidence: list[dict] | None = None,
                       note: str = "") -> None:
        self.history.append({
            "task_id": task_id,
            "agent": agent,
            "agent_version": agent_version,
            "section": section,
            "status": status,
            "evidence": copy.deepcopy(evidence or []),
            "note": note,
        })

    def snapshot(self) -> dict:
        return {
            "request": self.request,
            "sections": copy.deepcopy(self.sections),
            "provenance": copy.deepcopy(self.provenance),
            "history": copy.deepcopy(self.history),
            "approved_decisions": copy.deepcopy(self.approved_decisions),
        }
