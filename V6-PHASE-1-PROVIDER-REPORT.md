# V6 Phase 1 — Intelligent AI Provider Architecture Report

**Brand:** UNIVERSAL AI GAME STUDIO  
**Milestone:** V6 cross-engine intelligent game generation  
**Phase:** 1 — AI provider architecture  
**Status:** **COMPLETE** (evidence-backed; live-provider verification blocked by absent credentials and absent Ollama)  
**Repository HEAD:** `b628527` (no commit, push or tag)  
**Branch:** `main`

Machine-readable evidence:

- `reports/v6-provider-capabilities.json`
- `reports/v6-provider-routing.json`
- `reports/v6-phase1-audit.json` (Phase 0 audit re-run after Phase 1; 190 tests, 89 tools)
- `reports/v6-phase0-baseline.json` (unchanged Phase 0 baseline; 152 tests, 84 tools)

No Phase 2 work was started. No V4/V5 file was modified.

---

## 1. Objective and outcome

Phase 1 delivers a provider-independent connection and model-selection layer:

- typed capability discovery using `supported` / `unsupported` / `unknown`
- documented model listing for all five existing adapters
- provider configuration and credential workflow without exposing secrets
- capability-aware routing for six task categories
- honest Ollama detection without install, download or service start
- deterministic fallback preserved
- 38 new tests and 190/190 total tests passing

The five existing adapters were extended, not replaced: Ollama, OpenAI,
Anthropic, Gemini and OpenAI-compatible.

---

## 2. Governance and restrictions

| Restriction | Result |
| --- | --- |
| Do not install Ollama | Honoured — detection only |
| Do not download models | Honoured |
| No paid API calls | Honoured — 0 provider requests during implementation/reporting |
| Do not expose credentials | Honoured — values are never returned; reports scanned clean |
| Do not change V4/V5 | Honoured — V4/V5 hashes re-checked unchanged |
| Do not commit/push | Honoured — HEAD remains `b628527` |
| Do not weaken tests | Honoured — all 152 original tests retained and passing |
| Do not start Phase 2 | Honoured |

---

## 3. What existed before Phase 1

Inspection confirmed the following already worked and was reused:

| Area | Existing implementation |
| --- | --- |
| Adapters | `OpenAIProvider`, `OpenAICompatibleProvider`, `AnthropicProvider`, `GeminiProvider`, `OllamaProvider` behind one `complete()` interface |
| Registry | `_REGISTRY` + `build(cfg)` |
| Client reliability | budgets, retries with backoff, cancellation checks, schema repair, cache support |
| Structured output | versioned JSON schemas and validator |
| Configuration | environment + machine-local `llm.json` selection |
| Redaction | secret patterns in `llm/config.py`; `RedactedHeaders` |
| Fallback | deterministic parser in `game_studio.understanding`, labelled |
| MCP LLM tools | 12 tools including `llm_status` and real `llm_test_provider` |
| Privacy | project content disabled by default; local-only mode |

Phase 1 did not duplicate any of these. It added discovery, capability typing,
routing and a safer credential/settings workflow around them.

---

## 4. New modules and changed files

### New modules

| File | Purpose |
| --- | --- |
| `tools/game-studio-mcp/game_studio/llm/capabilities.py` | Typed tri-state capability model, provider profiles, task categories, capability report |
| `tools/game-studio-mcp/game_studio/llm/catalog.py` | Provider/model discovery, Ollama runtime detection, unavailable diagnostics |
| `tools/game-studio-mcp/game_studio/llm/routing.py` | Capability/budget-aware provider and model routing with deterministic fallback |
| `tools/game-studio-mcp/tests/test_v6_phase1_providers.py` | 38 mocked tests for capabilities, discovery, settings, secrets, routing and tool registration |
| `scripts/v6-phase1-report.py` | Reproducible configuration-only report generator |
| `reports/v6-provider-capabilities.json` | Capability evidence |
| `reports/v6-provider-routing.json` | Routing evidence |
| `reports/v6-phase1-audit.json` | Post-Phase-1 audit evidence |

### Modified files

| File | Change |
| --- | --- |
| `tools/game-studio-mcp/game_studio/llm/providers.py` | Added documented `list_models()` and `health()` to the base adapter and all five adapters; loopback handling for Ollama |
| `tools/game-studio-mcp/game_studio/llm/config.py` | Added `provider_config()`, provider/model/endpoint validation, `save_provider_selection()`, local-secret resolution |
| `tools/game-studio-mcp/game_studio/secrets.py` | Added private per-provider LLM credential storage, environment precedence, clear operation |
| `tools/game-studio-mcp/server.py` | Added five MCP tools, handlers and schemas |
| `scripts/v6-phase0-audit.py` | Optional output path so the Phase 0 baseline is not overwritten by later audits |

