# V5 Unity Vertical Slice Report

Observed from the actual project, build, PlayMode results and runtime evidence in
this repository on 2026-11-07. No value below was taken from a prior report
without re-reading the source file.

---

## 1. Environment and target

| Item | Value |
| --- | --- |
| Engine | Unity `6000.6.2f1` (changeset `770e33f6875c`, x86_64) |
| Build target | `StandaloneWindows64` |
| Build execute method | `V5.EditorTools.V5Build.BuildWindows` |
| Build tool | `unity-cli 1.0.0-beta.8` |
| Host platform | Windows |
| Project root | `validation/unity-jungle-v5` |
| Scene | `Assets/V5/Scenes/JungleMonkey.unity` |
| Build output | `validation/builds/v5-windows/JungleMonkey.exe` |

---

## 2. Scene and project paths

| Artifact | Path |
| --- | --- |
| Scene | `validation/unity-jungle-v5/Assets/V5/Scenes/JungleMonkey.unity` (62,862 bytes) |
| Runtime scripts | `validation/unity-jungle-v5/Assets/V5/Scripts/` |
| Blender source outputs | `validation/unity-jungle-v5/Assets/V5/Art/` |
| Banana prefab | `validation/unity-jungle-v5/Assets/V5/Prefabs/Banana.prefab` |
| PlayMode tests | `validation/unity-jungle-v5/Assets/V5/Tests/PlayMode/` |
| Evidence copies | `validation/unity-jungle-v5/.game-studio/evidence/source/` |

The scene was independently inspected and contains the Player, HUD,
GameManager, Main Camera, 10 banana components, the imported monkey and jungle
FBX GUIDs, and script markers for `MonkeyController`, `GameManager`,
`HUDController`, `CameraFollow` and `BananaCollectible`.

---

## 3. Gameplay systems implemented

| System | Script | Evidence |
| --- | --- | --- |
| Run/traversal | `MonkeyController.cs` | PlayMode `MovementChangesPlayerPosition`; player evidence 17.394 m |
| Jump | `MonkeyController.cs` | PlayMode `JumpRaisesPlayerAboveGround`; runtime peak Y 1.709 |
| Grounding | `MonkeyController.cs` + CharacterController | PlayMode `PlayerIsGroundedByPhysics`; runtime `groundedAtEnd: true` |
| Collectibles | `BananaCollectible.cs` | PlayMode `CollectibleIncrementsScoreAndDisappears` |
| Score | `GameManager.cs` | PlayMode score/HUD tests; runtime score 1 |
| HUD | `HUDController.cs` | PlayMode `HudDisplaysBananaProgress` (finds "Bananas" and "/") |
| Restart | `GameManager.cs` | PlayMode `RestartResetsScorePlayerAndBananas` |
| Follow camera | `CameraFollow.cs` | Scene + rendered runtime screenshot; follow behavior not directly asserted |
| Animation | Animator on monkey | PlayMode `AnimatorReactsToMovement`; runtime `animatorPresent: true` |
| Physics/imports | Scene + FBX `.meta` GUIDs | PlayMode `NoMissingScriptsOrMaterials` |

Runtime scripts present: `MonkeyController.cs`, `CameraFollow.cs`,
`BananaCollectible.cs`, `GameManager.cs`, `HUDController.cs`, `V5DemoDriver.cs`,
plus `V5.Runtime.asmdef`.

---

## 4. Blender assets and statistics

Recorded in `validation/unity-jungle-v5/v5-blender-assets.json` (SHA-256
`24382e58ad4646ed06aa18d4e746b3c2d6e0f36a19bbcf0bc9d43a6096c795a3`):

| Asset | Vertices | Triangles | Other | Imported FBX |
| --- | --- | --- | --- | --- |
| Monkey | 1,588 | **3,072** | **14 bones**; actions `Idle`, `Jump`, `Walk` | `Assets/V5/Art/Monkey.fbx` (454,556 bytes) |
| Jungle | 8,122 | **15,532** | **6 materials**: JungleGround, River, TreeTrunk, CanopyA, CanopyB, Rock | `Assets/V5/Art/Jungle.fbx` (347,068 bytes) |
| Banana | 432 | **828** | — | `Assets/V5/Art/Banana.fbx` (30,428 bytes) |

All three FBX files are imported by Unity; their `.meta` GUIDs are referenced by
the scene and the banana prefab. The statistics were not re-derived by opening
Blender in this session.

---

## 5. Build

| Property | Value |
| --- | --- |
| Outcome | `success` |
| Exit code | `0` |
| Started | `2026-11-06T04:30:53.394Z` |
| Ended | `2026-11-06T04:31:13.362Z` |
| Executable | `validation/builds/v5-windows/JungleMonkey.exe` |
| Executable size | **667,136 bytes** (0.636 MB) |
| Executable SHA-256 | `af88b840e599661ac63fc10ae27ac77dd97cd46b44df8a7ce60eb0dcfacfc99e` |
| UnityPlayer.dll | 38,693,808 bytes |
| Data directory | `validation/builds/v5-windows/JungleMonkey_Data` (40,721,172 bytes) |
| Provenance file | `validation/unity-player-build.provenance.json` |
| Provenance SHA-256 | `224b5f245ca3cf2e1a8636b29a2cc02a11fd33b6b3c8aeb8d73b4fe7270259d7` |

