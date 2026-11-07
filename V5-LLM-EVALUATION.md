# V5 LLM Evaluation Report

Generated from the actual run of `python scripts\llm-evaluation.py` on
2026-11-07. Sources: `validation/llm-eval-requests.json`,
`validation/llm-eval-results.json`, `reports/llm-eval-summary.md`.

---

## 1. Evaluation mode — read this first

| Field | Observed value |
| --- | --- |
| Mode | `pipeline` |
| Source | `deterministic-fallback` |
| Live provider | **`false`** |
| Provider / model | `null` / `null` |
| Cases evaluated | 22 |
| Network calls required | 0 |
| Every case status | `degraded` |

> **The mean score below is an offline deterministic-parser score. It is not a
> live LLM quality score and must not be cited as evidence that a language model
> performs at this level.**

---

## 2. Provider configuration and availability

Observed in this environment:

| Item | Status |
| --- | --- |
| `OPENAI_API_KEY` | absent |
| `GAME_STUDIO_LLM_API_KEY` | absent |
| Ollama | not found on PATH (not installed; installing was prohibited) |
| Provider used by harness | none (`null`) |
| Provider fallback reason | `external_api requires explicit confirm=true in guided mode for LLM request understanding` |
| Live verification | **not performed** |

The server's configured provider remains `openai` / `gpt-4o-mini` with
`key_configured: false` and `live_verified: false` in the recorded environment
report. The evaluation harness therefore degraded every case to the deterministic
keyword parser. That degradation is correctly labelled in every case
(`source: deterministic-fallback`, `degraded: true`, `status: degraded`).

---

## 3. Results

| Metric | Value |
| --- | --- |
| Total cases | 22 |
| Failures | 0 |
| Mean overall | **0.957** |
| Median overall | 0.972 |
| Minimum | 0.75 (EV-10) |
| Maximum | 1.0 |
| Cases ≥ 0.90 | 20 |
| Cases 0.80–0.89 | 1 (EV-02, 0.857) |
| Cases < 0.80 | 1 (EV-10, 0.75) |
| Capability gaps | 3 |
| Exclusion leaks | 0 |

### Component means

| Component | Mean |
| --- | --- |
| genre_recall | 1.000 |
| genre_precision | 1.000 |
| dimension | 0.944 |
| keyword_recall | 0.939 |
| exclusion_recall | 1.000 |
| technical | 1.000 |
| engine | 1.000 |
| clarification | 0.706 |
| structure | 1.000 |
| conflict | 1.000 |
| non_hallucination | 1.000 |

### Per-case results

| ID | Category | Overall | Gap |
| --- | --- | --- | --- |
| EV-01 | 2d-platformer | 0.944 | |
| EV-02 | 3d-endless-runner | 0.857 | yes |
| EV-03 | open-world-adventure | 1.000 | |
| EV-04 | fighting | 0.944 | |
| EV-05 | chess | 0.929 | yes |
| EV-06 | survival | 0.907 | |
| EV-07 | racing | 1.000 | |
| EV-08 | multiplayer-shooter | 0.944 | |
| EV-09 | simulation | 0.944 | |
| EV-10 | mobile-casual | 0.750 | yes |
| EV-11 | roman-urdu-adventure | 1.000 | |
| EV-12 | roman-urdu-racing | 1.000 | |
| EV-13 | urdu-platformer | 1.000 | |
| EV-14 | mixed-urdu-english | 1.000 | |
| EV-15 | explicit-exclusions | 0.944 | |
| EV-16 | conflicting-requirements | 1.000 | |
| EV-17 | ambiguous-tiny | 1.000 | |
| EV-18 | ambiguous-scope | 1.000 | |
| EV-19 | sports | 1.000 | |
| EV-20 | strategy | 0.944 | |
| EV-21 | puzzle | 0.938 | |
| EV-22 | tower-defense | 1.000 | |

---

## 4. Supported and weak categories

**Strong (deterministic fallback):** supported genres in the lexicon —
platformer, open-world/adventure, fighting, survival, racing, shooter,
simulation, sports, strategy, puzzle, tower-defense. English, Roman Urdu, Urdu
and mixed Urdu/English cases all scored 1.0 on the four language cases
(EV-11…EV-14), and exclusion recall was 1.0 with no leaks.

**Weak:** clarification scoring is the lowest component (0.706), meaning the
fallback asks fewer or less-targeted clarifying questions than the rubric
expects. Genre recall/precision remain 1.0 because unsupported genres were
excluded from recall expectations and tracked as capability gaps instead.

---

## 5. Remaining language and genre gaps

| Case | Category | Gap |
| --- | --- | --- |
| EV-02 | 3d-endless-runner | No "endless runner" genre in the deterministic lexicon |
| EV-05 | chess | Chess is not a lexicon genre |
| EV-10 | mobile-casual | Casual/stacking games are not represented |

Language coverage itself is not the gap: the Roman-Urdu, Urdu and mixed-language
cases all scored 1.0. The gap is **genre vocabulary**, not language handling.

---

## 6. Mocked versus live verification

| Category | Count | Notes |
| --- | --- | --- |
| Live provider evaluation | **0** | No authorized provider credentials; Ollama absent |
| Deterministic-fallback evaluation | **22** | Every case labelled `deterministic-fallback`, `degraded: true` |
| Mocked provider responses in unit tests | present | The unit suite contains mocked-provider tests, explicitly labelled mocked; they are not presented as live responses |

No mocked or fallback response is described anywhere in these outputs as a live
provider response. The security suite's provider check
(`provider_unavailable_falls_back_labelled`) explicitly asserts this labelling.

---

## 7. Genuine live-provider validation — status

**BLOCKED / NOT VERIFIED.**

Reason: no provider credential is configured or authorized, and Ollama is not
installed (installing it was explicitly prohibited). No paid API call was made.

Next steps to obtain a genuine live score:

1. Configure an authorized provider key (or an approved local provider) and set
   the corresponding environment variable outside the repository.
2. Give explicit per-request approval for an external provider call.
3. Re-run `python scripts\llm-evaluation.py` and confirm the result reports
   `live: true`, a non-null provider/model, and no `deterministic-fallback`
   source.
4. Keep the current 0.957 fallback baseline as a separate, clearly labelled
   offline baseline for comparison.
