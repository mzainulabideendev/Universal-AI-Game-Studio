# V6 Phase 10 — Controlled Real-World Validation

**Product:** UNIVERSAL AI GAME STUDIO
*From Game Idea to Playable World.*

| Field | Value |
| --- | --- |
| Document type | Proposal only — not an execution record |
| Generated | 2026-11-13T09:42:02Z |
| Repository HEAD | `5b263982b23334f0495413034c17eac1058e01fd` |
| Branch | `main` |
| Working tree at proposal | clean |
| Phase 10 implemented | no |
| Execution performed | none |
| **Final status** | **`PROPOSAL_ONLY_PENDING_USER_APPROVAL`** |

> **Read this first.** Nothing in this document has been executed. No network request was made, no credential was read, no engine was launched, no asset was imported, no build was produced, and no commit, tag or release exists. Every figure below is either a re-verified local fact from the proposal-time baseline or clearly labelled historical evidence. The status `PROPOSAL_ONLY_PENDING_USER_APPROVAL` is the only status this phase currently holds.

---

## 1. Why Phase 10 exists

Phases 0–9 produced a working studio, a deterministic game-generation pipeline, a Unity prototype scene, a Windows player and an extensive automated test suite. They also produced a large amount of *intermediate* evidence that has never been independently audited, and one integration that has never succeeded at all: a live AI provider returning a usable response body.

Phase 10 is deliberately not a feature phase. It is the phase that asks whether the claims already on record are true, and it refuses to manufacture new claims in the process.

Three trust boundaries are crossed for the first time:

1. **A live external service** (free-tier AI provider) receives a request and returns untrusted content.
2. **A real engine** (Unity 6000.6.2f1) imports generated assets and must prove mesh, rig, clip, texture and material correctness.
3. **A real Windows build** must be played, soaked and measured rather than assumed.

Each boundary is bounded, reversible and separately approved. No stage chains automatically into the next.

---

## 2. Verified baseline at proposal time

All figures below were recomputed locally while preparing this proposal. They are the starting point Phase 10 would freeze at `P10-S0`, not a claim about what Phase 10 will achieve.

### 2.1 Repository state

| Check | Result |
| --- | --- |
| HEAD | `5b263982b23334f0495413034c17eac1058e01fd` |
| HEAD subject | Update Phase 9 reports and audit scripts with human review decisions and adjustments |
| Branch | `main` |
| Working tree | clean (0 staged, 0 unstaged, 0 untracked) |
| Tags | none |
| Commits / pushes / tags by this proposal | 0 / 0 / 0 |

**Phase 9 uncommitted-change question:** resolved. The nine decision-recording paths recorded in the Phase 9 baseline were committed externally as `5b26398`. None remain uncommitted. The Phase 9 report head `fe28ba1d…` is one commit behind HEAD.

### 2.2 Automated verification

| Check | Result | Evidence |
| --- | --- | --- |
| Offline Python suite | **515 / 515 passed**, `OK`, exit 0, 75.327 s | `reports/v6-phase10-baseline.json` |
| MCP tool/handler parity | **107 tools / 107 handlers**, exact, 0 missing, 0 extra | same |
| Protected hash entries | **38 / 38 match**, 0 mismatched, 0 missing | same |
| Unique protected files | 23 | same |

The 38 recorded entries cover 23 unique files because the 23 Phase 5 records include the 13 V5 and 2 V4 records (duplicate coverage, not duplicate files).

### 2.3 Environment

| Component | Value |
| --- | --- |
| Platform | Windows 11 Pro 10.0.26200, 64-bit |
| CPU / RAM / GPU | Ryzen 5 4500U (6 threads), 15.4 GB, integrated Radeon |
| Python | 3.12.10 |
| Unity | 6000.6.2f1, changeset `770e33f6875c`, present |
| Unity modules | Windows Standalone, Android, WebGL |
| Blender | 5.2.2 LTS, present |
| Visual Studio / .NET SDK | 18.10.12217.157 / 10.0.401 |
| Free disk | C: 45.0 GB, D: 175.1 GB |

### 2.4 What is actually verified vs. not verified

**Verified (observed, local, reproducible):**

