# Game Studio MCP acceptance report

Date: 2026-11-06
Platform: Windows 11, Python 3.12.10
Blender: 5.2.2 LTS
Unity Editor: 6000.6.2f1
Unity CLI: 1.0.0-beta.8

This report separates implemented code from executed evidence. Nothing below is
claimed beyond what the recorded commands and artifacts show.

## 1. Implemented

| Area | Tools |
| --- | --- |
| Understanding/planning | `analyze_game_request`, `create_game_specification`, `init_project_manifest`, `get_project_manifest`, `update_requirement_status`, `record_project_decision`, `track_project_progress`, `compare_project_against_requirements` |
| Studio/config | `studio_info`, `detect_system`, `detect_game_engines`, `list_available_engines`, `select_game_engine`, `inspect_engine_capabilities`, `inspect_game_project`, `configure_studio`, `list_studio_projects`, `read_studio_audit` |
| Blender | `blender_info`, inspect, validate, export, import, render, procedural blockout, guarded `run_python` |
| Meshy | key setup guide, validated local key save/clear, balance, text-to-3D preview/refine, rigging, animation library/apply, task polling, output download |
| Assets | provider matrix, Poly Haven search/download with MD5 + provenance, Sketchfab search, license inspection, file validation, manifest |
| Animation | GLB/glTF rig classification, clip inspection, retarget map, compatibility check, source limitations |
| Engines | Unity stage/verify/refresh/test/build/editor commands, Godot stage/verify/import/build, Unreal inspect/stage-only |
| Governance | execution modes, granular permissions, confirm gates, persisted operations with cancellation, evidence inspection and caller-supplied requirement verification |
| LLM reasoning | `llm_status`, understand, hybrid specification, ambiguity analysis, engine compatibility, architecture, plan validation, governed execution plan, requirement trace, provider test, plan review, Game Director |

All modules are dependency-free Python. No simulated tool returns a success
payload for work that did not happen.

## 2. Automated tests

Command:

```powershell
python -m unittest discover -s .\tools\game-studio-mcp\tests -v
```

Result: **150 tests passed**.

Coverage includes path traversal rejection, config isolation and audit, project
discovery/inspection, OBJ and GLB validation, rig classification, retargeting,
Meshy confirmation/not-configured/key storage paths, staging/overwrite rules,
Blender render-only temporary-file handling, Unity and Unreal state logic, tool
registry parity, unknown tools and clean tool errors, plus:

- Roman Urdu/mixed-language intent extraction with traceable source phrases.
- Explicit vs implied vs technical vs optional requirement separation.
- Negation (`no guns`, `... nahi chahiye`) not becoming a requirement.
- Multi-engine and art-style conflict detection.
- Monkey-specific non-humanoid rig and retargeting warning.
- Acyclic dependency graph and topological ordering.
- Manifest confirmation, project-local path, reload after "restart".
- Evidence guards for `tested`/`verified` and missing evidence files.
- Tampered-manifest invalid-claim detection.
- Credential-like value rejection in project memory.

LLM layer tests (`tests/test_llm_v4.py`) use mocked HTTP providers and make no
paid calls:

- Provider wire formats for OpenAI, OpenAI-compatible, Anthropic, Gemini and
  Ollama; authorization headers and base-URL overrides.
- Secret redaction in configured headers and prompts; credential-shaped values
  never returned.
- Budget limits, request/day caps, timeout, bounded retry/backoff and
  cancellation-before-send.
- Schema validation and bounded repair; invalid model output is rejected rather
  than accepted.
- Deterministic fallback on missing provider, failed provider and unrecoverable
  schema errors, always labelled `deterministic-fallback` / `degraded: true`.
- Provider-independent intent, ambiguity (max five questions), engine reasoning,
  architecture and validation with mocked models.
- Deterministic execution plans: `executable: false`, allow-listed tools only,
  paid steps requiring explicit approval and blockable by policy; LLM review
  cannot upgrade a `blocked` verdict.
