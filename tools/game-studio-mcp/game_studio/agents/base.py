"""Base agent runner: scoped input, validated output, honest attribution."""

from __future__ import annotations

import time

from .contract import (
    AgentError, AgentResult, AgentSpec, COMPLETED, FAILED,
    evidence_ref, validate_agent_input, validate_agent_output,
)


class Agent:
    spec: AgentSpec

    def deterministic_output(self, input_data: dict) -> dict:
        raise NotImplementedError

    def run(self, *, task_id: str, context, routing_decision: dict | None = None,
            executor=None, attempt: int = 0, retry_count: int = 0) -> AgentResult:
        started = time.perf_counter()
        input_data = context.scoped(self.spec.required_context)
        input_errors = validate_agent_input(self.spec, input_data)
        if input_errors:
            return AgentResult(
                agent=self.spec.id, agent_version=self.spec.version, task_id=task_id,
                status=FAILED, input_validation=input_errors,
                error={"kind": "input-validation", "message": "agent input failed schema validation",
                       "retryable": False, "errors": input_errors},
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                retry_count=retry_count,
            )

        mode = "deterministic"
        provider_meta: dict = {
            "mode": "deterministic",
            "live_verified": False,
            "provider": None,
            "model": None,
            "routing_mode": (routing_decision or {}).get("mode"),
            "note": "Deterministic agent planning. No provider was contacted.",
        }
        try:
            if executor is not None:
                raw = executor(self.spec, input_data, routing_decision or {})
                if isinstance(raw, dict) and "output" in raw:
                    output = raw.get("output")
                    mode = str(raw.get("mode") or "mocked")
                    provider_meta = {
                        "mode": mode,
                        "live_verified": mode == "live",
                        "provider": raw.get("provider"),
                        "model": raw.get("model"),
                        "routing_mode": (routing_decision or {}).get("mode"),
                        "note": ("Provider executor result. Mocked results are never "
                                 "reported as live verification."),
                    }
                else:
                    output = raw
                    mode = "mocked"
                    provider_meta = {
                        "mode": "mocked",
                        "live_verified": False,
                        "provider": (routing_decision or {}).get("selected", {}).get(
                            "provider") if routing_decision else None,
                        "model": (routing_decision or {}).get("selected", {}).get(
                            "model") if routing_decision else None,
                        "routing_mode": (routing_decision or {}).get("mode"),
                        "note": "Injected executor output; not live provider verification.",
                    }
                if mode not in ("mocked", "live"):
                    raise AgentError(f"invalid executor mode {mode!r}", kind="executor")
            else:
                output = self.deterministic_output(input_data)
        except AgentError as exc:
            return AgentResult(
                agent=self.spec.id, agent_version=self.spec.version, task_id=task_id,
                status=FAILED,
                error={"kind": exc.kind, "message": str(exc),
                       "retryable": bool(exc.retryable), "details": exc.details},
                provider=provider_meta,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                retry_count=retry_count,
            )
        except Exception as exc:  # defensive: never claim success after an exception
            return AgentResult(
                agent=self.spec.id, agent_version=self.spec.version, task_id=task_id,
                status=FAILED,
                error={"kind": "internal", "message": f"{type(exc).__name__}: {exc}",
                       "retryable": False},
                provider=provider_meta,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                retry_count=retry_count,
            )

        output_errors = validate_agent_output(self.spec, output)
        if output_errors:
            return AgentResult(
                agent=self.spec.id, agent_version=self.spec.version, task_id=task_id,
                status=FAILED, output=output, output_validation=output_errors,
                error={"kind": "output-validation",
                       "message": "agent output failed schema validation",
                       "retryable": False, "errors": output_errors},
                provider=provider_meta,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                retry_count=retry_count,
            )

        output = output or {}
        budget = {
            "estimated_input_chars": len(str(input_data)),
            "network_calls": 0 if mode == "deterministic" else None,
            "limits": (routing_decision or {}).get("constraints") or {},
        }
        return AgentResult(
            agent=self.spec.id, agent_version=self.spec.version, task_id=task_id,
            status=COMPLETED, output=output,
            summary=str(output.get("summary") or self.spec.responsibility),
            evidence=[evidence_ref(task_id, self.spec.id)],
            provider=provider_meta, budget=budget,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            assumptions=[str(x) for x in output.get("assumptions", [])][:20],
            risks=[str(x) for x in output.get("risks", [])][:20],
            requirements_addressed=[
                str(x) for x in output.get("requirements_addressed", [])][:200],
            retry_count=retry_count,
        )
