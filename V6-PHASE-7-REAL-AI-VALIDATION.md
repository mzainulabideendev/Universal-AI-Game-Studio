# V6 Phase 7 — Real AI Provider Validation & Intelligent Game Generation

**Product:** UNIVERSAL AI GAME STUDIO  
**Tagline:** From Game Idea to Playable World  
**Phase:** 7 of V6  
**Status:** Offline implementation **PASS_AUTOMATED** (21/21) — live provider request **LIVE_REQUEST_FAILED (HTTP 503 / read timeouts)** — human review **HUMAN_REVIEW_REQUIRED**  
**Provider evidence retrieval date:** 2026-11-10  
**Audit evidence timestamp:** `2026-11-11T08:32:25Z` (`reports/v6-phase7-audit.json`)  
**Branch:** `main`  
**Baseline HEAD:** `51342fe17996dd62011c43dabf5f7c1936bdf0bd`  
**Current HEAD at final audit:** `5f2c99094badb0ffbf5380bd39008ef39d9eb425` — "Update Phase 7 documentation and tests to reflect changes in test counts and temperature handling" (committed externally by the repository owner; this agent performed no Git write)  
**Tests:** 409 → **463** (38 Phase 7 tests plus 16 bounded-timeout tests added, 0 failed, 0 skipped)  
**MCP tools/handlers:** 101/101 → **107/107** (six new tools, exact parity)  
**Audit:** 21/21 criteria PASS (automated scope); live criteria explicitly excluded and reported separately

---

## 1. The chain this phase had to prove

```text
Game idea (natural language)
  -> real AI understanding
  -> requirements + design specification
  -> schema validation + feasibility + provenance + quality
  -> human approval
  -> existing generation pipelines
  -> character / environment / gameplay specifications
```

Offline stages 1–5 and the pipeline bridge are implemented and tested. The **real AI**
link in that chain is the one thing this phase has only partly exercised: after explicit
approval of the request hash, three live attempts ran. One reached the provider and was
rejected with HTTP 503 ("high demand"); the other two ended in socket read timeouts before
a response body arrived. Everything below labels that boundary explicitly.

The chain must not be read as "an AI built a game". The farthest proven outcome is:
**a natural-language idea can be turned into stable, schema-checked, provenance-labelled,
engine-aware specifications that plug into the existing Phase 3/4/5 builders — with a real
provider ready behind a one-request approval gate.**

---

## 2. What was implemented

New modules (all under `tools/game-studio-mcp/game_studio/llm/`):

| Module | Responsibility |
| --- | --- |
| `response_validation.py` | JSON extraction/parsing, contract schema, required/type/enum checks, missing-field detection, contradictions, unsupported-claim detection, ambiguity detection, confidence, redaction |
| `quality_evaluation.py` | Deterministic 10-category rubric (0–100) with an explicit method and evidence per category |
| `game_spec_pipeline.py` | Idea → stable `REQ-` requirements → design → feasibility → Phase 3/4/5 bridges → approval boundary → non-executable generation plan → spec validation |
| `provider_validation.py` | Offline readiness, exact request plan + `request_sha256`, gated single-request execution, persistable audit record |

New MCP tools (registered with exact input schemas and handlers):

- `llm_provider_readiness`
- `llm_provider_validate`
- `llm_game_spec_generate`
- `llm_game_spec_validate`
- `llm_game_quality_evaluate`
- `llm_generation_plan_preview`

New evidence/report script: `scripts/v6-phase7-audit.py`.

New tests: `tools/game-studio-mcp/tests/test_v6_phase7_real_ai.py` (38 tests).

### Reuse, not duplication

Phase 7 imports and reuses the Phase 6/1 stack unchanged:

- `providers.py` adapters — the only transport path (including `GeminiProvider`).
- `free_policy.py` — free eligibility and documented evidence.
- `quota.py` — local ledger and conservative quota decisions.
- `free_routing.py` — free-only routing.
- `schemas.py` — dependency-free schema validation and JSON parsing.
- `intelligence.py` — deterministic understanding/design and Phase 3/4 spec bridging.
- `character_spec.py` / `environment_spec.py` — unchanged Phase 3/4 builders.

No adapter, router or schema was rewritten.

---

## 3. Provider selection and free-tier evidence

