# V3 upgrade audit — Universal AI Game Studio

Date: 2026-11-04
Repository audited: `D:\MCP\MCP`
Scope: V3 brief (Modules 1–15), existing MCP servers, skill, tests, docs.

This report separates **verified**, **implemented-unverified**, **missing** and
**blocked** work. Nothing is called working because it exists in a file.

---

## 1. Existing implementation audit (before this change)

### 1.1 What existed

| Area | State | Evidence |
| --- | --- | --- |
| MCP transport | Implemented | Custom dependency-free stdio JSON-RPC with `initialize`, `tools/list`, `tools/call`, batching and structured tool errors |
| Blender automation | Implemented, live-tested | 8 tools; real subprocess runs, imports, exports, renders, blockouts |
| System/engine detection | Implemented | Windows hardware, Unity/Unreal/Godot executables, project discovery |
| Project inspection | Implemented | Real parsing of Unity `ProjectVersion`/packages/scenes/missing scripts, Godot config, Unreal descriptors |
| Meshy | Implemented, not live-verified | Documented API, credit confirmations, key onboarding, task polling/download; no valid key was available |
| Asset search | Implemented | Poly Haven keyless search/download with MD5 + provenance; Sketchfab token search unverified; manual-only providers reported as such |
| Animation inspection | Implemented | GLB/glTF skeleton and clip parsing, rig classification, retarget map, compatibility warnings |
| Engine adapters | Mixed | Unity stage/verify/refresh/test/build, Godot stage/import/build, Unreal staged-only |
| Tests | 33 passing | Offline, no engine/network/API key |
| Skill + multi-agent rules | Implemented | OpenCode/Codex/Claude/Copilot/Cursor/Gemini/Windsurf/Cline/Roo/Aider files |

### 1.2 Architectural assessment

Strengths:

- Clean module split: `config`, `secrets`, `util`, `detect`, `projects`,
  `blender`, `meshy`, `assets`, `animations`, `engines`.
- Evidence-first culture already present: staged vs imported vs built is
  distinguished, and missing providers are not simulated.
- Real process execution without a shell; JSON argument files for Blender.
- Atomic writes via `write_text`/`write_json`.
- External machine config (`GAME_STUDIO_HOME`) keeps paths and secrets out of
  the repository.
- Consistent tool envelope (`ok`, structured errors, bounded output).

Weaknesses found:

- **No request-understanding layer.** Free-form requests were passed straight to
  implementation. No separation of explicit vs implied vs optional work, no
  multilingual handling, no traceability from wording to test.
- **No specification or dependency planning tools.** Genre knowledge lived in
  prose in the skill, not executable output.
- **No persistent project memory.** Session restarts lost decisions, scope and
  progress. `projects.py` inspected a project but stored nothing.
- **No requirement status model.** There was no way to distinguish "file
  created" from "tested" from "verified" inside a project.
- **No duplicate-work protection.** Without a manifest the agent could not know
  what was already completed or rejected.
- **No spec-to-project comparison.** Engine drift between plan and project was
  invisible.

---

## 2. Missing functionality vs the V3 brief

| V3 module | Before | After this change |
| --- | --- | --- |
| 1. Natural-language understanding | missing | **implemented** (`analyze_game_request`) |
| 1.2 Requirement classification | missing | **implemented** |
| 1.3 Clarification intelligence | partial (skill prose) | **implemented** bounded questions + defaults |
| 1.4 Traceability | missing | **implemented** source phrase → requirement → acceptance test |
| 2. Project architect/planning | partial (prose) | **implemented** spec, graph, milestones, gates |
| 3. Technical director | partial | engine selection state + warnings + next actions |
| 4. Deep MCP tool architecture | 52 tools | **60 tools**, schemas, handlers, tests; categories A–H partly covered |
| 5. New vs existing project mode | inspection only | manifest + comparison; existing-project edits still need agent discipline |
| 6. Character/environment intelligence | asset/staging only | character/environment specs, rig warnings, traversal/collision plans |
| 7. Genre gameplay engineering | skill guidance | genre→systems templates; implementation still engine-specific |
| 8. Asset/animation matching | implemented | unchanged; consumes spec requirements |
| 9. Self-correction | manual | evidence validation + invalid-claim detection; no autonomous retry loop |
| 10. Visual art direction | prose | style extraction + conflict detection; no renderer-based validation |
| 11. Project memory | missing | **implemented** versioned local manifest |
| 12. Reliability/security | strong | added secret scanning, path checks, evidence existence checks |
| 13. Truthful reporting | strong | status ladder now enforced per requirement |
| 14. Execution modes | missing | not implemented as a persisted mode; approval gates remain |
| 15. Acceptance tests | partial | 50 automated tests + validation script; multi-engine scenarios still blocked |

---

## 3. Security and reliability assessment

### Preserved strengths

- HTTPS-only downloads with host allow-lists and private-address rejection.
- Download size limits, MD5/SHA-256 checks, atomic replacement.
- Staging paths restricted to the project's asset roots; traversal rejected.
- No shell invocation; timeouts on subprocesses.
- Credentials resolved at call time and never returned.
- Explicit `confirm=true` for credits, writes, editor runs and builds.
- JSONL audit trail outside the repository.

### Gaps still open

