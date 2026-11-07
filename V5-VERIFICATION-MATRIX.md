# V5 Verification Matrix

Generated from the live manifest, verifier output and evidence files on
2026-11-07. Status values are exactly those stored in
`validation/unity-jungle-v5/.game-studio/manifest.json` (revision 35).

---

## 1. Requirement matrix

| ID | Requirement | Classification | Current status | Evidence path (primary) | Verification method | Result | Remaining limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | Dimension: 3d | explicit | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode scene test + verifier `dimension_3d` + build/runtime evidence | PASS (tested) | No human visual inspection |
| R-002 | Art direction: low poly | explicit | implemented | `v5-blender-assets.json` | Verifier `low_poly_style` + FBX stats | IMPLEMENTED | Visual style quality not independently assessed |
| R-003 | Environment: jungle | explicit | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode scene test + verifier `jungle_environment` + Jungle.fbx | PASS (tested) | No human assessment of level design |
| R-004 | Character: monkey | explicit | tested | `Assets/V5/Art/Monkey.fbx` | PlayMode animated-monkey test + verifier `monkey_character` | PASS (tested) | Animation playback quality not independently proven |
| R-005 | Genre: adventure | explicit | pending | — (none) | No automated proxy exists | OPEN (pending) | "Adventure feel" requires human playtesting |
| R-006 | Platform: pc | explicit | tested | `.game-studio/evidence/build-artifact.json` | Verifier `pc_platform` + StandaloneWindows64 provenance | PASS (tested) | Player not re-launched by driver this session |
| R-007 | Gameplay: jumping | explicit | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode `JumpRaisesPlayerAboveGround` + verifier `jumping` + peak Y 1.709 | PASS (tested) | Jump feel not human-assessed |
| R-008 | Gameplay: collectibles | explicit | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode collectible test + verifier `collectibles` | PASS (tested) | One collected banana in the recorded run (score 1/10) |
| R-009 | Gameplay: score | explicit | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode score/HUD tests + verifier `score` | PASS (tested) | Only score 1 observed, not the full 10-banana loop |
| R-010 | Player traversal | implied | tested | `.game-studio/evidence/source/v5-player-evidence.json` | PlayMode movement test + distance 17.394 m | PASS (tested) | Single scripted traversal |
| R-011 | Interaction system | implied | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode trigger-collectible test | PASS (tested) | Only banana trigger interaction exercised |
| R-012 | Collectibles and objectives | implied | tested | `.game-studio/evidence/source/v5-playmode-results.xml` | PlayMode collection objective test | PASS (tested) | Prototype objective only |
| R-013 | NPC and dialogue | implied | rejected | — | Approved scope decision D-007 | EXCLUDED (rejected) | Not implemented by design |
| R-014 | Save and progression | implied | rejected | — | Approved scope decision D-007 | EXCLUDED (rejected) | Not implemented by design |
| R-015 | Player controller | implied | tested | `Assets/V5/Scripts/MonkeyController.cs` | PlayMode movement/jump tests + verifier `player_controller` | PASS (tested) | Input-mapping edge cases not exhausted |
| R-016 | Camera | implied | implemented | `Assets/V5/Scripts/CameraFollow.cs` | Scene presence + camera verifier check + rendered frame | IMPLEMENTED | Follow behavior not directly asserted by a test |
| R-017 | UI/HUD | implied | tested | `Assets/V5/Scripts/HUDController.cs` | PlayMode HUD test finds "Bananas" and "/" | PASS (tested) | Visual layout/readability not human-assessed |
| R-018 | 3D asset import pipeline | technical | tested | `Assets/V5/Art/Monkey.fbx` (+ Jungle/Banana) | PlayMode `NoMissingScriptsOrMaterials` + FBX GUID references | PASS (tested) | Only this asset set exercised |
| R-019 | Version control and reproducible project setup | technical | implemented | `ProjectSettings/ProjectVersion.txt` | Project settings, package manifest and solution inspected | IMPLEMENTED | Not independently rebuilt by this driver |
| R-020 | Quest log | optional | rejected | — | Optional AI suggestion | EXCLUDED (rejected) | Not requested or approved |
| R-021 | Crafting | optional | rejected | — | Optional AI suggestion | EXCLUDED (rejected) | Not requested or approved |
| R-022 | Fast travel | optional | rejected | — | Optional AI suggestion | EXCLUDED (rejected) | Not requested or approved |
| R-023 | Photo mode | optional | rejected | — | Optional AI suggestion | EXCLUDED (rejected) | Not requested or approved |
| R-024 | Achievements | optional | rejected | — | Optional AI suggestion | EXCLUDED (rejected) | Not requested or approved |

### Status totals

| Status | Count |
| --- | --- |
| tested | 13 |
| implemented | 3 |
| pending | 1 |
| rejected | 7 |
| blocked | 0 |
| verified | **0** |

**No requirement is marked `verified`.** `verified` is reserved for documented
human playtesting and inspection, which does not exist.

---

## 2. Independent artifact-check results