- The offline suite passes 515/515.
- Tool and handler counts are exactly 107/107.
- All 38 protected hash entries match.
- The Phase 5 Unity project, scene and Windows build exist with recorded hashes.
- The built Windows player previously ran a scripted 23-second playthrough and completed the level.
- Blender 5.2.2 generated a rigged, textured character and a three-tier jungle environment.
- The Unity project contains `.meta` import state, FBX GUID references, an animator controller referencing four clips, and a succeeded build log.

**Not verified (and therefore not claimed):**

- No live AI provider has ever returned a response body. Three approved Gemini attempts failed (one HTTP 503, two read timeouts). Zero success.
- No live model output has been schema-validated or quality-scored.
- No independent Unity import audit has measured mesh, bone, clip, texture or material correctness.
- No test proves that imported clips actually deform the character mesh during playback.
- No objective material-appearance or texture colour-space test exists.
- No single run has taken a new idea through live AI, new assets, Unity integration and a new build.
- No Windows soak, cold-start matrix, DPI, resolution, save-corruption or clean-machine test exists.
- No human playtest or visual sign-off exists.
- No release candidate combines live AI, engine import and runtime evidence.
- Studio provider-to-engine import remains disabled per Phase 9 S12.

### 2.5 Existing import evidence and its exact meaning

Unity already consumed the Phase 3/4 FBX files during the Phase 5 scene build. That is **intermediate engine evidence**, not independent import verification. It proves the files were loadable and that a build succeeded; it does not prove triangle parity, bone binding, clip deformation, texture colour space or material appearance.

This reconciles the apparent contradiction with the Phase 8/9 statement `engine asset import performed=false`, which describes the *studio's provider/download-to-engine path*, not the Phase 5 scene builder loading local FBX files. Phase 10 must avoid both the overclaim ("import was fully validated") and the underclaim ("nothing was ever imported").

---

## 3. Scope

### 3.1 Five workstreams

| ID | Workstream | Stages | Core question |
| --- | --- | --- | --- |
| W1 | Live free-tier AI provider validation | S1–S3 | Can one genuinely free, currently eligible provider return a valid structured response for an exact approved request, with no paid fallback? |
| W2 | Real Unity character + environment import | S8–S11 | Do the FBX assets import with correct mesh, rig, clips, textures and materials, and do they render and animate? |
| W3 | Controlled end-to-end generation | S4–S7, S12–S13 | Can one new idea travel through spec, approval, orchestration, new character, new environment, integration and a new playable build, with no automatic step? |
| W4 | Windows application reliability | S14 | Does the player survive repeated starts, a soak, focus and display changes, save faults and a clean profile? |
| W5 | Release-candidate verification | S15 | Does the combined evidence support an honest release-candidate verdict without a production or release claim? |

### 3.2 Explicitly out of scope

- Paid providers, paid assets or paid services of any kind.
- Package, model, engine or runtime installation or download.
- Automatic full-pipeline execution.
- Publishing, releasing, committing, pushing or tagging.
- Modifying protected V4, V5 or Phase 5 projects, builds or accepted reports.
- Untrusted third-party engine asset import.
- Android, WebGL or multiplayer validation.
- Production art quality.

---

## 4. Execution model: 16 stages, one approval each

Execution is **stage-gated and manual**. There is no orchestrator that can run Phase 10 end to end. Approval is not reusable, not transferable between stages, and becomes invalid if any bound input changes.

Each approval binds to: stage id, exact command or operation, input hashes, output directory, provider or engine, maximum request/run count, and an expiry.

### 4.1 Stage table

| Stage | Name | Kind | Network | Credentials | Engine | Approval |
| --- | --- | --- | --- | --- | --- | --- |
| P10-S0 | Baseline re-verification and freeze | read-only local | no | no | no | A0 |
| P10-S1 | Provider terms and free-tier re-verification | human review | no | no | no | A1 |
| P10-S2 | Model discovery request | live network, read-only | yes | yes | no | A2 |
| P10-S3 | Single live generation request | live network, generation | yes | yes | no | A3 |
| P10-S4 | Human approval of the generated spec | human review | no | no | no | A4 |
| P10-S5 | Agent orchestration dry run | local planning | no | no | no | A5 |
| P10-S6 | New character generation (isolated) | Blender | no | no | yes | A6 |
| P10-S7 | New environment generation (isolated) | Blender | no | no | yes | A7 |
| P10-S8 | Unity import laboratory creation | project copy | no | no | yes | A8 |
| P10-S9 | Character import and playback validation | Unity import | no | no | yes | A9 |
| P10-S10 | Environment import and scene integration | Unity import | no | no | yes | A10 |
| P10-S11 | Unity EditMode and PlayMode suites | engine tests | no | no | yes | A11 |
| P10-S12 | Playable Windows build | engine build | no | no | yes | A12 |
| P10-S13 | Runtime playthrough and captures | local runtime | no | no | no | A13 |
| P10-S14 | Windows reliability matrix | local runtime | no | no | no | A14 |
| P10-S15 | Release-candidate verification | read-only audit | no | no | no | A15 |

