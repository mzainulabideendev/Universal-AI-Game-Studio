<p align="center">
  <img src="assets/universal-ai-game-studio-logo.svg" alt="Universal AI Game Studio" width="640">
</p>

<h1 align="center">Universal AI Game Studio</h1>

<p align="center">
  A reusable, evidence-driven game-development workflow for AI coding agents,
  game engines and asset tools.
</p>

This repository packages an OpenCode game-development skill, engine and production
guides, a local Blender MCP server, environment detection, and reusable validation
scripts. It is a workflow/toolkit—not a finished game or a promise that an agent
can create every requested feature without project-specific review.

## What it provides

- **A production workflow** for scoping, vertical slices, environment and level
  design, gameplay systems, animation, AI, QA and delivery.
- **Engine guidance** for Unity, Unreal Engine and Godot, with runtime discovery
  rather than assumptions about what is installed.
- **Blender automation** through a dependency-free MCP stdio server that launches
  the real Blender executable.
- **Asset research and provenance guidance**, including suitability, licensing,
  attribution and redistribution checks.
- **Agent-specific project instructions** for OpenCode, Codex, Claude Code,
  GitHub Copilot, Cursor, Gemini CLI, Windsurf, Cline, Roo Code and Aider.
- **Environment detection and smoke tests** to distinguish configured,
  implemented, compiled, tested and verified work.

## Visuals

The logo is an original vector mark included in this repository. The image below
is a real Blender render from the included MCP validation pipeline; it is a
test-asset render, **not** a screenshot of a finished game.

<p align="center">
  <img src="validation/exports/mcp_validation.png" alt="Blender-rendered checkerboard validation asset" width="640">
</p>

## Quick start

### 1. Clone and open the project

```powershell
git clone https://github.com/mzainulabideendev/Universal-AI-Game-Studio.git
Set-Location .\Universal-AI-Game-Studio
```

Open this folder as the workspace in your preferred supported AI coding agent.
The relevant root or client-specific instruction file is included in the clone.

### 2. Check local tools

Python 3.10 or later is required by the Blender MCP server. The game engine is
project-dependent; install only the engine required by your game.

```powershell
python --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\detect-dev-environment.ps1
```

The detector is read-only. Its generated report is written under `reports/` and
is intentionally ignored by Git because it can contain machine paths and
hardware details.

### 3. Run the lightweight MCP handshake test

This verifies the server initializes and advertises tools. Blender is not needed
for this handshake-only check.

```powershell
python .\scripts\test-mcp-server.py -- python .\tools\blender-mcp\server.py
```

### 4. Run the Blender end-to-end test

Install Blender separately and either add its executable to `PATH` as `blender`
or set `BLENDER_EXE` to the local executable path:

```powershell
$env:BLENDER_EXE = 'C:\Path\To\Blender\blender.exe'
python .\scripts\test-blender-mcp.py --full
```

The full test creates a temporary scene, inspects and validates it, exports a
GLB and renders a PNG. It does not install software or modify a game project.

The full smoke test was run successfully with Blender 5.2.2 LTS on Windows.
This verifies the Blender MCP pipeline only; it is not evidence that a
game-specific Unity, Unreal or Godot project builds or runs.

## Use with AI agents

### Easiest setup

Clone this repository and open its root folder in your agent. Its setup files
are already in their normal project locations. For a different game project, copy `AGENTS.md`, the instruction file for your
client, and the `.opencode/skills/` folder into that project's root, then open
that project in the agent.

| Agent/client | Project instruction or skill file | How to use |
| --- | --- | --- |
| OpenCode | `.opencode/skills/universal-game-development-engineer/SKILL.md` | Open the repo; ask the agent to use the **Universal Game Development Engineer** skill. |
| OpenAI Codex | `AGENTS.md` | Open the repo; Codex reads project instructions from `AGENTS.md`. |
| Claude Code | `CLAUDE.md` | Open the repo; Claude Code loads the project guidance from the root file. |
| GitHub Copilot | `.github/copilot-instructions.md` | Open the repo in VS Code with Copilot; repository instructions are applied to chat. |
| Cursor | `.cursor/rules/universal-game-development-engineer.mdc` | Open the repo in Cursor; the project rule is configured as always applicable. |
| Gemini CLI | `GEMINI.md` | Start Gemini CLI from the repository root so it can load project context. |
| Windsurf | `.windsurf/rules/game-development.md` | Open the repo in Windsurf and enable/use the project rule. |
| Cline | `.clinerules/game-development.md` | Open the repo in VS Code with Cline; include the project rule. |
| Roo Code | `.roo/rules/game-development.md` | Open the repo in VS Code with Roo Code; include the project rule. |
| Aider | `.aider.conf.yml` | Run Aider from the repository root; the config adds project guidance as read-only context. |

Agent versions differ. If a client does not automatically load its rule file,
use that client's documented project-rules feature and point it to the indicated
file. Do not copy the machine-specific generated reports or local MCP settings.

### Blender MCP setup

