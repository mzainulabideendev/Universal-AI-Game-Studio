# V6 Phase 2 — Intelligent Multi-Agent Orchestration

Status: **PASS** (planning and orchestration only)
Starting HEAD: `b628527` · Ending HEAD: `b628527` · Branch: `main`
Provider mode used for evidence: **deterministic, zero-network** (no live provider verification)
Game/assets/textures/animations/build generated: **No**

Phase 2 turns the game studio into a coordinated, typed planning team. It does not
generate characters, PBR textures, environments, scenes, code or builds. A
completed agent run is a validated planning artifact, never implementation
verification.

---

## 1. What was added

### New package: `tools/game-studio-mcp/game_studio/agents/`

| File | Purpose |
| --- | --- |
| `contract.py` | States, `AgentSpec`, `AgentResult`, `AgentError`, schema validation, evidence refs |
| `context.py` | Scoped shared context, provenance, history, approved decisions |
| `schemas.py` | Brief input plus all eight agent output schemas |
| `helpers.py` | Quality profiles, engine planning capabilities, requirement/exclusion helpers |
| `workflow.py` | Eight-task dependency graph and derived parallel groups |
| `base.py` | Common runner: scoped input, validation, attribution, failure mapping |
| `game_director.py` | Brief creation and final consolidation |
| `game_designer.py` | Genre, loop, objectives, progression, tests |
| `technical_architect.py` | Engine selection, scenes, systems, budgets |
| `character.py` | Geometry, UV, PBR, rig, animation plan |
| `environment.py` | Terrain, vegetation, water, lighting, atmosphere |
| `gameplay.py` | Controls, movement, physics, camera, scoring, tests |
| `uiux.py` | Screens, HUD, settings, accessibility, navigation |
| `qa.py` | Coverage, conflicts, evidence requirements |
| `registry.py` | Agent registry and registry report |
| `coordinator.py` | Scheduling, concurrency, retries, cancellation, routing, conflicts, consolidation |

### Other changes

- `tools/game-studio-mcp/server.py`: one new MCP tool `orchestrate_game_plan`
  (deterministic handler, strict arguments), tool/handler parity 90/90.
- `tools/game-studio-mcp/tests/test_v6_phase2_agents.py` — 33 tests.
- `tools/game-studio-mcp/tests/test_v6_phase2_coordinator.py` — 44 tests.
- `scripts/v6-phase2-demo.py` — reproducible zero-network demonstration.
- `scripts/v6-phase2-audit.py` — full audit runner.
- `reports/v6-agent-registry.json`, `reports/v6-agent-workflow.json`,
  `reports/v6-phase2-demo.json`, `reports/v6-orchestration-audit.json`.

No V4/V5, Phase 0 or Phase 1 file was modified.

---

## 2. Agent registry

All agents are version `1.0.0`, deterministic by default, and declare their own
input/output schemas, required context, dependencies and capabilities.

| Agent | Responsibility | Task category | Depends on | Produces |
| --- | --- | --- | --- | --- |
| `game_director` | Brief, coordination, consolidation | `game_design_reasoning` | `qa` (consolidation) | `brief`, `consolidation` |
| `game_designer` | Genre, core loop, objectives, progression, tests | `game_design_reasoning` | — | `design` |
| `technical_architect` | Engine recommendation, scenes, systems, budgets | `technical_architecture` | `design` | `architecture` |
| `character` | Geometry, UV, PBR maps, rig, animations (plan only) | `character_environment_planning` | `design`, `architecture` | `character` |
| `environment` | Terrain, vegetation, structures, water, lighting (plan only) | `character_environment_planning` | `design`, `architecture` | `environment` |
| `gameplay` | Controls, movement, physics, camera, scoring, acceptance tests | `technical_architecture` | `design`, `architecture` | `gameplay` |
| `uiux` | Menus, HUD, settings, pause, accessibility, navigation | `game_design_reasoning` | `design`, `gameplay` | `uiux` |
| `qa` | Coverage, conflicts, test plan, evidence requirements | `qa_verification` | all planning agents | `qa` |