**Plus one release gate:** `A16` covers any commit, push, tag, publication or release. Its default state is `NOT_REQUESTED_AND_NOT_AUTHORIZED`. Approving the proposal does not approve A16.

That is 16 stage approvals (A0–A15) plus 1 release approval (A16) = 17 recorded gates.

### 4.2 Stage detail

**P10-S0 — Baseline re-verification and freeze** (~5 min)
Recompute HEAD and clean-tree state, all 38 protected hashes, the 515-test suite, 107/107 parity, and record Unity/Blender versions. No engine or network operation. Output: `reports/v6-phase10-execution-baseline.json`.

**P10-S1 — Provider terms and free-tier re-verification** (~20 min, human)
A human opens the provider's current official pricing, rate-limit, model and data-policy pages. No agent fetch, no credential read. Must confirm: free eligibility, no payment method, explicit retention terms, exact model on the current free list. The human signs the provider choice. Output: `reports/v6-phase10-provider-reverification.json`.

**P10-S2 — Model discovery** (~5 min, 1 request)
Exactly one authenticated model-list/metadata request. No prompts, no project content, no repository data. Credential is provisioned by the user outside the repository and outside chat; the agent checks presence only and never prints or stores the value. Output: `reports/v6-phase10-model-discovery.json` plus a quota-ledger entry.

**P10-S3 — Single live generation** (~10 min, 1 request)
A request plan is hashed with SHA-256 over provider, model, endpoint, prompt, output cap, JSON mode, timeout and zero-retry policy. The user approves that exact hash. One request, 60-second total deadline, 2,048 output-token cap, `retries=0`, `provider_fallback=false`, `paid_fallback=false`. The response is validated locally for JSON, schema, required fields, contradictions and unsupported claims, then scored with a deterministic rubric.

Failure is evidence. On failure: record the redacted error class and status, do not retry, do not switch provider, do not fall back to paid. Continue with a labelled deterministic fallback only if the user approves the next stage.

**P10-S4 — Human approval of the specification** (~20 min)
A named human accepts, rejects or requests changes. No requirement is marked verified or implemented. The approved spec hash is frozen.

**P10-S5 — Orchestration dry run** (~5 min)
The existing deterministic coordinator produces a plan with `executable=false`, every step `executed=false` and `requires_approval=true`.

**P10-S6 — Character generation** (~5 min)
One Blender 5.2.2 process, writing only to `validation/v6-phase10/character/`. Validates geometry, UVs, materials, rig, clips and exports; re-imports the GLB into an empty scene. Acceptance: exit 0, UVs present, no degenerate faces, ≥6 bones, 100% weighted vertices, Idle/Walk/Run/Jump exported, all formats hashed.

**P10-S7 — Environment generation** (~10 min)
One Blender process, writing only to `validation/v6-phase10/environment/`. Acceptance: exit 0, non-flat terrain within bounds, river/spawn/route/destination present, all material slots resolve, all formats hashed.

**P10-S8 — Unity import laboratory** (~20 min, ~350 MB)
Copy only `Assets`, `ProjectSettings` and `Packages` from `validation/unity-jungle-v6` to `validation/v6-phase10/unity-import-lab`. Never copy `Library` or `Logs`. Open once in batch mode to regenerate the Library. Confirm the source project is unchanged. This satisfies both constraints: use the existing Unity 6000.6.2f1 baseline, and never modify the Phase 5 project.

**P10-S9 — Character import and playback** (~15 min)
Import with animation type Generic, animation enabled. An editor validation script reports mesh, bone, clip, material and texture facts. A PlayMode test samples bone poses over time and captures screenshots. Acceptance: 0 import errors, triangle count within 2% of 15,688, SkinnedMeshRenderer with ≥23 bones, four non-empty clips, sampled bone motion > 1 cm, no NaN, fur base-colour and normal maps bound, no magenta render, human review.

