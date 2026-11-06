# LLM testing guide

## Principles

- The default suite is offline: no network, paid API, engine, Blender or key.
- Provider calls in unit tests use in-process mocked providers and are labelled
  as mocked.
- A mocked test proves the integration logic, not the provider or model quality.
- Live verification is never claimed unless a real provider request succeeded.
- No test requires a paid service.

## Commands

```powershell
python -m compileall -q .\tools\game-studio-mcp

# whole suite
python -m unittest discover -s .\tools\game-studio-mcp\tests -v

# reasoning layer only
python -m unittest .\tools\game-studio-mcp\tests\test_llm_v4.py -v

# offline end-to-end demonstration
python .\scripts\llm-demo.py --json

# mocked LLM path demonstration (labelled mocked)
python .\scripts\llm-demo.py --mock-llm --json

# real provider connectivity, explicit approval required
$env:GAME_STUDIO_LLM_PROVIDER = "ollama"
python .\scripts\llm-demo.py --live --confirm --json
```

## Coverage map

| Requirement | Test |
| --- | --- |
| English description | `test_english_request_extracts_core_requirements` |
| Roman Urdu | `test_roman_urdu_request_is_understood` |
| Urdu | `test_urdu_request_is_understood` |
| Mixed language | `test_mixed_language_request` |
| Complex multi-feature | `test_complex_multi_feature_request_has_technical_dependencies` |
| Conflicting requirements | `test_conflicting_requirements_are_surfaced_not_silently_resolved` |
| Explicit exclusions | `test_exclusions_never_become_explicit_requirements` |
| Ambiguous request | `test_ambiguous_request_produces_material_questions` |
| Unrealistic technical request | `test_engine_reasoning_never_claims_installation` + engine fallback |
| Invalid LLM response | `test_invalid_json_is_repaired_within_bound` |
| Malformed structured output | `test_malformed_output_is_never_accepted` |
| Provider timeout | `test_provider_timeout_falls_back_and_is_labelled` |
| Rate limiting | `test_rate_limit_is_retried` |
| Provider unavailable | `test_unavailable_provider_fails_loudly` |
| Missing API key | `test_missing_api_key_refuses_before_sending` |
| Fallback parser | `test_ambiguity_falls_back_without_provider` |
| Prompt injection | `test_prompt_injection_markers_are_flagged` |
| Secret redaction | `test_secret_redaction_removes_keys_and_bearer_tokens` |
| Context overflow | `test_context_overflow_is_refused_before_request` |
| Cancellation | `test_pre_cancelled_operation_stops_before_sending` |
| Requirement traceability | `TraceabilityTests` |
| Manifest persistence | `test_requirements_map_to_specification_and_manifest` |
| Provider wire formats | `ProviderAdapterTests` |
| Execution-plan safety | `ExecutionPlanTests` |
| End-to-end pipeline | `EndToEndMockedPipelineTests` |

## What is not tested here

- Live provider quality or latency (requires credentials/local model).
- Paid Meshy generation (requires credits).
- Engine builds and playtests (require installs and a device).
- Real asset imports and animation playback.

These are reported as unverified until actually run.
