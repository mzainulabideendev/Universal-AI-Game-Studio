# World, Environment and Level Design

Build environments as designed gameplay spaces. Scattering props is not level
design; a large map is not a level.

## Environment brief (before building)

1. Visual direction and palette.
2. World setting, time of day, weather, atmosphere.
3. Playable area and hard boundaries.
4. Intended player path and sightlines.
5. Gameplay spaces and encounter locations.
6. Hazards and interactive objects.
7. Lighting/shadow/reflection requirements.
8. Performance target and budget for the target devices.

## What to construct

Terrain and landscape, cliffs and valleys, vegetation and grass, rocks and caves,
water bodies and crossings, buildings and ruins, roads/tracks/paths, platforms,
props and landmarks, sky/fog/clouds, lighting and reflections, navigation areas,
boundaries, interactive objects, distant vistas.

Choose per project: licensed assets, existing project resources, procedural
generation, or a mix. Record the provenance of every external asset.

## Level plan template

```
Level:            <name / index>
Entry:            <spawn point, camera framing>
Critical path:    <ordered beats>
Optional routes:  <rewards / risk>
Objectives:       <exact completion conditions>
Enemies:          <type, count, placement, difficulty>
Hazards:          <type, telegraph, response>
Checkpoints:      <positions and state saved>
Landmarks:        <navigation aids visible from the path>
Pacing:           <calm / tension / climax beats>
Replay:           <collectibles, score attack, alternate route>
Exit:             <condition and transition>
```

## Blockout first

- Grey-box geometry with correct scale and collision.
- Walk/run the critical path and measure traversal time.
- Confirm every jump/gap is possible with the real controller (not by eye).
- Confirm camera framing at corners, slopes and tight spaces.
- Only then replace with final art, keeping colliders in sync.

## Procedural generation requirements

- Reproducible seed exposed in config/logs.
- Parameters: density, spacing, biome, difficulty, bounds.
- Placement constraints: slope limits, clearance, no overlap, no blocking the
  critical path, minimum spacing between hazards.
- Collision generated with the geometry, not assumed.
- Connectivity validation: graph/BFS from spawn to every required objective.
- Performance controls: pooling, chunk streaming, LOD, draw-call budgets.
- A deterministic test that generates N seeds and asserts invariants.

Random placement without constraints and validation is a defect.

## Interaction contract

| Element | Must do |
| --- | --- |
| Solid rock/building/wall | Block movement with matching collider |
| Water | Explicit swim / damage / impassable rule, not accidental fall-through |
| Bridge/platform | Reliable collision; moving platforms driven by physics or synced transforms |
| Collectible | Trigger effect once, then despawn/pool safely |
| Destructible | Health/rules, debris cleanup, no orphan objects |
| Trigger volume | Fires the intended event once, idempotent on reload |
| Nav obstacle | Reflected in NavMesh/bake or avoided by AI |

Visual meshes do not imply collision. Verify by playing the interaction.

## Lighting and atmosphere

- One clear key light direction; consistent shadow direction.
- Bake static lighting where supported; budget real-time lights.
- Fog/atmosphere supports depth readability, not just mood.
- Exposure/post-processing tuned in the running build, not only the Scene view.
- Verify night/dark scenes remain playable (telegraph hazards, readable paths).

## Readability and boundaries

- Landmarks visible from the critical path.
- Invisible walls aligned with visual barriers; never block a route the player
  can see as open.
- Kill volumes / respawn rules for out-of-bounds.
- No unreachable objectives, floating props, or props intersecting the path.

## Acceptance for a level

- Completable start to finish with the shipping controller.
- Every objective reachable and verified.
- No stuck spots; respawn/checkpoint recovers the player.
- Collision correct for every interactive element.
- Frame time within budget in the heaviest area.
- Visual pass done with final (or documented placeholder) assets.
