"""Gameplay Agent: controls, movement, physics, interactions and tests."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import clean_values, excluded_values, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, GAMEPLAY_SCHEMA


class GameplayAgent(Agent):
    spec = AgentSpec(
        id="gameplay",
        name="Gameplay Agent",
        version="1.0.0",
        responsibility="Plan controls, movement, physics, camera, scoring and tests.",
        task_category="technical_architecture",
        dependencies=("design", "architecture"),
        required_context=("brief", "design", "architecture"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=GAMEPLAY_SCHEMA,
        produces="gameplay",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        design = input_data.get("design") or {}
        mechanics = set(clean_values(brief, "mechanics"))
        excluded = excluded_values(brief)
        platform = set(clean_values(brief, "platform", ["pc"]))

        controls = [
            {"action": "Move", "keyboard": "WASD / Arrow keys", "gamepad": "Left stick"},
            {"action": "Look", "keyboard": "Mouse", "gamepad": "Right stick"},
            {"action": "Jump", "keyboard": "Space", "gamepad": "South button"},
            {"action": "Restart", "keyboard": "R", "gamepad": "Select"},
        ]
        if "mobile" in platform:
            controls.append({"action": "Move/Jump", "touch": "virtual joystick + jump button"})

        systems = [
            {"id": "player-movement", "name": "Player Movement",
             "reusable": True,
             "acceptance_tests": [
                 "Player moves on all ground surfaces without falling through.",
                 "Jump reaches every required platform in the level.",
             ]},
            {"id": "follow-camera", "name": "Follow Camera",
             "reusable": True,
             "acceptance_tests": [
                 "Camera follows smoothly and does not clip through walls.",
             ]},
            {"id": "collectibles", "name": "Collectible and Score",
             "reusable": True,
             "acceptance_tests": [
                 "Each pickup increments the score exactly once.",
                 "Collected pickups cannot be collected again.",
             ]},
            {"id": "restart", "name": "Restart and Reset",
             "reusable": True,
             "acceptance_tests": [
                 "Restart restores player position, score and pickups.",
             ]},
        ]
        if "physics" in mechanics or "movement" in mechanics:
            systems.append({
                "id": "physics-interaction", "name": "Physics and Collision",
                "reusable": True,
                "acceptance_tests": [
                    "Collision layers prevent the player passing through level geometry.",
                ],
            })

        for name in excluded:
            systems = [system for system in systems
                       if name not in system["id"].lower()
                       and name not in system["name"].lower()]

        return {
            "summary": f"Planned {len(systems)} reusable gameplay systems with acceptance tests.",
            "controls": controls,
            "movement": {
                "style": "third-person character controller",
                "states": ["idle", "walk", "run", "jump", "fall", "land"],
                "speed": {"walk": 2.0, "run": 5.5, "jump_height": 1.6},
                "root_motion": False,
            },
            "physics": {
                "engine": "engine-native character controller and colliders",
                "gravity": -9.81,
                "collision_layers": ["Player", "Ground", "Collectible", "Obstacle", "Trigger"],
            },
            "interactions": [
                {"id": "collect-banana", "trigger": "player enters pickup trigger",
                 "effect": "increment score; despawn pickup; play feedback"},
                {"id": "restart", "trigger": "R key or game-over action",
                 "effect": "reload the level and reset runtime state"},
            ],
            "camera": {
                "type": "follow camera", "offset": [0, 3.2, -5.5],
                "smoothing": 8.0, "collision": True,
            },
            "scoring": {
                "event": "collectible", "increment": 10,
                "persist_across_restart": False,
            },
            "progression": {
                "completion_condition": "collect all required bananas",
                "failure_condition": "no failure state unless hazards are approved",
            },
            "systems": systems,
            "acceptance_tests": [
                "PlayMode test: player moves forward within one second of input.",
                "PlayMode test: jump and ground detection remain stable.",
                "PlayMode test: collecting three pickups yields a score of 30.",
                "PlayMode test: restart returns score to zero.",
                "Static check: excluded mechanics have no input bindings or code paths.",
            ],
            "exclusions": excluded,
            "requirements_addressed": requirement_ids(brief),
            "assumptions": [
                "One playable level is sufficient unless the user requests more.",
                "Keyboard and mouse are the primary PC input method.",
            ],
            "risks": [
                "No gameplay script was implemented in Phase 2; all acceptance tests are "
                "planned, not executed.",
                "Camera and jump values require tuning against the real level geometry.",
            ],
        }