Selected: **Google Gemini Developer API**, model **`gemini-3.8-flash`**, using the
existing `GeminiProvider` adapter.

Classification: `free_limited` (a documented free allowance that is rate/token limited
and account-dependent).

Evidence recorded on **2026-11-10** from official pages:

| Question | Evidence |
| --- | --- |
| Free-tier eligibility | Pricing page lists a Free plan with free input/output tokens for selected models; `gemini-3.8-flash` is marked **Free of charge** in its pricing row |
| Model availability | Model page documents `gemini-3.8-flash` with 1,048,576 input tokens and 65,536 output tokens |
| Structured output | Structured-output docs confirm JSON-Schema-constrained responses |
| API route | `POST /v1beta/models/{model}:generateContent` remains documented |
| Rate limits | Per project (not per key), measured in RPM, TPM and RPD; exact values are account/model specific and shown in AI Studio |
| Daily reset | RPD resets at midnight Pacific time |
| Billing required | No payment method is required to use the free tier |
| Data handling | Free-tier content is documented as usable to improve Google products |
| Regional restrictions | Availability follows Google's supported-regions list; the account region must be checked in AI Studio |

Evidence files:

- `reports/v6-phase7-provider-policy.json`
- `reports/v6-phase7-provider-evidence.json`

Refusals remain in force: `gemini-4-argon` and Pro preview models are paid-only;
unknown providers/models and unknown billing are rejected; unknown quota is never
treated as unlimited; there is no paid fallback.

---

## 4. Offline readiness

`reports/v6-phase7-readiness.json` (no network call):

| Field | Value |
| --- | --- |
| Adapter | `GeminiProvider` |
| Model | `gemini-3.8-flash` |
| Free status | `free_limited` |
| Model eligibility | eligible |
| Credential | **not configured** (value never read or exposed) |
| Quota | 0 requests today; documented per-key daily limit unavailable; **not** treated as unlimited |
| Structured output | declared supported; adapter JSON mode on |
| Request timeout | 60 s total wall-clock deadline (connect 10 s, TLS 10 s, headers 30 s, body 45 s) |
| Provider retries | 0 in the Phase 7 path; no provider fallback |
| Phase 7 live retries | **0** |
| Blockers | none (credential configured locally; value never exposed) |
| Network calls | 0 |

---

## 5. What was tested offline, and what it proves

### 5.1 Response contract

- Malformed JSON and non-object output are rejected.
- Missing required fields and wrong types are reported.
- A complete fixture passes schema validation.
- Contradictions are detected (e.g. both 2D and 3D presentation).
- Unsupported claims are flagged (multiplayer, netcode, open world, ray tracing, Nanite/Lumen, MetaHuman, etc.) with `auto_accepted: false`.
- Subjective acceptance criteria without measurable checks are flagged as ambiguous.
- Secrets are redacted before evidence is persisted.

### 5.2 Requirements and specification

- Stable `REQ-` IDs: the same idea produces identical IDs across runs.
- Every requirement carries description, category, priority, dependencies, acceptance
  criteria, required assets, target engine, target platforms, verification method,
  provenance, confidence, implementation status and unsupported assumptions.
- All requirements are `not_implemented`, `proposed`, `human_approved: false`.
- The spec validator rejects any attempt to mark a requirement `verified`, pre-approve
  the specification, or mark a plan step `executed`.
- Feasibility is labelled engineering assessment, not a build result.

### 5.3 Quality rubric

Ten fixed categories with explicit methods: completeness, internal consistency, gameplay
clarity, technical feasibility, engine compatibility, performance awareness, asset
specificity, testability, requirement traceability, unsupported-claim avoidance.

Offline results (these are **not** live model quality):

| Input | Score | Grade | Note |
| --- | --- | --- | --- |
| Offline fixture payload | 87.5 / 100 | strong | Testability 7.5; traceability 0 (fixture has no requirement array) |
| Fixture after pipeline attaches requirement IDs | 95.5 / 100 | strong | One consistency penalty from the deterministic design's missing collectible field |
| Deterministic fallback design (no model) | 74.67 / 100 | usable_with_review | Weak testability and gameplay clarity; contradictions surfaced |
| Live provider output | **not measured** | — | three attempts: HTTP 503 or read timeout; no response body |

The rubric is deterministic and never uses one model to judge another. A single response
cannot demonstrate general AI intelligence; the reports say so explicitly.

