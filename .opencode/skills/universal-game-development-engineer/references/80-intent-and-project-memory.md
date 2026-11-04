# Request intent, specification and project memory

Use this reference at the **start** of every game task and again when a session
resumes. It is the contract behind `analyze_game_request`,
`create_game_specification` and the project-memory tools in
`tools/game-studio-mcp`.

## 1. Understand before planning

Do not translate an informal request directly into code. Run
`analyze_game_request` with the user's words **unedited**, then read:

| Output | What to do with it |
| --- | --- |
| `original_request` | Quote it when reporting scope. Never rewrite the user's idea silently. |
| `language` | Confirms English / Roman Urdu / Urdu / mixed input was understood. |
| `understanding` | Genre, dimension, engine, platform, characters, environment, style, mechanics. |
| `requirements.explicit` | The only items the user actually asked for. |
| `requirements.implied` | Systems the genre needs. Engineering recommendations, not user demands. |
| `requirements.technical_dependencies` | Engine/dimension/multiplayer prerequisites. |
| `requirements.optional_enhancements` | Ideas to offer, never to sneak into the milestone plan. |
| `exclusions` | Negated requests such as "no guns" or "multiplayer ke baghair". |
| `conflicts` | Contradictions that must be resolved before implementation. |
| `unresolved` / `questions` | Missing decisions, with materiality and a recommended default. |
| `matched_terms` | Traceability: each concept's surface form and character offsets. |

Roman Urdu and Urdu coverage is a deterministic vocabulary, not a general
translator. It recognises common production vocabulary (dimension, genre,
characters, biomes, mechanics, platforms) plus common verb stems such as
`banao`, `charh`, `tair`, `uchal`. If a user's dialect is not recognised, ask a
short clarifying question instead of guessing.

### Requirement traceability

Every explicit requirement keeps:

- the user's matched phrase (`source_text`),
- a technical statement,
- an acceptance test,
- a status that starts at `pending`.

Do not mark a requirement complete because a related script or asset exists.
Completion is a separate, evidence-backed claim (section 4).

## 2. Clarify only what changes architecture

Ask at most five questions. Material topics are engine, dimension, target
platform, and online vs local multiplayer. Ask about art style and character
source when they change asset sourcing. Do not ask about things that have a safe
default (scope starts as one vertical slice; weather is not part of the core
loop).

When a default is used, record it as an assumption. When the user answers,
record it with `record_project_decision` and `source=user`, `approved=true`.

## 3. Create and approve the specification

`create_game_specification` returns:

- overview and engine selection state (`verified` only when detected),
- character specs with species-appropriate rigs (a monkey is **not** a humanoid
  retarget),
- environment specs with traversal, collision and performance budgets,
- animation clips and retargeting warnings,
- classified requirements,
- a dependency graph with a topological order and cycle check,
- milestones A–G with gate criteria,
- acceptance tests linked to requirement ids,
- assumptions, unresolved decisions and limitations.

The specification is `awaiting-approval` until the user approves the design,
engine, platform, art direction and scope. Approval is a user decision; pass
`approved=true` only after they have seen the plan.

Engine-specific code must not start while the engine is unresolved. Other work
(asset research, briefs, blockouts in Blender) may proceed.

## 4. Persist project intelligence

`init_project_manifest` writes `<project>/.game-studio/manifest.json`:

```text
schema_version, revision, project_id, project_path, timestamps
spec                      approved specification snapshot
requirements[]            status, evidence, notes, per-change history
decisions[]               topic, decision, rationale, source, approved
pending_questions[]
known_errors[]
milestones[]
history[]                 bounded audit of manifest changes
```

Rules:

- It is project-local and survives agent restarts. Read it with
  `get_project_manifest` / `track_project_progress`.
- Writes require `confirm=true`.
- Credential-like keys and values are refused. Secrets belong in the studio's
  private config, never in project memory.
- Do not edit the JSON by hand to make progress look better; the comparison tool
  detects unsupported claims.

### Status ladder

`pending -> in_progress -> implemented -> tested -> verified`

Plus `blocked` and `rejected`. Each change is appended to the requirement's
history. The tool enforces:

| Status | Minimum evidence |
| --- | --- |
| `implemented` | any recorded evidence |
| `tested` | `test` or `playtest` evidence |
| `verified` | `test`, `build`, `playtest` or `inspection` evidence, and referenced files must exist |

File creation is never accepted as verification. A build artifact is not a
playtest. An imported asset is not a verified gameplay system.

## 5. Re-check against the real project

Run `compare_project_against_requirements` after implementation changes and
before reporting:

- detects the real engine,
- checks evidence files still exist,
- flags requirements claimed done with missing or non-qualifying evidence,
- reports engine mismatch between the spec and the project,
- returns `verified` only when every recorded requirement has evidence.

The comparison checks existence, not semantic correctness. Human playtesting and
build review remain mandatory. Report configured, implemented, compiled, tested
and verified as separate facts.

## 6. Session recovery

On a new session:

1. `get_project_manifest` — recover spec, decisions, questions and statuses.
2. `track_project_progress` — coverage and next P0/P1 actions.
3. `inspect_game_project` — confirm the project still matches the manifest.
4. `compare_project_against_requirements` — detect drift before editing.

If no manifest exists, say so and reconstruct the plan from the request instead
of pretending to remember prior decisions.

## 7. Example

Input:

> "Bhai ek realistic 3D bandar adventure game banao jungle mein. Bandar ped par
> charh sake aur pani mein tair sake. Bandooq nahi chahiye."

Resulting interpretation:

- Explicit: 3D, adventure, monkey, jungle, climbing, swimming, realistic.
- Excluded: weapons.
- Implied: traversal, interaction, collectibles/objectives, NPC/dialogue, save.
- Technical: 3D import pipeline, engine project configuration, version control.
- Unresolved: engine, platform, character source (defaulted), scope.
- Rig: quadruped-capable, with an explicit warning not to retarget humanoid
  locomotion blindly.
- Acceptance tests include climbing, swimming, collision blocking and a
  five-minute playable build.
