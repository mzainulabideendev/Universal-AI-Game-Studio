# Universal AI Game Studio — Agent Instructions

These are project-wide instructions for coding agents. For game-development
tasks, read
`.opencode/skills/universal-game-development-engineer/SKILL.md` and the relevant
references in its `references/` directory before implementation.

## Workflow

- Inspect the project, engine version, architecture, existing assets and tests
  before changing files.
- When engine/tool versions matter, run
  `scripts/detect-dev-environment.ps1` and read its local report.
- Discover MCP tools at runtime. Never infer that a configured server is
  connected or invent tool names.
- Before Unity editor tools, check `unity status` and `unity pipeline list`;
  confirm the editor is open on the intended project.
- For Blender asset work, use the discovered Blender MCP tools or the documented
  headless fallback. Verify imports in the target engine.
- Follow `references/05-production-pipeline.md` for complete-game requests;
  build and test in vertical slices with milestone gates.
- Verify asset licenses and provenance before including external assets.
- Report configured, implemented, compiled, tested and verified separately.

## Safety and quality

- Preserve existing project architecture and user data. Back up configuration
  before edits; do not print or commit secrets.
- Ask before destructive changes, system-wide installs, purchases or uploads
  beyond the user's explicit request.
- Never fabricate tool names, versions, screenshots, test results or build
  artifacts. Do not call a build/game verified without running it and checking
  its logs.
- Do not leave essential mechanics as disconnected scripts, TODOs or fake
  success-shaped results.
- Use focused tests and report limitations and failures explicitly.
