# LLM structured-output schemas

Every model response is validated against a versioned schema in
`game_studio/llm/schemas.py`. Validation is intentionally dependency-free: it
supports types, `required`, `properties`, `items`, `enum`, `minLength`,
`maxLength`, `minItems`, `maxItems`, `minimum` and `maximum`.

Invalid JSON or an incomplete object triggers at most two repair attempts. If it
still fails, the call raises `LLMError(kind="invalid_output")` and no plan is
accepted.

## Versions

| Task | Schema | Version |
| --- | --- | --- |
| `understanding` | `UNDERSTANDING_SCHEMA` | 1.1 |
| `specification` | `SPECIFICATION_SCHEMA` | 1.0 |
| `review` | `REVIEW_SCHEMA` | 1.0 |
| `ambiguity` | `AMBIGUITY_SCHEMA` | 1.0 |
| `engine` | `ENGINE_SCHEMA` | 1.0 |
| `architecture` | `ARCHITECTURE_SCHEMA` | 1.0 |
| `validation` | `VALIDATION_SCHEMA` | 1.0 |

## Understanding

Required top-level fields:

```json
{
  "schema_version": "1.1",
  "summary": "...",
  "genre": "adventure",
  "dimension": "3d",
  "platforms": ["android"],
  "requirements": [
    {
      "id": "R001",
      "category": "movement",
      "statement": "The monkey can climb trees",
      "source_text": "climb trees",
      "classification": "explicit",
      "priority": "P0",
      "acceptance_test": "Climb works on tagged geometry",
      "confidence": 0.9,
      "depends_on": []
    }
  ],
  "assumptions": [],
  "questions": []
}
```

`classification` is one of `explicit`, `implied`, `technical`, `optional`,
`unresolved`, `conflict`, `excluded`. `priority` is `P0`–`P3`.

Optional fields: `subgenre`, `engine_recommendation`, `art_direction`,
`core_loop`, `abilities`, `character`, `environment`, `animation_needs`,
`physics_needs`, `ai_needs`, `ui_needs`, `audio_needs`, `save_system`,
`performance_targets`, `exclusions`, `conflicts`, `risks`,
`technical_dependencies`, `language`, `confidence`, `uncertainty`.

## Ambiguity

```json
{
  "schema_version": "1.0",
  "blocking": false,
  "summary": "...",
  "ambiguities": [
    {"area": "multiplayer", "issue": "not specified", "impact": "architecture",
     "requirement_id": "R010", "safe_default": "single-player offline"}
  ],
  "questions": [
    {"question": "Is multiplayer required?",
     "why_it_matters": "changes networking architecture and cost",
     "options": ["No", "Local co-op", "Online"], "default": "No"}
  ],
  "assumptions": ["single-player"]
}
```

`impact` is `architecture`, `cost`, `feasibility`, `functionality` or `polish`.
The server caps returned questions at five even if the model returns more.

## Engine reasoning

```json
{
  "schema_version": "1.0",
  "recommendation": "unity",
  "reason": "mobile tooling",
  "confidence": 0.8,
  "candidates": [
    {"engine": "unity", "fit": "strong", "reason": "...", "risks": []}
  ],
  "platform_constraints": ["thermal budget"],
  "verification_needed": ["detect_game_engines", "real build"]
}
```

`recommendation` is `unity`, `unreal`, `godot` or `unresolved`. A recommendation
never implies the engine is installed.

## Architecture

Required: `summary`, `systems[]`, `milestones[]`. Systems require `id`, `name`,
`responsibility`, `requirement_ids[]`. Optional: `core_experience`,
`dependency_edges`, `asset_plan`, `animation_plan`, `risks`, `next_actions`,
`assumptions`, `questions`.

Unknown requirement ids are returned in
`unknown_requirement_references` rather than silently accepted.

## Validation

```json
{
  "schema_version": "1.0",
  "verdict": "valid",
  "summary": "...",
  "issues": [
    {"severity": "high", "area": "mobile input", "issue": "no touch mapping",
     "requirement_id": "R004", "fix": "add on-screen controls"}
  ],
  "verified_facts": [],
  "unverified_claims": ["no runtime evidence"]
}
```

The deterministic validator is authoritative for structural safety; an LLM
review can add findings but cannot upgrade `blocked` to `valid`.

## Execution plan

Execution plans use an internal schema, not an LLM schema. They are produced by
`planning.py`, always have `executable: false`, and are validated for forbidden
execution keys and tool allow-list membership.
