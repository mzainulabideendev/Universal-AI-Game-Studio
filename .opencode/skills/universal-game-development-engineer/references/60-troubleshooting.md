# Troubleshooting Playbooks

Diagnose from evidence: logs, process state, ports, versions, paths. Change one
variable at a time.

## MCP server connects but exposes 0 tools

1. Confirm the server process exists and why it exists:
   `Get-Process | ? { $_.Path -like '*unity*' }`.
2. Confirm the dependency: for Unity, is an editor running and is the Pipeline
   package installed? `unity status`.
3. Confirm the configured project path exists — a stale path yields a healthy
   server with no editor.
4. Confirm the editor-side plugin registered: `unity list`.
5. Only then consider ports/transport. Do not add a second server for the same
   editor.

## Server fails to start / times out

- Run the exact configured command manually and read stderr.
- Check the executable path and quoting in `command` (array entries, no shell).
- Check `cwd` and environment variables.
- Increase `mcp.timeout.startup` only after confirming the process starts slowly,
  not because it crashes.
- Host log: `%USERPROFILE%\.local\share\opencode\log\opencode.log`, filter
  `mcp`.

## Unity: character passes through obstacles

| Check | Evidence |
| --- | --- |
| Colliders present and enabled | Inspector + `Physics.Overlap` probe |
| Layer collision matrix | `Physics.GetIgnoreLayerCollision(a,b)` |
| Collision detection mode | Continuous / ContinuousDynamic |
| Speed vs collider thickness | tunnelling at high speed |
| Rigidbody vs transform writes | moving via `transform.position` bypasses physics |
| Trigger vs collider misuse | triggers don't block |

Fix with CCD + thicker colliders + `MovePosition`/velocity, not by disabling
collision or teleporting out.

## Unity: falls through floor

- Ground has a collider and is on a layer included in the player's mask.
- Ground check origin is inside the collider or too short.
- Terrain collider present (TerrainCollider, not just mesh).
- Player starts above the ground and gravity is applied in `FixedUpdate`.

## Imported model wrong

- Scale/rotation: check `validate_asset` bounds and engine import scale.
- Grey: URP material + texture references; reimport with materials.
- No animation: actions not exported; verify clips in the FBX/GLB inspector.
- Rig broken: Avatar configuration, bone naming, T-pose.

## Performance collapse

1. Profile before changing anything.
2. Identify whether CPU main thread, render thread, GPU or GC.
3. Fix the single largest cost; re-measure.
4. Only then tune quality settings.

## Build fails

- Read the first error, not the last. Often a missing module or API level.
- Unity Android: module installed, SDK/NDK/JDK paths set, keystore, target API.
- Unreal: run `GenerateProjectFiles`, build Editor target first, then package.
- Godot: export templates installed, preset path valid.
- Disk space: builds need several GB free; check the detector report.

## Nothing works after a config change

- Revert to the timestamped backup you made before editing.
- `opencode mcp list` after each change.
- Config changes hot-reload; a full `opencode service restart` is a last resort.
