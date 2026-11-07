#!/usr/bin/env python3
"""V6 Phase 2 zero-network multi-agent orchestration demonstration.

Runs the eight typed agents through the coordinator using deterministic planning
only. No provider, engine, Blender, asset pipeline or paid service is contacted.
The written report is evidence of orchestration, not of a generated game.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "tools" / "game-studio-mcp"
OUT = ROOT / "reports" / "v6-phase2-demo.json"

REQUEST = (
    "Create a professional 3D jungle adventure game for Windows PC. The player "
    "controls a monkey that can run, jump, and collect bananas. Include a detailed "
    "jungle environment, character assets, follow camera, score HUD, and restart "
    "functionality."
)

ZERO_NETWORK_ENV = {
    "GAME_STUDIO_LLM_PROVIDER": "",
    "GAME_STUDIO_LLM_MODEL": "",
    "GAME_STUDIO_LLM_BASE_URL": "",
    "GAME_STUDIO_LLM_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
    "GAME_STUDIO_LLM_LOCAL_ONLY": "true",
}


def main(output: str | None = None) -> int:
    for key, value in ZERO_NETWORK_ENV.items():
        os.environ[key] = value
    sys.path.insert(0, str(SERVER_DIR))

    from game_studio.agents import Orchestrator, registry_report  # noqa: E402

    out = Path(output) if output else OUT
    orchestrator = Orchestrator(
        REQUEST, installed_engines=["unity"], quality_target="prototype",
        concurrency=2, max_retries=0, use_provider=False)
    report = orchestrator.run()

    stages = []
    for task in report["tasks"]:
        run = next(item for item in report["agent_runs"]
                   if item["task_id"] == task["id"])
        stages.append({
            "step": task["id"],
            "agent": task["agent"],
            "agent_version": run["agent_version"],
            "status": task["status"],
            "dependencies": task["dependencies"],
            "provider_mode": run["provider"]["mode"],
            "duration_ms": run["duration_ms"],
            "evidence": [ref["ref"] for ref in run["evidence"]],
            "summary": run["summary"],
        })

    demo = {
        "schema_version": 1,
        "phase": "V6 Phase 2 - multi-agent orchestration demonstration",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": REQUEST,
        "mode": "deterministic-zero-network",
        "network_calls": 0,
        "live_provider_verified": False,
        "outputs_are_plans_only": True,
        "game_generated": False,
        "assets_generated": False,
        "textures_animated_or_built": False,
        "executable": report["executable"],
        "status": report["status"],
        "ok": report["ok"],
        "engine": (report["outputs"].get("architecture", {})
                   .get("engine", {}).get("name")),
        "agent_count": registry_report()["agent_count"],
        "stages": stages,
        "diagnostics": report["diagnostics"],
        "routing": report["routing"],
        "conflicts": report["conflicts"],
        "approval_required": report["approval_required"],
        "governance": report["governance"],
        "provider_summary": report["provider_summary"],
        "consolidated_summary": (report["consolidated"] or {}).get("summary"),
        "limitations": report["limitations"],
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(demo, indent=2) + "\n", encoding="utf-8")

    print(f"status={demo['status']} ok={demo['ok']} engine={demo['engine']}")
    for stage in stages:
        print(f"  {stage['step']:<14} {stage['agent']:<20} {stage['status']}")
    print(f"conflicts={[c['id'] for c in demo['conflicts']]}")
    print(f"provider={demo['provider_summary']['mode']} "
          f"live_verified={demo['provider_summary']['live_verified']}")
    print(f"executable={demo['executable']} game_generated={demo['game_generated']}")
    print(f"report={out}")

    ok = (demo["status"] == "completed" and demo["executable"] is False
          and len(stages) == 8
          and all(stage["status"] == "completed" for stage in stages))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
