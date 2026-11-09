# V6 Phase 5 - Gameplay Integration

Status: implemented, built, automatically tested and played end-to-end on
Windows. **Human playtest and visual sign-off are still pending.**

- Repository: `D:\MCP\MCP`
- Branch/HEAD at time of work: `main` / `9056529a1145ecc11fc207ee46a04537a3f60be5`
- Working tree: uncommitted Phase 5 changes. **No commit, tag or push was made.**
- Engine: Unity `6000.6.2f1` (Windows Standalone x64)
- Project: `validation/unity-jungle-v6`
- Network calls, downloads, paid requests and AI asset providers: **none**

Phase 5 turns the Phase 3 JungleMonkey character and the Phase 4 jungle level
into a genuinely playable third-person game: a CharacterController player,
run/jump, banana collection, collisions, ground detection, a follow camera, HUD,
pause/restart, objectives, completion and game-over states.

---

## 1. What was built

| Area | Implementation |
| --- | --- |
| Player | `CharacterController` movement with walk/run acceleration, gravity, jump, coyote time, jump buffering and fall recovery |
| Ground detection | Sphere + ray probe with slope limits and ground normals (`GroundDetector`) |
| Collisions | Real controller collisions against terrain, rocks, logs, trees and ruins; river contact is lethal |
| Camera | Third-person orbit/follow camera with collision-aware positioning |
| Collectibles | 10 bananas placed on the Phase 4 route; collection updates score, HUD and objectives |
| Objectives | Collect all 10 bananas **and** reach the jungle ruins |
| Game flow | Explicit states: Initializing, MainMenu, Playing, Paused, GameOver, LevelCompleted, Restarting |
| HUD | Banana counter, objective text, best score, toasts, pause menu, completion results, controls footer |
| Persistence | Best score and settings saved locally |
| Audio | Audio hooks exist; no audio assets are present, and the game reports this honestly |
| Automation | `AutoPlayDriver` runs a real scripted playthrough, captures screenshots and writes measured performance |
| Build | Windows Standalone player built from the real scene |

Excluded by scope: climbing, swinging, swimming, weapons, multiplayer, Android.

---

## 2. Architecture

Key runtime systems (`Assets/V6/Scripts/`):

- `Core/GameStateController.cs` - legal state transitions and time-scale ownership
- `Core/GameManager.cs` - orchestration, pause/restart/completion, save data
- `Core/LevelManager.cs` - spawn/destination anchors, ground snapping, bounds, kill plane
- `Core/ObjectiveManager.cs` - 10-banana + destination objective
- `Core/CheckpointManager.cs` - checkpoint activation and safe respawn
- `Core/DestinationZone.cs` - ruins destination trigger
- `Player/PlayerMovement.cs` - CharacterController movement, jump and gravity
- `Player/GroundDetector.cs` - ground and slope probing
- `Player/PlayerCollisionHandler.cs` - solid collisions and hazard detection
- `Player/PlayerAnimationDriver.cs` - Idle/Walk/Run/Jump animator parameters
- `Camera/CameraFollowController.cs` - follow/orbit camera
- `Collectibles/Collectible.cs`, `CollectibleManager.cs` - banana pickups and reset
- `UI/UIManager.cs` - HUD, pause, completion and game-over screens
- `Performance/PerformanceMonitor.cs` - real frame-time and scene-cost measurement
- `Core/AutoPlayDriver.cs` - command-line playthrough and capture harness

The playable scene is generated deterministically by
`Assets/V6/Editor/V6SceneBuilder.cs` into
`Assets/V6/Scenes/JungleMonkeyV6.unity`. The build entry point is
`Assets/V6/Editor/V6Build.cs`.

### Gameplay loop

1. Start in `MainMenu`; press Start to enter `Playing`.
2. Move/run/jump through the jungle, collect 10 bananas and pass checkpoints.
3. Pause with Escape; restart with R.
4. Touching the river ends the run in `GameOver`; restart is available.
5. Collecting all bananas and entering the ruins calls
   `GameManager.CompleteLevel()` and enters `LevelCompleted`.

---

## 3. Tests

| Suite | Tests | Result | Evidence |
| --- | --- | --- | --- |
| Unity EditMode | 16 | 16 passed | `validation/unity-jungle-v6/Logs/editmode-results.xml` |
| Unity PlayMode | 15 | 15 passed | `validation/unity-jungle-v6/Logs/playmode-results.xml` |
| Python (MCP project) | 373 | OK | audit output / `reports/v6-phase5-audit.json` |

PlayMode coverage includes scene composition, missing scripts/materials/shaders,
grounded spawn, movement, jump and double-jump rejection, banana collection,
objective progress, pause/resume, restart reset, completion gating, solid
obstacle collision, animator parameters, river game over and out-of-bounds
respawn.

Python tests include the existing suite plus Phase 5 evidence integration tests
that re-hash the build, scene, screenshots and performance report.

---

## 4. Build

Command (batchmode):

```
Unity.exe -batchmode -nographics -projectPath validation/unity-jungle-v6 \
  -executeMethod V6.EditorTools.V6Build.BuildWindows -quit \
  -logFile validation/unity-jungle-v6/Logs/build-windows-final2.log
```

