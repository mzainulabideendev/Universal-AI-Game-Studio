# MCP integration

The LLM never replaces existing tools. It produces structured plans that the
existing MCP tools consume.

## Tool groups

### Reasoning

| Tool | Purpose | Writes? | Provider call |
| --- | --- | --- | --- |
| `llm_status` | configuration, budgets, provider matrix, fallback policy | no | no |
| `llm_understand_request` | structured, classified requirements | no | yes (`confirm=true`) |
| `llm_generate_specification` | hybrid spec: LLM reasoning + deterministic structure | no | yes |
| `llm_analyze_ambiguities` | at most five material questions | no | yes |
| `llm_engine_compatibility` | engine fit and risks | no | yes |
| `llm_plan_architecture` | systems, dependencies, asset/animation plans | no | yes |
| `llm_review_plan` | feasibility review (advice only) | no | yes |
| `llm_validate_plan` | structural validation + optional LLM review | no | optional |
| `llm_build_execution_plan` | deterministic governed tool steps | no | no |
| `llm_trace_requirements` | requirement → spec → manifest trace | no | no |
| `llm_game_director_plan` | grounded production roadmap | no | yes |
| `llm_test_provider` | one real reachability request | no | yes |

### Execution (unchanged)

`blender_*`, `meshy_*`, `search_assets`, `download_polyhaven_asset`,
`inspect_animation_rig`, `create_animation_retarget_map`,
`check_animation_compatibility`, `stage_asset_for_engine`,
`verify_staged_import`, `engine_build`, `unity_*`, `godot_*`, `unreal_status`,
`init_project_manifest`, `update_requirement_status`, `record_project_decision`,
`compare_project_against_requirements`.

## Recommended sequence

```text
1. llm_status                          (read-only, no request)
2. llm_understand_request              (confirm=true)
3. llm_analyze_ambiguities             (confirm=true, max 5 questions)
4. llm_engine_compatibility            (confirm=true)
5. llm_generate_specification          (confirm=true, approved=false)
6. user reviews and approves
7. init_project_manifest               (confirm=true)
8. llm_plan_architecture               (confirm=true)
9. llm_validate_plan                   (optional LLM review)
10. llm_build_execution_plan           (no execution)
11. each execution step                (its own permission + confirm)
12. compare_project_against_requirements
```

## Execution plan shape

Each step names a real tool:

```json
{
  "id": "P2-build",
  "phase": "engine",
  "tool": "unity_build",
  "risk": "engine-run",
  "requires_confirm": true,
  "cost": "free",
  "requires_paid_approval": false,
  "allowed_by_default": true,
  "executed": false,
  "requirement_ids": ["R001"]
}
```

Constraints enforced by `validate_execution_plan`:

- `executable` must be `false`;
- tool must be in the allow-list of registered MCP tools;
- forbidden keys (`command`, `shell`, `script`, `url`, `exec`, ...) are rejected;
- paid steps must require explicit approval;
- write/engine/paid steps must require confirmation;
- no step may claim execution.

## Mapping to the production pipeline

| Plan phase | Tools |
| --- | --- |
| ground truth | `inspect_game_project`, `inspect_engine_capabilities`, `init_project_manifest` |
| assets | `search_assets`, `download_polyhaven_asset`, `blender_create_environment_blockout`, `blender_validate_asset` |
| character / animation | `inspect_animation_rig`, `create_animation_retarget_map`, `check_animation_compatibility`, optional paid `meshy_*` |
| engine integration | `stage_asset_for_engine`, `verify_staged_import`, `unity_batch_refresh`, `unity_run_tests`, `unity_build`, `godot_batch_import`, `godot_build` |
| evidence | `compare_project_against_requirements`, `track_project_progress` |

## Status changes

No LLM tool writes a requirement status. `update_requirement_status` requires
recorded evidence and `verification.run_requirement_verification` performs the
actual check. `compare_project_against_requirements` re-checks claims against the
project before progress is reported.

## Existing project mode

`llm_game_director_plan` with `project_path` reads:

- `inspect_game_project` evidence;
- the manifest via `track_progress`.

It does not modify them. Project content is only sent to a provider when
`GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT=true`, `include_project_content=true` and
`confirm=true`.
