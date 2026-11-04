# Monkey Adventure — end-to-end reasoning demo

Generated: 2026-11-04T16:54:00Z

## Request (verbatim)

> Create a realistic 3D monkey adventure game for Android. The monkey can run, jump, climb trees, swing between branches, swim in rivers and collect bananas. Include multiple jungle environments, day-night cycles, weather changes, wildlife, progression and mobile-friendly controls. No weapons.

## Pipeline

- Understanding: deterministic fallback (no paid LLM call in this run)
- Specification: deterministic dependency graph, milestones and acceptance tests
- Approval: awaiting user approval; no engine, asset or build action was taken
- Manifest: created

## Specification summary

- Spec id: `d68673e7f9e1`
- Requirements: 27
- Layers: `null`
- Engine recommendation: `{"selected": null, "source": "unresolved", "requested": [], "installed": [], "verified": false, "warning": "No engine was requested or detected; the specification stays engine-agnostic until the user chooses."}`

## Dependency graph

```json
{
  "nodes": [
    {
      "id": "T-01",
      "key": "setup",
      "label": "Create/verify project and version control",
      "depends_on": [],
      "role": "Technical Director",
      "milestone": "A",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-02",
      "key": "engine",
      "label": "Configure engine (unresolved) project settings",
      "depends_on": [
        "T-01"
      ],
      "role": "Technical Director",
      "milestone": "A",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-03",
      "key": "input",
      "label": "Input actions and remapping",
      "depends_on": [
        "T-02"
      ],
      "role": "Gameplay Programmer",
      "milestone": "A",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-04",
      "key": "controller",
      "label": "Player/vehicle controller",
      "depends_on": [
        "T-03"
      ],
      "role": "Gameplay Programmer",
      "milestone": "B",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-05",
      "key": "camera",
      "label": "Camera system",
      "depends_on": [
        "T-04"
      ],
      "role": "Gameplay Programmer",
      "milestone": "B",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-06",
      "key": "physics",
      "label": "Physics, collision layers and boundaries",
      "depends_on": [
        "T-04"
      ],
      "role": "Technical Director",
      "milestone": "B",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-07",
      "key": "char_source",
      "label": "Character model or licensed asset",
      "depends_on": [
        "T-02"
      ],
      "role": "Character Technical Artist",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-08",
      "key": "char_rig",
      "label": "Skeleton/rig validation and scale",
      "depends_on": [
        "T-07"
      ],
      "role": "Character Technical Artist",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-09",
      "key": "animations",
      "label": "Animation clips and retargeting",
      "depends_on": [
        "T-08",
        "T-05"
      ],
      "role": "Animation Engineer",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-10",
      "key": "animator",
      "label": "Animation state machine connected to gameplay",
      "depends_on": [
        "T-09",
        "T-04"
      ],
      "role": "Animation Engineer",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-11",
      "key": "env_blockout",
      "label": "Environment blockout and scale test",
      "depends_on": [
        "T-02"
      ],
      "role": "Level Designer",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-12",
      "key": "env_art",
      "label": "Materials, props and lighting",
      "depends_on": [
        "T-11"
      ],
      "role": "Environment Artist",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-13",
      "key": "env_collision",
      "label": "Environment collision and navigation",
      "depends_on": [
        "T-12",
        "T-06"
      ],
      "role": "Level Designer",
      "milestone": "C",
      "requirement_ids": [],
      "status": "pending"
    },
    {
      "id": "T-14",
      "key": "system-1",
      "label": "Genre: adventure",
      "depends_on": [
        "T-02"
      ],
      "role": "Game Director",
      "milestone": "D",
      "requirement_ids": [
        "R-005"
      ],
      "status": "pending"
    },
    {
      "id": "T-15",
      "key": "system-2",
      "label": "Gameplay: jumping",
      "depends_on": [
        "T-10"
      ],
      "role
```

## Material questions

- Which engine should this be built in? (None)

## Blockers (honest)

- **no Unity project exists for this demonstration** — there is no scene, controller or build to test. Resolution: create a Unity project, then stage assets and implement gameplay through approved MCP tools
- **no licensed monkey character or compatible animation set is installed** — character/rig/animation requirements cannot be verified. Resolution: use Meshy (paid, explicit approval) or a licensed asset source, then check_animation_compatibility
- **no automated gameplay test exists yet** — run_requirement_verification cannot prove movement, climbing or swimming. Resolution: implement PlayMode/edit-mode tests, then run them via unity_run_tests or run_requirement_verification

## Completion state

- reasoning_pipeline: `completed`
- game_created: `False`
- assets_imported: `False`
- gameplay_implemented: `False`
- build_produced: `False`
- playable_scene_verified: `False`
- honest_summary: `The plan is complete and verifiable. No playable Unity game was produced, because the required editor, project, character and animation assets are not available in this environment.`

## What is still required

1. Approve engine/platform/art direction.
2. Install Unity + Blender and select the engine.
3. Create/import the character and compatible animations (licensed or paid, with explicit approval).
4. Generate the environment, implement the controller/physics, and create the scene.
5. Add gameplay tests and run them; only then upgrade requirements to tested/verified.
6. Build and playtest the actual build before any completion claim.