| Field | Value |
| --- | --- |
| Result | Succeeded |
| Platform | StandaloneWindows64 |
| Unity | 6000.6.2f1 |
| Build errors | 0 |
| Build warnings | 16 |
| Executable | `validation/builds/v6-windows/V6JungleMonkey.exe` |
| Executable size | 667,136 bytes |
| Build directory | 99,723,790 bytes, 156 files |
| SHA-256 | `af88b840e599661ac63fc10ae27ac77dd97cd46b44df8a7ce60eb0dcfacfc99e` |

The build output directory is ignored by git (`/validation/builds*/`).

---

## 5. Real playthrough and screenshots

The built player was launched with the in-game harness:

```
V6JungleMonkey.exe -v6autoplay \
  -v6capture reports/v6-captures \
  -v6seconds 60 \
  -v6perf reports/v6-gameplay-performance.json
```

The scripted run collected all 10 bananas, reached both checkpoints and entered
the ruins destination, producing a real `LevelCompleted` state. The run finished
in ~23 s of game time and exited cleanly after the completion screen.

| Screenshot | Path |
| --- | --- |
| Main menu | `reports/v6-captures/01-main-menu.png` |
| Playing | `reports/v6-captures/02-playing.png` |
| Paused | `reports/v6-captures/03-paused.png` |
| Level complete | `reports/v6-captures/04-level-complete.png` |

The completion screenshot shows `Bananas: 10 / 10` and the Play Again / Main
Menu actions. All captures are 1280x720 PNGs generated by the built player with
`ScreenCapture.CaptureScreenshot`.

---

## 6. Measured performance

Measured inside the built player on the test machine (AMD Radeon integrated GPU,
1280x720, Ultra quality). This is a real sample, not an estimate:

| Metric | Value |
| --- | --- |
| Frames sampled | 1,206 |
| Sample duration | 23.18 s |
| Average FPS | 52.0 |
| p95 frame time | 16.77 ms (~60 FPS) |
| Average frame time | 19.22 ms |
| 1% low FPS | 3.95 |
| Max frame time | 2,599 ms (first-run shader compilation hitch) |
| Managed memory | ~1.45 MB |
| Active triangles | 37,986 |
| Active renderers | 328 |
| Draw calls | -1 (recorder unavailable in the player) |
| Physics step | 20 ms |

The 1% low and maximum are dominated by a multi-second one-time shader
compilation hitch at startup. Steady-state p95 is 16.77 ms, i.e. 60 FPS class.
Draw calls could not be reported by the player build and are reported as `-1`
rather than guessed.

---

## 7. Defects found and fixed during integration

1. **Spawn resolved to the top of the player capsule.** `LevelManager` raycast
   with a serialized "Everything" mask sampled the player's own
   `CharacterController`, placing the spawn 1.68 m above the terrain. Fixed by
   always excluding the Player layer (layer 8) from the ground mask. The
   previously failing spawn/restart PlayMode tests now pass.
2. **River hazard never fired.** The water collider was a concave `MeshCollider`
   marked as a trigger, which Unity rejects ("Triggers on concave MeshColliders
   are not supported"). It is now an exact solid collider and
   `PlayerCollisionHandler` treats controller contact with `River_Water` as a
   hazard. A PlayMode test scans the river mesh, drops the player onto it and
   asserts `GameOver`.
3. **Automated capture froze on focus loss.** `Application.runInBackground`
   was false, so the player loop stopped when the window lost focus. It is now
   enabled in `GameBootstrap`, which makes scripted capture and performance
   sampling deterministic.
4. **Unity 6.2 API error in CollectibleManager.** `GetInstanceID()` usage that
   is a hard error in Unity 6 was replaced with a `HashSet<Collectible>`.

---

## 8. Evidence files

- `reports/v6-gameplay-integration.json` - systems, build, scene, playthrough,
  screenshots and performance, all hashed
- `reports/v6-gameplay-validation.json` - acceptance matrix, test evidence and
  requirement statuses
- `reports/v6-gameplay-performance.json` - raw measured performance
- `reports/v6-phase5-audit.json` - independent re-hash/audit verdict
- `reports/v6-build-raw.json` - Unity `BuildReport` summary
- `reports/v6-captures/` - four real screenshots
- `scripts/v6-phase5-demo.py` - reproducible build/test/play/report driver
- `scripts/v6-phase5-audit.py` - independent audit driver
- `validation/unity-jungle-v6/Logs/` - Unity scene/build/test/player logs

---

## 9. Honest limitations

- The scene is a stylized procedural prototype, not production art.
- No audio assets exist; audio hooks are silent.
- The river is contact-lethal; there is no swimming or water physics.
- Automated tests and a scripted playthrough do not replace human playtesting.
- Draw-call measurement was unavailable in the player build and is reported as
  `-1`.
- The first-run performance sample includes a shader compilation hitch.
- No requirement is marked human-verified. `human_review.status` is `pending`.

---

## 10. Gate

Phase 5 stops here for human review. A person must play the built player and
inspect the screenshots before sign-off. Phase 6 has **not** been started.
