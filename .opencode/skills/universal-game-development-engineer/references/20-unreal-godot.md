# Unreal Engine and Godot Automation

## Unreal Engine

### Discovery

- Install roots: `C:\Program Files\Epic Games\UE_5.x`, `D:\Epic Games\UE_5.x`.
- Editor CLI: `Engine\Binaries\Win64\UnrealEditor-Cmd.exe`.
- Build tool: `Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe`.
- Project files: `.uproject` + `Config/DefaultEngine.ini` + `Source/<Module>`.
- Verify version from `Engine/Build/Build.version` (JSON) — do not trust folder names.

### Safe automation pattern

```powershell
# Generate project files
& "<Engine>\Engine\Build\BatchFiles\GenerateProjectFiles.bat" -project="D:\Games\MyGame.uproject" -game -rocket

# Build editor target
& "<Engine>\Engine\Build\BatchFiles\Build.bat" MyGameEditor Win64 Development -Project="D:\Games\MyGame.uproject" -WaitMutex

# Headless commandlet / automation
& "<Engine>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "D:\Games\MyGame.uproject" -run=Automation -ExecCmds="Automation RunTests MyGame; Quit" -unattended -nopause -nullrhi -log
```

Packaging:

```powershell
& "<Engine>\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun `
  -project="D:\Games\MyGame.uproject" -noP4 -platform=Win64 -clientconfig=Development `
  -cook -build -stage -pak -archive -archivedirectory="D:\Games\Builds"
```

Write C++ for systems that need performance or tests; expose tuning to
Blueprints/DataAssets. Validate gameplay with Automation Spec tests
(`IMPLEMENT_SIMPLE_AUTOMATION_TEST`) and a scripted functional test map.

Report exact build tool exit codes and the tail of `Saved/Logs/MyGame.log`.

## Godot

### Discovery

- Executable may be `Godot_v4.x-stable_win64.exe`; add it to PATH as `godot`.
- Project marker: `project.godot`. Do not create it by hand — use the editor or a
  template, then validate by importing headlessly.

### Headless validation

```powershell
godot --headless --path "D:\Games\MyGame" --editor --quit        # import assets, check for script errors
godot --headless --path "D:\Games\MyGame" --script res://ci/check.gd
godot --headless --path "D:\Games\MyGame" --export-release "Windows Desktop" "D:\Games\Builds\MyGame.exe"
```

Export presets live in `export_presets.cfg`; the export template must be
installed (`--export-release` fails loudly otherwise). For Android the preset
needs SDK path, keystore and package name.

### Conventions

- Scenes composable and small; scripts extend the node they belong to.
- Use `CharacterBody3D`/`CharacterBody2D` with `move_and_slide()`; do not set
  `global_position` to fake collision.
- Signals over polling; disconnect in `_exit_tree` when connecting dynamically.
- `@export` for tunables; `@onready` for node caches.
- Test with GUT or the built-in `--headless` script runner; report the exact
  command and number of passing tests.

## Engine-neutral automation rules

1. Prefer the engine's own CLI/API over GUI clicking. GUI-only steps must be
   reported as manual.
2. Add a timeout to every engine process and capture stdout/stderr to a log file.
3. A process that exits 0 but produced no artifact is a failure.
4. Never patch engine installation files; keep changes inside the project.
5. Android verification needs a real device or emulator; without one, mark the
   on-device gate as pending, not passed.
