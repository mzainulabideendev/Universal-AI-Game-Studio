#!/usr/bin/env python3
"""V6 Phase 1 provider report generator (configuration-only).

Performs no network request, no paid call, reads no credential value and changes
no V4/V5 file. It writes:

* reports/v6-provider-capabilities.json
* reports/v6-provider-routing.json

Run: python scripts/v6-phase1-report.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
OUT_DIR = ROOT / "reports"
sys.path.insert(0, str(SERVER_DIR))

from game_studio.llm import capabilities, catalog, routing  # noqa: E402
from game_studio.llm import config as llm_config  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def capability_payload() -> dict:
    report = capabilities.capability_report()
    statuses = [catalog.provider_status(name) for name in llm_config.PROVIDERS]
    return {
        "schema_version": 1,
        "phase": "V6 Phase 1 - AI provider architecture",
        "generated_at": now(),
        "mode": "configuration-only",
        "network_calls": 0,
        "live_verified": None,
        "credential_values_included": False,
        "states": report["states"],
        "capability_keys": report["capability_keys"],
        "task_categories": report["task_categories"],
        "providers": report["providers"],
        "provider_status": statuses,
        "model_level": report["model_level"],
        "discovery": {
            "endpoints": {
                "openai": "GET {base_url}/models",
                "openai_compatible": "GET {base_url}/models",
                "anthropic": "GET {base_url}/models?limit=100",
                "gemini": "GET {base_url}/models?pageSize=200",
                "ollama": "GET {base_url}/api/tags (loopback HTTP allowed)",
            },
            "requires": "llm_list_models with confirm=true (one read-only request)",
            "capability_metadata": (
                "Gemini documents supportedGenerationMethods and inputTokenLimit. "
                "OpenAI-compatible and Anthropic list ids only. Ollama tags do not "
                "declare capabilities, so they stay unknown."
            ),
        },
        "ollama": catalog.ollama_detection(),
        "limitations": [
            "No live provider request was made while producing this report.",
            "Provider-level states describe adapter implementation, not vendor features.",
            "Tool calling, vision, streaming and embeddings are unsupported by every "
            "adapter in this repository.",
            "Anthropic structured output is unsupported because no documented JSON mode "
            "is sent by the adapter.",
            "Context window is unknown unless discovery exposes token limits.",
            "Mocked tests prove code paths only, never live provider behaviour.",
        ],
    }


def routing_payload() -> dict:
    strict = routing.routing_matrix(allow_paid=False, require_known=False)
    known = routing.routing_matrix(allow_paid=False, require_known=True)
    paid = routing.routing_matrix(allow_paid=True, require_known=False)
    return {
        "schema_version": 1,
        "phase": "V6 Phase 1 - AI provider architecture",
        "generated_at": now(),
        "mode": "configuration-only",
        "network_calls": 0,
        "live_verified": None,
        "policy": {
            "unsupported_capability": "rejected",
            "unknown_capability": "allowed with unverified warning (rejected when "
                                  "require_known=true)",
            "paid_switch": "never automatic",
            "fallback": "deterministic parser in game_studio.understanding",
            "paid_opt_in": "allow_paid=true is explicit approval to consider hosted providers",
        },
        "matrices": {
            "default_no_paid": strict,
            "require_known_capabilities": known,
            "explicit_paid_approval": paid,
        },
        "task_decisions": [
            {
                "task": task,
                "required_capabilities": info["required_capabilities"],
                "default": routing.route(task)["selected"],
                "default_mode": routing.route(task)["mode"],
                "with_paid_approval_mode": routing.route(
                    task, allow_paid=True)["mode"],
            }
            for task, info in capabilities.TASK_CATEGORIES.items()
        ],
        "constraints": {
            "max_tokens_per_request": llm_config.load_config()["max_tokens"],
            "max_context_chars": llm_config.load_config()["max_context_chars"],
            "max_requests_per_session": llm_config.load_config()["max_requests"],
            "max_requests_per_day": llm_config.load_config()["max_requests_per_day"],
            "retries": llm_config.load_config()["retries"],
            "timeout_seconds": llm_config.load_config()["timeout_seconds"],
        },
        "note": ("Routing is a configuration decision. It does not verify reachability "
                 "or output quality."),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cap_path = OUT_DIR / "v6-provider-capabilities.json"
    route_path = OUT_DIR / "v6-provider-routing.json"
    capabilities_data = capability_payload()
    routing_data = routing_payload()
    cap_path.write_text(json.dumps(capabilities_data, indent=2) + "\n", encoding="utf-8")
    route_path.write_text(json.dumps(routing_data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "capabilities_report": str(cap_path),
        "routing_report": str(route_path),
        "providers": len(capabilities_data["providers"]),
        "tasks": len(capabilities_data["task_categories"]),
        "network_calls": 0,
        "live_verified": None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
