"""Game Director Agent: brief coordination and final plan consolidation."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import clean_values, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, BRIEF_SCHEMA, DIRECTOR_SCHEMA
from .workflow import dependency_graph, parallel_groups


class GameDirectorAgent(Agent):
    spec = AgentSpec(
        id="game_director",
        name="Game Director",
        version="1.0.0",
        responsibility="Coordinate the workflow, resolve dependencies and consolidate the plan.",
        task_category="game_design_reasoning",
        dependencies=("qa",),
        required_context=("brief", "design", "architecture", "character", "environment",
                          "gameplay", "uiux", "qa"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=DIRECTOR_SCHEMA,
        produces="consolidation",
    )

    def create_brief(self, *, request: str, understanding: dict,
                     quality_target: str = "prototype",
                     engine_hint: str | None = None,
                     installed_engines: list[str] | None = None) -> dict:
        raw = understanding.get("understanding") or {}
        brief = {
            "request": request,
            "summary": understanding.get("summary") or request[:240],
            "genre": list(raw.get("game_genre") or []),
            "dimension": list(raw.get("dimension") or []),
            "platform": list(raw.get("target_platform") or []),
            "characters": list(raw.get("characters") or []),
            "environment": list(raw.get("environment") or []),
            "mechanics": list(raw.get("mechanics") or []),
            "exclusions": list(understanding.get("exclusions") or []),
            "requirements": list(
                (understanding.get("requirements") or {}).get("explicit") or [])
                + list((understanding.get("requirements") or {}).get("implied") or [])
                + list((understanding.get("requirements") or {}).get("technical") or []),
            "assumptions": list(understanding.get("assumptions") or []),
            "conflicts": list(understanding.get("conflicts") or []),
            "quality_target": quality_target,
            "engine_hint": engine_hint or "",
            "installed_engines": list(installed_engines or []),
        }
        errors = []
        from ..llm.schemas import validate
        errors = validate(brief, BRIEF_SCHEMA)
        if errors:
            raise ValueError(f"brief failed validation: {errors}")
        return brief

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        design = input_data.get("design") or {}
        architecture = input_data.get("architecture") or {}
        character = input_data.get("character") or {}
        environment = input_data.get("environment") or {}
        gameplay = input_data.get("gameplay") or {}
        uiux = input_data.get("uiux") or {}
        qa = input_data.get("qa") or {}

        engine = (architecture.get("engine") or {})
        conflicts = list(qa.get("conflicts") or [])
        if engine and not engine.get("installed"):
            conflicts.append({
                "id": "C-engine-not-installed",
                "category": "engine",
                "severity": "high",
                "message": (f"Recommended engine {engine.get('name')!r} is not detected; "
                            "implementation is blocked."),
                "blocking": True,
                "requires_approval": True,
                "source_agents": ["technical_architect", "qa"],
                "status": "open",
            })

        open_questions = []
        open_questions.extend(str(x) for x in design.get("missing_requirements") or [])
        missing = (qa.get("coverage") or {}).get("missing") or []
        if missing:
            open_questions.append(f"Requirements without coverage: {missing}")
        if any(item.get("blocking") for item in conflicts):
            open_questions.append("Resolve blocking conflicts before implementation.")

        workstreams = [
            {"id": "design", "owner": "game_designer",
             "deliverable": "game design", "status": "planned"},
            {"id": "architecture", "owner": "technical_architect",
             "deliverable": "technical architecture", "status": "planned"},
            {"id": "character", "owner": "character",
             "deliverable": "character asset plan", "status": "planned"},
            {"id": "environment", "owner": "environment",
             "deliverable": "environment plan", "status": "planned"},
            {"id": "gameplay", "owner": "gameplay",
             "deliverable": "gameplay tasks", "status": "planned"},
            {"id": "uiux", "owner": "uiux",
             "deliverable": "UI/UX plan", "status": "planned"},
            {"id": "qa", "owner": "qa", "deliverable": "test plan and conflicts",
             "status": "reviewed-in-plan"},
        ]
        milestones = [
            {"id": "M1", "name": "Approved plan", "depends_on": [],
             "exit_criteria": ["brief validated", "no blocking conflict"]},
            {"id": "M2", "name": "Playable movement slice",
             "depends_on": ["M1"], "exit_criteria": [
                 "engine project exists", "PlayMode movement test passes"]},
            {"id": "M3", "name": "Gameplay and UI",
             "depends_on": ["M2"], "exit_criteria": [
                 "pickup/score test passes", "restart test passes"]},
            {"id": "M4", "name": "Character and environment assets",
             "depends_on": ["M3"], "exit_criteria": [
                 "asset manifests exist", "texture references validated",
                 "animation playback tested"]},
            {"id": "M5", "name": "Verified build",
             "depends_on": ["M4"], "exit_criteria": [
                 "Windows build succeeds", "runtime evidence collected",
                 "human playtest complete"]},
        ]

        return {
            "summary": (f"Consolidated a non-executable plan for {brief.get('summary', '')} "
                        f"on {engine.get('name', 'an unselected engine')}; "
                        f"{len(conflicts)} open conflict(s)."),
            "project": {
                "name": "planned-project",
                "request": brief.get("request"),
                "engine": engine.get("name"),
                "platform": clean_values(brief, "platform"),
                "quality_target": brief.get("quality_target"),
                "planned_assets": len(character.get("characters") or []),
                "planned_screens": len(uiux.get("screens") or []),
                "planned_systems": len(gameplay.get("systems") or []),
            },
            "milestones": milestones,
            "workstreams": workstreams,
            "dependency_graph": dependency_graph(),
            "parallel_groups": parallel_groups(),
            "conflicts": conflicts,
            "open_questions": open_questions,
            "approval_required": [
                "Approve the plan before implementation.",
                "Approve any paid provider use separately.",
                "Approve asset generation and engine writes separately.",
                "Resolve all blocking conflicts.",
            ],
            "executable": False,
            "implementation_status": "planned-not-implemented",
            "requirements_addressed": sorted(set(
                requirement_ids(brief)
                + [str(x) for x in design.get("requirements_addressed") or []])),
            "assumptions": [
                "All agents received only their declared context.",
                "No engine, Blender, asset or provider write occurred in Phase 2.",
            ],
            "risks": [
                "The plan is not a playable game and does not verify any requirement.",
                "Asset generation, textures and animation remain Phase 3 work.",
                "Engine build and runtime verification remain later phases.",
            ],
        }