| Gap | Risk | Recommendation |
| --- | --- | --- |
| Custom JSON-RPC instead of the official MCP SDK | protocol drift, no cancellation/resources/prompts | Migrate behind a compatibility layer; keep the dependency-free runtime as a fallback |
| No request cancellation | long Blender/engine jobs cannot be aborted by the client | Add cancellation tokens and process termination |
| No per-tool permission policy | every tool is equally callable | Add a local permission config and read-only/confirm tiers |
| No rate limiting | repeated paid calls possible | Add per-tool cooldowns and credit guards |
| Evidence semantics are recorded, not re-played | a `verified` claim can be stale | Add a re-run command per evidence kind and freshness timestamps |
| Heuristic intent parser | unusual language may be misread | Always show the classification for approval; ask when confidence is low |
| No execution-mode persistence | Guided/Balanced/Autonomous is not enforceable | Store mode in the manifest/config and gate tools by mode |
| Build/playtest not executed here | cannot claim end-to-end delivery | Keep scenario matrix below explicit |

---

## 4. Implemented in this pass

### New modules

| File | Responsibility |
| --- | --- |
| `tools/game-studio-mcp/game_studio/understanding.py` | Multilingual lexical intent extraction, classification, exclusions, conflicts, material questions |
| `tools/game-studio-mcp/game_studio/specification.py` | Engine-aware specification, character/environment/animation plans, dependency graph, milestones, acceptance tests |
| `tools/game-studio-mcp/game_studio/manifest.py` | Versioned project memory, evidence-backed status transitions, decisions, progress, comparison |

### New MCP tools (8)

`analyze_game_request`, `create_game_specification`, `init_project_manifest`,
`get_project_manifest`, `update_requirement_status`, `record_project_decision`,
`track_project_progress`, `compare_project_against_requirements`.

### New validation

- `scripts/validate-intent-memory.py` — end-to-end offline check.
- 17 new unit tests (33 → **50 passing**).
- New skill reference: `references/80-intent-and-project-memory.md`.
- Updated `AGENTS.md`, `SKILL.md`, root README, MCP README and ACCEPTANCE.

### Verified behaviour

| Claim | Evidence |
| --- | --- |
| Roman Urdu + English request understood | `validate-intent-memory.py`: `english`, `roman-urdu`; monkey/climbing/swimming |
| Negation preserved | `Bandooq nahi chahiye` → exclusion `weapons`, no weapon requirement |
| Conflicts detected | multi-engine and realistic-vs-pixel tests |
| Plan is acyclic | topological order covers all nodes; cycle check empty |
| Manifest survives restart | reload returns same `project_id`, decisions and statuses |
| Evidence guards work | `verified` without evidence rejected; missing build file rejected |
| Invalid claims caught | tampered manifest → `blocked`, requirement listed |
| Secret-like values refused | credential-pattern test raises `ToolError` |
| MCP handshake | `initialize` + `tools/list` → 60 unique tools, all with handlers |

### Not verified

- Intent parsing beyond the lexicon (dialects, metaphor, implicit references).
- Live Meshy generation/rigging/animation.
- Unity batch refresh/tests/build against a real project.
- Godot import/export.
- Unreal import/build (staged-only by design).
- Any generated asset imported and played in a running game.
- 2D workflow end-to-end.

---

## 5. Acceptance scenario matrix (brief Module 15)

| # | Scenario | Status | Note |
| --- | --- | --- | --- |
| 1 | Natural-language understanding | **verified (offline)** | English/Roman Urdu; classification and questions tested |
| 2 | User-selected engine | **verified** | Detection exists; specification honours override and warns when not installed |
| 3 | Character production | **partial** | Blender/Meshy tooling exists; no character was produced and imported in this pass |
| 4 | Animation | **partial** | Inspection/retarget mapping exists; playback not verified |
| 5 | Environment production | **partial** | Real Blender blockouts exist from earlier work; collision/navigation validation not done |
| 6 | Real gameplay | **not verified** | No playable build was produced in this pass |
| 7 | Existing project modification | **implemented, not exercised** | Manifest + project inspection; a limited-change scenario still needs a real project run |
| 8 | Failure diagnosis | **partial** | Evidence guards/invalid claims; no automated root-cause engine |
| 9 | Session recovery | **verified (offline)** | Manifest reload test |
| 10 | 2D and 3D pipelines | **partial** | Dimension-aware plans; no end-to-end 2D run |

---

## 6. Prioritized roadmap

### P0 — next

1. **Execution modes** (Guided/Balanced/Autonomous) persisted in config and
   enforced by the server, not just prose.
2. **Cancellation + per-tool permissions** so long Blender/engine jobs and paid
   calls are controllable.
3. **Evidence freshness and re-run**: a `verify_evidence` tool that re-runs a
   named test/build command and records a new timestamp.
4. **Existing-project regression check**: snapshot file hashes before a change,
   compare after, and fail if unrelated files changed.

### P1

5. **Official MCP SDK compatibility layer** while retaining the stdlib runtime.
6. **Engine-specific spec outputs**: Unity `Animator`/URP plan, Godot scene tree,
   Unreal asset/blueprint plan, generated only for the verified engine.
7. **Gameplay scaffolds with tests**: player controller/camera/collision
   templates that compile and pass a deterministic test in the target engine.
8. **Art-direction validation**: material/lighting checklist per style, with
   Blender render inspection.
9. **Meshy live verification** once a key is available; record generated asset
   hashes and import results.

### P2

10. **2D pipeline parity**: tilemap, sprite import, pixel-perfect and 2D physics
    validation.
11. **Multiplayer plan generator** with online/local decision and test plan.
12. **Project manifest migration tooling** for schema changes.
13. **Human playtest capture** and comparison against acceptance tests.

---

## 7. Reproduce

```powershell
python -m compileall -q .\tools\game-studio-mcp
python -m unittest discover -s .\tools\game-studio-mcp\tests -v
python .\scripts\validate-intent-memory.py
python .\scripts\test-mcp-server.py --call studio_info -- python .\tools\game-studio-mcp\server.py
```

Expected: compile clean, **50 tests OK**, validation `PASS`, and a truthful
`studio_info` payload that includes only detected integrations.
