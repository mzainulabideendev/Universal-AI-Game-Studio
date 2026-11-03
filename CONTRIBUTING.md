# Contributing

Thank you for helping improve Universal AI Game Studio. Contributions should
make the workflow more useful, accurate, portable, safe or verifiable without
claiming functionality that has not been tested.

## Ways to contribute

- Fix an inaccurate instruction or reproducible issue.
- Improve the game-production skill or one of its focused references.
- Add or improve setup guidance for an AI agent or MCP client.
- Improve Blender MCP reliability, errors or validation behavior.
- Improve tests or document a verified workflow.
- Report accessibility, licensing, portability or security concerns.

For larger changes, open an issue or discussion first so scope and approach can
be agreed before implementation.

## Development workflow

1. Fork the repository and create a focused branch from `main`.
2. Describe the user-facing problem and intended result.
3. Inspect the existing skill, scripts, documentation and tests before editing.
4. Make a narrow change that follows the repository's existing conventions.
5. Run the smallest relevant validation commands (see below).
6. Review the final diff for unrelated files, machine-specific paths, generated
   reports and secrets.
7. Open a pull request with a concise summary, test results and limitations.

Use descriptive commit messages. Keep pull requests focused and split unrelated
changes into separate contributions.

## Validation

For documentation-only changes, check links and rendered Markdown where
practical. For Python changes, run syntax checks and the MCP handshake:

```powershell
python -m py_compile .\tools\blender-mcp\server.py .\scripts\test-blender-mcp.py .\scripts\test-mcp-server.py
python .\scripts\test-mcp-server.py -- python .\tools\blender-mcp\server.py
```

When Blender is installed, also run the real integration test:

```powershell
$env:BLENDER_EXE = 'C:\Path\To\Blender\blender.exe'
python .\scripts\test-blender-mcp.py --full
```

For a game-engine integration, test against the actual engine and project
version. State which commands ran and whether they passed. Do not claim engine,
build or runtime verification from a documentation check or MCP handshake alone.

## Documentation expectations

- Explain prerequisites, setup, commands, expected observations and limitations.
- Use portable paths and placeholders rather than a contributor's machine paths.
- Distinguish tested facts from suggested workflows.
- Link to relevant existing guides instead of copying long instructions into
  multiple files.
- Do not add screenshots unless they are genuine, useful, and safe to publish.
  Label test renders and mockups accurately.

## Code and safety expectations

- Preserve backward compatibility unless a breaking change is intentional and
  documented.
- Keep error messages explicit; do not convert failures into success-shaped
  fallbacks.
- Do not add credentials, private MCP settings, machine-specific reports,
  proprietary game assets, generated builds or unrelated project data.
- For external assets, document exact source, creator, license, attribution and
  restrictions. Do not assume a source website's general policy applies to
  every asset.
- Do not bypass authentication, access controls, download restrictions or
  license terms.
- Ask before introducing dependencies or system-wide installation steps.

## Pull request checklist

- [ ] The change addresses a specific issue or documented need.
- [ ] Only relevant files are included.
- [ ] Setup and usage documentation is updated when needed.
- [ ] Tests/checks and their actual results are included in the PR description.
- [ ] No secrets, private settings, local reports, generated builds or
      unlicensed assets are included.
- [ ] Limitations and unverified behavior are stated explicitly.

## License

By submitting a contribution, you agree that your contribution is provided
under the repository's [MIT License](LICENSE), to the extent you have the right
to do so. You remain responsible for ensuring that submitted content is
original or appropriately licensed and attributed.