**P10-S10 — Environment import and scene integration** (~20 min)
Import and validate counts, slots, textures and hierarchy; build the scene with the existing builder; instantiate the character and run existing gameplay systems. Acceptance: 0 import errors, triangles within 2% of 53,674, terrain non-flat with valid collider, river present and contact-lethal, ≥19 material slots resolve, no missing shader, player spawns grounded, camera/HUD/10 collectibles/destination present.

**P10-S11 — Unity test suites** (~15 min)
Run EditMode and PlayMode in batch mode; record XML results and console. Acceptance: 0 failures each, skipped tests reported not hidden, no unhandled exception.

**P10-S12 — Windows build** (~15 min)
Build StandaloneWindows64 into `validation/v6-phase10/builds/windows/`. Acceptance: result Succeeded, 0 errors, executable and payload exist and are hashed, executable is not the V5/Phase 5 artifact.

**P10-S13 — Runtime playthrough** (~10 min)
Launch with the in-game auto-play harness; collect 10/10 bananas, reach checkpoints, complete the level; capture menu/playing/pause/completion at 1280×720; record performance and the player log. Acceptance: exit 0, `LevelCompleted`, 10/10 bananas, four captures, no missing object, no unhandled exception.

**P10-S14 — Windows reliability matrix** (~120 min)
20 cold starts; one 60-minute soak with memory and frame-time sampling; focus loss, pause/resume, resolution change, DPI scaling, multi-monitor; save, reload, corrupted save, read-only save directory; path with spaces and non-ASCII characters; launch on a profile without Unity installed; document SmartScreen and antivirus behaviour for the unsigned executable. Acceptance: 20/20 exit 0, no crash in 60 minutes, post-warmup managed-memory growth < 10%, no progress loss, input/UI survive display changes, corrupted save handled, read-only directory produces a clear diagnostic, unsigned-build warnings documented.

**P10-S15 — Release-candidate verification** (~30 min)
Recompute protected hashes, run the full offline suite, re-read every Phase 10 evidence file, mark each criterion `PASS`, `FAIL`, `NOT_TESTED` or `HUMAN_REVIEW_REQUIRED`, and publish no release and make no commit. A human then signs off separately.

---

## 5. Provider recommendation

**Recommended primary: Groq (GroqCloud).**
Recorded on 2026-11-10 as `free_limited`: documented per-model limits of 30 RPM, 1,000 RPD, 8,000 TPM and 200,000 TPD; no documented payment requirement; OpenAI-compatible adapter already exists; structured output documented.

**Alternatives for consideration only:**
- **Gemini** — existing adapter and prior approval path, but three live attempts failed before any response body, free-tier limits are not reliably exposed per project, and free-tier content may be used for product improvement.
- **OpenRouter** — only `:free` model ids are eligible, no specific free model is verified in the catalogue, daily limits depend on all-time credits, and data policy varies by upstream provider.

**All availability is `UNVERIFIED_AT_PROPOSAL_TIME`.** No network request or web fetch was permitted while preparing this proposal, so no statement here describes today's live catalogue. `P10-S1` must re-verify every field against the provider's own current pages before any credential is used or any request is approved.

**Rejected options:** Stability AI (trial credits then paid), Hugging Face Inference Providers (paid), Meshy (prepaid), Tripo (usage-based paid), Ollama (local but requires an unapproved runtime install and model download; a possible later option only with separate approval).

### 5.1 Hard request limits

| Limit | Value |
| --- | --- |
| Model-discovery requests | 1 |
| Generation requests | 1 |
| Maximum total live requests | 2 |
| Maximum total output tokens | 2,048 |
| Per-request wall clock | 60 s |
| Retries | 0 |
| Provider switches after failure | 0 |
| Paid fallback | none |
| Project / repository / personal content sent | none |

### 5.2 What a successful live request must produce

Current free eligibility re-verified by a human, credential present but never read, model discovery returning the exact approved model id, exactly one generation request matching the approved hash, HTTP 2xx with a complete body, one JSON object passing the contract schema with zero errors, unsupported claims and contradictions reported, a deterministic quality score, a quota-ledger entry with a zero-cost estimate, no project/asset/build file modified, and a clean credential scan of every artifact.