No existing test was edited, skipped or removed. V4 and V5 artifacts are byte-identical
to the Phase 0 baseline.

---

## 5. Capability model

States are explicit:

- `supported` — the adapter implements and tests the capability.
- `unsupported` — the adapter does not implement it.
- `unknown` — no documented source established it; never assumed.

### Provider-level matrix (adapter facts)

| Capability | OpenAI | OpenAI-compatible | Anthropic | Gemini | Ollama |
| --- | --- | --- | --- | --- | --- |
| Text generation | supported | supported | supported | supported | supported |
| Structured output | supported | supported | **unsupported** | supported | supported |
| JSON mode | supported | supported | **unsupported** | supported | supported |
| Tool calling | unsupported | unsupported | unsupported | unsupported | unsupported |
| Vision / image input | unsupported | unsupported | unsupported | unsupported | unsupported |
| Streaming | unsupported | unsupported | unsupported | unsupported | unsupported |
| Embeddings | unsupported | unsupported | unsupported | unsupported | unsupported |
| Context window | unknown | unknown | unknown | supported* | unknown |
| Model listing | supported | supported | supported | supported | supported |
| Health check | supported | supported | supported | supported | supported |

\* Gemini context window becomes known only after discovery returns
`inputTokenLimit` for a concrete model.

`unsupported` for tool calling, vision, streaming and embeddings is deliberate:
the adapters do not send tools, image parts or streams, and embeddings are not
implemented. Vendor support is not claimed.

### Model-level policy

Model capabilities start as `unknown`. Only documented discovery fields can
change them:

- Gemini: `supportedGenerationMethods` and `inputTokenLimit`
- OpenAI/OpenAI-compatible: id, created, owner only → capabilities unknown
- Anthropic: id, display name, type only → capabilities unknown
- Ollama `/api/tags`: names and details only → capabilities unknown

A model name is never used as capability evidence.

---

## 6. Model discovery

One read-only request per invocation, using documented endpoints:

| Provider | Endpoint | Auth |
| --- | --- | --- |
| OpenAI | `GET {base_url}/models` | `Authorization: Bearer` |
| OpenAI-compatible | `GET {base_url}/models` | `Authorization: Bearer` |
| Anthropic | `GET {base_url}/models?limit=100` | `x-api-key` + `anthropic-version` |
| Gemini | `GET {base_url}/models?pageSize=200` | `x-goog-api-key` |
| Ollama | `GET {base_url}/api/tags` | none; loopback HTTP allowed |

Discovery:

- requires `confirm=true` and `external_api` governance
- refuses to run when a hosted credential is missing (no network attempt)
- classifies authentication, rate-limit, not-found, timeout, unavailable and
  invalid-response failures
- redacts credentials from every error message
- labels output `mode: "live"` only after a real request succeeded
- never sends project content and performs no generation request

**Not performed in Phase 1:** no live discovery request was made, because no
credential is configured and Ollama is not installed.

---

## 7. Ollama (optional, never installed)

Detection is limited to:

- `shutil.which("ollama")` for a runtime on PATH
- the configured loopback service via `GET /api/tags` when discovery is approved

Results in this environment:

| Field | Value |
| --- | --- |
| Runtime on PATH | **false** |
| Executable | `null` |
| Started by this project | **false** |
| Models downloaded | 0 |
| Service reachability | unknown (not probed live) |

If the runtime is missing, routing does not auto-select Ollama and explains why.
An explicit Ollama request is kept but warns that reachability is unverified.
Models discovered through `api/tags` keep every model capability `unknown`;
local models are never assumed to support tools or structured output.

---

## 8. Provider settings and diagnostics

New MCP tools:

| Tool | Network | Confirmation | Purpose |
| --- | --- | --- | --- |
| `llm_provider_capabilities` | none | no | Capability matrix, task categories, limitations |
| `llm_list_models` | one read-only request | **required** | Documented model discovery |
| `llm_route` | none | no | Capability/budget routing decision |
| `llm_configure_provider` | none | **required** | Persist provider/model/endpoint |
| `llm_configure_credential` | none | **required** | Store/clear credential privately |

Settings workflow guarantees:

- provider, model and endpoint are validated before persistence
- hosted endpoints must be HTTPS; HTTP is allowed only for local Ollama loopback
- credentials are never accepted by `llm_configure_provider`
- credentials are never returned, logged, written to project files or reports
- `llm_configure_credential` returns only `api_key: "[REDACTED]"`
- configuration status reports `credential_configured` and its source
  (`environment`, a named env var, or `local-file`)