- Requirement traceability across understanding, specification and manifest,
  including exclusions.
- Project-content gate requires environment flag + request flag + confirmation.
- Multilingual request scenarios (English, Roman Urdu, Urdu, mixed).

## 2b. Executed intent/memory validation

Command:

```powershell
python .\scripts\validate-intent-memory.py
```

Result: `PASS`.

| Check | Evidence |
| --- | --- |
| Roman Urdu + English request | detected `english`, `roman-urdu` |
| Character/mechanics | `monkey`, `climbing`, `swimming` |
| Exclusion | `weapons` (from `Bandooq nahi chahiye`) |
| Requirements | 7 explicit, 8 implied, 22 total |
| Plan | 33-node acyclic graph, 7 milestones, 20 acceptance tests |
| Persistence | manifest revision 1; decisions and `tested` status reloaded |
| Comparison | `partial`, detected engine `unity`, 0 invalid claims |
| Guard | `verified` rejected without qualifying evidence |

## 2c. LLM reasoning demo (offline and mocked)

Commands:

```powershell
python .\scripts\llm-demo.py --json
python .\scripts\llm-demo.py --mock-llm --json
```

Both pipelines use the same English monkey/Android request ("Create a realistic
3D monkey adventure game for Android ... No weapons.") and produce understanding,
a specification, traceability, validation and a governed execution plan. Neither
runs Blender, an engine, an asset download, gameplay or a build.

| Check | Offline (`--json`) | Mocked provider (`--mock-llm`) |
| --- | --- | --- |
| `provider_mode` | `deterministic-fallback` | `mocked` |
| Understanding `source` | `deterministic-fallback` | `llm` |
| Requirements | 28 total (12 explicit, 8 implied, 2 technical, 5 optional, 1 excluded) | fixture response, 6 requirements (5 explicit, 1 excluded) |
| Plan validation | `valid` | `valid` |
| Execution plan | `executable: false` | `executable: false` |
| Execution steps | 20 total: 17 available, 3 paid (require approval), 0 blocked | same |
| `implementation_claimed` | `false` | `false` |

The mocked run proves schema validation, adapter plumbing and the
reasoning-to-plan pipeline. It does **not** prove model quality. The offline run
proves the deterministic fallback remains usable with no provider, key or
network.

## 3. Executed live evidence

### MCP stdio

- `initialize` returned `universal-game-studio` 1.0.0.
- `tools/list` returned 84 unique tools with matching handlers.
- `studio_info` returned config/audit paths outside the repository and reported
  Meshy/Sketchfab as not configured without exposing values.
- `blender_info` returned Blender 5.2.2 LTS, Python 3.13.13, exporter flags and
  `D:\blender data\blender.exe`.
- `meshy_animation_library` returned `ok: false`, `state: not-configured` with
  remediation, not a fake result.
- `meshy_setup_guide` returned real key creation steps, the
  `https://www.meshy.ai/developers/keys` page, storage/rotation instructions and
  `configured: false` without exposing any secret.
- `meshy_configure_api_key` with an invalid key and `confirm=true` made a real
  request to the Meshy balance endpoint and returned `saved: false`,
  `status: 401`, `error: Invalid API key`; no local key file was created.

### Poly Haven (live API)

- Models for `rock`: `rock_moss_set_02`, `rock_moss_set_01`, `Rockingchair_01`.
- HDRIs: `kloofendal_48d_partly_cloudy_puresky`, `moonless_golf`.

### Blender end-to-end

Tool: `blender_create_environment_blockout` with `preset=jungle`, `seed=4242`,
`size=80`, `segments=48`, `tree_count=40`, `rock_count=15`.

| Artifact | Result |
| --- | --- |
| `.blend` | 196,461 bytes, 59 objects, 6,670 triangles |
| `.glb` | 283,272 bytes, 57 meshes, 5 materials, SHA-256 `b0ded67b…4d779b` |
| `.png` | 278,904 bytes, EEVEE render |

The render was opened and visually inspected: terrain, trees, rocks and water are
present and consistent with a blockout. It is **not** production art. The
validator reported no issues and correctly warned about off-origin prop pivots
and missing terrain UVs.

The exported GLB was independently parsed by `validate_asset_file` (57 meshes, 5
materials, no rig) and `inspect_animation_rig` (unrigged). This is expected for an
environment blockout.

A second live run exercised the render-only path with `preset=alpine`, `seed=2027`,
`size=120`, `segments=48`, `tree_count=75`, `rock_count=35`, no `save_blend`.
It returned `ok: true`, wrote a 640×360 PNG (287,522 bytes; 12,194 triangles,
114 objects) and removed the temporary `.blend` afterwards. Both renders are
committed under `docs/images/` and shown in the README.

### Engine detection and project inspection

- Unity 6000.6.2f1 was verified at its installed editor path; Unity CLI
  1.0.0-beta.8 was found.
- `inspect_game_project` succeeded on a local Unity `Legend Run` project
  (path redacted) with no warnings.
- `unity status` reported no connected editor with the Pipeline package.
- `unity_list_commands` correctly reported `connected: false` and the CLI error
  instead of inventing a command list.
- `inspect_engine_capabilities` listed Unity batch refresh/tests/build as
  implemented but unverified, and editor commands as unavailable.

## 4. Not verified / blocked

| Item | State | Reason |
| --- | --- | --- |
| Meshy generation, rigging, animation | blocked | `MESHY_API_KEY` absent; not-configured, guide, local save/clear, environment precedence, real invalid-key 401 rejection and mocked valid-key save tested; live valid-key acceptance and task execution not |
| Sketchfab authenticated search | blocked | `SKETCHFAB_TOKEN` absent |
| Unity batch refresh | unverified | Not run; would modify/reimport a project without user approval |
| Unity tests and player build | unverified | No run against the real project in this session |
| Unity editor command execution | unavailable | No connected editor with `com.unity.pipeline` |
| Unreal inspection/staging | implemented, fixture-tested | Unreal is not installed; no editor automation exists |
| Godot import/export | implemented, unverified | Godot is not installed |
| Visual/runtime quality | not assessed | No gameplay scene, playtest or player run |
| Production character art | not implemented | The server never generates placeholder characters; use Meshy or an artist |
| General natural-language understanding | heuristic, unproven beyond vocabulary | The parser is a deterministic lexicon; dialects, metaphors and implicit cultural references may need clarification |
| Requirement evidence correctness | not independently re-run | Comparison checks that evidence exists and qualifies by kind; it does not replay the test, build or playtest |
| Full multi-engine acceptance scenarios | not executed | Blender/Meshy/Unity/Unreal/Godot end-to-end asset, animation, gameplay and build scenarios require the real engines and user-approved projects |
| Live LLM providers | unverified | No hosted credential or local Ollama model was used; all five adapters are wire-format tested with mocked HTTP only |
| LLM output quality | unproven | Mocked fixtures validate plumbing and schemas, not reasoning quality across models or languages |
| LLM cost accounting | approximate | Budgets count requests; currency pricing and model-specific tokenizer limits are not implemented |

## 5. Acceptance conclusion

The server is **implemented, compiled, unit-tested and live-tested** for the
paths listed in section 3. It is **not** a complete game studio by itself:
paid Meshy execution, Godot/Unreal automation, Unity batch builds and runtime
quality remain unverified or unavailable in this environment. Those gaps are
reported by the tools themselves and must stay visible in any delivery report.

The LLM reasoning layer is **implemented, schema-validated and tested offline
and with mocked providers**. It has **not** been live-verified against any
provider, and its plans are advisory. It never executes work, never changes
requirement status and never overrides a deterministic safety verdict.
