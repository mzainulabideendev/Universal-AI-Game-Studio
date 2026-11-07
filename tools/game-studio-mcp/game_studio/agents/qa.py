"""QA Agent: plan review and conflict detection; never certifies implementation."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import excluded_values, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, QA_SCHEMA


class QAAgent(Agent):
    spec = AgentSpec(
        id="qa",
        name="QA Agent",
        version="1.0.0",
        responsibility="Review coverage, dependencies and conflicts; define test evidence.",
        task_category="qa_verification",
        dependencies=("design", "architecture", "character", "environment",
                      "gameplay", "uiux"),
        required_context=("brief", "design", "architecture", "character", "environment",
                          "gameplay", "uiux"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=QA_SCHEMA,
        produces="qa",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        design = input_data.get("design") or {}
        architecture = input_data.get("architecture") or {}
        character = input_data.get("character") or {}
        environment = input_data.get("environment") or {}
        gameplay = input_data.get("gameplay") or {}
        uiux = input_data.get("uiux") or {}

        checks = []
        conflicts = []

        def add(check_id: str, category: str, status: str, evidence: str,
                remediation: str, *, conflict: bool = False, severity: str = "info",
                blocking: bool = False, requires_approval: bool = False) -> None:
            checks.append({"id": check_id, "category": category, "status": status,
                           "evidence": evidence, "remediation": remediation})
            if conflict:
                conflicts.append({
                    "id": f"C-{check_id}",
                    "category": category,
                    "severity": severity,
                    "message": remediation,
                    "blocking": blocking,
                    "requires_approval": requires_approval,
                    "source_agents": ["qa"],
                    "status": "open",
                })

        required_ids = requirement_ids(brief)
        addressed = set()
        for section in (design, gameplay, uiux):
            addressed.update(str(x) for x in section.get("requirements_addressed") or [])
        missing = [rid for rid in required_ids if rid not in addressed]
        if missing:
            add("coverage", "requirements", "fail",
                f"missing requirement ids: {missing}",
                "Assign every requirement to at least one workstream.",
                conflict=True, severity="high", blocking=True)
        else:
            add("coverage", "requirements", "pass-in-plan",
                f"{len(required_ids)} requirement ids referenced by planning agents",
                "Keep traceability current when the plan changes.")

        engine = (architecture.get("engine") or {}).get("name")
        installed = bool((architecture.get("engine") or {}).get("installed"))
        if not engine:
            add("engine-selected", "engine", "fail", "no engine selected",
                "Select a verified engine before implementation.",
                conflict=True, severity="high", blocking=True)
        elif not installed:
            add("engine-installed", "engine", "fail", f"{engine} is not detected",
                f"Install or verify {engine} before implementation.",
                conflict=True, severity="high", blocking=True)
        else:
            add("engine-installed", "engine", "pass-in-plan",
                f"{engine} was reported detected by local detection",
                "Re-check engine state immediately before any build.")

        excluded = excluded_values(brief)
        leaked = []
        for system in gameplay.get("systems") or []:
            name = str(system.get("name") or system.get("id") or "").lower()
            for item in excluded:
                if item in name:
                    leaked.append(item)
        if leaked:
            add("exclusions", "scope", "fail", f"excluded mechanics leaked: {leaked}",
                "Remove excluded mechanics from systems and input bindings.",
                conflict=True, severity="high", blocking=True)
        else:
            add("exclusions", "scope", "pass-in-plan",
                f"exclusions checked: {excluded or 'none'}",
                "Re-run the check after any mechanics change.")

        gaps = character.get("capability_gaps") or []
        if gaps:
            add("character-pipeline", "asset-pipeline", "gap",
                "; ".join(str(x) for x in gaps[:3]),
                "Phase 3 must implement and verify mesh, PBR texture, UV and rig work; "
                "Phase 2 must not claim assets exist.",
                conflict=True, severity="medium", requires_approval=True)
        else:
            add("character-pipeline", "asset-pipeline", "pass-in-plan",
                "no character capability gaps reported",
                "Verify actual asset files in a later phase.")

        estimates = environment.get("estimates") or {}
        if estimates and not estimates.get("within_budget", False):
            add("environment-budget", "performance", "fail",
                f"estimate {estimates} exceeds budget",
                "Reduce draw calls, texture resolution or prop counts before implementation.",
                conflict=True, severity="high", blocking=False, requires_approval=True)
        else:
            add("environment-budget", "performance", "pass-in-plan",
                f"environment estimates within budget: {estimates}",
                "Replace estimates with measured build data in a later phase.")

        restart_system = any("restart" in (str(s.get("id")) + str(s.get("name"))).lower()
                             for s in gameplay.get("systems") or [])
        game_over = any(s.get("id") == "game_over" for s in uiux.get("screens") or [])
        if not (restart_system and game_over):
            add("restart-flow", "ui", "fail",
                "restart system or game-over screen is missing",
                "Add a restart system and a game-over/restart screen.",
                conflict=True, severity="high", blocking=True)
        else:
            add("restart-flow", "ui", "pass-in-plan",
                "restart system and game-over screen are both planned",
                "Verify restart at runtime in a later phase.")

        add("verification-boundary", "evidence", "pass-in-plan",
            "status is not-verified; no implementation evidence exists in Phase 2",
            "Only runtime tests and human inspection may verify requirements later.")

        coverage = {
            "requirements_total": len(required_ids),
            "addressed": len(required_ids) - len(missing),
            "missing": missing,
        }
        return {
            "summary": (f"QA review found {len(conflicts)} open conflict(s); "
                        "verification status is not-verified."),
            "checks": checks,
            "coverage": coverage,
            "test_plan": [
                {"phase": "static", "test": "schema and exclusion checks",
                 "required_evidence": "audit JSON"},
                {"phase": "engine", "test": "PlayMode movement, pickup, restart tests",
                 "required_evidence": "engine test XML and build log"},
                {"phase": "runtime", "test": "human playtest of movement and camera",
                 "required_evidence": "signed runtime checklist"},
                {"phase": "visual", "test": "material and texture reference inspection",
                 "required_evidence": "asset manifest plus texture file hashes"},
            ],
            "evidence_requirements": [
                "Agent outputs validated against their JSON schemas.",
                "Engine test results produced by the engine, not synthesized.",
                "Texture files and material references verified in Phase 3.",
                "Animation playback verified at runtime before claiming animation works.",
            ],
            "conflicts": conflicts,
            "verification_status": "not-verified",
            "assumptions": [
                "QA can only review plans in Phase 2; no runtime evidence exists yet.",
            ],
            "risks": [
                "A passing plan review is not implementation verification.",
                "Asset pipeline gaps remain open until Phase 3.",
            ],
        }