---

## 6. Unity import plan

**Engine:** Unity 6000.6.2f1 (changeset `770e33f6875c`), target StandaloneWindows64.
**Source project (read-only input):** `validation/unity-jungle-v6`.
**Execution lab:** `validation/v6-phase10/unity-import-lab`.
**New build output:** `validation/v6-phase10/builds/windows`.

Copy, never modify. The Phase 5 project and all protected evidence stay hash-stable. Protected inputs include `validation/unity-jungle-v5`, `validation/unity-jungle-v6`, `validation/builds/v5-windows` and `validation/builds/v6-windows`.

### 6.1 Asset inventory (all byte-identical to Blender outputs)

| Asset | Bytes | SHA-256 (short) | Known facts |
| --- | --- | --- | --- |
| Character FBX `JungleMonkey.fbx` | 1,513,628 | `634e2e64…b9cf6` | 7,974 verts, 15,688 tris, 7 materials, 23 bones, 23 vertex groups, 100% weighted, UVMap, clips Idle/Walk/Run/Jump |
| Character base colour | 162,812 | `0442abca…c990c` | 512², sRGB expected |
| Character normal | 235,413 | `36c73708…b6e8ce` | 512², Normal map, non-sRGB |
| Character roughness | 146,417 | `9aa24e98…4c2000` | 512², non-sRGB; not wired into current material |
| Environment FBX `JungleLevel.fbx` | 2,250,540 | `fc39f575…a81f9` | medium tier, 53,674 tris, 8,450 terrain tris, 287 vegetation instances, 343 objects, 19 materials, 120×120 m terrain, 7.09 m relief, river 192 tris |
| Environment base colour | 177,081 | `841259b1…ee955` | 512², sRGB |
| Environment normal | 286,025 | `dc5f9463…78c6f0` | 512², Normal map |
| Environment roughness | 149,377 | `581e9092…71e5f` | 512², non-sRGB |
| High-tier environment (optional) | 3,671,740 | — | 83,930 tris, 562 objects, 19 materials, 1024² textures; never tested in Unity |

Animation clips (embedded): Idle 1–60 @30 fps (2.0 s, 6 fcurves), Walk 1–25 (0.833 s, 9), Run 1–19 (0.633 s, 12), Jump 1–30 (1.0 s, 12).

### 6.2 Objective tests (UT1–UT14)

| ID | Area | Assertion | Threshold |
| --- | --- | --- | --- |
| UT1 | Import | Zero import errors, no missing-script message | errors = 0 |
| UT2 | Mesh | Character triangle count matches source | within 2% of 15,688 |
| UT3 | Rig | Skinned mesh with full skeleton | 23 bones; every vertex weighted |
| UT4 | Clips | Four named clips with non-zero length | all present, > 0.1 s |
| UT5 | Playback | Bones move over time | > 1 cm Idle/Walk/Run; > 5 cm Jump; no NaN |
| UT6 | Textures | Correct colour space | base sRGB true; normal false + NormalMap; roughness false |
| UT7 | Materials | Every renderer has a valid shader | 0 missing; 0 `Hidden/InternalErrorShader` |
| UT8 | Appearance | Not magenta | no dominant full-frame magenta; human accepts capture |
| UT9 | Environment | Terrain non-flat, river exists | Y range > 5 m; `River_Water` present |
| UT10 | Env materials | All slots resolve | 0 missing; ≥19 distinct slots |
| UT11 | Integration | Real gameplay loop works | all PlayMode tests pass |
| UT12 | Build | New player builds | Succeeded; 0 errors |
| UT13 | Runtime | Player completes level | exit 0; LevelCompleted; 10/10; 4 captures |
| UT14 | Preservation | Source projects unchanged | 38/38 hashes; 0 protected changes |

### 6.3 Known differences Phase 10 will not fix

Procedural prototype art, short procedural clips, no AO/emission/opacity maps, unwired roughness maps, visual-only water with contact hazard (no swimming), metadata-only navigation, no audio, no automatic provider-to-engine import, and no untrusted third-party asset import.

---

## 7. Risks and mitigations

**Overall risk: HIGH**, because three trust boundaries are crossed. Residual after the stated mitigations: **MEDIUM**. Risk is not accepted until the user approves each gate.

