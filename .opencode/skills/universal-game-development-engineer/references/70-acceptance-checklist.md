# Acceptance Checklist

Mark each item with one of: `verified` (evidence attached), `implemented`
(not run), `configured` (not connected), `blocked` (reason), `not applicable`.

## Environment

- [ ] Detector script ran; `reports/environment.json` fresh.
- [ ] Engine executables verified by running them, not by folder names.
- [ ] Art tool (Blender) version verified.
- [ ] Toolchains (compiler, SDK/NDK, JDK, .NET) verified.
- [ ] Disk/RAM/GPU sufficient for the target.

## Agent integration

- [ ] Skill file exists at the documented location and ID matches the directory.
- [ ] Skill appears in the agent's available list / can be loaded by ID.
- [ ] Existing MCP configuration preserved (backup exists).
- [ ] Each MCP server: name, config path, command, start result, connection,
      tool count, read-only test.
- [ ] No duplicate servers on the same port/editor.
- [ ] Secrets not printed or committed.

## Engine project

- [ ] Correct project path confirmed (not assumed).
- [ ] Editor version matches `ProjectVersion.txt`.
- [ ] Project opens without new errors.
- [ ] Scene list and build settings inspected.
- [ ] Code compiles.
- [ ] Existing tests still pass.

## Assets

- [ ] Source and licence recorded.
- [ ] `validate_asset` clean (or exceptions documented).
- [ ] Export artifact exists, non-zero, correct format.
- [ ] Import log clean.
- [ ] Material/texture correctness verified visually.
- [ ] Scale/orientation verified against a known reference.
- [ ] Animations verified; absence reported.
- [ ] Collision configured and tested.

## Gameplay

- [ ] Core loop playable end to end.
- [ ] Every button has real behaviour.
- [ ] Scores/stats derive from live state.
- [ ] Failure and restart work.
- [ ] Save/load round-trip verified if persistence exists.
- [ ] Frame-rate independence checked.
- [ ] Pause/settings mutate real state.

## Quality

- [ ] No exceptions in logs during the tested flow.
- [ ] Performance measured against target.
- [ ] Build produced and launched.
- [ ] Platform-specific gates (Android device, signing) verified or marked pending.

## Report

- [ ] Exact commands and outputs included.
- [ ] Paths and versions exact.
- [ ] Limitations and next actions listed.
- [ ] No unverified claim marked complete.