Command: `python scripts\v5-verify-slice.py --check all --json`

| # | Artifact check | Result | Key observation |
| --- | --- | --- | --- |
| 1 | PlayMode XML | **PASS** | 9/9 tests passed, 0 failed, 0 skipped, 4.1241215 s |
| 2 | Windows executable | **PASS** | `JungleMonkey.exe`, 667,136 bytes, Unity runtime + data present |
| 3 | Build evidence JSON | **PASS** | Success, StandaloneWindows64, exit 0 |
| 4 | Build provenance consistency | **PASS** | Provenance and log agree (success, exit code 0) |
| 5 | Player runtime evidence | **PASS** | Distance 17.394 m, peak Y 1.709, grounded true, score 1/10 |
| 6 | Screenshot | **PASS** | Valid PNG 1280×720, 300,694 bytes |
| 7 | Blender asset statistics | **PASS** | Monkey 3,072 tris / 14 bones; Jungle 15,532 tris / 6 materials; Banana 828 tris |
| 8 | Imported Unity assets | **PASS** | FBX GUIDs referenced by scene and banana prefab |
| 9 | `JungleMonkey.unity` scene | **PASS** | Player, HUD, camera, manager, 10 bananas, 5 runtime script markers |
| 10 | Runtime scripts / gameplay systems | **PASS** | 6 scripts and all gameplay markers present |
| 11 | Evidence copies | **PASS** | In-project copies match source SHA-256 for all 5 artifacts |
| 12 | Human playtest | **NOT VERIFIED** | No dated human playtest checklist exists |

Verifier top-level result: **NOT VERIFIED** (11/12 component checks passed;
exit code 1). This is correct and expected because human playtest evidence is
absent.

### Evidence-copy integrity

| Artifact | SHA-256 (source = copy) | Match |
| --- | --- | --- |
| `v5-playmode-results.xml` | `4cac427c…184d82bb` | yes |
| `v5-player-evidence.json` | `139c7a43…34ef40a7` | yes |
| `v5-player-screenshot.png` | `b045c643…c870a9` | yes |
| `unity-player-build.provenance.json` | `224b5f24…70259d7` | yes |
| `v5-player.log` | `e845ccaa…2081c28` | yes |

---

## 3. Human playtest status

**NOT VERIFIED.**

No human playtest record — a dated checklist with build hash and observations —
exists. Automated PlayMode tests, a rendered screenshot and machine runtime
values cannot verify fun, visual quality, camera feel or animation quality.

---

## 4. Failed, blocked and not-verified checks

| Check | Status | Reason |
| --- | --- | --- |
| Human playtest | NOT VERIFIED | No human evidence recorded |
| Live LLM provider evaluation | BLOCKED / NOT VERIFIED | No authorized provider credential; Ollama absent and not installed |
| Requirement `R-005` (adventure genre) | PENDING | No automated proxy for genre feel |
| Independent verifier overall | NOT VERIFIED | Correctly reports the missing human-playtest check; all 11 artifact checks PASS |
| Failed artifact checks | none | 0 FAIL, 0 BLOCKED among the 11 machine checks |

No requirement was upgraded to success to hide a failure. No check was weakened.

---

## 5. Overall comparison result

`compare_project_against_requirements` reported:

| Field | Value |
| --- | --- |
| Overall | **`partial`** |
| Total requirements | 24 |
| Tested | 13 |
| Implemented | 3 |
| Pending | 1 |
| Rejected | 7 |
| Verified | 0 |
| Blocked | 0 |
| Open (pending + implemented) | 4 |
| Invalid claims | 0 |
| Requirements with issues | 0 |
| Detected engine | `unity` |

**What `partial` means here:** the vertical slice is built and machine-tested for
the core loop and shipped artifacts, but it is not fully verified. 13
requirements have automated test evidence, 3 are implemented without full
behavioral verification, 1 (adventure genre feel) is still pending, and 7 are
explicitly rejected/out of scope. Zero requirements are human-verified. The
`partial` result is accurate and must not be read as "every requirement passes."

---

## 6. Manifest integrity summary

| Check | Result |
| --- | --- |
| Original request preserved exactly | PASS |
| 24 requirements with consistent classifications | PASS |
| Exclusions preserved (climbing, swimming, weapons, Android) | PASS |
| Swinging excluded via approved decision D-006 | PASS |
| Excluded features absent from requirement work | PASS |
| Optional R-020…R-024 rejected | PASS |
| Evidence paths relative and inside project boundary | PASS |
| Evidence copies exist and hashes match | PASS |
| No secrets/tokens/raw long hex digests in manifest | PASS (0 raw 40+ hex) |
| Dependency graph valid and acyclic (34 nodes / 37 edges) | PASS |
| Decisions approved with provenance | PASS (9/9, source `user`) |
| Execution plan `executable: false` | PASS |
| Paid/unavailable actions approval-gated | PASS |
| No requirement `verified` | PASS |
| Revision/history coherent | PASS (revision 35, 34 history entries) |