| ID | Risk | Likelihood | Impact | Mitigation | Stop |
| --- | --- | --- | --- | --- | --- |
| R1 | Free models/quotas/terms no longer valid | high | medium | Fresh human re-read in S1; one discovery request in S2; never trust a static model name; stop rather than substitute | SC4 |
| R2 | Provider requires billing or paid upgrade | medium | critical | Free-only gate; paid fallback hard-disabled; no payment details ever entered | SC3 |
| R3 | Credential exposure in command line, log, report or chat | medium | critical | User provisions outside repo/chat; presence-only checks; header redaction; secret scan; rotation on suspicion | SC2 |
| R4 | Free-tier retention/training terms | high | medium | Send only a controlled non-proprietary idea; no project/repo/personal data; record and accept policy in S1 | S1 disqualifier |
| R5 | Rate-limit / HTTP 429 | medium | low | Two bounded requests total; 2,048-token cap; no retry; record reset info | SC5 |
| R6 | Provider slow or hangs (as in Phase 7) | high | medium | 60 s total deadline; bounded DNS/connect/TLS/header/body stages; no retry or switch | SC6 |
| R7 | Malformed, contradictory or overclaiming output | high | medium | Strict schema, contradiction and unsupported-claim detection, deterministic rubric, no execution of model output | SC14 |
| R8 | Prompt injection in output | medium | high | Treat all provider content as untrusted data; never execute it; flag and report attempts | SC15 |
| R9 | Protected Unity project modified | medium | critical | Disposable lab; read-only sources; 38-hash check before and after every engine stage; never `git reset`/`git clean` | SC1 |
| R10 | FBX imports with wrong scale, bones, clips or materials | medium | high | Existing Generic importer settings; measure facts; fail before scene work | SC8 |
| R11 | Clips exist but do not deform the mesh | medium | high | Sample bone transforms over time; check duration vs source; render per clip; human review | SC8 |
| R12 | Magenta material or wrong colour space | high | medium | Assert shader/texture bindings and sRGB flags; capture and review; document smoothness simplification | SC8 |
| R13 | Missing or wrong environment collision | medium | high | Validate colliders from imported meshes; PlayMode spawn/collision/river tests; preserve Phase 5 river fix | SC8 |
| R14 | Build fails or uses stale assets | low | high | Fresh lab Library; force scene rebuild and hash it; assert Succeeded; launch and parse the log | SC9 |
| R15 | Passes one run but unreliable on Windows | medium | high | 20 cold starts, 60-min soak, focus/resolution/DPI/save/clean-profile tests, documented SmartScreen behaviour | SC10 |
| R16 | Performance regression on integrated GPU | medium | medium | Measure post-warmup; separate first-run shader hitch; compare to Phase 5 p95 16.77 ms; no unmeasured target claim | Human review if p95 > 20 ms |
| R17 | Scope expands into a full pipeline | high | high | 16 separate gates, no automatic chaining, one idea and one build, scope changes need a new proposal | SC17 |
| R18 | Historical evidence mistaken for current proof | high | high | Re-verify at S0; fresh artifact per stage; five-level verification vocabulary; no PASS without a linked observation | SC18 |
| R19 | Unclear asset provenance or licence | low | high | Project-original assets only; no third-party downloads; provenance required before import | SC16 |
| R20 | Disk, memory, time or Unity licence prevents completion | low | medium | Check free disk (175 GB); one Blender process at a time; batch Unity with timeouts; stop below 20 GB | SC7 / SC12 |
| R21 | Automated PASS mistaken for human acceptance | medium | high | Human decisions recorded with name and scope; approvals bind to hashes; no release claim derived from automation | SC18 |

**Summary:** 21 risks — 4 critical impact (R2, R3, R9, plus provider-cost class), 10 high, 7 medium, 0 low. Most likely: R1, R4, R6, R7, R12, R17, R18.

**Risks that cannot be fully eliminated:** free-tier terms can change mid-work; a provider can stay unavailable despite a correct request; a procedural asset can import cleanly and still look poor to a human; OS-level socket cancellation remains unproven (carried over from Phase 9).

---

## 8. Acceptance criteria

Each criterion must end as `PASS`, `FAIL`, `NOT_TESTED` or `HUMAN_REVIEW_REQUIRED`, with a linked artifact. No criterion may be inferred from a previous phase.