- connectivity is never reported as successful without a real request

Precedence for credentials:

1. `GAME_STUDIO_LLM_API_KEY`
2. provider environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
3. private `secrets/llm.json` under the studio config directory

---

## 9. Intelligent routing

Task categories and their required capabilities:

| Task | Required capabilities |
| --- | --- |
| `game_design_reasoning` | text generation, structured output |
| `technical_architecture` | text generation, structured output |
| `code_generation` | text generation |
| `character_environment_planning` | text generation, structured output |
| `asset_analysis` | text generation |
| `qa_verification` | text generation, structured output |

Routing rules:

- a required capability known `unsupported` **blocks** the candidate
- an `unknown` capability is allowed with an explicit unverified warning, or
  blocked when `require_known=true`
- context chars, output tokens, session/day request budgets, zero request budget
  and discovered model context windows are enforced
- a model absent from a supplied discovery result is rejected
- hosted providers require explicit `allow_paid=true`; they are never selected
  silently
- when a preferred provider is rejected, the router does **not** switch to another
  provider automatically
- when no candidate qualifies, the deterministic fallback is returned with
  `network_calls: 0`
- routing output always states `live_verified: false`

Example decisions:

| Scenario | Result |
| --- | --- |
| No credential, Ollama missing | deterministic fallback |
| Ollama installed (configuration only) | selects local Ollama, reachability unverified |
| `provider="openai"`, `allow_paid=false` | rejected; no silent switch |
| `provider="openai"`, `allow_paid=true`, key present | selects OpenAI |
| `provider="anthropic"`, structured-output task | rejected (unsupported) |
| Required `vision` | every provider rejected |
| Required `context_window`, `require_known=true` | rejected until known |

---

## 10. Security and reliability verification

| Control | Evidence |
| --- | --- |
| Secret redaction | Discovery error containing a key-shaped string is redacted; test asserts absence |
| No credentials in reports | Regex scan of all three JSON reports: 0 matches |
| No credentials in settings file | Test asserts `api_key` absent from stored config |
| No credentials in responses | Credential tool returns `[REDACTED]`; test asserts absence |
| Environment precedence | Test asserts env key overrides local file |
| Endpoint validation | HTTPS enforced; HTTP rejected for hosted providers |
| Loopback exception | Only the local Ollama adapter may use loopback HTTP |
| Timeout handling | Discovery uses the configured connect timeout; provider errors classify timeout |
| Retry limits | Existing client retry/backoff preserved; routing reports configured limits |
| Rate-limit handling | HTTP 429 remains classified `rate_limit`, retryable |
| Request budgets | Routing blocks zero budget, oversized context and oversized output |
| Cancellation | Existing client cancellation path preserved; discovery is bounded by timeout |
| Prompt-injection resistance | Existing client marker inspection preserved; no new execution path |
| No shell execution | Provider reasoning still cannot run commands |
| No unauthorized network | Discovery requires `confirm=true` + `external_api`; reports made 0 calls |
| No unauthorized file access | Settings/secret paths are under the studio config directory |

---

## 11. Tests

Command:

```powershell
python -m unittest discover -s tools\game-studio-mcp\tests -q
```

| Run | Tests | Result |
| --- | --- | --- |
| Phase 0 baseline | 152 | OK |
| Phase 1 full suite | **190** | **OK** (14.669 s manual; 14.603 s audit) |
| New Phase 1 tests | 38 | OK |

Coverage added:

- every adapter's model discovery wire format
- Gemini documented metadata vs unknown fields
- Ollama loopback tags and unknown model capabilities
- invalid discovery responses
- missing credentials → no request
- confirmation required before network
- authentication failure redaction
- Ollama unavailable diagnostics
- private credential storage, environment precedence and clearing
- provider selection validation and endpoint rules
- capability tri-state honesty
- unknown capability handling (`require_known`)
- unsupported capability blocking
- hosted provider refusal without `allow_paid`
- explicit paid approval
- Anthropic structured-output rejection
- invalid model selection
- context/token budgets
- deterministic fallback
- tool registration (89 tools / 89 handlers / valid schemas)
- no-network guarantees for capability and routing tools

All provider calls in tests are mocked. Mocked success is never reported as live
provider verification.

---

## 12. MCP inventory

| Check | Phase 0 | Phase 1 |
| --- | --- | --- |
| Tools | 84 | **89** |
| Handlers | 84 | **89** |
| Unique names | 84 | 89 |
| Missing handlers | 0 | 0 |
| Invalid object schemas | 0 | 0 |
| `llm_*` tools | 12 | **17** |

---

