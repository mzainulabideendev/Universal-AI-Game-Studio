#!/usr/bin/env python3
"""End-to-end demonstration of the V4 LLM reasoning pipeline.

Default mode is OFFLINE and DETERMINISTIC:

* no provider, network, key or paid API is used;
* every LLM-only result is labelled as a deterministic fallback;
* no project file is written unless ``--project`` and ``--confirm`` are given.

Optional modes:

* ``--mock-llm``  runs the LLM code path with an in-process mocked provider.
                  The output is explicitly labelled ``mocked``. It proves the
                  plumbing, not model quality.
* ``--live``      sends one real request per step to the configured provider.
                  Requires ``--confirm`` and a configured key/local model.
                  Paid usage is the user's explicit choice.

The script never claims the game is implemented. It ends with an execution
plan that still needs governance approval and real MCP tool calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "game-studio-mcp"))

from game_studio import manifest  # noqa: E402
from game_studio.llm import reasoning  # noqa: E402
from game_studio.llm.client import LLMClient  # noqa: E402

REQUEST = ("Create a realistic 3D monkey adventure game for Android. The monkey can "
           "run, jump, climb trees, swing between branches, swim in rivers and collect "
           "bananas. Include multiple jungle environments, day-night cycles, weather "
           "changes, wildlife, progression and mobile-friendly controls. No weapons.")


class MockProvider:
    """In-process mock used only by --mock-llm. Never opens a socket."""

    def __init__(self, response: dict):
        self.response = response

    def complete(self, messages, *, system=None, max_tokens=2048, temperature=0.2,
                 json_mode=False, timeout=60):
        return {"text": json.dumps(self.response),
                "usage": {"prompt_tokens": 100, "completion_tokens": 200,
                          "total_tokens": 300},
                "model": "mock-model", "raw_meta": {}}


def mock_client(response: dict) -> LLMClient:
    client = LLMClient()
    client.provider = MockProvider(response)
    return client


def mock_understanding() -> dict:
    return {
        "schema_version": "1.1",
        "summary": "A realistic 3D monkey adventure across jungle islands on Android.",
        "genre": "adventure",
        "subgenre": "exploration",
        "dimension": "3d",
        "platforms": ["android"],
        "engine_recommendation": {"engine": "unity",
                                  "reason": "mature mobile tooling and C# iteration",
                                  "confidence": 0.85},
        "art_direction": "stylised realism, readable silhouettes on mobile",
        "language": "english",
        "confidence": 0.85,
        "requirements": [
            {"id": "R001", "category": "movement",
             "statement": "The monkey can run, jump, climb trees and swing between branches",
             "source_text": "climb trees, swing between branches",
             "classification": "explicit", "priority": "P0",
             "acceptance_test": "Each traversal action works on tagged geometry"},
            {"id": "R002", "category": "movement",
             "statement": "The monkey can swim in rivers",
             "source_text": "swim in rivers", "classification": "explicit",
             "priority": "P0", "acceptance_test": "Swimming enters, moves and exits water"},
            {"id": "R003", "category": "collectible",
             "statement": "Bananas unlock new abilities",
             "source_text": "collect bananas", "classification": "explicit",
             "priority": "P1", "acceptance_test": "Collecting reaches the unlock threshold"},
            {"id": "R004", "category": "world",
             "statement": "Day-night cycle and weather changes",
             "source_text": "day-night cycles, weather changes",
             "classification": "explicit", "priority": "P1",
             "acceptance_test": "Time and weather change visibly and affect ambience"},
            {"id": "R005", "category": "platform",
             "statement": "Smooth Android performance with mobile controls",
             "source_text": "Android ... mobile-friendly controls",
             "classification": "explicit", "priority": "P0",
             "acceptance_test": "Target device sustains the agreed frame budget"},
            {"id": "R006", "category": "exclusion",
             "statement": "No weapons",
             "source_text": "No weapons", "classification": "excluded",
             "priority": "P0", "acceptance_test": "No weapon system exists"},
        ],
        "core_loop": ["explore islands", "traverse", "collect bananas", "unlock"],
        "abilities": ["run", "jump", "climb", "swing", "swim"],
        "character": {"type": "monkey", "description": "playable monkey"},
        "environment": "multiple jungle islands with rivers",
        "animation_needs": ["run", "jump", "climb", "swing", "swim", "idle"],
        "physics_needs": ["climbable surfaces", "branch swing constraint", "water buoyancy"],
        "ai_needs": ["wildlife behaviour"],
        "ui_needs": ["mobile touch controls", "ability unlock UI"],
        "audio_needs": ["jungle ambience", "weather layers"],
        "save_system": "progression save",
        "performance_targets": ["mobile frame budget", "memory budget"],
        "exclusions": ["weapons"],
        "conflicts": [],
        "assumptions": ["single-player", "offline-first"],
        "questions": [{"question": "Is multiplayer required?",
                       "why_it_matters": "it changes networking architecture and cost"}],
        "risks": ["creature animation coverage", "mobile thermal budget"],
        "technical_dependencies": ["climbable surface tagging", "water volumes",
                                   "rig with climb/swim clips"],
        "uncertainty": ["exact target device tier is unknown"],
    }


def mock_spec() -> dict:
    return {
        "schema_version": "1.0",
        "overview": "A mobile 3D jungle traversal adventure starring a monkey.",
        "engine": {"selected": "unity"},
        "art_direction": "stylised realism with strong readability",
        "core_loop": ["explore", "traverse", "collect", "unlock"],
        "milestones": [
            {"id": "A", "name": "Foundation", "gate": "project builds"},
            {"id": "B", "name": "Vertical slice", "gate": "traversal loop playable"},
        ],
        "acceptance_criteria": ["monkey climbs, swings and swims",
                                "Android build runs on a real device"],
        "risks": ["animation coverage", "mobile performance"],
        "unresolved_questions": ["Is multiplayer required?"],
        "technical_dependencies": ["climbable surface tagging", "water volumes"],
    }


def mock_architecture() -> dict:
    return {
        "schema_version": "1.0",
        "summary": "Traversal-first architecture with streaming jungle islands.",
        "core_experience": "playful exploration and movement mastery",
        "systems": [
            {"id": "S001", "name": "Monkey locomotion",
             "responsibility": "run, jump, climb, swing, swim state machine",
             "requirement_ids": ["R001", "R002"], "depends_on": [],
             "engine_notes": "Unity CharacterController plus custom states"},
            {"id": "S002", "name": "Progression",
             "responsibility": "banana collection and ability unlocks",
             "requirement_ids": ["R003"], "depends_on": ["S001"],
             "engine_notes": "ScriptableObject data"},
        ],
        "dependency_edges": [{"from": "S002", "to": "S001",
                              "reason": "progression depends on traversal"}],
        "asset_plan": [{"asset": "monkey rig", "purpose": "player",
                        "source": "blender"}],
        "animation_plan": [{"clip": "climb", "purpose": "traversal"},
                           {"clip": "swim", "purpose": "water"}],
        "milestones": [{"id": "A", "name": "Foundation", "gate": "project builds"}],
        "risks": ["non-humanoid rig retargeting"],
        "next_actions": ["blockout one island", "verify traversal on device"],
        "assumptions": ["offline single-player"],
        "questions": [],
    }


def mock_ambiguity() -> dict:
    return {
        "schema_version": "1.0",
        "blocking": False,
        "summary": "Only one material question remains.",
        "ambiguities": [{"area": "multiplayer",
                         "issue": "multiplayer not mentioned",
                         "impact": "architecture",
                         "safe_default": "single-player offline"}],
        "questions": [{"question": "Is multiplayer required?",
                       "why_it_matters": "networking changes architecture and cost",
                       "options": ["No", "Local co-op", "Online"],
                       "default": "No"}],
        "assumptions": ["single-player", "offline-first"],
    }


def mock_engine() -> dict:
    return {
        "schema_version": "1.0",
        "recommendation": "unity",
        "reason": "mature mobile tooling and C# iteration",
        "confidence": 0.85,
        "candidates": [
            {"engine": "unity", "fit": "strong",
             "reason": "mobile tooling and asset ecosystem", "risks": []},
            {"engine": "unreal", "fit": "partial",
             "reason": "high fidelity but heavy for mobile", "risks": ["thermals"]},
            {"engine": "godot", "fit": "partial",
             "reason": "lightweight but smaller ecosystem", "risks": ["asset gaps"]},
        ],
        "platform_constraints": ["memory and thermal budgets"],
        "verification_needed": ["run detect_game_engines", "verify a real build"],
    }


def run(mode: str, confirm: bool, project_path: str | None) -> dict:
    provider = {"offline": "deterministic-fallback", "mock": "mocked",
                "live": "live"}[mode]
    if mode == "mock":
        # A mocked provider still goes through the real config/permission checks.
        # Ollama has no credential requirement, so use it as the transport profile
        # while the in-process MockProvider supplies the responses.
        import os
        os.environ["GAME_STUDIO_LLM_PROVIDER"] = "ollama"
    steps: dict = {}
    clients = {
        "mock": {
            "understanding": lambda: mock_client(mock_understanding()),
            "specification": lambda: mock_client(mock_understanding()),
            "architecture": lambda: mock_client(mock_architecture()),
            "ambiguity": lambda: mock_client(mock_ambiguity()),
            "engine": lambda: mock_client(mock_engine()),
        }
    }

    def client_for(step: str) -> LLMClient | None:
        if mode == "mock":
            return clients["mock"][step]()
        if mode == "live":
            return LLMClient()
        return None

    # 1. Natural-language understanding.
    understood = reasoning.understand_request(
        REQUEST, confirm=(mode != "offline"), client=client_for("understanding"))
    steps["1_natural_language_understanding"] = {
        "source": understood.get("source"),
        "summary": (understood.get("understanding") or {}).get("summary")
        or (understood.get("analysis") or {}).get("summary"),
        "confidence": understood.get("confidence"),
        "prompt_injection_suspected": understood.get("prompt_injection_suspected"),
    }

    # 2. Structured requirements.
    trace = understood.get("traceability") or {}
    steps["2_structured_requirements"] = {
        "counts": trace.get("counts"),
        "requirements": [
            {"id": item["id"], "classification": item["classification"],
             "priority": item["priority"], "statement": item["statement"],
             "source_text": item["source_text"]}
            for item in (trace.get("requirements") or [])[:12]
        ],
    }

    # 3. Technical reasoning.
    architecture = reasoning.plan_game_architecture(
        REQUEST,
        understanding_data=understood.get("understanding") or {},
        client=client_for("architecture"),
        confirm=(mode != "offline"),
        allow_fallback=True,
    )
    steps["3_technical_reasoning"] = {
        "source": architecture.get("source"),
        "systems": [s.get("name") for s in
                    (architecture.get("architecture") or {}).get("systems") or []],
        "risks": (architecture.get("architecture") or {}).get("risks"),
    }

    # 4. Engine recommendation.
    engine = reasoning.reason_about_engine_compatibility(
        REQUEST, platform="android",
        understanding_data=understood.get("understanding") or {},
        installed_engines=[],
        client=client_for("engine"),
        confirm=(mode != "offline"),
        allow_fallback=True,
    )
    engine_payload = engine.get("engine_reasoning") or engine
    steps["4_engine_recommendation"] = {
        "source": engine.get("source"),
        "recommendation": engine_payload.get("recommendation"),
        "reason": engine_payload.get("reason"),
        "installed_verified": engine.get("installed_verified"),
        "note": "A recommendation is not proof that the engine is installed.",
    }

    # 5. Specification generation (deterministic structure + LLM additions).
    if mode == "mock":
        from game_studio.llm.client import LLMClient as _Client
        class SequenceProvider:
            def __init__(self):
                self.calls = 0
            def complete(self, messages, **kwargs):
                self.calls += 1
                payload = mock_understanding() if self.calls == 1 else mock_spec()
                return {"text": json.dumps(payload),
                        "usage": {"total_tokens": 300}, "model": "mock-model",
                        "raw_meta": {}}
        client = _Client()
        client.provider = SequenceProvider()
    else:
        client = client_for("specification")
    spec = reasoning.generate_specification(
        REQUEST, confirm=(mode != "offline"), client=client,
        project_name="Monkey Isle", platform="mobile", dimension="3d",
        engine="unity", approved=True, allow_fallback=True)
    steps["5_game_specification"] = {
        "source": spec.get("llm_layer", {}).get("source")
        or ("llm" if spec.get("llm_layer", {}).get("used") else "deterministic"),
        "engine": (spec.get("engine") or {}).get("selected"),
        "requirement_count": len(spec.get("requirements") or []),
        "status": spec.get("status"),
        "note": spec.get("llm_layer", {}).get("note"),
    }

    # 6. Dependency graph.
    graph = spec.get("dependency_graph") or {}
    steps["6_dependency_graph"] = {
        "nodes": len(graph.get("nodes") or []),
        "edges": len(graph.get("edges") or []),
        "deterministic": True,
    }

    # 7. Clarification detection.
    ambiguity = reasoning.analyze_ambiguities(
        REQUEST,
        understanding_data=understood.get("understanding") or {},
        client=client_for("ambiguity"),
        confirm=(mode != "offline"),
        allow_fallback=True,
    )
    steps["7_clarification_detection"] = {
        "source": ambiguity.get("source"),
        "blocking": (ambiguity.get("ambiguity") or {}).get("blocking"),
        "questions": ambiguity.get("questions"),
    }

    # 8. Approval workflow.
    steps["8_user_approval_workflow"] = {
        "specification_status": spec.get("status"),
        "approved": spec.get("approved"),
        "note": ("This demo passes approved=true only to demonstrate the workflow. "
                 "A real project must record the user's explicit approval."),
    }

    # 9. Manifest creation (only on explicit request).
    if project_path:
        if not confirm:
            steps["9_project_manifest"] = {
                "written": False,
                "reason": "--confirm is required to write a manifest",
            }
        else:
            created = manifest.init_manifest(project_path, spec, confirm=True)
            steps["9_project_manifest"] = {
                "written": True,
                "path": created.get("path"),
                "requirements": created.get("requirements"),
                "note": "Only the manifest was written; no gameplay code or assets.",
            }
    else:
        steps["9_project_manifest"] = {
            "written": False,
            "reason": "no --project path supplied; nothing was written",
        }

    # 10. MCP execution plan.
    execution = reasoning.build_execution_plan(
        spec, understanding_data=understood.get("understanding") or {})
    steps["10_mcp_execution_plan"] = {
        "executable": execution["executable"],
        "counts": execution["counts"],
        "approval": execution["approval"],
        "steps": [
            {"tool": step["tool"], "phase": step["phase"],
             "cost": step["cost"], "blocked": step["blocked"],
             "requires_confirm": step["requires_confirm"]}
            for step in execution["steps"]
        ],
        "validation": execution.get("validation"),
    }

    # Extra: traceability and plan validation.
    validation = reasoning.validate_generated_plan(
        spec, request=REQUEST,
        understanding_data=understood.get("understanding") or {})
    steps["validation"] = {
        "verdict": validation["verdict"],
        "issues": validation["deterministic"]["issues"],
        "unverified_claims": validation["deterministic"]["unverified_claims"],
    }

    return {
        "ok": True,
        "provider_mode": provider,
        "mocked_provider": mode == "mock",
        "request": REQUEST,
        "steps": steps,
        "implementation_claimed": False,
        "limitations": [
            "This demonstration produces a plan and an execution plan only.",
            "No Blender, engine, asset download, gameplay test or build was run.",
            "Offline mode uses the deterministic parser and says so.",
            "Mocked mode proves integration plumbing, not model quality.",
            "A playable game is not claimed until real engine operations and tests exist.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock-llm", action="store_true",
                       help="run the LLM code path with a labelled mocked provider")
    group.add_argument("--live", action="store_true",
                       help="use the configured provider (real, possibly paid)")
    parser.add_argument("--confirm", action="store_true",
                        help="approve live provider requests and manifest writes")
    parser.add_argument("--project", help="optional project path for manifest creation")
    parser.add_argument("--json", action="store_true", help="print raw JSON only")
    args = parser.parse_args()

    mode = "mock" if args.mock_llm else ("live" if args.live else "offline")
    if mode == "live" and not args.confirm:
        print("Refusing live mode without --confirm: a real provider request may cost "
              "money.", file=sys.stderr)
        return 2
    if args.project and not args.confirm:
        print("Warning: --project without --confirm will not write a manifest.",
              file=sys.stderr)

    report = run(mode, args.confirm, args.project)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("UNIVERSAL AI GAME STUDIO — V4 reasoning pipeline demonstration")
    print(f"Provider mode: {report['provider_mode']}")
    print(f"Mocked provider: {report['mocked_provider']}")
    print("Implementation claimed: no")
    print()
    for name, payload in report["steps"].items():
        print(f"[{name}]")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print()
    print("LIMITATIONS")
    for item in report["limitations"]:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
