"""Game project specification and dependency planning.

Builds a project specification from a Lake of analysis produced by
:mod:`game_studio.understanding`. The output is intentionally explicit about
what is requested, what is assumed and what is still unresolved.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .understanding import (
    ANIMATION_BY_MECHANIC,
    DEFAULT_ASSUMPTIONS,
    PERFORMANCE_TARGETS,
    RIG_BY_CHARACTER,
    analyze_request,
)

MILESTONES = [
    ("A", "Foundation", "Project opens, compiles and runs an empty/test scene."),
    ("B", "Vertical slice", "Player, camera, one environment and the core loop are playable."),
    ("C", "Content", "Required characters, environments, animations and levels exist."),
    ("D", "Features", "Requested mechanics, UI, save and settings are wired."),
    ("E", "Polish", "Visual consistency, audio, balance and accessibility pass."),
    ("F", "Optimise/QA", "Measured performance, regression tests and platform builds."),
    ("G", "Delivery", "Source, build, licences and known issues documented."),
]

ROLE_BY_CATEGORY = {
    "dimension": "Technical Director",
    "genre": "Game Director",
    "engine": "Technical Director",
    "platform": "Build Engineer",
    "style": "Art Director",
    "character": "Character Technical Artist",
    "environment": "Level Designer",
    "mechanic": "Gameplay Programmer",
    "system": "Gameplay Programmer",
    "technical": "Technical Director",
    "optional": "Game Director",
}

POLY_BUDGETS = {
    "pc": {"character": "40k-120k triangles", "environment_prop": "5k-40k triangles",
           "texture": "up to 4K for hero assets"},
    "console": {"character": "40k-100k triangles", "environment_prop": "5k-30k triangles",
                "texture": "up to 4K for hero assets"},
    "mobile": {"character": "8k-35k triangles", "environment_prop": "500-5k triangles",
               "texture": "1K-2K, atlas where possible"},
    "web": {"character": "5k-25k triangles", "environment_prop": "500-3k triangles",
            "texture": "512-1K, compressed"},
    "vr": {"character": "15k-60k triangles", "environment_prop": "2k-15k triangles",
           "texture": "1K-2K"},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_id(name: str, request: str) -> str:
    digest = hashlib.sha1(f"{name}\n{request}".encode("utf-8")).hexdigest()
    return digest[:12]


def _all_requirements(analysis: dict) -> list[dict]:
    req = analysis["requirements"]
    merged = []
    for key in ("explicit", "implied", "technical_dependencies", "optional_enhancements"):
        for item in req.get(key, []):
            merged.append(dict(item))
    return merged


def _select_engine(analysis: dict, override: str | None,
                   installed: list[str] | None) -> dict:
    requested = analysis["understanding"]["engine_requested"]
    if override:
        chosen = override.lower()
        verified = chosen in (installed or [])
        warning = None
        if installed and not verified:
            warning = (f"{chosen} was selected but was not detected on this machine; "
                       "install it or choose an installed engine before implementation.")
        elif not installed:
            warning = ("No engine installations were supplied, so the selected engine "
                       "could not be verified.")
        return {"selected": chosen, "source": "user-override",
                "requested": requested, "installed": installed or [],
                "verified": verified, "warning": warning}
    if requested:
        selected = requested[0]
        verified = selected in (installed or [])
        warning = None
        if installed and not verified:
            warning = (f"{selected} was requested but was not detected on this machine; "
                       "install it or choose an installed engine before implementation.")
        elif not installed:
            warning = ("No engine installations were supplied, so the requested engine "
                       "could not be verified.")
        return {"selected": selected, "source": "user-request", "requested": requested,
                "installed": installed or [], "verified": verified, "warning": warning}
    return {"selected": None, "source": "unresolved", "requested": [],
            "installed": installed or [], "verified": False,
            "warning": "No engine was requested or detected; the specification stays "
                       "engine-agnostic until the user chooses."}


def _character_specs(analysis: dict, platform: str, style: list[str]) -> list[dict]:
    specs = []
    budget = POLY_BUDGETS.get(platform, POLY_BUDGETS["pc"])
    mechanics = analysis["understanding"]["mechanics"]
    camera = "third-person"
    dims = analysis["understanding"]["dimension"]
    if "first-person" in dims:
        camera = "first-person"
    elif "2d" in dims and "3d" not in dims:
        camera = "2D side/top view"
    for character in analysis["understanding"]["characters"]:
        rig = RIG_BY_CHARACTER.get(character, {
            "rig": "custom rig matched to the body plan",
            "animations": ["idle", "walk", "run"], "warning": None})
        animations = list(rig["animations"])
        for mechanic in mechanics:
            animations.extend(ANIMATION_BY_MECHANIC.get(mechanic, []))
        specs.append({
            "character": character,
            "species_type": character,
            "visual_style": style or ["unresolved"],
            "camera_perspective": camera,
            "gameplay_role": "player" if character == (
                analysis["understanding"]["characters"] or [None])[0] else "npc",
            "movement": "ground + jump" if character not in ("car", "ship") else "vehicle",
            "rig_requirement": rig["rig"],
            "animation_requirements": sorted(set(animations)),
            "polygon_budget": budget["character"],
            "texture_budget": budget["texture"],
            "retargeting_warning": rig["warning"],
            "source_options": ["Blender-authored", "licensed asset", "Meshy (credit-gated)"],
        })
    return specs


def _environment_specs(analysis: dict, platform: str) -> list[dict]:
    specs = []
    mechanics = set(analysis["understanding"]["mechanics"])
    for environment in analysis["understanding"]["environment"]:
        traversal = ["walk", "run"]
        if "climbing" in mechanics:
            traversal.append("climb")
        if "swimming" in mechanics:
            traversal.append("swim")
        if "driving" in mechanics:
            traversal.append("drive")
        specs.append({
            "biome": environment,
            "scale": "one playable slice first; size decided after the traversal test",
            "traversal": traversal,
            "collision_requirements": [
                "solid ground and boundary collision",
                "no pass-through on tree trunks, rocks and buildings",
                "slopes walkable up to the configured limit",
            ],
            "interactive_objects": [m for m in mechanics
                                    if m in ("collectibles", "checkpoints", "quests", "crafting")],
            "lighting_style": "realistic" if "realistic" in analysis["understanding"]["visual_style"]
            else "stylised, readable key light",
            "weather": "only if explicitly requested; it is not part of the core loop",
            "asset_density": "start sparse, measure frame time, then add set dressing",
            "performance_budget": PERFORMANCE_TARGETS.get(platform, PERFORMANCE_TARGETS["pc"]),
        })
    return specs


def _animation_plan(analysis: dict) -> dict:
    mechanics = analysis["understanding"]["mechanics"]
    required = set()
    for mechanic in mechanics:
        required.update(ANIMATION_BY_MECHANIC.get(mechanic, []))
    characters = analysis["understanding"]["characters"]
    rigs = [RIG_BY_CHARACTER.get(c, {}).get("rig", "custom rig") for c in characters]
    skeleton_types = sorted({r for r in rigs if r})
    incompatible = []
    if any(c in ("monkey", "animal", "dragon") for c in characters):
        incompatible.append(
            "Humanoid locomotion clips are not automatically compatible with quadruped "
            "characters; check bone names, chain lengths and rest pose before retargeting.")
    if "car" in characters:
        incompatible.append("Vehicles use wheel/suspension animation, not skeletal clips.")
    return {
        "required_clips": sorted(required) or ["idle", "move"],
        "skeleton_types": skeleton_types or ["unresolved"],
        "retargeting_order": ["source rig -> bone map -> rest-pose check -> scale check -> "
                              "test clip -> engine import -> playback test"],
        "incompatibilities": incompatible,
        "acceptance": "Every clip plays on the target character in the engine, with the "
                      "correct root motion and loop behaviour.",
    }


def _systems(analysis: dict) -> list[dict]:
    requirements = _all_requirements(analysis)
    systems = []
    for requirement in requirements:
        if requirement["classification"] not in ("explicit", "implied", "technical"):
            continue
        if requirement["category"] not in ("system", "mechanic", "technical", "genre"):
            continue
        systems.append({
            "name": requirement["statement"],
            "detail": requirement["acceptance_test"],
            "requirement_id": requirement["id"],
            "priority": requirement["priority"],
            "role": ROLE_BY_CATEGORY.get(requirement["category"], "Gameplay Programmer"),
        })
    deduped = []
    seen = set()
    for system in systems:
        key = system["name"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(system)
    return deduped


def _graph(analysis: dict, engine: dict, characters: list[dict],
           environments: list[dict], systems: list[dict]) -> dict:
    nodes: list[dict] = []
    ids: dict[str, str] = {}

    def add(key: str, label: str, deps: list[str], role: str, milestone: str,
            requirement_ids: list[str] | None = None) -> None:
        node_id = f"T-{len(nodes) + 1:02d}"
        ids[key] = node_id
        nodes.append({
            "id": node_id,
            "key": key,
            "label": label,
            "depends_on": [ids[d] for d in deps if d in ids],
            "role": role,
            "milestone": milestone,
            "requirement_ids": requirement_ids or [],
            "status": "pending",
        })

    add("setup", "Create/verify project and version control", [], "Technical Director", "A")
    add("engine", f"Configure {engine['selected'] or 'engine (unresolved)'} project settings",
        ["setup"], "Technical Director", "A")
    add("input", "Input actions and remapping", ["engine"], "Gameplay Programmer", "A")
    add("controller", "Player/vehicle controller", ["input"], "Gameplay Programmer", "B")
    add("camera", "Camera system", ["controller"], "Gameplay Programmer", "B")
    add("physics", "Physics, collision layers and boundaries", ["controller"], "Technical Director", "B")

    if characters:
        add("char_source", "Character model or licensed asset", ["engine"],
            "Character Technical Artist", "C")
        add("char_rig", "Skeleton/rig validation and scale", ["char_source"],
            "Character Technical Artist", "C")
        add("animations", "Animation clips and retargeting", ["char_rig", "camera"],
            "Animation Engineer", "C")
        add("animator", "Animation state machine connected to gameplay", ["animations", "controller"],
            "Animation Engineer", "C")
    if environments:
        add("env_blockout", "Environment blockout and scale test", ["engine"], "Level Designer", "C")
        add("env_art", "Materials, props and lighting", ["env_blockout"], "Environment Artist", "C")
        add("env_collision", "Environment collision and navigation", ["env_art", "physics"],
            "Level Designer", "C")

    for index, system in enumerate(systems, start=1):
        deps = ["controller"] if system["role"] == "Gameplay Programmer" else ["engine"]
        if characters and system["role"] == "Gameplay Programmer":
            deps = ["animator"]
        if environments and "collision" in system["name"].lower():
            deps = ["env_collision"]
        add(f"system-{index}", system["name"], deps, system["role"], "D",
            [system["requirement_id"]])

    add("ui", "HUD, menus and settings", [ids.get("system-1") and "system-1" or "engine"],
        "UI/UX Designer", "D")
    add("audio", "Music and gameplay audio", ["engine"], "Audio Designer", "D")
    add("save", "Save/load and persistence", ["engine"], "Gameplay Programmer", "D")
    add("tests", "Automated tests and playtest checklist", ["controller", "ui"],
        "QA Engineer", "F")
    add("optimise", "Performance profiling and optimisation", ["tests"], "Graphics Engineer", "F")
    add("build", "Target-platform build", ["optimise"], "Build Engineer", "F")
    add("verify", "Runtime verification and acceptance evidence", ["build"], "QA Engineer", "G")

    # Topological order (deterministic, cycle-detecting).
    by_id = {node["id"]: node for node in nodes}
    order: list[str] = []
    visiting: set[str] = set()
    cycles: list[str] = []

    def visit(node_id: str) -> None:
        if node_id in order:
            return
        if node_id in visiting:
            cycles.append(node_id)
            return
        visiting.add(node_id)
        for dep in by_id[node_id]["depends_on"]:
            visit(dep)
        visiting.discard(node_id)
        order.append(node_id)

    for node in nodes:
        visit(node["id"])
    return {
        "nodes": nodes,
        "edges": [{"from": dep, "to": node["id"]}
                  for node in nodes for dep in node["depends_on"]],
        "topological_order": order,
        "cycles": cycles,
    }


def _acceptance_tests(analysis: dict, characters: list[dict],
                      environments: list[dict]) -> list[dict]:
    tests = []
    counter = 1
    for requirement in _all_requirements(analysis):
        if requirement["classification"] == "optional":
            continue
        tests.append({
            "id": f"AT-{counter:03d}",
            "requirement_id": requirement["id"],
            "statement": requirement["acceptance_test"],
            "source_requirement": requirement["statement"],
            "method": "engine playtest + evidence capture",
            "status": "not-run",
            "evidence": [],
        })
        counter += 1
    for character in characters:
        if character["retargeting_warning"]:
            tests.append({
                "id": f"AT-{counter:03d}",
                "requirement_id": None,
                "statement": character["retargeting_warning"],
                "source_requirement": "animation compatibility",
                "method": "inspect bone map, rest pose and playback",
                "status": "not-run",
                "evidence": [],
            })
            counter += 1
    for environment in environments:
        tests.append({
            "id": f"AT-{counter:03d}",
            "requirement_id": None,
            "statement": "Player cannot pass through solid environment collision "
                         f"({environment['biome']}).",
            "source_requirement": "environment collision",
            "method": "move directly into a tree/rock/building and confirm blocking",
            "status": "not-run",
            "evidence": [],
        })
        counter += 1
    tests.append({
        "id": f"AT-{counter:03d}",
        "requirement_id": None,
        "statement": "The built game launches, accepts input and reaches the core loop.",
        "source_requirement": "playable build",
        "method": "launch the produced build and play for five minutes",
        "status": "not-run",
        "evidence": [],
    })
    return tests


def create_specification(*, request: str | None = None, analysis: dict | None = None,
                         project_name: str | None = None,
                         engine: str | None = None, platform: str | None = None,
                         dimension: str | None = None, art_style: str | None = None,
                         scope: str | None = None,
                         installed_engines: list[str] | None = None,
                         known_engine: str | None = None,
                         known_platform: str | None = None,
                         approved: bool = False) -> dict:
    if analysis is None:
        if not request:
            raise ValueError("request or analysis is required")
        analysis = analyze_request(request, installed_engines=installed_engines,
                                   known_engine=known_engine,
                                   known_platform=known_platform)
    else:
        # Re-run on the original text so a stale analysis object cannot smuggle
        # in mismatched requirements.
        analysis = analyze_request(
            analysis["original_request"], installed_engines=installed_engines,
            known_engine=known_engine, known_platform=known_platform)

    original = analysis["original_request"]
    name = (project_name or "Untitled Game Project").strip()[:120]
    platform_value = (platform or (analysis["understanding"]["target_platform"] or ["pc"])[0])
    dimension_value = dimension or (analysis["understanding"]["dimension"] or ["3d"])[0]
    style_values = [art_style] if art_style else analysis["understanding"]["visual_style"]
    engine_info = _select_engine(analysis, engine, installed_engines)

    # Replace analysis dimension/platform when the user supplied an override.
    analysis["understanding"]["dimension"] = [dimension_value]
    analysis["understanding"]["target_platform"] = [platform_value]
    analysis["understanding"]["visual_style"] = style_values

    characters = _character_specs(analysis, platform_value, style_values)
    environments = _environment_specs(analysis, platform_value)
    animations = _animation_plan(analysis)
    systems = _systems(analysis)
    graph = _graph(analysis, engine_info, characters, environments, systems)
    tests = _acceptance_tests(analysis, characters, environments)

    requirements = _all_requirements(analysis)
    by_milestone: dict[str, list[str]] = {}
    for node in graph["nodes"]:
        by_milestone.setdefault(node["milestone"], []).append(node["id"])

    milestones = [{
        "id": letter,
        "name": milestone,
        "gate": gate,
        "task_ids": by_milestone.get(letter, []),
        "status": "not-started",
    } for letter, milestone, gate in MILESTONES]

    limitations = []
    if not engine_info["selected"]:
        limitations.append("Engine not chosen; no engine-specific code or build can be "
                           "produced yet.")
    elif engine_info.get("warning"):
        limitations.append(engine_info["warning"])
    if not analysis["understanding"]["visual_style"]:
        limitations.append("Art style unresolved; asset sourcing is provisional.")
    if "multiplayer" in analysis["understanding"]["mechanics"]:
        limitations.append("Networking mode (online/local) is unresolved.")
    limitations.append("This specification is a plan, not a playable game. Each gate needs "
                       "its own implementation and evidence.")
    limitations.append("Content scope is one vertical slice until the core loop is verified.")

    spec = {
        "ok": True,
        "spec_id": _project_id(name, original),
        "project_name": name,
        "generated_at": _now(),
        "status": "approved" if approved else "awaiting-approval",
        "approved": bool(approved),
        "request": original,
        "analysis": {key: value for key, value in analysis.items()
                     if not key.startswith("_")},
        "overview": {
            "summary": analysis["summary"],
            "genre": analysis["understanding"]["game_genre"],
            "dimension": dimension_value,
            "target_platform": platform_value,
            "visual_style": style_values or ["unresolved"],
            "scope": scope or "one vertical slice",
        },
        "engine": engine_info,
        "characters": characters,
        "environments": environments,
        "animations": animations,
        "gameplay_systems": systems,
        "requirements": requirements,
        "dependency_graph": graph,
        "milestones": milestones,
        "acceptance_tests": tests,
        "performance_targets": PERFORMANCE_TARGETS.get(platform_value,
                                                       PERFORMANCE_TARGETS["pc"]),
        "assumptions": DEFAULT_ASSUMPTIONS,
        "unresolved": analysis["unresolved"],
        "questions": analysis["questions"],
        "conflicts": analysis["conflicts"],
        "limitations": limitations,
        "deliverables": [
            "Project source under version control",
            "Playable build for the chosen platform",
            "Asset provenance and licence record",
            "Automated tests plus a playtest checklist",
            "Build/run instructions and known issues",
        ],
        "next_actions": _next_actions(engine_info, analysis, approved),
    }
    return spec


def _next_actions(engine_info: dict, analysis: dict, approved: bool) -> list[str]:
    actions = []
    if not engine_info["selected"]:
        actions.append("Choose an engine (select_game_engine) or pass engine to this tool.")
    elif engine_info.get("warning"):
        actions.append(engine_info["warning"])
    if not approved:
        actions.append("Review the specification, answer material questions, then approve it.")
    if analysis["conflicts"]:
        actions.append("Resolve the reported conflicts before implementation.")
    actions.append("Inspect the existing project (inspect_game_project) before creating or "
                   "overwriting files.")
    actions.append("Initialise the project manifest to persist this plan across sessions.")
    return actions


def summarize_spec(spec: dict) -> dict:
    """A compact view used by progress/verification tools."""
    return {
        "spec_id": spec.get("spec_id"),
        "project_name": spec.get("project_name"),
        "status": spec.get("status"),
        "engine": (spec.get("engine") or {}).get("selected"),
        "platform": (spec.get("overview") or {}).get("target_platform"),
        "genre": (spec.get("overview") or {}).get("genre"),
        "requirement_count": len(spec.get("requirements") or []),
        "milestones": spec.get("milestones"),
        "unresolved": spec.get("unresolved"),
        "limitations": spec.get("limitations"),
    }