## 13. Provider status in this environment

| Provider | Credential configured | Source | Reachable | Live verified |
| --- | --- | --- | --- | --- |
| OpenAI | false | — | unknown | null |
| OpenAI-compatible | false | — | unknown | null |
| Anthropic | false | — | unknown | null |
| Gemini | false | — | unknown | null |
| Ollama | false (not required) | — | unknown | null |

No live provider verification exists. `llm_test_provider` remains the only tool
that can prove a real completion, and it was not run because no provider is
authorized or configured.

---

## 14. Blocked and unimplemented functionality (honest list)

**Blocked by environment**

1. Live provider connectivity and model listing: no credentials configured.
2. Ollama live detection: runtime absent, service absent; installing/downloading
   is prohibited.
3. Real end-to-end LLM quality evaluation remains blocked.

**Deliberately unimplemented in Phase 1**

1. Tool/function calling is not sent by any adapter (`unsupported`).
2. Vision/image input is not implemented (`unsupported`).
3. Streaming is not implemented (`unsupported`).
4. Embeddings are not implemented (`unsupported`).
5. Anthropic structured output is not requested through a documented JSON control
   (`unsupported`).
6. Ollama per-model capability inspection via `/api/show` is not implemented;
   `/api/tags` exposes no capabilities, so they remain `unknown`.
7. Model discovery is not cancellable mid-request beyond the configured timeout.
8. Discovery requests are not counted against generation budgets or usage totals.
9. Automatic model benchmarking/selection by measured quality does not exist.
10. Per-agent model assignment and orchestration belong to Phase 2 and were not
    started.

**Not claimed**

- No claim that any model produces good game designs, code or plans.
- No claim that a selected provider is reachable.
- No claim that Ollama models support structured output or tools.
- No claim that the four V6 acceptance criteria involving generated games,
  textures, animations or builds were addressed in this phase.

---

## 15. Acceptance criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| Existing adapters preserved and extended | PASS | 5 adapters still registered; `list_models`/`health` added |
| Typed tri-state capabilities | PASS | `capabilities.py`; limitation tests |
| No capability inferred from model name | PASS | model-level default `unknown`; Gemini-only documented upgrade |
| Model listing where supported | PASS (implementation) | 5 documented endpoints; wire tests |
| Model selection and filtering | PASS | `routing.py`; invalid-model and budget tests |
| Provider health/availability | PASS (implementation) | `health()` + configuration status; live blocked |
| Model-selection explanations | PASS | `explanation`, `candidates`, `fallback_plan` |
| Six task categories | PASS | `TASK_CATEGORIES` |
| Ollama optional, never installed | PASS | detection only; `started: false` |
| Settings workflow | PASS | 2 new settings tools with confirmation |
| Credentials secure and redacted | PASS | tests + report scan |
| Intelligent routing | PASS | unsupported blocked, unknown labelled, no silent paid switch |
| Deterministic fallback preserved | PASS | routing fallback + existing parser |
| Existing tests preserved | PASS | 152 original + 38 new = 190 OK |
| V4/V5 unchanged | PASS | hashes re-checked |
| Documentation + JSON reports | PASS | this report + 3 JSON evidence files |
| No commit/push | PASS | HEAD `b628527` |

**Phase 1 gate: PASS for implementation, tests, security and documentation.**
**Live provider verification remains BLOCKED by environment, not by code.**

---

## 16. Reproduction

```powershell
# Full suite (190 tests)
python -m unittest discover -s tools\game-studio-mcp\tests -q

# Configuration-only evidence (0 network calls)
python scripts\v6-phase1-report.py

# Phase 0 preservation audit, written to a Phase 1 evidence file
python scripts\v6-phase0-audit.py reports\v6-phase1-audit.json

# Inspect the reports
python -c "import json;print(json.load(open(r'reports\v6-provider-capabilities.json'))['providers'])"
python -c "import json;print(json.load(open(r'reports\v6-provider-routing.json'))['policy'])"
```

To perform a real (authorized) discovery or connection test:

```powershell
# Live model listing (one read-only request; requires confirm=true)
# llm_list_models { "provider": "openai", "confirm": true }

# Live completion test (still the existing tool; requires confirm=true)
# llm_test_provider { "confirm": true }
```

---

## 17. Phase 1 conclusion and next gate

Phase 1 is complete: the provider architecture now has typed capability
discovery, documented model listing, secure settings and credentials, honest
Ollama handling, capability-aware routing, deterministic fallback, and
regression coverage. All 190 tests pass and V4/V5 remain untouched.

**Phase 2 — Agent Orchestration has not been started.** Work will not continue
until explicit approval is given.