### 5.4 Phase 3 / 4 / 5 bridges

`reports/v6-phase7-generation-bridge.json`:

- **Character** — reuses `character_spec.build_character_spec`; result passes
  `validate_character_spec` with zero errors; `ai_generated_asset: false`.
- **Environment** — reuses `environment_spec.build_environment_spec`; result passes
  `validate_environment_spec` with zero errors; `ai_generated_asset: false`.
- **Gameplay** — player controls, physics, collectibles, hazards, objectives,
  checkpoints, camera, UI, game states and acceptance tests; inspects the 12 declared
  Phase 5 interfaces read-only (none missing); `generated`, `build_started` and
  `phase5_project_modified` are all `false`.
- Requirement IDs are carried into every bridge.

The fixture spec produced **32 requirements** (9 user requirements, 23 recommendations,
0 blocked, 0 verified, 0 human-approved) with 15/15 coverage items.

### 5.5 Generation plan

Six steps (approve spec → character → environment → integrate → test → build). Every
step is `executed: false`, `requires_approval: true`; the plan is `executable: false`.
Nothing was generated or built.

---

## 6. Network and quota safety

- Readiness and planning report `network_calls: 0`.
- An unapproved execute call returns `BLOCKED_AUTHORIZATION_MISSING` with 0 network calls.
- The audit repeats readiness, planning, spec generation, quality scoring, response
  validation and free routing with `socket.socket.connect` patched to raise; all
  operations complete, proving no hidden network path.
- Quota logic: exhausted → refused; unknown → allowed but explicitly labelled
  `quota_unknown_not_unlimited`.
- One request maximum after approval; zero retries; zero provider fallback; no project
  files or credentials are ever sent.

---

## 7. MCP integration

- Tools: **107**, handlers: **107**, no missing/extra/duplicate entries.
- All schemas are JSON objects with declared properties.
- One existing test assertion (`test_v6_phase2_coordinator.py`) was updated from `101`
  to `107` to reflect the required new tool surface; its uniqueness, set-equality and
  schema checks were **not** weakened.
- No Phase 0–6 tool was removed or renamed.

---

## 8. Testing

| Metric | Value |
| --- | --- |
| Baseline tests (before Phase 7 edits) | 409 |
| New tests | 54 (38 Phase 7 + 16 bounded-timeout) |
| Final tests | **463** |
| Passed | 463 |
| Failed | 0 |
| Skipped | 0 |
| Existing tests changed | 1 registry-count assertion (documented above) |
| Live tests in the default suite | none |
| Environment | Windows, Python 3.12.10 |

Command:

```powershell
python -m unittest discover -s tools/game-studio-mcp/tests -q
```

Coverage includes readiness, paid/unknown refusal, missing credential, quota exhaustion,
request bounds, authorization hash gating, mocked success and mocked provider error,
malformed JSON, schema/type/missing-field errors, contradictions, unsupported claims,
ambiguity, secret redaction, deterministic fallback, provenance, ID stability, bridge
validity, preview-only planning, MCP parity and protected hashes.

The mocked "live" case replaces the adapter; **the suite never opens a socket**.

---

## 9. Independent audit

`python scripts/v6-phase7-audit.py` — report: `reports/v6-phase7-audit.json`.

| # | Criterion | Status |
| --- | --- | --- |
| 1 | Phase 6 baseline preserved | PASS |
| 2 | Existing provider architecture reused | PASS |
| 3 | Free-only policy enforced | PASS |
| 4 | Unknown billing rejected | PASS |
| 5 | No paid fallback | PASS |
| 6 | No secrets exposed | PASS |
| 7 | No unapproved network requests | PASS |
| 8 | Quota controls enforced | PASS |
| 9 | Structured responses validated | PASS |
| 10 | Requirement provenance preserved | PASS |
| 11 | AI quality evaluation present | PASS |
| 12 | Phase 3 bridge valid | PASS |
| 13 | Phase 4 bridge valid | PASS |
| 14 | Phase 5 interfaces preserved | PASS |
| 15 | MCP parity preserved | PASS |
| 16 | Tests pass | PASS |
| 17 | V4 protected artifacts unchanged | PASS |
| 18 | V5 protected artifacts unchanged | PASS |
| 19 | Phase 5 project/build/payload unchanged | PASS |
| 20 | No unauthorized Git operations | PASS |
| 21 | Bounded total request deadline implemented | PASS |

