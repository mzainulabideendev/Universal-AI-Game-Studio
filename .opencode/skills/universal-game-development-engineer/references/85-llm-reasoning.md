# LLM reasoning and MCP execution

This reference explains how to use the LLM reasoning layer without confusing a
plan with a working game.

## The boundary

```text
LLM: understand · reason · recommend · draft · validate · trace
MCP: inspect · download · generate · stage · build · test · verify
```

The reasoning layer has no execution capability. It cannot run a command, edit a
file, download an asset, spend credits, change a permission or mark a
requirement verified.

## When to use which path

| Situation | Path |
| --- | --- |
| No provider configured | deterministic tools; response says `deterministic-fallback` |
| User approves external reasoning | `llm_*` tools with `confirm=true` |
| Local-only requirement | `GAME_STUDIO_LLM_LOCAL_ONLY=true` + Ollama |
| Existing project | `llm_game_director_plan` with `project_path`; project content needs explicit flags |
| Any real operation | the corresponding MCP tool with its own confirmation |

## Recommended sequence

1. `llm_status` — configuration and budgets, no request.
2. `llm_understand_request` — classified requirements in any supported language.
3. `llm_analyze_ambiguities` — at most five material questions; otherwise
   labelled assumptions.
4. `llm_engine_compatibility` — engine fit; never an installation claim.
5. `llm_generate_specification` — LLM reasoning plus deterministic dependency
   graph, milestones and acceptance tests.
6. User reviews and approves engine, platform, dimension, art direction, scope.
7. `init_project_manifest` — persist the approved plan.
8. `llm_plan_architecture` — systems, dependencies, asset/animation plans.
9. `llm_validate_plan` — structural validation; deterministic verdict wins.
10. `llm_build_execution_plan` — governed tool steps; `executable: false`.
11. Execute steps individually through MCP with `confirm=true`.
12. `compare_project_against_requirements` — re-check evidence before reporting.

## Evidence rules

- `source: "llm"` means the model reasoned; it does not mean anything works.
- `source: "deterministic-fallback"` means the safe keyword path was used.
- `verified` status requires test, build, playtest or inspection evidence.
- A staged file is not an import. An imported file is not working gameplay.
- A build artefact is not a working game until it runs and is checked.
- Requirement traceability proves mapping, not implementation.

## Language support

English, Roman Urdu, Urdu, mixed Urdu-English and any language the configured
model supports. The deterministic fallback recognises common game vocabulary in
these languages; the LLM handles the rest. Preserve the user's original wording
in `source_text`.

## Cost and privacy

- Every provider call requires `confirm=true`.
- Paid provider usage is the user's choice; the server never sends a request just
  because a key exists.
- Project content is never sent automatically.
- Secrets are read from the environment and redacted from output.
- Budgets, timeouts, retries and a context limit are configurable.

## Failure handling

Provider timeout, rate limit, unavailability, missing key, invalid output,
context overflow and cancellation all produce explicit errors or a labelled
deterministic fallback. Never report a failed request as a success.
