"""Common typed contract for every V6 Phase 2 agent.

An agent returns a structured envelope, never free-form conversation. The
envelope carries identity, version, status, validated output, evidence,
provider attribution and budget information. Malformed output is rejected, not
silently repaired into a success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..llm import schemas

PENDING = "pending"
READY = "ready"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
BLOCKED = "blocked"
SKIPPED = "skipped"
CANCELLED = "cancelled"

STATES = (PENDING, READY, RUNNING, COMPLETED, FAILED, BLOCKED, SKIPPED, CANCELLED)
TERMINAL_STATES = (COMPLETED, FAILED, BLOCKED, SKIPPED, CANCELLED)


class AgentError(Exception):
    """A typed agent failure. ``retryable`` is explicit, never guessed."""

    def __init__(self, message: str, *, kind: str = "agent-error",
                 retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    version: str
    responsibility: str
    task_category: str
    dependencies: tuple[str, ...]
    required_context: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    input_schema: dict
    output_schema: dict
    max_retries: int = 0
    produces: str = ""

    def describe(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "responsibility": self.responsibility,
            "task_category": self.task_category,
            "dependencies": list(self.dependencies),
            "required_context": list(self.required_context),
            "required_capabilities": list(self.required_capabilities),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "max_retries": self.max_retries,
            "produces": self.produces,
            "states": list(STATES),
        }


# A provider executor is injected by a caller/test. It receives the agent spec,
# the scoped input and the Phase 1 routing decision, and returns either the
# structured output or an envelope-like object containing "output" and "mode".
ProviderExecutor = Callable[[AgentSpec, dict, dict], Any]


@dataclass
class AgentResult:
    agent: str
    agent_version: str
    task_id: str
    status: str
    output: dict | None = None
    summary: str = ""
    input_validation: list[str] = field(default_factory=list)
    output_validation: list[str] = field(default_factory=list)
    error: dict | None = None
    evidence: list[dict] = field(default_factory=list)
    provider: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    retry_count: int = 0
    duration_ms: int = 0
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    requirements_addressed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "agent_version": self.agent_version,
            "task_id": self.task_id,
            "status": self.status,
            "summary": self.summary,
            "output": self.output,
            "input_validation": list(self.input_validation),
            "output_validation": list(self.output_validation),
            "validation": {
                "input_valid": not self.input_validation,
                "output_valid": not self.output_validation,
            },
            "error": self.error,
            "evidence": list(self.evidence),
            "provider": dict(self.provider),
            "budget": dict(self.budget),
            "retry_count": self.retry_count,
            "duration_ms": self.duration_ms,
            "assumptions": list(self.assumptions),
            "risks": list(self.risks),
            "requirements_addressed": list(self.requirements_addressed),
        }


def validate_agent_input(spec: AgentSpec, payload: dict) -> list[str]:
    return schemas.validate(payload, spec.input_schema)


def validate_agent_output(spec: AgentSpec, payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["$: agent output must be a JSON object"]
    return schemas.validate(payload, spec.output_schema)


def evidence_ref(task_id: str, agent_id: str, kind: str = "agent-output") -> dict:
    return {
        "kind": kind,
        "ref": f"agent://{agent_id}/{task_id}",
        "source_agent": agent_id,
        "note": "Structured agent output produced during Phase 2 planning.",
    }
