# V6 Phase 6 — Free AI Intelligence, Provider Integration & Asset-Generation Research

**Product:** UNIVERSAL AI GAME STUDIO  
**Tagline:** From Game Idea to Playable World.  
**Phase:** 6 of V6  
**Status:** Automated audit **PASS** — human review pending  
**Verification date:** 2026-11-10  
**Branch:** `main`  
**Starting HEAD:** `ee6093ecb3df086c835d430e75d7c381bbe7ca03`  
**Ending HEAD:** `ee6093ecb3df086c835d430e75d7c381bbe7ca03` (unchanged; no commit)  
**Tests:** 373 → **409** (36 Phase 6 tests added, existing tests preserved)  
**MCP tools/handlers:** 94/94 → **101/101** (exactly seven new tools, exact parity)

---

## 1. Summary

Phase 6 adds a free-first, provider-aware intelligence layer on top of the existing Phase 1–5 architecture. It does **not** replace that architecture:

- Phase 1 provider adapters, credential handling, budgets and model discovery remain the only transport path.
- GroqCloud and OpenRouter were added as OpenAI-compatible adapters; Gemini was retained and its default model was updated to a documented free-tier model.
- Phase 2's eight agents, Phase 3 character pipeline and Phase 4 environment pipeline remain intact and are now reachable through free-only routing and design bridges.
- Phase 5's Unity project, executable, build payload and protected artifacts were not modified.

The phase delivers:

1. An evidence-backed free-provider catalog with explicit statuses.
2. A persistent free-quota ledger with redaction and unknown-quota honesty.
3. A free-only router that refuses paid, trial-only, unknown-billing and non-free OpenRouter models.
4. Typed, schema-validated game design and requirement decomposition.
5. Deterministic bridges into Phase 3/4 specs without any AI asset claim.
6. A research catalogue that separates free hosted, free limited, open-source local, paid, and research-only asset routes.
7. Seven MCP tools and a reproducible audit/demo.

**No live provider request, paid API call, subscription, install, model download, asset download, commit, push, tag, release or merge occurred.** Audit evidence records `network_calls = 0`, `live_tests_performed = 0`, `asset_downloads = 0`, `model_downloads = 0`, `installs = 0`.

---

## 2. Pre-flight and Phase gates

| Gate | Result | Evidence |
|---|---|---|
| Phase 0 baseline manifest present | PASS | `reports/v6-phase0-baseline.json` |
| Phase 4 independent PASS audit | PASS | `reports/v6-phase4-audit.json` (`verdict=PASS`, `all_criteria_passed=true`) |
| Phase 5 audit present | PASS | `reports/v6-phase5-audit.json` (`PASS_AUTOMATED`) |
| Phase 5 build-identity verification present | PASS | `reports/v6-phase5-build-identity-verification.json`, `V6-PHASE-5-BUILD-IDENTITY-VERIFICATION.md` |
| Starting test count | 373 (OK) | pre-flight run, `python -m unittest discover -s tools/game-studio-mcp/tests -q` |
| Starting MCP parity | 94 tools / 94 handlers | pre-flight parse of `server.TOOLS` and `HANDLERS` |
| V4 protected hashes | Unchanged | Phase 6 audit |
| V5 protected hashes | Unchanged | Phase 6 audit |
| Phase 5 project/build/payload | Git-clean within protected paths | Phase 6 audit |

The two untracked Phase 5 build-identity deliverables (`V6-PHASE-5-BUILD-IDENTITY-VERIFICATION.md` and `reports/v6-phase5-build-identity-verification.json`) pre-existed Phase 6 and were not modified.

---

## 3. Provider evidence and free-tier classification

Status vocabulary: `verified_free`, `free_limited`, `local_free`, `paid`, `trial_only`, `unknown`, `unavailable`. Only the first three satisfy free-only routing.

