"""UI/UX Agent: menus, HUD, settings, accessibility and navigation."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import clean_values, requirement_ids
from .schemas import AGENT_INPUT_SCHEMA, UIUX_SCHEMA


class UIUXAgent(Agent):
    spec = AgentSpec(
        id="uiux",
        name="UI/UX Agent",
        version="1.0.0",
        responsibility="Plan menus, HUD, settings, pause, accessibility and navigation.",
        task_category="game_design_reasoning",
        dependencies=("design", "gameplay"),
        required_context=("brief", "design", "gameplay"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=UIUX_SCHEMA,
        produces="uiux",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        gameplay = input_data.get("gameplay") or {}
        mechanics = clean_values(brief, "mechanics")

        screens = [
            {"id": "main_menu", "purpose": "Start the game or open settings",
             "widgets": ["Start", "Settings", "Quit"], "navigation": ["game", "settings"]},
            {"id": "game_hud", "purpose": "Show score and objective feedback",
             "widgets": ["Score", "Objective", "Hint"], "navigation": []},
            {"id": "pause", "purpose": "Pause, resume, restart or return to menu",
             "widgets": ["Resume", "Restart", "Settings", "Main Menu"],
             "navigation": ["game", "settings", "main_menu"]},
            {"id": "game_over", "purpose": "Show result and restart",
             "widgets": ["Final Score", "Restart", "Main Menu"],
             "navigation": ["game", "main_menu"]},
            {"id": "settings", "purpose": "Adjust audio, display and controls",
             "widgets": ["Volume", "Resolution", "Fullscreen", "Sensitivity", "Back"],
             "navigation": ["main_menu", "pause"]},
        ]

        hud = ["Score value updates on pickup"]
        if "collectibles" in mechanics:
            hud.append("Pickup progress or remaining count")
        hud.append("Objective reminder for the current level")

        return {
            "summary": f"Planned {len(screens)} screens with HUD, settings and accessibility.",
            "screens": screens,
            "hud": hud,
            "settings": ["Master volume", "Music volume", "SFX volume", "Resolution",
                         "Fullscreen/windowed", "Mouse sensitivity", "Invert Y"],
            "accessibility": [
                "Remappable keyboard controls",
                "Scalable HUD text",
                "High-contrast score display",
                "Subtitles/captions for any dialogue or audio cues",
                "No colour-only state communication",
            ],
            "navigation": [
                "Main Menu -> Game",
                "Game -> Pause -> Settings -> Game",
                "Game -> Game Over -> Restart",
                "Game Over -> Main Menu",
            ],
            "dependencies": [
                "Score and collectible events from the Gameplay Agent",
                "Scene loading from the Technical Architect",
                "No UI implementation is performed in Phase 2",
            ],
            "requirements_addressed": requirement_ids(brief),
            "assumptions": [
                "A single-level game needs one HUD; additional levels reuse the same HUD.",
                "Text is English unless localization is requested.",
            ],
            "risks": [
                "Restart and pause flows must be tested at runtime; planned screens are not "
                "evidence of working UI.",
                "Accessibility options require real input remapping support in the engine.",
            ],
        }