The Blender server is `tools/blender-mcp/server.py`. In the MCP settings for
your client, add a **local stdio server** with:

- **Command:** `python` (or the full path to your Python executable)
- **Argument:** `<repository-root>/tools/blender-mcp/server.py`
- **Working directory:** the repository root
- **Environment:** `BLENDER_EXE` set to your Blender executable, if Blender is
  not available as `blender` on `PATH`

MCP settings are client-specific, so this repository does not ship a user-level
configuration containing absolute paths. Restart or reload the client after
adding the server, then verify that it advertises tools and call `blender_info`.

### Unity MCP setup

Use the Unity CLI and editor integration supported by the installed Unity
version. Open the intended project in the editor first, then check `unity
status` and `unity pipeline list`. Configure the agent's MCP server to use the
same project path; a running editor and its Unity-side integration are required
for editor tools to appear.

## Repository map

| Path | Purpose |
| --- | --- |
| `.opencode/skills/universal-game-development-engineer/` | Core skill and engine, production, gameplay, testing and asset references |
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | Shared and CLI-specific project instructions |
| `.github/`, `.cursor/`, `.windsurf/`, `.clinerules/`, `.roo/` | Editor/agent-specific rules |
| `.aider.conf.yml` | Aider read-only instruction context |
| `scripts/detect-dev-environment.ps1` | Read-only Windows environment detector |
| `scripts/test-mcp-server.py` | Generic MCP stdio handshake/tool-list test |
| `scripts/test-blender-mcp.py` | Blender MCP smoke test; `--full` exercises create/inspect/validate/export/render |
| `tools/blender-mcp/server.py` | Dependency-free Blender MCP stdio server |
| `validation/assets/` | Small Blender validation source asset and texture |
| `validation/exports/` | Exported validation meshes and actual Blender preview render |
| `reports/README.md` | Notes on local generated reports |

## Production workflow

For a complete-game request, read
`.opencode/skills/universal-game-development-engineer/references/05-production-pipeline.md`
and work through its milestone gates:

1. **Foundation:** verify project, engine version, architecture and baseline.
2. **Vertical slice:** make one representative loop playable and testable.
3. **Content:** add designed levels, characters, assets, animation and audio.
4. **Features:** wire menus, settings, persistence and results to real state.
5. **Polish:** review usability, accessibility, visuals, sound and balance.
6. **QA and performance:** test, profile, fix and verify target builds.
7. **Delivery:** document setup, dependencies, licenses, evidence and limitations.

Do not treat generated concept art as a model, a copied asset as an import, or a
successful build as proof of clean runtime behavior. Record what was actually
configured, implemented, compiled, tested and verified.

### Skill reference guide

| Reference | Focus |
| --- | --- |
| `00-engine-selection.md` | Engine selection, project creation and constraints |
| `05-production-pipeline.md` | Studio roles, milestones, gates and evidence |
| `05b-autonomous-art-asset-research.md` | Art direction, asset research, licenses and provenance |
| `10-unity.md` | Unity CLI/MCP, project inspection, tests and builds |
| `15-world-and-level-design.md` | World briefs, routes, blockouts and procedural levels |
| `20-unreal-godot.md` | Unreal and Godot workflows |
| `30-blender-asset-pipeline.md` | Blender MCP, export/import and validation |
| `40-gameplay-systems.md` | Gameplay architecture and common systems |
| `45-character-ai.md` | Character animation and enemy behavior |
| `50-testing-and-builds.md` | Test matrices and platform builds |
| `55-art-audio-ui.md` | Art, audio, graphics and interface guidance |
| `60-troubleshooting.md` | Diagnostic playbooks |
| `70-acceptance-checklist.md` | Evidence-based completion checklist |
| `75-performance-qa-delivery.md` | Performance budgets, QA and handoff |

All references are under
`.opencode/skills/universal-game-development-engineer/references/`.

## Asset licensing

Before using an external asset, verify the license for the exact asset and its
dependencies. Record source, creator, license, attribution, restrictions and
destination in the project's asset provenance manifest. Do not silently buy,
scrape, redistribute or include assets whose terms are unclear.

No third-party game assets are bundled as a content library here. The included
Blender files and render are pipeline validation artifacts. **This repository
does not yet include a `LICENSE` file; do not assume permission to reuse or
redistribute its contents until the owner adds one.**

## Contributing and safety

- Inspect the existing project and preserve user work before editing.
- Do not commit credentials, private MCP configuration, generated machine
  reports, game builds, or unrelated project screenshots.
- Ask before purchases, external uploads beyond the explicitly requested
  repository, destructive changes, or system-wide installs.
- Use the smallest relevant test and report its actual result.

## Current limitations

- The repository is a development workflow and toolset, not a packaged game.
- Engine/editor MCP tools depend on the user's installed tools, project, editor
  state and client configuration.
- Blender MCP requires Blender; set `BLENDER_EXE` or make `blender` discoverable
  on `PATH`.
- The environment detector currently targets Windows.
- There is no repository license file yet.
