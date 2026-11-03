# Gameplay Systems

Design first, then implement the smallest complete loop. Every system below must
be driven by real state; no hardcoded scores, no fake screens.

## Universal core loop template

```
Boot → Menu → (Play) → spawn → input → simulate → score/progress →
        fail or win → result → retry/next → persist best
```

Implement in this order: input → movement → world/chunking → hazards/pickups →
scoring → difficulty → UI → audio/VFX → persistence → settings.

## 2D platformer

- `CharacterBody2D`/`Rigidbody2D` with ground check (`Physics2D.OverlapCircle`
  on a ground layer), coyote time (~0.1 s), jump buffer (~0.1 s).
- Variable jump height by cutting vertical velocity on early release.
- One-way platforms via effector or layer filtering.
- Hazards use trigger colliders and damage cooldowns; respawn at checkpoint.
- Camera with look-ahead and pixel-perfect settings for pixel art.
- Level completion triggers only when the exit condition is met.

## 2D fighting

- Fixed timestep simulation; input buffer for specials.
- Frame data per attack (startup/active/recovery), hitboxes enabled only during
  active frames.
- Hit detection with `OverlapBox` on an attack layer; one hit per attack per
  target (track hit set).
- Damage, hitstun, blockstun, knockback, health, round timer, best-of-3.
- AI opponent with state machine: approach, attack, block, retreat, punish.
- Round results from actual health/timer state.

## 3D endless runner

- Player runs forward at increasing speed; lateral lanes or free strafe.
- Jump + slide with distinct collider heights; slide cancels jump apex.
- Ground detection via downward ray/SphereCast on a ground mask, not by Y value.
- Obstacles pooled, spawned ahead on chunks, recycled behind.
- Collectibles increase score with combo multiplier; score derived from pickups
  and distance.
- Difficulty curve: speed and spawn density increase with distance; cap it.
- Power-ups: magnet, shield, x2 score — each with a duration and visible timer.
- Animation states: Idle/Run/Jump/Slide/Stumble/Death via Animator parameters.
- States: Menu, Playing, Paused, GameOver, Revive; pause stops time and input.
- Persist best score, currency, unlocks with versioned save data.

## Physics correctness checklist

- Colliders match visual bounds; no gaps at seams between ground chunks.
- Rigidbody mass/drag sane; no `transform.position` writes on physics bodies.
- Continuous collision for fast movers; interpolation for the camera target.
- Layer collision matrix explicit; verify no unintended layer pairs.
- Triggers for pickups/hazards; colliders for solid geometry.
- Fixed timestep 0.02 for gameplay stability; scale all speeds by delta time.
- Test at 30, 60 and 144 FPS (or with `Time.timeScale` variations) to catch
  frame-rate-dependent movement.
- Verify no double-trigger: guard with cooldown or `TryGetComponent` once.

## UI/HUD

- Every screen has one owner and explicit transitions.
- Buttons call real methods; disabled states reflect real availability.
- HUD values bound to the model each frame or on change events.
- Pause/settings actually mutate time scale, audio volume, quality.
- Safe areas for mobile notches; scalable canvas.
- Keyboard/gamepad focus navigation; touch targets ≥ 44 px.

## Save data

- Versioned schema with migration function.
- Atomic write (temp file + replace) to avoid corruption.
- Never store secrets; validate on load and fall back to defaults.
- Test round-trip: save → mutate → load → assert equality.

## Performance budgets (starting points)

| Target | Triangle/frame | Draw calls | Lights | Texture memory |
| --- | --- | --- | --- | --- |
| Mobile 3D 60 fps | < 150k | < 150 | 1 dir + baked | < 256 MB |
| Desktop 3D 60 fps | < 2M | < 1000 | few real-time | < 2 GB |
| Mobile 2D 60 fps | sprites batched | < 100 | n/a | < 128 MB |

Use the profiler, not intuition. Fix the top cost first (usually overdraw,
shadows, physics queries or per-frame allocations).

## Anti-patterns to reject

- `Update` allocating (`new`, LINQ, string concat) every frame.
- `FindObjectOfType` in loops.
- Score increments inside UI code.
- `Time.deltaTime` missing from movement.
- Coroutines that never stop on disable.
- Physics materials with zero friction causing endless sliding.
- "Temporary" debug keys shipped enabled.
