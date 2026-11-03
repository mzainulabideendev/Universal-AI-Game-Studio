# Learning Universal AI Game Studio

This guide is a practical path for new users, game developers and contributors.
It teaches how to use the repository's workflow responsibly; it is not a
substitute for learning the chosen engine or for testing a real game.

## Learning outcomes

By the end, you should be able to:

1. Find the project instructions that your AI agent should load.
2. Ask an agent to inspect a project without prematurely changing it.
3. Identify the installed engine, MCP state and available Blender tools.
4. Turn a game idea into a scoped brief and a playable vertical slice.
5. Validate an asset and check its source and license before using it.
6. Verify behavior through tests, a launched build and logs.
7. Write a useful handoff that distinguishes facts, assumptions and blockers.

## Before you begin

- Clone this repository and open its root directory in an AI coding agent.
- Have Python 3.10+ available to run the included MCP scripts.
- Install Blender only if you intend to run actual Blender operations.
- A Unity, Unreal or Godot project is only needed for engine-specific exercises.
- Read the root [README](README.md) and [agent instructions](AGENTS.md).

No external API key, account or paid asset is required for the local MCP
handshake test.

## Module 1 — Orient yourself

### Read

- [README.md](README.md): setup, repository map and evidence expectations.
- [AGENTS.md](AGENTS.md): shared instructions for coding agents.
- `.opencode/skills/universal-game-development-engineer/SKILL.md`: main task
  workflow and reference index.

### Exercise

Ask your agent:

> Inspect this repository without editing it. Summarize its purpose, list which
> game-development systems are documented, identify the available tests, and
> separate verified facts from things that would need a live project to verify.

### Check your result

The agent should not claim this repository is a complete game, should not
invent an engine/editor connection, and should identify the real Blender smoke
test rather than claiming that a Unity/Unreal/Godot game was tested.

## Module 2 — Discover local capabilities

Run:

```powershell
python --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\detect-dev-environment.ps1
python .\scripts\test-mcp-server.py -- python .\tools\blender-mcp\server.py
```

The environment detector is read-only and Windows-specific. Its report is
local-only because it may contain hardware details and absolute paths. The MCP
handshake lists the server's tools; it does not call Blender operations.

### Exercise

Ask the agent to explain the difference between:

- Blender installed vs. Blender MCP configured.
- MCP server configured vs. connected.
- Tool list received vs. an actual operation succeeded.
- Compilation succeeded vs. a game launched and behaved correctly.

The answers should follow the evidence vocabulary in the main skill.

## Module 3 — Run a real Blender pipeline test

If Blender is installed, set its path and run:

```powershell
$env:BLENDER_EXE = 'C:\Path\To\Blender\blender.exe'
python .\scripts\test-blender-mcp.py --full
```

The test creates a temporary cube project, inspects it, validates basic asset
data, exports GLB, renders a PNG and checks that the output files exist. The
temporary test output is not a production asset or a playable game.

### Exercise

Use the Blender MCP server to call `blender_info`, then describe the returned
Blender version and enabled features. Do not infer export success solely from
the tool listing; run the export and inspect its returned status and output
file.

If Blender is not available, complete the handshake test and state that
Blender execution is blocked by the missing executable. Do not install it
without permission.

## Module 4 — Turn an idea into a production brief

Read:

- `references/05-production-pipeline.md`
- `references/15-world-and-level-design.md`
- `references/40-gameplay-systems.md`
- `references/50-testing-and-builds.md`

For a game concept, record:

- Genre, presentation and target platform.
- The core loop in a few seconds of play.
- Controls, camera, win/lose conditions and progression.
- One initial level or gameplay space.
- Needed characters, environment, assets, audio and UI.
- Technical/performance constraints.
- Explicit out-of-scope features.
- Assumptions that the user has not specified.

### Exercise

Ask the agent:

> Convert my game idea into a one-page brief and a vertical-slice plan. First
> separate my explicit requirements from your assumptions. Do not add features
> that do not support the core loop. Include a way to test whether the level is
> completable.

Review the scope. A good vertical slice should prove one real gameplay loop;
it should not be a list of unrelated systems or an empty scene with placeholder
menus.

## Module 5 — Design and evaluate a level

Read `references/15-world-and-level-design.md`. A level plan should specify
entry and exit, player route, objectives, optional routes, encounters, hazards,
checkpoints, sightlines, boundaries and a completion test.

### Exercise

Choose a small level and write:

1. A route from spawn to the objective and exit.
2. One optional route and its reward.
3. One encounter or obstacle and its gameplay rule.
4. A way to prove objectives are reachable with the actual player controller.
5. A fallback if procedural generation blocks the route.

Avoid random prop scattering as a replacement for pacing and level design.

## Module 6 — Research and validate assets

Read:

- `references/05b-autonomous-art-asset-research.md`
- `references/30-blender-asset-pipeline.md`

Before using an external asset, record the exact asset page, creator, license,
attribution requirements, modification/redistribution terms, dependencies,
download date and destination. Check the exact asset license instead of
assuming every item on a site shares one license.

### Exercise

Create a small asset candidate table with two candidates for a game prop.
Compare:

- Visual fit and quality.
- File format and engine compatibility.
- Scale, geometry/material budget and collision.
- Exact license, attribution and distribution restrictions.
- Integration effort and unresolved questions.

Do not download or use an asset if rights remain unclear for the intended
distribution.

## Module 7 — Test implementation and delivery

Read:

- `references/45-character-ai.md`
- `references/50-testing-and-builds.md`
- `references/60-troubleshooting.md`
- `references/70-acceptance-checklist.md`
- `references/75-performance-qa-delivery.md`

For an actual gameplay change, identify one test that directly proves the
changed rule, one in-engine or integration flow, and one runtime/log check.
Report which ran, the result, and what remains unverified.

### Exercise

Ask the agent to produce a handoff for a small change with these headings:

- Configured
- Implemented
- Compiled
- Tested
- Verified
- Blocked or remaining limitations

Reject any status that lacks evidence. A successful build alone does not prove
the build launched or that the gameplay feature behaved as intended.

## Suggested next steps

- Follow the installed engine's official learning path for gameplay scripting,
  input, scenes, physics and builds.
- Repeat the production brief exercise using an existing game project; preserve
  its architecture and assets.
- Propose a documentation or test improvement using [CONTRIBUTING.md](CONTRIBUTING.md).
- Practice explaining tradeoffs and blockers before making expensive or
  irreversible changes.

## Glossary

| Term | Meaning |
| --- | --- |
| **MCP** | Model Context Protocol; a standard for exposing tools/resources to compatible AI clients. |
| **stdio server** | A local MCP process that exchanges protocol messages through standard input/output. |
| **Vertical slice** | A small but representative, playable section proving the core game loop end to end. |
| **Blockout** | A simple geometry pass used to check scale, route, collision and pacing before final art. |
| **Asset provenance** | Records showing where an asset came from, who made it, how it is licensed and where it is used. |
| **Runtime verification** | Observing the running game and checking its behavior and logs, not just compiling it. |
