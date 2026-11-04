# Game Studio MCP acceptance report

Date: 2026-11-04
Platform: Windows 11, Python 3.12.10
Blender: 5.2.2 LTS
Unity Editor: 6000.6.2f1
Unity CLI: 1.0.0-beta.8

This report separates implemented code from executed evidence. Nothing below is
claimed beyond what the recorded commands and artifacts show.

## 1. Implemented

| Area | Tools |
| --- | --- |
| Studio/config | `studio_info`, `detect_system`, `detect_game_engines`, `list_available_engines`, `select_game_engine`, `inspect_engine_capabilities`, `inspect_game_project`, `configure_studio`, `list_studio_projects`, `read_studio_audit` |
| Blender | `blender_info`, inspect, validate, export, import, render, procedural blockout, guarded `run_python` |
| Meshy | key setup guide, validated local key save/clear, balance, text-to-3D preview/refine, rigging, animation library/apply, task polling, output download |
| Assets | provider matrix, Poly Haven search/download with MD5 + provenance, Sketchfab search, license inspection, file validation, manifest |
| Animation | GLB/glTF rig classification, clip inspection, retarget map, compatibility check, source limitations |
| Engines | Unity stage/verify/refresh/test/build/editor commands, Godot stage/verify/import/build, Unreal inspect/stage-only |

All modules are dependency-free Python. No simulated tool returns a success
payload for work that did not happen.

## 2. Automated tests

Command:

```powershell
python -m unittest discover -s .\tools\game-studio-mcp\tests -v
```

Result: **32 tests passed**.

Coverage includes path traversal rejection, config isolation and audit, project
discovery/inspection, OBJ and GLB validation, rig classification, retargeting,
Meshy confirmation and not-configured guards, staging/overwrite rules, Unity and
Unreal state logic, tool registry parity, unknown tools and clean tool errors.

## 3. Executed live evidence

### MCP stdio

- `initialize` returned `universal-game-studio` 1.0.0.
- `tools/list` returned 52 unique tools with matching handlers.
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

## 5. Acceptance conclusion

The server is **implemented, compiled, unit-tested and live-tested** for the
paths listed in section 3. It is **not** a complete game studio by itself:
paid Meshy execution, Godot/Unreal automation, Unity batch builds and runtime
quality remain unverified or unavailable in this environment. Those gaps are
reported by the tools themselves and must stay visible in any delivery report.