| ID | Criterion | Target | Evidence |
| --- | --- | --- | --- |
| AC1 | Baseline integrity | 38/38 hashes, 515/515 tests, 107/107 parity | `v6-phase10-execution-baseline.json` |
| AC2 | Approval integrity | Every operation maps to an approved stage and exact input hash | `v6-phase10-approval-ledger.json` |
| AC3 | Live AI request | One schema-valid response, or an explicit honest failure with no success claim | `v6-phase10-live-validation.json` |
| AC4 | Unity import | Zero import errors; measured mesh/bone/clip/material facts | `v6-phase10-unity-character-import.json`, `v6-phase10-unity-environment-import.json` |
| AC5 | Animation playback | Four clips bind; sampled motion > 1 cm; no NaN | `v6-phase10-animation-playback.json` |
| AC6 | Material appearance | Textures bind; no pink; human visual check recorded | `v6-phase10-material-validation.json` |
| AC7 | End-to-end generation | One new idea reaches a new build through all approved stages | `v6-phase10-end-to-end.json` |
| AC8 | Windows reliability | 20/20 cold starts; 60-min soak; display/save tests pass | `v6-phase10-windows-reliability.json` |
| AC9 | Preservation | No protected V4/V5/Phase 5/report modification | `v6-phase10-protection.json` |
| AC10 | No paid service | Zero paid requests, zero paid fallback, zero billing changes | `v6-phase10-cost-audit.json` |
| AC11 | Honest reporting | Every criterion carries a status and evidence path | `v6-phase10-release-candidate.json` |
| AC12 | Human sign-off | A named human accepts or rejects the release candidate | `v6-phase10-human-signoff.json` |

**On a failed live request:** the honest outcome of Phase 10 may be `AI_LIVE_VALIDATION_FAILED` with the engine and reliability work still valid. That is an acceptable result. What is not acceptable is reporting success without a response body.

---

## 9. Expected evidence

Every stage writes a fresh, timestamped artifact. Historical files are never reused as proof of a new operation.

**Baseline and governance:** `v6-phase10-execution-baseline.json`, `v6-phase10-approval-ledger.json`, `v6-phase10-protection.json`, `v6-phase10-cost-audit.json`.

**Provider:** `v6-phase10-provider-reverification.json`, `v6-phase10-model-discovery.json`, `v6-phase10-live-request-plan.json`, `v6-phase10-live-response.json`, `v6-phase10-live-validation.json`, `v6-phase10-schema-validation.json`, `v6-phase10-quality-evaluation.json`, `v6-phase10-quota-ledger.json`, `v6-phase10-secret-scan.json`, `v6-phase10-request-audit.json`.

**Generation:** `v6-phase10-spec-approval.json`, `v6-phase10-orchestration.json`, `v6-phase10-generation-plan.json`, `v6-phase10-character.json`, `v6-phase10-environment.json`.

**Unity:** `v6-phase10-unity-lab.json`, `v6-phase10-unity-character-import.json`, `v6-phase10-animation-playback.json`, `v6-phase10-material-validation.json`, `v6-phase10-unity-environment-import.json`, `v6-phase10-scene-integration.json`, `v6-phase10-unity-tests.json`, plus capture directories and lab `Logs/` XML.

**Build and runtime:** `v6-phase10-build.json`, `v6-phase10-runtime.json`, `v6-phase10-player.log`, `v6-phase10-captures/`, `v6-phase10-windows-reliability.json`, `v6-phase10-windows-logs/`.

**Verdict:** `v6-phase10-release-candidate.json`, `v6-phase10-human-signoff.json`, `V6-PHASE-10-VALIDATION-REPORT.md`.

**Test evidence detail:** offline Python exit code and exact count; provider request hash, HTTP status, redacted error, response bytes, schema result, quality score; Blender logs and FBX/GLB hashes; Unity editor logs with mesh/bone/clip/material facts; sampled bone transforms at multiple times; shader names, texture GUIDs and sRGB flags plus a pixel sample proving non-magenta; EditMode/PlayMode XML; build report and executable hash; player log with the scene-valid line; cold-start table and soak samples; criterion table with statuses.

---

## 10. Resource estimate