| Provider | Status | Documentation (verified 2026-11-10) | Documented free allowance | Payment info | Live test |
|---|---|---|---|---|---|
| Google Gemini Developer API | `free_limited` | `https://ai.google.dev/gemini-api/docs/pricing`, `.../rate-limits`, `.../models` | Selected Flash/Flash-Lite models are marked **Free of charge**; eligible list recorded as `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`. `gemini-4-argon` and Pro preview are explicitly not free-tier. RPM/TPM/RPD are account/project specific and shown in AI Studio. | Not required for free tier | Not authorized, not performed |
| GroqCloud | `free_limited` | `https://console.groq.com/docs/rate-limits`, `.../models`, `.../structured-outputs` | Free Plan: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, each 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD. HTTP 429 on limit. | Not required for free plan | Not authorized, not performed |
| OpenRouter | `free_limited` | `https://openrouter.ai/docs/api-reference/limits`, `.../guides/overview/models`, models API reference | Only model ids ending in `:free` are eligible. 20 RPM; 50 RPD for accounts with under 10 all-time credits, 1,000 RPD with ≥10 credits; `GET /api/v1/key` exposes `free_model_daily_requests`. | Not required for free models | Not authorized, not performed |
| Ollama | `local_free` | `https://docs.ollama.com/api/tags`, `.../generate`, `.../chat` | Local runtime, no hosted billing. `/api/tags` lists installed models. Never installed, started or populated by this project. | Not applicable | Not authorized, not performed |

Researched and **rejected** for free-only operation:

- **Stability AI** — 25 trial credits (1 credit = $0.01), then paid → `trial_only`. A trial does not satisfy free-tier acceptance.
- **Hugging Face Inference Providers** — free accounts receive no monthly credits; purchase required → `paid`.
- **Meshy API** — prepaid credits → `paid`.
- **Tripo API** — usage-based paid credits → `paid`. TripoSR is separately documented as an open-source local route.
- **Pollinations Classic** — free, no signup documented, roughly one image per 45 seconds, one model, JPEG with a small logo, best-effort with no uptime guarantee → `free_limited`, image-only.

**Important restrictions recorded in evidence:**

- Gemini free-tier content may be used to improve Google products; do not send proprietary content without approval.
- Gemini limits are per project, not per key, and reset at midnight Pacific time.
- Groq fast inference is not unlimited inference; model eligibility and limits change.
- OpenRouter free-model availability depends on account credits and upstream providers; paid variants are separate ids.
- Ollama suitability depends on local hardware; the documented 16 GB / integrated-GPU machine was **not** benchmarked.

Full machine-readable evidence: `reports/v6-free-provider-catalog.json`, `reports/v6-free-provider-evidence.json`.

---

## 4. Architecture changes

### 4.1 Extension, not replacement

Existing Phase 1 modules (`config.py`, `providers.py`, `capabilities.py`, `routing.py`, `client.py`, `catalog.py`) were extended. New Phase 6 modules live beside them:

| Module | Responsibility |
|---|---|
| `game_studio/llm/free_policy.py` | Static, evidence-backed free-provider catalog, status vocabulary, model eligibility, known daily limits, asset-provider research records. No network I/O. |
| `game_studio/llm/quota.py` | Persistent daily free-quota ledger with provider/model/tokens/cost/allowance/remaining/status/fallback reason/timestamp. Redacts secrets. |
| `game_studio/llm/free_routing.py` | Free-only policy over Phase 1 capability evaluation. Refuses paid/trial/unknown, non-`:free` OpenRouter models and exhausted quotas. Records fallback reasons. |
| `game_studio/llm/intelligence.py` | Typed game design, requirement decomposition, contradiction/unsupported detection, Phase 3/4 bridges, deterministic benchmark. |
| `game_studio/llm/asset_research.py` | Honest asset-generation research catalogue and capability summary. |

### 4.2 Provider registry changes

- `PROVIDERS`: `openai, openai_compatible, anthropic, gemini, groq, openrouter, ollama`.
- `groq` → `https://api.groq.com/openai/v1`, default `openai/gpt-oss-120b`, `GROQ_API_KEY`.
- `openrouter` → `https://openrouter.ai/api/v1`, default `openai/gpt-oss-20b:free`, `OPENROUTER_API_KEY`.
- `gemini` default updated from the legacy `gemini-1.5-flash` to documented free-tier `gemini-3.8-flash`.
- Credentials remain environment-variable/private-secret-store only; no key was added to source, config, reports or Git.

### 4.3 Capability declarations

`image_generation`, `texture_generation` and `3d_mesh_generation` were added to the tri-state capability model. Every text adapter, including Groq/OpenRouter, declares them `unsupported`. Capabilities are never inferred from model names.

### 4.4 Free-only orchestration