Live-provider criteria are deliberately **not** in the PASS list:

| Criterion | Status | Reason |
| --- | --- | --- |
| Live provider reachability | BLOCKED | one approved request returned HTTP 503 (`unavailable`) |
| Live structured response validity | NOT_TESTED | no response body was produced |
| Live output quality | NOT_TESTED | no response body was produced |
| Human approval of specification | HUMAN_REVIEW_REQUIRED | pending |

---

## 10. Preservation

| Artifact group | Result |
| --- | --- |
| V4 protected files (2) | hashes match Phase 6 evidence |
| V5 protected artifacts (13) | hashes match Phase 6 evidence |
| `validation/unity-jungle-v5/`, `validation/builds/v5-windows/` | no Git-visible changes |
| `validation/unity-jungle-v6/`, `validation/builds/v6-windows/` | no Git-visible changes |
| Phase 5 gameplay interfaces (12 files) | all present, unmodified |
| Accepted phase reports | not modified |

No protected artifact was repaired, regenerated or replaced.

---

## 11. Actual Git status

The repository owner committed the Phase 7 implementation, correction and reports in
three linear external commits on top of the Phase 7 baseline `51342fe`:
`ef8f72f` (initial tools), `b36f066` and `5f2c990` (correction and test-count/documentation
updates). None touches a protected artifact.

At the final audit, uncommitted work exists only in:

- modified: `scripts/v6-phase7-audit.py`, the regenerated `reports/v6-phase7-*.json`
  files, `V6-PHASE-7-REAL-AI-VALIDATION.md`, and the Phase 7 transport surface
  (`game_studio/llm/providers.py`, `game_studio/llm/provider_validation.py`,
  `game_studio/util.py`)
- new: `game_studio/llm/bounded_http.py`, `tests/test_v6_phase7_timeout.py`,
  `reports/v6-phase7-timeout-fix.json`, `reports/v6-phase7-timeout-validation.json`,
  the Phase 7 live-validation reports, and the connectivity diagnostics script,
  report and document

No V4, V5 or Phase 5 artifact is among the changes.

This agent performed **no** commit, push, tag, merge, rebase, reset, clean, stash or
branch change. Audit criterion 20 verifies that `51342fe` is an ancestor of the current
HEAD, that every path changed since the baseline is a Phase 7 path, and that no
`validation/` or accepted phase-report path changed.

Pre-existing user changes were preserved (the tree was clean at baseline).

---

## 11b. Request correction: temperature removed

The accepted offline scope was followed by a controlled correction of the pending live
request, before any authorization was requested.

| Item | Value |
| --- | --- |
| Model ID re-verified | `gemini-3.8-flash` — stable model code on the official model page |
| Model documentation | `https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash` |
| GenerateContent reference | `https://ai.google.dev/api/generate-content` |
| Documented limits | 1,048,576 input tokens / 65,536 output tokens |
| Official statement | `temperature` (and `topP`/`topK`) is "no longer supported and is silently ignored on Gemini 3.6 Flash and newer models" |
| Change | `temperature` is **omitted** from `generationConfig`; no ignored field is sent |
| Preserved | JSON-only contract, `response_mime_type: application/json`, 2,048 max output tokens, one request, zero retries, no fallback, 60 s total deadline |
| Request hash | recalculated from the corrected request: `865fe5ba547ce13cdad50ccd706ef28aca26e213549532b52b9fb501b549c648` |
| Superseded hash | the earlier `08db560c…dd552` request must not be approved |
| Tests | 4 correction tests plus 16 bounded-timeout tests; full suite now 463 |
| Network calls | **0** at correction time; the approved attempts are recorded in §12 |

The Gemini adapter now accepts `temperature: float | None` and only serialises the field
when a value is supplied. Phase 7 always passes `None`, so the live request can never
carry an unsupported sampling field.

---

## 12. Mandatory live-request approval gate

**The exact request was approved and executed once. It failed with HTTP 503 before a response was produced.**

### Exact proposed request

