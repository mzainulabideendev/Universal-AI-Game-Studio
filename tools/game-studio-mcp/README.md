# Universal AI Game Studio MCP server

A dependency-free Python stdio MCP server that drives real tools for game
production: system/engine detection, Blender automation, Meshy AI tasks, licensed
asset search, animation inspection, and Unity/Unreal/Godot asset staging and CLI
builds.

It is intentionally strict about evidence. A staged file is not described as
imported, a produced build is not described as a working game, and a provider or
engine that is missing is reported instead of being simulated.

## Requirements

- Python 3.10+ (tested with 3.12.10). No third-party Python packages.
- Optional: Blender 3.x/4.x/5.x, Unity Editor + Unity CLI, Unreal Engine, Godot 4.
- Optional credentials:
  - `MESHY_API_KEY` for Meshy generation, rigging, animation and balance.
  - `SKETCHFAB_TOKEN` for authenticated Sketchfab search.
- Poly Haven search and downloads need no key.

## Run

```powershell
python .\tools\game-studio-mcp\server.py
```

Configure it as a local stdio server in your MCP client. Example shape:

```json
{
  "servers": {
    "game-studio": {
      "type": "stdio",
      "command": "python",
      "args": ["${workspaceFolder}/tools/game-studio-mcp/server.py"],
      "env": {
        "MESHY_API_KEY": "${env:MESHY_API_KEY}",
        "SKETCHFAB_TOKEN": "${env:SKETCHFAB_TOKEN}"
      }
    }
  }
}
```

Credentials are read from the server process environment only. They are never
written to the studio config, audit log or tool output.

## Configuration

Machine-local settings live outside the repository:

- Windows: `%APPDATA%\UniversalAIGameStudio\config.json`
- macOS: `~/Library/Application Support/UniversalAIGameStudio/config.json`
- Linux: `$XDG_CONFIG_HOME/universal-game-studio/config.json`
- Override with `GAME_STUDIO_HOME`.

Paths and selected engine can be set with the `configure_studio` and
`select_game_engine` tools. Project roots default to common folders that exist
on the machine; they are never guessed into the repository.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `MESHY_API_KEY` | Enables Meshy API tools. |
| `SKETCHFAB_TOKEN` | Enables authenticated Sketchfab search. |
| `BLENDER_EXE` | Blender executable when it is not on `PATH` or configured. |
| `GAME_STUDIO_HOME` | Overrides the config/audit/download directory. |
| `GAME_STUDIO_ENGINE_TIMEOUT` | Default engine command timeout in seconds (1800). |
| `BLENDER_MCP_TIMEOUT` | Default Blender job timeout in seconds (900). |

## Tools

### Discovery and configuration

`studio_info`, `detect_system`, `detect_game_engines`, `list_available_engines`,
`select_game_engine`, `inspect_engine_capabilities`, `inspect_game_project`,
`configure_studio`, `list_studio_projects`, `read_studio_audit`.

### Blender

`blender_info`, `blender_inspect_blend`, `blender_validate_asset`,
`blender_export_asset`, `blender_import_asset`, `blender_render_preview`,
`blender_create_environment_blockout`, `blender_run_python`.

`blender_create_environment_blockout` generates a reproducible terrain blockout
(`jungle`, `forest`, `desert`, `alpine`) with trees, rocks, water, sun and camera.
It is explicitly a blockout, not production environment art.

`blender_run_python` executes arbitrary Blender Python and requires
`confirm=true`.

### Meshy

`meshy_setup_guide`, `meshy_configure_api_key`, `meshy_clear_api_key`,
`meshy_balance`, `meshy_text_to_3d`, `meshy_rig_character`,
`meshy_animation_library`, `meshy_create_animation`, `meshy_task_status`,
`meshy_wait_for_task`, `meshy_download_output`, `meshy_generate_asset`.

If no key is configured, `meshy_setup_guide` returns the real setup steps:
create/sign in to a Meshy account, open
`https://www.meshy.ai/developers/keys`, create a key (optionally with a monthly
credit limit), copy it once, then either set `MESHY_API_KEY` in the MCP client
environment and reconnect, or call `meshy_configure_api_key` with `confirm=true`.
That tool validates the key against the balance endpoint before saving it to a
private file outside the repository.

Key resolution order:

1. `MESHY_API_KEY` environment variable (wins when set).
2. `%APPDATA%\UniversalAIGameStudio\secrets\meshy.json` (or the platform
   equivalent under `GAME_STUDIO_HOME`).

To rotate, create a new key and call `meshy_configure_api_key` again, or update
the environment variable and restart the server. `meshy_clear_api_key` deletes
the local file, but cannot remove an environment variable. No tool returns the
key, and it is never written to the audit log.

All credit-spending calls require `confirm=true` and record an audit entry.
Rigging supports humanoid/biped models. Meshy returns GLB/FBX files; it does not
configure a Unity Animator, Unreal Anim Blueprint or Godot AnimationPlayer.