`Orchestrator(..., free_only=True)` forces `allow_paid=False` and uses `free_routing` for every agent task. The default path is unchanged, preserving all Phase 2 tests. Plans remain `executable:false`; no engine action follows from an agent proposal.

---

## 5. Free-only routing policy

Route order: `gemini → groq → openrouter → ollama`, then deterministic fallback. This is a policy order, not a quality ranking.

For each candidate the router checks:

1. Documented provider status is `verified_free`, `free_limited` or `local_free`.
2. Model eligibility (Gemini free-tier list, Groq free-plan list, OpenRouter `:free` suffix, local Ollama).
3. Phase 1 capability/budget/credential/discovery evaluation.
4. Documented daily quota where available; the ledger's usage today.
5. Unknown quota is explicitly **not** unlimited.
6. Failure reason classification (`429`, `401`, `403`, timeout, network, invalid model, deprecated, malformed output).

The router never silently switches providers, never upgrades to paid, and returns the deterministic fallback with recorded reasons. `fallback_plan.paid_switch` and `policy.paid_fallback` are always `false`.

Report: `reports/v6-free-routing-policy.json`.

### Quota/cost governance

The ledger tracks provider, model, request count, input/output tokens, estimated cost, verified allowance, remaining allowance, status, fallback reason and timestamp. It stores no credentials or prompts. When a provider does not expose a reliable per-key remaining quota, `remaining_today` and `exhausted` are `null` and the decision is labelled `quota_unknown_not_unlimited`.

---

## 6. Game design and requirement decomposition

The deterministic engine reuses `game_studio.understanding` and adds a Phase 6 contract. Every requirement includes a stable id, description, category, priority, dependencies, acceptance criteria, required assets, target engine, verification method, status, provenance and confidence.

For the reference request:

> "Create a 3D jungle adventure where a monkey collects bananas."

The proposal contains **28 requirements** (5 user requirements, 23 recommendations) and covers all 15 checklist items:

`player_character`, `character_rig_animations`, `jungle_terrain`, `vegetation`, `collectibles`, `collision`, `camera`, `player_controls`, `score_system`, `objectives`, `hud`, `game_states`, `performance`, `build_configuration`, `tests`.

The design output distinguishes:

- `user_requirements` (from the user's words),
- `recommendations` (implied/technical/optional engineering items),
- `assumptions`,
- `unsupported_features`,
- `blocked_requirements`,
- `approved_decisions`,
- `missing_information`,
- `contradictions`.

Contradiction rules detect 2D/3D conflict, single-player/multiplayer, UI excluded-but-required, audio excluded-but-required and free-vs-paid mixing. Unsupported rules flag multiplayer, open-world scope, AAA scope, AI texture generation, AI 3D generation and ray tracing on the documented hardware. Design output is schema-validated and always `executable:false`.

Reports: `reports/v6-ai-game-design-evaluation.json`.

---

## 7. Phase 3 / Phase 4 integration

`character_spec_from_design` and `environment_spec_from_design` build the existing Phase 3/4 specs. For the reference design both validate successfully.

They explicitly return:

- `ai_generated_asset: false`
- `procedural_blender: true`
- `generation_performed: false`

The Blender pipeline remains deterministic procedural generation. No mesh or texture was generated, and procedural output is never relabelled as AI-generated.

---

## 8. Asset-generation research

Categories:

1. **Free hosted API** — Pollinations Classic (image-only, rate-limited, best-effort).
2. **Free limited hosted service** — no additional verified free texture/3D service was found.
3. **Open-source local** — Stable Diffusion, ComfyUI, TripoSR (not installed; no weights downloaded).
4. **Paid service** — Stability AI, Hugging Face Inference Providers, Tripo API, Meshy API.
5. **Research-only / unavailable** — no verified ongoing free hosted text-to-3D API.

Capability summary: no free hosted texture, normal-map, roughness-map or 3D-mesh route is available now. `available_now` is `false` for every capability. No asset or model was downloaded and nothing was installed.

Report: `reports/v6-asset-generation-research.json`.

---

## 9. MCP tools

Seven tools were added, for exact parity at **101/101**:

| Tool | Purpose |
|---|---|
| `llm_free_provider_catalog` | Evidence-backed provider status, eligible models, quota basis and docs. |
| `llm_free_quota_status` | Ledger usage, documented limits, remaining/unknown states and estimated cost. |
| `llm_free_route` | Free-only routing with paid/trial/unknown and non-`:free` rejection. |
| `llm_game_requirements` | Typed requirement decomposition and provenance separation. |
| `llm_game_design` | Schema-validated design proposal, optional Phase 3/4 spec bridge. |
| `llm_asset_generation_capabilities` | Free/paid/local asset research summary. |
| `llm_ai_benchmark` | Deterministic structural benchmark; no live-quality ranking. |

Every tool has an object input schema and an exact handler. `llm_free_route` performs no network request. `llm_game_design` and `llm_game_requirements` remain non-executable proposals.

---

## 10. Testing and verification

Command:

```text
python -m unittest discover -s tools/game-studio-mcp/tests -q
```

| Metric | Result |
|---|---|
| Starting tests | 373, OK |
| Final tests | **409, OK** |
| Added Phase 6 tests | 36 |
| Duration | ~75 s |
| Failures/errors | 0 |
| Existing tests weakened/deleted/skipped | None |

The only pre-existing test changed was the Phase 2 MCP parity assertion, which hard-coded 94 tools. It now asserts the actual 101-tool count and still checks exact tool/handler set equality plus Phase 6 tool presence. This reflects the intentional seven-tool addition rather than weakening coverage.

Phase 6 tests cover provider discovery/status, paid/trial/unknown rejection, OpenRouter `:free`, quota exhaustion, unknown quota, 429/401/403/timeout/network/invalid-model/deprecation/malformed-output reasons, secret redaction, schema validation, contradiction detection, unsupported detection, approval boundaries, Phase 3/4 bridges, eight-agent free-only orchestration, asset research separation, MCP parity/handlers, and deterministic benchmark reproducibility.

Audit: `reports/v6-phase6-audit.json` → **PASS**, all 20 criteria passed.

---

## 11. Security

- Credentials remain environment-variable or private-secret-store only.
- Generated reports contain environment-variable **names** as documentation, not credential values.
- The quota ledger and failure records redact `Authorization`, `Bearer`, `sk-`, `gsk_` and `sk-or-` patterns.
- Existing HTTPS enforcement, request timeouts, response-size limits, prompt-injection markers and schema validation remain in Phase 1.
- Provider output is never executed automatically.
- No secret was printed, logged, committed or written into a report.

---

## 12. Performance and hardware

Documented hardware profile: AMD Ryzen 5 4500U, 16 GB RAM, integrated Radeon graphics.

- No local model was installed or downloaded.
- No local inference was measured.
- No claim is made that Stable Diffusion, ComfyUI or TripoSR run efficiently on this machine.
- Performance targets in design output are targets, not measurements (`measured: false`).
- Ollama remains optional and is never started automatically.

---

## 13. Known limitations and blocked requirements

**Limitations**

1. No live provider request was authorized or performed; mock tests do not prove live functionality or output quality.
2. Gemini free-tier limits are account/project specific and were not read from a live account.
3. Groq free-plan and OpenRouter free-model catalogues can change; re-verify before use.
4. The structural benchmark does not rank or measure live model quality.
5. No free hosted texture/normal/roughness/3D API was verified.
6. Open-source local asset routes were not installed, licensed in detail, or benchmarked.
7. The free-quota ledger records this machine's usage, not provider-side remaining quota unless the provider documents a limit.
8. Phase 6 does not add a live provider execution path to orchestration; it adds policy and prompt/design structure.

**Blocked/unsupported by design**

- Paid, trial-only and unknown-billing providers under free-only mode.
- OpenRouter paid model variants.
- Automatic paid or cross-provider fallback.
- AI texture/normal-map/3D generation claims.
- Multiplayer, open-world and AAA scope as verified deliverables.
- Any asset download, model download or software installation.

---

## 14. Human-review gate

Phase 6 stops here. Before live use or Phase 7:

1. Review provider terms, data-retention policies and free-tier eligibility in the provider dashboards.
2. Configure credentials only through environment variables or the private secret store; never paste secrets into source or chat.
3. If live verification is desired, approve one small, budgeted request per provider explicitly.
4. Inspect `reports/v6-free-provider-evidence.json` and `reports/v6-phase6-audit.json`.
5. Approve material scope decisions; no requirement is human-verified by this phase.

No Phase 7 work was started.