| Field | Value |
| --- | --- |
| Provider | `gemini` (Google Gemini Developer API) |
| Model | `gemini-3.8-flash` |
| Endpoint | `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent` |
| Auth | local `GEMINI_API_KEY` (or the studio's private credential store) — never sent to chat |
| Request hash | `865fe5ba547ce13cdad50ccd706ef28aca26e213549532b52b9fb501b549c648` |
| Input | controlled test idea + system prompt; **1,362 characters total** (idea 301) |
| Max input policy | 4,000 characters |
| Max output tokens | 2,048 |
| Temperature | **omitted** — `generationConfig` contains no `temperature` field |
| Model ID verification | `gemini-3.8-flash` confirmed as the stable model code on the official model page (2026-11-11) |
| Timeout | 60 seconds |
| Retries | **0** |
| Provider fallback | **none** |
| Requests | **exactly 1** |
| JSON mode | enabled; JSON-only response required |
| Project files sent | **no** |
| Repository content sent | **no** |
| Personal data sent | **no** |

Exact user prompt:

```text
Game idea:
Create a polished third-person 3D tropical jungle adventure game for Windows and Android. The player controls a monkey, explores a jungle, collects bananas, avoids environmental hazards, and reaches a final destination. The game should support low-end hardware and use an efficient rendering approach.

Produce the JSON object described in the system instructions. Use short arrays of concise strings. Do not include markdown fences.
```

The system prompt (918 characters) requires exactly one JSON object with the 18 contract
fields and explicitly forbids inventing engine APIs, plugins, features, asset files or
verified functionality. It is recorded verbatim in `reports/v6-phase7-request-audit.json`
and `provider_validation.SYSTEM_PROMPT`.

### Quota impact

- 1 request against the project's Gemini free tier.
- Token estimate: input well under 1,000 tokens; output capped at 2,048.
- Documented daily request limit is **not exposed reliably per project/key**, so remaining
  quota is **unknown**. Unknown is not treated as unlimited.
- RPD resets at midnight Pacific time.
- Estimated cost: **$0.00**; no paid fallback exists.
- If the provider returns 429, the run stops; it does not retry.

### Data handling

- Gemini free-tier content may be used to improve Google products. Only the controlled
  test idea above is sent; no proprietary project content, code, assets or personal data.
- The API key and authorization headers are never stored, logged or returned.

### Expected result

One JSON object matching the Phase 7 contract, validated locally for schema, types,
required fields, contradictions, unsupported claims and ambiguity, then scored with the
deterministic rubric. HTTP success alone will not be treated as design quality.

### On error / rollback

- Provider errors are classified (`auth`, `rate_limit`, `not_found`, `invalid_request`,
  `unavailable`, `timeout`) and returned redacted.
- No retry, no provider switch, no paid upgrade.
- Deterministic fallback is labelled and used; the failed attempt is recorded in the quota
  ledger with `status: error:<kind>`.
- The request writes no files, modifies no project and starts no build.

### Approval and single execution record

The repository owner approved exactly hash
`865fe5ba547ce13cdad50ccd706ef28aca26e213549532b52b9fb501b549c648` and configured the
credential in the studio's private machine-local secrets store (outside the repository;
the value was never printed, returned or written to any report).

One request was then executed. Measured facts:

| Field | Result |
| --- | --- |
| Authorization | approved for the exact hash |
| Requests made | **1** |
| Retries | **0** |
| Provider fallback | **none** (deterministic fallback remains available) |
| HTTP status | **503** |
| Error class | `unavailable` |
| Provider message (redacted) | "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later." |
| JSON extracted | no |
| Schema validated | not reached |
| Usage tokens | unavailable (no successful response) |
| Secrets recorded | no |
| Files/projects modified by the request | none; no project, asset or build change |

Evidence: `reports/v6-phase7-live-validation.json`.

The request hash binds approval to this exact prompt, model, output cap, JSON mode and
zero-retry/zero-fallback configuration. It deliberately does **not** include a temperature:
the Gemini `generateContent` reference states that `temperature` (and `topP`/`topK`) is
"no longer supported and is silently ignored on Gemini 3.6 Flash and newer models", so
Phase 7 omits the field from `generationConfig` entirely. Any change produces a different
hash and is refused.

**Current status:** `LIVE_REQUEST_FAILED`. Three separate approved attempts made exactly one
request each with zero retries: attempt 1 returned HTTP 503 `unavailable`; attempts 2 and 3
ended in a socket read timeout before any response was received. No retry and no provider
fallback was attempted. Any further live attempt needs a new explicit human approval.