The server deliberately does **not** generate placeholder characters or claim
that a rig will work in-engine. Use Meshy, an artist or your own Blender model,
then inspect the rig and verify import and animation playback.

### Assets

`list_asset_providers`, `search_assets`, `download_polyhaven_asset`,
`inspect_asset_license`, `validate_asset_file`, `create_asset_manifest`.

- Poly Haven: keyless search and download, CC0, MD5 verification and a
  `provenance.json` beside the files.
- Sketchfab: search with the license field returned by its API. Missing license
  data is flagged as unknown.
- Mixamo, Kenney, OpenGameArt, Unity Asset Store and Fab are reported as
  `manual-only`; this server does not scrape them or bypass access controls.

### Animation

`inspect_animation_rig`, `create_animation_retarget_map`,
`check_animation_compatibility`, `list_animation_sources`.

Parses GLB/glTF skeletons and clips, classifies humanoid vs quadruped/generic
heuristically, and produces a bone-name map. A name map is not proof of correct
retargeting; verify rest pose, scale, axes and playback in Blender or the engine.

### Engines

`stage_asset_for_engine`, `verify_staged_import`, `engine_build`,
`unity_editor_status`, `unity_list_commands`, `unity_run_command`,
`unity_batch_refresh`, `unity_run_tests`, `unity_build`,
`godot_batch_import`, `godot_build`, `unreal_status`.

| Engine | Inspect | Stage | Import verification | Refresh | Tests | Build |
| --- | --- | --- | --- | --- | --- | --- |
| Unity | yes | yes | `.meta` + hash | `unity run -quit -batchmode` | `unity test` + NUnit parse | `unity build` + artifact check |
| Godot | yes | yes | `.import` + `.godot/imported` | `godot --headless --editor --quit` | not implemented | export preset |
| Unreal | yes | yes | not possible without editor automation | no | no | no |

The Unreal adapter is deliberately staged-only. It does not claim an import or a
build succeeded.

## Confirmation model

These calls fail unless `confirm=true`:

- Meshy text-to-3D, refine, rigging and animation tasks (credits).
- Poly Haven downloads.
- Asset staging into a game project.
- Unity batch refresh, tests, builds, editor commands.
- Godot import and export.
- `blender_run_python`.

Exports, renders and staging refuse to replace an existing target unless
`confirm_overwrite=true`.

## Safety and portability

- Subprocesses run without a shell; Blender receives arguments through a JSON
  file rather than string interpolation.
- Downloads use HTTPS, an allow-list of provider hosts, size limits and private
  address rejection. Poly Haven files are MD5-checked; all downloads are
  SHA-256 hashed.
- Staged paths must stay inside the project's `Assets/`, `Content/` or root.
  Traversal and absolute paths are rejected.
- The audit log is append-only JSONL in the external config directory.
- No machine paths or credentials are committed to the repository.

## Validation performed

The following was run on Windows with Python 3.12.10, Blender 5.2.2 LTS and Unity
CLI 1.0.0-beta.8:

```powershell
python -m py_compile .\tools\game-studio-mcp\server.py
python -m unittest discover -s .\tools\game-studio-mcp\tests -v   # 32 passed
python .\scripts\test-mcp-server.py --call studio_info -- python .\tools\game-studio-mcp\server.py
python .\scripts\test-mcp-server.py --call blender_info -- python .\tools\game-studio-mcp\server.py
```

A real Blender blockout was created, saved, exported and rendered through the
MCP tool (`jungle`, seed 4242, 80 m, 6,670 triangles): `.blend` 196,461 bytes,
`.glb` 283,272 bytes, `.png` preview 278,904 bytes. The GLB has 57 meshes, 5
materials and no rig. The render was inspected and shows terrain, trees, rocks
and water, matching the blockout description.

Live Poly Haven search returned real assets (`rock_moss_set_02`,
`rock_moss_set_01`, `Rockingchair_01`). Unity installation/CLI detection and
read-only project inspection succeeded.

### Not verified in this environment

- **Meshy:** `MESHY_API_KEY` is absent. Only the not-configured path was tested.
  Generation, rigging and animation task execution are unverified.
- **Unreal:** not installed. Inspection/staging logic is tested with fixtures;
  no editor automation exists.
- **Godot:** not installed. Commands follow documented CLI syntax but were not
  executed.
- **Unity writes:** no editor was connected with the Pipeline package, and no
  batch refresh, test run or player build was executed. Those adapter paths are
  implemented but unverified against this Unity version.
- **Sketchfab:** no token, so only the unauthenticated path is covered.
- **Runtime quality:** no generated asset, staging result or build has been
  playtested. Blockouts are placeholders.

## Tests

```powershell
python -m unittest discover -s .\tools\game-studio-mcp\tests -v
```

The suite uses temporary projects and synthetic GLB/OBJ files; it needs no
network, engine, Blender or API key.
