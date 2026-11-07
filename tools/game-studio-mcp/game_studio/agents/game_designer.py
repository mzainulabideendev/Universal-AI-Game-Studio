"""Game Designer agent: genre, loop, objectives, progression and tests."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import clean_values, excluded_values, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, DESIGN_SCHEMA


class GameDesignerAgent(Agent):
    spec = AgentSpec(
        id="game_designer",
        name="Game Designer",
        version="1.0.0",
        responsibility="Design the gameplay loop, objectives, progression and acceptance tests.",
        task_category="game_design_reasoning",
        dependencies=(),
        required_context=("brief",),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=DESIGN_SCHEMA,
        produces="design",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        genre = clean_values(brief, "genre", ["adventure"])
        mechanics = clean_values(brief, "mechanics", ["movement", "collectibles", "score"])
        excluded = excluded_values(brief)
        dimension = clean_values(brief, "dimension", ["3d"])
        platform = clean_values(brief, "platform", ["pc"])
        characters = clean_values(brief, "characters")
        environment = clean_values(brief, "environment")

        core_loop = [
            "Spawn in the level with a clear objective visible in the HUD.",
            "Explore and traverse the environment using the primary movement set.",
        ]
        if "collectibles" in mechanics:
            core_loop.append("Find and collect the requested pickups.")
        if "score" in mechanics:
            core_loop.append("Update score and pickup feedback immediately.")
        core_loop.append("Reach the completion condition or restart from the game-over state.")

        objectives = []
        if "collectibles" in mechanics:
            objectives.append("Collect every required pickup in the level.")
        objectives.append("Reach the level exit or completion trigger without violating exclusions.")
        objectives.append("Restart cleanly after failure or manual restart.")

        progression = [
            "Milestone 1: playable movement and camera in a test scene.",
            "Milestone 2: collectibles, scoring and HUD.",
            "Milestone 3: environment dressing and character presentation.",
            "Milestone 4: restart flow, automated tests and build verification.",
        ]

        missing = []
        if not characters:
            missing.append("No player character was specified; a generic player is assumed.")
        if not brief.get("target_resolution"):
            missing.append("Target resolution and display mode are not specified.")
        if "collectibles" in mechanics and not any(
                term in " ".join(mechanics) for term in ("count", "target", "goal")):
            missing.append("Pickup target count is not specified.")

        risks = []
        if excluded:
            risks.append("Explicit exclusions must remain out of the design: "
                         + ", ".join(excluded))
        if "multiplayer" in mechanics:
            risks.append("Multiplayer scope is not assumed; networking requires separate approval.")
        if "mobile" in platform and "pc" in platform:
            risks.append("Cross-platform input and performance must be validated separately.")

        assumptions = list(brief.get("assumptions") or [])
        if "prototype" == brief.get("quality_target"):
            assumptions.append("Prototype quality target is assumed unless changed by the user.")

        return {
            "summary": f"{' '.join(dimension).upper()} {'/'.join(genre)} design for "
                       f"{', '.join(platform)}.",
            "genre": genre,
            "dimension": dimension,
            "platform": platform,
            "core_loop": core_loop,
            "mechanics": mechanics,
            "objectives": objectives,
            "progression": progression,
            "exclusions": excluded,
            "missing_requirements": missing,
            "acceptance_tests": [
                "Player can move using the documented controls.",
                "Camera follows the player without clipping through the level.",
                "Collecting a pickup increments the score exactly once.",
                "Restart returns gameplay, score and pickups to the initial state.",
                "Excluded mechanics are absent from input bindings, UI and gameplay code.",
            ],
            "requirements_addressed": requirement_ids(brief),
            "assumptions": assumptions[:20],
            "risks": risks[:20],
        }