Machine-readable registry: `reports/v6-agent-registry.json`.

---

## 3. Common agent contract

Every agent satisfies the same typed interface (`contract.py`):

- identity, name, semantic version, responsibility, task category;
- `input_schema` and `output_schema` (JSON-schema-subset validated);
- `required_context` (only those sections are handed to the agent);
- `dependencies`, `required_capabilities`, `max_retries`, `produces`;
- execution status, structured error, retryability, evidence references;
- provider attribution (`deterministic` / `mocked` / `live`) and budget metadata.

States: `pending`, `ready`, `running`, `completed`, `failed`, `blocked`,
`skipped`, `cancelled` (`STATES` in `contract.py`).

Failure rules:

- input failing validation → `failed` (`input-validation`), no execution;
- output that is not a JSON object or fails the schema → `failed`
  (`output-validation`); it is never coerced into a success;
- typed `AgentError` → `failed` with explicit `retryable` flag;
- unexpected exception → `failed` (`internal`);
- dependent task whose prerequisite did not complete → `blocked`;
- cancellation → `cancelled`.

Each successful result carries an `agent://<agent>/<task>` evidence reference,
the input-character size estimate, and the routing decision that was applied.

---

## 4. Coordinator architecture

`Orchestrator` (`game_studio/agents/coordinator.py`):

1. Accepts the unedited request; builds a validated brief through
   `understanding.analyze_request` and the Game Director.
2. Builds the eight-task plan with an explicit dependency graph and parallel
   groups (a cycle makes `parallel_groups()` raise, and the graph validator
   reports it).
3. Executes level by level, only when every prerequisite is `completed`;
   otherwise the task is `blocked` with a structured reason.
4. Runs each level with `ThreadPoolExecutor` capped by an explicit
   `concurrency` limit (1–4, default 2). No uncontrolled parallel requests.
5. Passes only the declared context sections, deep-copied, with provenance
   (`agent`, `agent_version`, `task_id`, `status`).
6. Collects results, retries only retryable failures within `max_retries`
   (0–3, default 1), and records the actual retry count.
7. Honours cancellation before and during a run; unstarted tasks become
   `cancelled`.
8. Detects conflicts, consolidates via the Game Director, and emits a
   non-executable report with evidence and diagnostics.

Execution order for the demonstration:

```
design → architecture → {character, environment, gameplay} → uiux → qa → consolidation
```

Failure of a prerequisite stops dependent execution and leaves the affected
tasks `blocked`; the report status becomes `failed` (or `blocked` when only
blocking conflicts exist).

---

## 5. Shared context and communication

`ProjectContext` stores the request, brief, eight output sections, provenance,
history and approved decisions. Agents receive `request`, only their declared
sections, `context_sources` and any approved decisions. Views are deep copies, so
an agent cannot mutate shared state. Every output records the producing agent and
version, and history records statuses and evidence.

---

## 6. Provider integration (Phase 1 reuse)

- Each task calls the existing `game_studio.llm.routing.route` with its task
  category, required capabilities and context size.
- Routing decisions (mode, selected provider/model, capability compatibility,
  explanation, network calls) are preserved per task in the report.
- No provider adapter was rebuilt; Ollama is optional, not assumed.
- Deterministic mode is labelled `deterministic`; injected executors are
  labelled `mocked` unless they explicitly report `live`.
- `live_verified` is only true when an authorized live executor reports live
  results. No such run exists in Phase 2.
- Routing never silently switches to a paid provider (`allow_paid=false` by
  default).
- Budgets: with `use_provider=true`, the coordinator enforces
  `GAME_STUDIO_LLM_MAX_REQUESTS` (zero blocks work) and
  `GAME_STUDIO_LLM_MAX_CONTEXT_CHARS` before any agent runs. Deterministic mode
  performs no budget-gated provider work.

Provider status for this phase: **not live-tested**. Credentials remain
unconfigured for the evidence runs; all automated provider tests use mocked
responses.

---

## 7. Conflict and governance handling

`detect_conflicts` reports structured conflicts with id, category, severity,
blocking flag, approval requirement, source agents and open status:

- required mechanic also excluded;
- missing prerequisite section;
- recommended engine not detected (blocking);
- environment estimate over the performance budget;
- character asset pipeline gap (Phase 3 dependency);
- QA-reported coverage/scope failures;
- contradiction with an approved project decision (never silently overridden).

The consolidated plan is always `executable: false`, with
`implementation_status: "planned-not-implemented"`, explicit approval items and
open questions. Governance flags record no engine invocations, writes, asset
generation or requirement status changes.

The demonstration produces one non-blocking conflict, `C-character-pipeline`
(medium, requires approval), because mesh/PBR/rig work is Phase 3.

---

## 8. MCP integration

Only one new tool was added: `orchestrate_game_plan`. It exposes meaningful
user-facing orchestration without one tool per internal agent.

- Strict object schema: `request` required; bounded `concurrency` (1–4) and
  `max_retries` (0–3); enumerated `quality_target`; optional engine/platform,
  detected-engine list and approved decisions.
- Handler validates arguments, defaults engines to local detection, and forces
  deterministic mode (`use_provider=false`).
- Tool/handler parity: **90/90**, no missing or orphan handlers, all schemas
  valid objects.

---

## 9. Tests and demonstration

Full suite: **267 tests, OK** (190 pre-existing preserved + 77 new).

New coverage includes: every agent, input/output schemas, malformed outputs,
non-object outputs, typed/unexpected failures, assignment, dependency graph,
sequential and bounded-parallel execution, context isolation, provenance,
provider attribution, routing capability checks, provider failure, deterministic
fallback, budget enforcement, retry limits, retry recovery, cancellation (before
and during), dependency blocking, conflict detection (engine, scope,
performance, missing prerequisite, approved decision, deduplication),
governance, evidence traceability, secret redaction, MCP parity, and V4/V5/Phase 1
regression hashes.

Demonstration (`reports/v6-phase2-demo.json`):

- status `completed`, `ok=true`, engine `unity`;
- all eight steps `completed` in dependency order;
- `executable=false`, `game_generated=false`, `assets_generated=false`;
- provider `deterministic`, `live_verified=false`, `network_calls=0`;
- measured orchestration duration ~98 ms (environment-dependent, not a
  performance claim).

---

## 10. Preservation and security

- V4 checkpoint `4bf92a8`: both protected test files hash-identical.
- V5 Unity vertical slice: all baseline artifacts hash-identical; requirement
  counts unchanged (24 requirements, 13 tested / 3 implemented / 1 pending / 7
  rejected).
- Phase 0/1 reports untouched; Phase 1 audit remains 190 tests / 89 tools.
- No secrets read, printed or written to project files. The audit scans produced
  reports for credential markers and environment credential values; result:
  clean.
- No commit, push, tag, install, download or paid request was performed.

---

## 11. Known limitations

1. Phase 2 is planning only: no character mesh, UV layout, PBR texture, rig,
   animation, environment, scene, gameplay code or build exists.
2. Performance numbers in the environment plan are estimates, not measurements.
3. QA status is always `not-verified`; it cannot certify implementation.
4. Live provider behavior (latency, output quality, reachability) is unverified;
   mocked tests prove plumbing, not provider correctness.
5. The character pipeline gap and all environment/asset work remain open for
   Phase 3+.
6. The consolidated plan stays non-executable until governance explicitly
   authorizes implementation.

---

## 12. Reproduction commands

```powershell
# Full test suite (expect 267 tests, OK)
python -m unittest discover -s tools\game-studio-mcp\tests -q

# Zero-network demonstration (writes reports/v6-phase2-demo.json)
python scripts\v6-phase2-demo.py

# Full audit: tests, demo, registry, workflow, parity, hashes, security
python scripts\v6-phase2-audit.py

# Registry and workflow evidence
Get-Content reports\v6-agent-registry.json
Get-Content reports\v6-agent-workflow.json
Get-Content reports\v6-orchestration-audit.json
```

Audit result: `ok=true` with every acceptance criterion true. Phase 2 is
complete. Phase 3 (character models, PBR textures, asset generation) has not
started and requires explicit approval.
