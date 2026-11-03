# Engine Selection and Project Creation

## Decision matrix

| Requirement | Unity | Unreal Engine | Godot |
| --- | --- | --- | --- |
| 2D platformer/fighter | Strong (2D URP, Tilemap, Animator) | Weak fit | Excellent |
| 3D mobile runner/action | Strong (URP, IL2CPP) | Heavy; possible but costly | Good for small 3D |
| High-fidelity 3D / large world | Good | Best (Nanite/Lumen) | Limited |
| Fast iteration, C# | Best | C++/BP, slower | GDScript/C# |
| Small download, MIT licence | No | No | Yes |
| Android + Windows | Best-supported | Supported, large builds | Supported |
| Existing team knowledge | Usually decisive | Usually decisive | Usually decisive |

Rules:

1. If a project already exists, stay in its engine unless it cannot meet a hard
   requirement. Record the reason if you even consider migration.
2. Prefer an engine already installed and verified by the detector.
3. Never download a multi-GB engine without approval.
4. Do not select an engine based on marketing; select based on the brief.

## Verifying an engine before creating anything

- Unity: `unity --version`, `unity editors list`, `unity projects list`,
  `unity status` (live editors). Editor executable must exist at
  `<EditorRoot>\<version>\Editor\Unity.exe`.
- Unreal: `UnrealEditor-Cmd.exe -version` or check
  `Engine/Binaries/Win64/UnrealEditor-Cmd.exe` and `Engine/Build/Build.version`.
- Godot: `godot --version` (must print `4.x`).

A version folder without its executable is `broken`, not `installed`.

## Creating real projects

### Unity

Prefer the Unity CLI when available:

```powershell
unity templates list
unity projects create "D:\Games\MyGame" --template 2d-urp   # exact flags vary by CLI version
```

Fallback: create through the editor (`-createProject`) or Unity Hub. Never
hand-write `ProjectSettings/ProjectVersion.txt` to fake a project. Validate by
opening the project and confirming `Library/` and `Packages/manifest.json`
resolve.

After creation, set:

- `ProjectSettings/ProjectVersion.txt` matches the installed editor.
- URP asset assigned in Graphics/Quality settings for 3D; 2D renderer for 2D.
- Input System package and an `InputActions` asset for cross-device input.
- `Company Name`, `Product Name`, bundle identifier, icon, target API levels.
- Android: IL2CPP, ARM64, target SDK 35+, minimum API per store policy.

### Unreal

Never hand-create `.uproject` structures. Use:

```powershell
UnrealEditor-Cmd.exe "D:\Games\MyGame.uproject" -run=...
# or the Launcher/Editor new-project flow
```

Verify by generating project files (`GenerateProjectFiles.bat`) and building the
Editor target with `UnrealBuildTool`.

### Godot

```powershell
godot --headless --path . --editor --quit          # imports and validates
godot --headless --path . --script res://tools/ci/check.gd
```

Validate by importing the project headlessly and confirming `project.godot`
parses and `.godot/` is generated.

## Recording the decision

Write into the project (or task report):

- Chosen engine + exact version + executable path.
- Why it fits the brief.
- Alternatives rejected and why.
- Known platform constraints (Android thermals, build size, licence).
- What is still unverified.