Provenance records a source Git revision of
`4bf92a84c42e8516e6f54718ce675481e44f3139` with `dirty: true`. The build log is
244,384 bytes and ends with a successful batch-mode exit (code 0).

---

## 6. PlayMode test results

Source: `validation/v5-playmode-results.xml`
(SHA-256 `4cac427c6d22ff0bc852496dd0890cdb9cab6d524d9a3a3ed909a8df184d82bb`).

- Result: **Passed**
- Total: **9**, passed: **9**, failed: **0**, skipped: **0**
- Duration: 4.1241215 s
- Start/end: `2026-11-06 04:30:28Z` → `2026-11-06 04:30:32Z`

Tests:

1. `SceneContainsPlayerEnvironmentAndHud` — Passed
2. `MovementChangesPlayerPosition` — Passed
3. `JumpRaisesPlayerAboveGround` — Passed
4. `PlayerIsGroundedByPhysics` — Passed
5. `CollectibleIncrementsScoreAndDisappears` — Passed
6. `HudDisplaysBananaProgress` — Passed
7. `RestartResetsScorePlayerAndBananas` — Passed
8. `AnimatorReactsToMovement` — Passed
9. `NoMissingScriptsOrMaterials` — Passed

These tests support the status `tested`; they do not prove human-perceived
quality.

---

## 7. Runtime evidence

Source: `validation/v5-player-evidence.json`
(SHA-256 `139c7a43224a9a7e9b21afc5172391008e67ac6f5b1518a2b6e1688d34ef40a7`).

| Field | Value |
| --- | --- |
| `demoRan` | true |
| `scene` | JungleMonkey |
| Start position | (0.0, 0.15, 0.0) |
| End position | (0.0, 0.08, 17.394) |
| `distanceMoved` | **17.394 m** |
| `peakY` | **1.709** |
| `groundedAtEnd` | **true** |
| `score` | **1** |
| `totalBananas` | **10** |
| `animatorPresent` | true |
| `animatorSpeed` | 0.0 (idle at capture) |
| `error` | empty |

Caveat: this is machine-generated runtime evidence from the recorded player run.
It was not re-launched by the integration driver in this session, and it is not a
human playtest.

---

## 8. Screenshot evidence

| Property | Value |
| --- | --- |
| Path | `validation/v5-player-screenshot.png` |
| Format | PNG, valid signature and decodable |
| Dimensions | **1280 × 720** |
| Size | **300,694 bytes** |
| SHA-256 | `b045c643208bea5530aad2af2d621d41c500d1fad38a76c5de31816472c870a9` |
| Copy | `.game-studio/evidence/source/v5-player-screenshot.png` (hash matches) |

A valid screenshot proves one rendered frame exists. It does not prove that
every gameplay feature works or that the visuals meet human quality standards.

---

## 9. Evidence-copy integrity

The independent verifier compared source artifacts with the in-project copies
and all hashes matched:

| Artifact | Source = copy |
| --- | --- |
| `v5-playmode-results.xml` | yes |
| `v5-player-evidence.json` | yes |
| `v5-player-screenshot.png` | yes |
| `unity-player-build.provenance.json` | yes |
| `v5-player.log` | yes |

Paths are relative to the V5 project and stay inside the project boundary.

---

## 10. Reproduction commands

```powershell
# Rebuild and re-run the full governed V5 integration (archives prior memory)
python scripts\v5-mcp-integration.py --reset

# Independent slice verification (human-readable and JSON)
python scripts\v5-verify-slice.py
python scripts\v5-verify-slice.py --check all --json

# Security / handshake / provider / evidence regression
python scripts\v5-security-checks.py

# Deterministic fallback LLM evaluation
python scripts\llm-evaluation.py

# Full test suite
python -m unittest discover -s tools\game-studio-mcp\tests -q
```

Individual artifact checks can be targeted, for example:

```powershell
python scripts\v5-verify-slice.py --check windows_executable
python scripts\v5-verify-slice.py --check playmode_xml
python scripts\v5-verify-slice.py --check evidence_copies
```

---

## 11. Explicit exclusions and features not implemented

Out of scope and not implemented:

- Climbing
- **Swinging** (excluded through approved decision D-006; not in the analyzer's
  exclusion vocabulary)
- Swimming
- Weapons
- Android support

Also not implemented for this prototype (approved scope decision D-007): NPC
dialogue, save system and progression. These requirements are `rejected`, not
silently treated as done.

---

## 12. Unity slice limitations

- No human playtest or human visual inspection.
- The follow camera's behavior is inferred from code, scene presence and a
  rendered frame; it is not directly asserted by a dedicated automated test.
- Animation clips exist and an Animator is present; correct playback of every
  clip is not independently proven.
- Blender source statistics were not re-generated in this session.
- The executable was not re-launched by the integration driver.
