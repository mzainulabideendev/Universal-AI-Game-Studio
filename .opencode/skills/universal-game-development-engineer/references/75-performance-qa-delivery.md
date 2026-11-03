# Performance, Automated Playtesting and Delivery

## Performance budgets (define before optimising)

| Target | Frame time | CPU | GPU | Memory | Build |
| --- | --- | --- | --- | --- | --- |
| PC 60 fps | 16.6 ms | < 10 ms main | < 14 ms | < 4 GB | < 2 GB |
| PC 30 fps | 33 ms | < 20 ms | < 28 ms | < 4 GB | < 2 GB |
| Mobile 60 fps | 16.6 ms | < 10 ms | < 12 ms | < 1.5 GB | < 200 MB APK |
| Mobile 30 fps | 33 ms | < 20 ms | < 26 ms | < 1.5 GB | < 200 MB APK |

These are starting budgets, not measured facts. Replace with project values.

## Measurement

- Record: average and p95 frame time, main-thread time, GPU time where available,
  GC allocation per frame, peak memory, texture memory, draw calls, triangles,
  load time, build size.
- Measure in a build matching the target quality tier, at target resolution.
- Compare like for like (same scene, same camera path, same settings).
- Keep a `reports/performance.md` with device, build id, scene and numbers.
- Never report an fps figure without the method and the hardware.

## Optimisation order

1. Profile; identify CPU main / render thread / GPU / GC.
2. Fix the largest cost (usually overdraw, shadows, per-frame allocations,
   physics queries, or too many unique materials).
3. Re-measure; stop when within budget.
Techniques: batching/SRP Batcher, GPU instancing, LOD, occlusion/frustum culling,
texture compression, pooling, addressables/streaming, shader variant stripping,
fixed update throttling, spatial partitioning.

## Automated playtesting

Build a repeatable suite where the engine allows:

| Case | Unity | Unreal | Godot |
| --- | --- | --- | --- |
| Boot/scene load | PlayMode test + log scan | functional test | headless scene run |
| Movement/physics | PlayMode test driving API/input | automation spec | scripted scene test |
| Combat rules | EditMode unit tests | automation spec | GUT unit test |
| UI flow | PlayMode test invoking handlers | functional UI test | scripted input |
| Save/load | round-trip test | automation spec | scripted save test |
| Level completion | scripted scenario | automation | headless run |
| Perf | ProfilerRecorder | stat commands | Performance monitors |

Also run the real application: launch the build, exercise controls via input
automation or a scripted scenario, capture logs and screenshots. A unit test does
not prove camera framing, readability or fun.

## Runtime verification checklist

- Player launches, reaches first interactive frame.
- No exceptions/errors in the player log.
- Input works for keyboard/mouse/gamepad/touch as designed.
- Scene transitions and pause/resume leave no orphaned objects.
- Save/load survives an app restart.
- Exit is graceful; no crash on quit.
- Target platform specifics (resolution, safe area, permissions).

## Regression discipline

- Every fixed defect gets a test when practical.
- Maintain `KNOWN_ISSUES.md` with severity, reproduction and workaround.
- Keep a smoke-test script that runs compile → tests → build → launch → log scan.
- Re-run the full suite before declaring a milestone done.

## Delivery package

```
/Project            editable source project (engine files, assets, settings)
/Builds/<platform>  verified build artifacts
/docs/SETUP.md      how to open, configure and build
/docs/ASSETS.md     asset sources and licences
/docs/KNOWN_ISSUES.md
/docs/PERFORMANCE.md measured results and hardware
/docs/TEST_REPORT.md commands, counts, pass/fail
CHECKSUMS.txt       SHA-256 of build artifacts
```

Release candidate criteria: opens in the intended engine; core loop playable;
required levels/assets present and validated; controls/physics correct; UI
functional; no critical defects; tests and builds executed with recorded results;
performance measured; limitations documented; full source preserved.