| Resource | Estimate |
| --- | --- |
| Human review | 3–5 hours |
| Supervised execution | 4–6 hours |
| Elapsed | 1–2 working days |
| Live requests | 2 maximum (1 discovery + 1 generation) |
| Live cost | **USD 0.00** |
| Blender runs | 2 |
| Unity batch runs | 5–7 |
| Windows player runs | 21+ (20 cold starts + 1 soak) |
| New disk | ~425 MB (lab Library 250, build 100, captures/logs 50, assets 25) |
| Free disk available | 175.1 GB (D:) |
| Installs / downloads | 0 / 0 |

---

## 11. Stop conditions

Execution halts immediately — with a recorded, redacted reason — if any of the following occurs:

1. Any protected hash mismatch or protected path modification.
2. Any credential value appears in a log, report, command line or chat.
3. A provider requires billing, a card or a paid tier.
4. The selected model is not on the current free list.
5. Rate limit, quota exhaustion or HTTP 429.
6. Any unapproved network request is attempted or observed.
7. Unity licence, activation or editor launch failure.
8. Unity import error, missing script, missing shader or missing material.
9. Build errors > 0, or build result not `Succeeded`.
10. Player crash, non-zero exit or unhandled exception.
11. Any request to modify V5 or the Phase 5 project or build.
12. Free disk below 20 GB.
13. A stage exceeds its approved time or request count.
14. AI output claims verified, implemented, approved or executable status.
15. Prompt injection or instruction-like content appears in provider output.
16. Asset provenance or licence is missing.
17. A stage is asked to run the whole pipeline automatically.
18. Human approval is missing, expired or bound to a different hash.

---

## 12. Rollback and preservation

All Phase 10 writes go to new report files or `validation/v6-phase10/`. Deleting that directory and the Phase 10 reports restores the repository to the proposal state.

Rollback **never** uses `git reset --hard`, `git clean`, deletion of protected paths, or restoration of protected artifacts from generated copies. `validation/unity-jungle-v5` and `validation/unity-jungle-v6` are read-only inputs and are never rollback targets.

---

## 13. Go / no-go

**Recommendation:** `CONDITIONAL_GO_ONLY_AFTER_USER_APPROVES_A0_A1`.

Preconditions:
- The user accepts the stage-gated scope.
- The user selects a provider after current terms are recorded.
- The user provides credentials outside the repository.
- The user confirms the disposable Unity lab instead of modifying the Phase 5 project.
- The user accepts that a failed live request is a valid, honest outcome.

**No-go if:** the user expects an automatic pipeline, expects a production-ready game, cannot provide any free-tier credential, requires modifying the Phase 5 project, or requires a release in the same phase.

---

## 14. What approval of this proposal would and would not mean

**If approved explicitly, it would authorize only the first gate — `P10-S0` baseline re-verification.** Nothing else.

It would **not**:
- start Phase 10 execution;
- authorize any network request;
- authorize credential access;
- authorize a Unity or Blender build;
- authorize asset import;
- authorize a commit, push, tag, publication or release;
- make the product production-ready.

The Phase 9 S12, S14 and R3 decisions accept documented limitations only. They do not authorize Phase 10, live requests, engine imports, builds or releases, and this proposal does not inherit or imply any such authorization.

---

## 15. Deliverables of this proposal

| File | Purpose |
| --- | --- |
| `reports/v6-phase10-baseline.json` | Verified baseline, protected hashes, integration status matrix |
| `reports/v6-phase10-validation-plan.json` | 16 stages, 17 approval gates, acceptance criteria, stop conditions, resources |
| `reports/v6-phase10-provider-plan.json` | Groq/Gemini/OpenRouter terms, quotas, credentials, failure handling, evidence |
| `reports/v6-phase10-unity-import-plan.json` | Asset inventory, lab strategy, 14 objective tests, visual review |
| `reports/v6-phase10-risk-assessment.json` | 21 risks, mitigations, go/no-go |
| `reports/v6-phase10-proposal.json` | Proposal index and approval semantics |
| `V6-PHASE-10-PROPOSAL.md` | This document |

---

## 16. Final status

No Phase 10 operation was executed. No live request was sent. No credential was read. No engine was launched. No asset was imported. No build was produced. No commit, tag, push or release exists. The repository remains at `5b263982b23334f0495413034c17eac1058e01fd` with a clean working tree apart from these seven new proposal files.

**`PROPOSAL_ONLY_PENDING_USER_APPROVAL`**
