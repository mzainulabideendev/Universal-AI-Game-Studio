# Unity Workflow (Unity 6 / 6000.x, URP)

Use the project's actual editor, packages and render pipeline. Discover paths
and versions from the local installation and project files; do not copy sample
paths or version numbers from another machine.

## Connecting to a running editor

The Unity MCP server is the official CLI's stdio server:

```
unity mcp --project-path "D:\path\to\Project"
```

It exposes **0 tools until an editor with the Pipeline package is running for
that exact project**. Order of operations:

1. `unity status` → must list the project, port, version and PID.
2. `unity list` → tools registered by the Pipeline package on that editor.
3. Only then call MCP tools.

If `unity status` is empty: the editor is not running or the project path in
config is wrong. Check `Test-Path` on the configured path first; a stale path is
the most common cause. Start the editor with the path discovered on the current machine:

```powershell
& "<path-to-Unity.exe>" -projectPath "<path-to-project>"
```

Do not start a second MCP server for the same editor, and do not switch to a
different port unless the CLI documents it.

## CLI reference (verify with `unity <cmd> --help`)

| Command | Purpose |
| --- | --- |
| `unity status` | Live editors (port/project/version/PID) |
| `unity list` | Tools available on the connected editor |
| `unity command <cmd> [args]` | Execute a registered editor command |
| `unity test <project> ...` | EditMode/PlayMode tests with results report |
| `unity build <project> ...` | Batch-mode build with CI flags |
| `unity open <project>` | Open with the correct editor version |
| `unity close <project>` | Close editor without saving |
| `unity pipeline ...` | Editor pipeline automation |
| `unity logs` | Hub log |

Always read the help for the exact flags of the installed CLI version; the CLI is
`1.0.0-beta.x` and flags can change.

## Project inspection (non-destructive)

Read before writing:

- `ProjectSettings/ProjectVersion.txt` — editor version.
- `Packages/manifest.json` + `packages-lock.json` — packages actually resolved.
- `Assets/**/*.asmdef` — assembly boundaries; create new asmdefs instead of
  dumping code into `Assembly-CSharp` when the project already uses them.
- `ProjectSettings/ProjectSettings.asset` — product name, bundle id, API levels.
- `ProjectSettings/GraphicsSettings.asset` + URP asset — render pipeline.
- `Assets/**/*.unity` — scenes; check `EditorBuildSettings.asset` for build order.
- Existing tests under `Assets/**/Tests` — mirror their conventions.
- `.csproj` files at the project root show code modules and assembly names.

Never rewrite `.meta` files or GUIDs. Never delete `Library/` while the editor is
running. Back up the scene and any asset you are about to restructure.

## Code conventions

- One responsibility per MonoBehaviour; expose tunables via `[SerializeField]`
  with sensible ranges, not magic numbers scattered in `Update`.
- Cache components in `Awake`, resolve references in `OnEnable`, unsubscribe in
  `OnDisable`.
- Use `Time.deltaTime` (or `FixedUpdate` + `fixedDeltaTime`) for all movement.
- Physics: set `Rigidbody.interpolation`, `collisionDetectionMode`, and explicit
  layers/masks. Query with `Physics.Raycast/SphereCast` using a ground mask.
- Prefer the new Input System (`InputAction` assets, `PlayerInput`) over legacy
  `Input.GetAxis` in projects that already include it.
- Use assembly definitions and namespaces consistently with the project.
- UI: wire buttons in code or via serialized references; every button must call
  real state transitions. Text values must read from the game model, not constants.
- Addressables/Resources: only if the project already uses them.

## URP checklist

- URP asset assigned in Graphics and each Quality level.
- Camera has `UniversalAdditionalCameraData`; post-processing enabled deliberately.
- Materials use URP/Lit or URP/Unlit; imported Standard shaders must be upgraded.
- Shadows: cascade count and distance tuned for mobile (2 cascades, ~30 m).
- Avoid real-time lights beyond budget; bake where static.
- GPU instancing / SRP Batcher compatible shaders for repeated props.

## Testing

```powershell
unity test "D:\...\My project" --mode EditMode  --output reports/editmode.xml
unity test "D:\...\My project" --mode PlayMode  --output reports/playmode.xml
```

Confirm the report file exists and contains `result="Passed"` counts. A zero-test
run is a failure, not a pass. For gameplay defects add a PlayMode test that
enters Play Mode, drives input through the Input System test fixtures or direct
API calls, asserts state, then exits.

## Building

```powershell
unity build "D:\...\My project" --target StandaloneWindows64 --output-path "D:\...\Builds\Windows"
```

After building: verify the output executable exists, check its size and
timestamp, launch it with `-logFile`, and scan the player log for exceptions.

Android: confirm `unity modules` lists Android Build Support + SDK/NDK + OpenJDK,
`ProjectSettings` uses IL2CPP/ARM64, keystore configured, target API within store
policy. `adb devices` must show a device for on-device verification; otherwise
report device testing as pending.

## Import formats

Choose a format supported by the project's installed importers and pipeline.
FBX is a common Unity path; glTF/GLB support depends on installed packages and
their versions. Texture embedding and material conversion can vary by exporter,
importer and render pipeline. Verify imports by loading the asset as a
`GameObject`, instantiating it, and checking renderers, bounds,
vertex/triangle counts, shader and texture references.

## Common Unity failure signatures

| Symptom | Root cause | Fix |
| --- | --- | --- |
| MCP `tools=0` | Editor not running / wrong project path | Fix path, start editor, `unity status` |
| Grey imported model | URP material or texture path | Reassign URP/Lit, fix texture references |
| Model 100× too large | FBX unit scale | Import scale 0.01 / bake scale in Blender |
| Character falls through floor | No collider / wrong layer / CCD | Add collider, set mask, enable Continuous |
| Tunnelling at speed | Discrete collision | Continuous/ContinuousDynamic, thicker colliders |
| Animation not playing | Avatar/rig mismatch or state default | Reconfigure Avatar, check Animator defaults |
| Build fails on Android | Missing module/SDK/NDK/keystore | Install module, set paths, verify licences |
