# Production Pipeline, Roles and Milestones

Use this when the request is to build a complete game, not a tech demo. The agent
acts as a small studio; every role has an explicit deliverable and gate.

## Roles and deliverables

| Role | Owns | Deliverable |
| --- | --- | --- |
| Game Director | Vision, scope, priorities | One-page game brief + milestone plan |
| Gameplay Programmer | Player, rules, state, combat | Playable systems + unit tests |
| Technical Director | Architecture, engine config, build | Compiling project, stable build config |
| Level Designer | Routes, pacing, encounters | Level plan + playable levels |
| Environment Artist | World art, lighting, atmosphere | Populated, lit environments |
| Character TA | Rig, skinning, animation setup | Working avatar + clip library |
| Animation Engineer | State machines, blending, root motion | Responsive animation states |
| AI Programmer | Enemy behaviour, navigation | AI with real detection/attack rules |
| UI/UX Designer | Menus, HUD, accessibility | Screens wired to real state |
| Audio Designer | Music, ambience, SFX, mixing | Audio events bound to gameplay |
| Graphics/Performance | Budgets, profiling, optimisation | Measured frame time, quality tiers |
| QA/Build Engineer | Tests, builds, release artifacts | Test report, verified build, known issues |

## Stage 0 — Brief (mandatory before code)

```
Title / genre / camera:
Core loop (5–30 s):
Session length and fail/win conditions:
Progression and persistence:
Controls (keyboard, gamepad, touch):
Art direction and references:
Target platforms and hardware:
Performance budget (fps, memory, build size):
Content list (levels, enemies, characters, audio):
Out of scope (explicit):
```

Undefined items get a documented assumption, not silent invention.

## Milestones (adapt size, keep the gates)

### A — Technical foundation
- Engine/version verified, project opens, scene loads.
- Architecture map: assemblies, scenes, input, render pipeline, save location.
- Baseline tests + baseline build recorded.
- **Gate:** compiles, existing tests pass, one build launches.

### B — Playable vertical slice
- Real player controller, one representative environment, core mechanic,
  collision, fail/win loop, minimal HUD.
- **Gate:** 5 minutes of play without a blocking defect; automated test for the
  core rule; captured evidence.

### C — Content production
- Required levels/environments, enemies, props, animation, sound.
- Each asset validated (geometry/scale/UV/material/rig/clips/collision).
- **Gate:** every level completable, no missing-asset errors, asset inventory.

### D — Feature completion
- Menus, settings, pause, save/load, results, level flow.
- **Gate:** every button has a handler; save round-trip test passes.

### E — Quality and polish
- Visual consistency, balancing, VFX, animation polish, accessibility, audio mix.
- **Gate:** playtest notes addressed; no placeholder art in shipping paths.

### F — Optimisation and QA
- Profile, fix top costs, regression suite, platform builds.
- **Gate:** measured performance within budget; platform build verified.

### G — Delivery
- Source project, verified builds, licence inventory, setup instructions,
  known-issues list, checksums.
- **Gate:** a fresh machine could open and build from the docs.

Do not advance past a critical defect by relabelling it "known issue" unless the
game remains playable and the limitation is explicit.

## Scope control

- Build the smallest complete loop first, then widen.
- Prefer one polished level over five empty ones.
- Cut features by writing them in "out of scope", not by leaving stubs.
- Any system without a player-facing effect is cut.

## Evidence discipline

Tag every claim:

- `implemented` — code exists and compiles.
- `wired` — reachable from the running game.
- `tested` — automated test exercised it.
- `verified` — observed in a build/Play Mode with logs or screenshots.
- `blocked` — reason recorded.

Visual quality is never proven by a unit test. State when human/visual review is
the only available evidence.

## Risks to watch

| Risk | Early signal | Mitigation |
| --- | --- | --- |
| Scope creep | new systems with no loop impact | re-read brief, cut |
| Works in Editor only | player log exceptions | build + launch every milestone |
| Asset debt | grey materials, missing clips | validation gate per asset |
| Physics fragility | tunnelling, jitter | CCD, fixed timestep, tests |
| Performance cliff | frame time spikes | profile each milestone |
| Save corruption | partial writes | atomic save + versioning |