Connectivity diagnostics (`V6-PHASE-7-CONNECTIVITY-DIAGNOSTICS.md`) ruled out DNS, TCP, TLS,
proxy and firewall faults. They confirmed that the existing `urllib` timeout was per socket
operation, not a total deadline, and that the advertised 10 s connect timeout and the DNS
lookup were not bounded.

### 12.1 Bounded request deadline (offline fix)

A dedicated bounded transport now executes the Gemini request:

`GeminiProvider.complete` → `providers._request` → `util.http_request` →
`game_studio.llm.bounded_http.request`.

| Property | Implementation |
| --- | --- |
| Total deadline | caller `timeout` (60 s for Phase 7) enforced by a watchdog |
| DNS | daemon worker; the caller stops waiting at the deadline |
| TCP connect | bounded per-address attempts, 10 s stage budget |
| TLS | `CERT_REQUIRED` + hostname check, 10 s stage budget |
| Response headers | 30 s stage budget, capped by remaining deadline |
| Response body | 45 s stage budget, capped by remaining deadline |
| Cancellation | watchdog shuts down and closes the registered socket |
| Retries | 0 |
| Provider fallback | none |
| Dependencies | standard library only |

Distinct structured errors are returned for `dns_timeout`, `dns_failure`, `connection_timeout`,
`connection_failure`, `tls_failure`, `http_response_timeout`, `response_body_timeout`,
`response_body_incomplete`, `deadline_exceeded` and provider HTTP status classes. A partial or
truncated body is never parsed as JSON; it is reported with `partial_response: true` and
`partial_bytes`. Timing fields cover DNS, connect, TLS, send, headers, body and total, and
never include header or credential values.

Evidence: `reports/v6-phase7-timeout-fix.json` and
`reports/v6-phase7-timeout-validation.json`. The offline suite has 463 tests (16 new),
the MCP parity check is 107/107, and the audit passes 21/21 criteria. No live request was
made while implementing or testing this fix.

---

## 13. What remains unverified

- The provider was reachable; the three approved requests failed with HTTP 503 or a read
  timeout before any response body arrived.
- Whether a live model will return the required JSON contract remains unobserved.
- Live output quality on the rubric (no live score exists).
- Actual quota remaining and the account's exact free-tier limits.
- Android build viability, low-end performance targets, and any runtime measurement.
- Actual character/environment asset generation, scene integration and playability.
- Whether an approved specification can be delivered without human design changes.

A successful API request would still not prove high-quality game generation. A valid
specification is not a playable game.

---

## 14. Exact human decisions required next

1. **Decide whether to authorize one new attempt** for the same request hash
   `865fe5ba547ce13cdad50ccd706ef28aca26e213549532b52b9fb501b549c648`; the previous
   attempts failed with HTTP 503 and read timeouts and made no retry. The bounded
   deadline fix is implemented and tested offline but has not been exercised live.
2. **Rotate the API key** that was pasted into chat, then store the replacement locally.
3. **Review the specification**: 32 proposed requirements, their priorities, the
   deterministic design's flagged contradictions, and any ambiguous acceptance criteria.
4. **Decide whether Phase 8 may begin** (asset generation / integration / build). Phase 7
   stops here regardless.

---

## 15. Honest status summary

| Statement | Truth |
| --- | --- |
| Offline Phase 7 implementation complete | **yes** |
| Automated audit 21/21 | **yes** |
| Tests 463/463 with parity 107/107 | **yes** |
| Live request authorized | **yes** — exact hash approved |
| Live provider request succeeded | **no** — HTTP 503 and read timeouts |
| Real AI output validated | **no** — no response body |
| Real AI output judged useful | **no** — unmeasured |
| Specifications bridged to Phase 3/4/5 | **yes, specification-only** |
| Assets generated | **no** |
| Phase 5 Unity project modified | **no** |
| Build started | **no** |
| Human-approved specification | **no** — pending |

Verdict: **PASS_AUTOMATED** for the implemented and tested offline scope, including the
bounded total-deadline fix; **LIVE_REQUEST_FAILED** for all three authorized live attempts;
**HUMAN_REVIEW_REQUIRED** for the specification and the next phase.
