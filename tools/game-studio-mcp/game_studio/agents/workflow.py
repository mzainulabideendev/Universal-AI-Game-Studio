"""Static Phase 2 workflow definition: agents, tasks and dependency order."""

from __future__ import annotations

TASK_DEFINITIONS = (
    {
        "id": "design",
        "agent": "game_designer",
        "section": "design",
        "dependencies": (),
        "description": "Define the game loop, objectives, progression and acceptance tests.",
    },
    {
        "id": "architecture",
        "agent": "technical_architect",
        "section": "architecture",
        "dependencies": ("design",),
        "description": "Select a verified engine and define scenes, systems and budgets.",
    },
    {
        "id": "character",
        "agent": "character",
        "section": "character",
        "dependencies": ("design", "architecture"),
        "description": "Plan character geometry, UVs, PBR textures, rig and animations.",
    },
    {
        "id": "environment",
        "agent": "environment",
        "section": "environment",
        "dependencies": ("design", "architecture"),
        "description": "Plan terrain, vegetation, structures, water, lighting and atmosphere.",
    },
    {
        "id": "gameplay",
        "agent": "gameplay",
        "section": "gameplay",
        "dependencies": ("design", "architecture"),
        "description": "Plan controls, movement, physics, camera, scoring and tests.",
    },
    {
        "id": "uiux",
        "agent": "uiux",
        "section": "uiux",
        "dependencies": ("design", "gameplay"),
        "description": "Plan menus, HUD, settings, pause, accessibility and navigation.",
    },
    {
        "id": "qa",
        "agent": "qa",
        "section": "qa",
        "dependencies": ("design", "architecture", "character", "environment",
                         "gameplay", "uiux"),
        "description": "Review coverage, dependencies, conflicts and evidence needs.",
    },
    {
        "id": "consolidation",
        "agent": "game_director",
        "section": "consolidation",
        "dependencies": ("qa",),
        "description": "Consolidate a non-executable project plan with open decisions.",
    },
)

TASK_BY_ID = {task["id"]: task for task in TASK_DEFINITIONS}


def dependency_graph() -> dict:
    return {
        task["id"]: {
            "agent": task["agent"],
            "depends_on": list(task["dependencies"]),
            "section": task["section"],
            "description": task["description"],
        }
        for task in TASK_DEFINITIONS
    }


def parallel_groups() -> list[list[str]]:
    """Derive execution levels from the dependency graph (no cycles assumed)."""
    remaining = {task["id"]: set(task["dependencies"]) for task in TASK_DEFINITIONS}
    completed: set[str] = set()
    groups: list[list[str]] = []
    while remaining:
        ready = sorted(task for task, deps in remaining.items() if deps <= completed)
        if not ready:
            raise ValueError("dependency graph contains a cycle")
        groups.append(ready)
        completed.update(ready)
        for task in ready:
            remaining.pop(task)
    return groups


def validate_graph() -> list[str]:
    errors: list[str] = []
    for task in TASK_DEFINITIONS:
        for dep in task["dependencies"]:
            if dep not in TASK_BY_ID:
                errors.append(f"{task['id']} depends on unknown task {dep}")
            elif dep == task["id"]:
                errors.append(f"{task['id']} depends on itself")
    try:
        parallel_groups()
    except ValueError as exc:
        errors.append(str(exc))
    return errors
