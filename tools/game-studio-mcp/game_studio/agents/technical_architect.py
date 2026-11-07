"""Technical Architect agent: engine recommendation and system architecture."""

from __future__ import annotations

from .base import Agent
from .contract import AgentSpec
from .helpers import (
    ENGINE_PLANNING_CAPABILITIES, clean_values, excluded_values, quality_profile,
    requirement_ids,
)
from .schemas import AGENT_INPUT_SCHEMA, ARCHITECTURE_SCHEMA


class TechnicalArchitectAgent(Agent):
    spec = AgentSpec(
        id="technical_architect",
        name="Technical Architect",
        version="1.0.0",
        responsibility="Choose a verified engine and define scenes, systems and budgets.",
        task_category="technical_architecture",
        dependencies=("design",),
        required_context=("brief", "design"),
        required_capabilities=("text_generation", "structured_output"),
        input_schema=AGENT_INPUT_SCHEMA,
        output_schema=ARCHITECTURE_SCHEMA,
        produces="architecture",
    )

    def deterministic_output(self, input_data: dict) -> dict:
        brief = input_data.get("brief") or {}
        design = input_data.get("design") or {}
        installed = [str(x) for x in (brief.get("installed_engines") or [])]
        hint = str(brief.get("engine_hint") or "").strip().lower()
        mechanics = clean_values(brief, "mechanics")
        excluded = excluded_values(brief)
        profile, quality = quality_profile(brief.get("quality_target"))

        if hint and hint in installed:
            engine = hint
            rationale = f"User requested {hint} and the engine was detected locally."
        elif "unity" in installed:
            engine = "unity"
            rationale = ("Unity is the only detected engine with a verified Windows "
                         "project, test and build workflow in this repository.")
        elif installed:
            engine = installed[0]
            rationale = (f"{installed[0]} is the only detected engine; its Phase 6 "
                         "adapter is not fully verified.")
        else:
            engine = hint or "unity"
            rationale = ("No game engine was detected. The recommendation is provisional "
                         "and implementation must not start until an engine is verified.")

        capabilities = ENGINE_PLANNING_CAPABILITIES.get(engine, {})
        supported = [name for name, value in capabilities.items()
                     if value is True or isinstance(value, str)]
        unsupported = [name for name, value in capabilities.items() if value is False]

        systems = ["GameBootstrap", "SceneLoader", "InputRouter", "PlayerController",
                   "FollowCamera", "CollectibleSystem", "ScoreSystem", "RestartSystem"]
        if "score" in mechanics:
            systems.append("HudPresenter")
        if "animation" in mechanics or True:
            systems.append("CharacterAnimator")
        if "weather" in mechanics:
            systems.append("WeatherController")
        dependencies = ["Input System", "Unity Test Framework (PlayMode)",
                        "TextMeshPro or UI Toolkit"]
        if engine == "godot":
            dependencies = ["InputMap", "GDScript/C# runtime", "GUT or gdUnit4"]
        if engine == "unreal":
            dependencies = ["Enhanced Input", "Blueprints/C++", "Automation Test Framework"]

        scenes = ["Boot", "MainMenu", "Level_Jungle", "GameOver"]
        if excluded:
            for name in excluded:
                if name in " ".join(systems).lower():
                    systems = [item for item in systems
                               if name not in item.lower()]

        return {
            "summary": f"Recommend {engine} with {len(systems)} systems at "
                       f"{quality} quality.",
            "engine": {
                "name": engine,
                "rationale": rationale,
                "installed": engine in installed,
                "detected_engines": installed,
                "supported_systems": systems + supported,
                "unsupported_features": unsupported,
                "planning_capabilities": capabilities,
            },
            "architecture": {
                "scenes": scenes,
                "systems": systems,
                "dependencies": dependencies,
                "folder_structure": [
                    "Assets/Game/Scripts", "Assets/Game/Scenes", "Assets/Game/Art",
                    "Assets/Game/Prefabs", "Assets/Game/Tests",
                ] if engine == "unity" else ["game/scenes", "game/scripts", "game/assets"],
            },
            "performance": {
                "quality_target": quality,
                "budget": {
                    "target_fps": profile["target_fps"],
                    "max_draw_calls": profile["max_draw_calls"],
                    "texture_budget_mb": profile["texture_budget_mb"],
                    "character_triangle_budget": profile["character_triangles"],
                    "lod_levels": profile["lod_levels"],
                    "hardware_note": ("Developed on a 6-core Ryzen 5 4500U with integrated "
                                      "Radeon graphics; use prototype budgets unless the "
                                      "user approves a higher target."),
                },
            },
            "risks": ([f"Engine {engine!r} is not detected; implementation is blocked."
                       if engine not in installed else
                       f"Engine {engine!r} is detected, but build success still requires a "
                       "real project build and test run."]
                      + ([f"Excluded mechanics must not appear in systems: {excluded}"]
                         if excluded else [])),
            "requirements_addressed": requirement_ids(brief),
            "assumptions": [
                "Planning assumes the detected engine version is compatible with the "
                "project template.",
                "No editor automation is claimed unless the pipeline package is available.",
            ],
        }
