# LLM limitations and provider compatibility

## Compatibility matrix

| Capability | OpenAI | OpenAI-compatible | Anthropic | Gemini | Ollama |
| --- | --- | --- | --- | --- | --- |
| Chat completion | yes | yes (server-dependent) | yes | yes | yes |
| JSON mode | `response_format` | server-dependent | prompt/schema only | `responseMimeType` | `format=json` |
| System prompt | message | message | top-level `system` | `systemInstruction` | message |
| Token usage returned | usually | usually | yes | yes | yes |
| Streaming | not used | not used | not used | not used | not used |
| Tool/function calling | not used | not used | not used | not used | not used |
| Live-verified in this repo | no | no | no | no | no |

`implemented` means the adapter code exists and its wire format is covered by
mocked tests. `live-verified` means a real request succeeded; none is claimed in
this repository because no credential or local model was available during the
build.

## Known limitations

### Reasoning

- LLM output quality depends on the model. Small models may miss nuance, produce
  weaker architectures, or need more repair attempts.
- The deterministic fallback is keyword/heuristic based. Urdu and Roman Urdu
  coverage is broad but not a translator; metaphors, rare dialects and unusual
  vocabulary may require clarification.
- The LLM does not have access to private engine APIs or undocumented features.
  It must not be trusted to invent engine capabilities.
- Architecture and risk reports are proposals, not validated designs.

### Execution boundary

- The LLM cannot execute, download, install or edit anything. This is deliberate.
- Execution plans are abstract: they name tools, not concrete arguments. The
  client/user must supply project paths, asset ids and confirmations.
- There is no automatic retry of failed MCP operations by the LLM.

### Provider transport

- HTTP requests use Python's standard library. A request cannot be aborted
  mid-flight; cancellation is honoured before sending and during retry backoff.
- Streaming responses are not consumed.
- Provider-specific retry headers (`Retry-After`) are not parsed; a conservative
  backoff is used instead.
- Large context windows depend on the model and provider; the local character
  limit is an approximation, not a tokenizer.

### Cost

- Token counts come from provider usage fields when present. Cached responses
  report no usage. Budgets count requests, not currency.
- Price estimation is not implemented; consult the provider's pricing.
- Paid Meshy operations are marked but never auto-approved.

### Verification

- A successful `llm_test_provider` proves reachability only.
- Requirement traceability proves mapping, not implementation.
- Requirement status changes only with recorded evidence.
- No game, build, import, animation playback or playtest is claimed by the
  reasoning layer.

## Roadmap

1. Live verification against at least one hosted provider and Ollama.
2. Tokenizer-aware context budgeting per model.
3. Optional `Retry-After` parsing.
4. Streaming for long architecture plans.
5. Richer engine capability grounding from `inspect_engine_capabilities` (still
   without letting the model execute).
6. Evaluation harness with golden multilingual requests and scored plans.
7. Human-reviewed prompt/version registry for reproducible planning.
