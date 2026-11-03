# Character, Animation and Enemy AI

## Animation inventory first

Before referencing clips:

1. List clips with exact names, lengths, loop flags, root-motion track.
2. Confirm the rig/Avatar maps to the model.
3. Note missing required clips (jump, hit, death, attack).
4. Find compatible licensed clips or implement a documented fallback
   (procedural pose, additive motion) and report it.

Never reference a clip or state that does not exist. Never report a clip as
imported because a file exists — open the import result and read the clip list.

## Locomotion and game feel

- Input sampling in `Update`; physics in `FixedUpdate`; visuals interpolated.
- Acceleration/deceleration curves instead of instant velocity changes.
- Jump: coyote time, input buffer, variable height, distinct fall gravity.
- Landing: short recovery, squash/VFX/audio feedback, camera dip.
- Turning: rotate toward movement with a max turn rate; avoid snapping.
- Slide/roll: collider resize + timing window + invulnerability if designed.
- Grounding: ray/sphere cast against a ground mask, not a Y threshold.
- Root motion only when clips are authored for it; otherwise drive movement in
  code and keep the clip in place.

### Animation state machine

```
Idle ↔ Run ↔ Sprint
Run → Jump → Fall → Land → Run
Run/Any → Slide → Run
Any → Hit → Recover → Run
Any → Death
```

- Parameters: speed, grounded, verticalVelocity, slide, hit, dead.
- Transitions have exit time/has-exit-time disabled for responsiveness.
- Attack/hit reactions gated by gameplay rules, not animation events alone.
- Verify no clipped states, no T-pose, no sliding feet at max speed.

## Attacks and hit rules

- Frame windows: startup / active / recovery.
- Hitbox enabled only during active frames; one hit per target per swing.
- Damage, knockback, hitstop, invulnerability windows explicit.
- Animation plays the swing; **the combat rule decides the hit**.
- Test whiffs, trades, blocks, and simultaneous hits.

## Enemy AI

Use a state machine or behaviour tree with explicit transitions:

```
Idle → Patrol → Investigate → Chase → Attack → Recover → Search → Return
                                   ↘ Stunned → Recover
```

Requirements:

- Detection: vision cone + range + line-of-sight raycast against world layers;
  optional hearing radius.
- Navigation: NavMesh/NavMeshAgent (Unity), NavMesh/AI Controller (Unreal),
  NavigationAgent (Godot). Re-path on target move, not every frame.
- Attack: range check, cooldown, telegraph, damage applied at the active frame.
- Avoidance: agent avoidance/steering; never push the player through geometry.
- Group behaviour: simple role assignment (flank, hold, ranged) if the game needs
  it; otherwise keep it readable.
- Difficulty scaling: speed, reaction time, damage, count — clamped and tested.
- Boss: phase thresholds with distinct attack sets and transitions on real health.
- Return/reset: leash distance, heal/reset on disengage, no infinite chase.

### AI validation

- Path exists from spawn to the player's reachable areas.
- LOS blocked by real geometry (test behind cover).
- Cooldowns enforced; no damage spam.
- No NaN/zero-distance normalization errors.
- Performance: agent count and update rate within budget.
- Deterministic tests for detection and damage rules where the engine allows.

## Anti-patterns

- Enemies that wander randomly and call it AI.
- Damage by distance alone with no attack/telegraph.
- Animator bools set every frame causing transition thrash.
- Root motion + code movement fighting each other.
- Hitboxes left enabled for the whole clip.
- Enemies pathing through walls because navigation was never baked.
