# LLM troubleshooting

## The server falls back even though a provider is configured

Check, in order:

1. `llm_status` → is `api_key_configured` true?
2. `GAME_STUDIO_LLM_LOCAL_ONLY=true` and the provider is hosted? Hosted is
   refused by design.
3. Did the tool call include `confirm=true`?
4. Is the provider id one of `openai`, `openai_compatible`, `anthropic`,
   `gemini`, `ollama`?
5. Read `fallback_reason` in the response: it carries the redacted error kind.

## `missing API key`

Set the provider-specific variable or `GAME_STUDIO_LLM_API_KEY`. The key is never
returned by any tool. For Ollama no key is required.

## `authentication failed`

The key was rejected (HTTP 401/403). This error is not retried. Verify the key in
the provider dashboard, then call `llm_test_provider` with `confirm=true`.

## `rate limited`

HTTP 429 is retried with a longer backoff, bounded by `GAME_STUDIO_LLM_RETRIES`.
If it still fails, wait or raise the budget deliberately. Do not loop
aggressively; it may extend the limit.

## `provider unavailable` / `timeout`

The endpoint is unreachable or too slow. Check `base_url`, DNS/proxy, and whether
a local server is running (`ollama serve`). Increase `GAME_STUDIO_LLM_TIMEOUT` if
the model is slow. Timeouts are retryable within the bound.

## `context_overflow`

The prompt exceeded `GAME_STUDIO_LLM_MAX_CONTEXT_CHARS` (default 64,000). Shorten
the request or project context. Raising the limit increases cost and may exceed
the model's real context window.

## `invalid_output`

The model did not return valid JSON matching the schema after two repair
attempts. Try a stronger instruction-following model, lower temperature, or a
larger output budget. Invalid output is never accepted.

## `model or endpoint not found`

Check the model id and base URL. For Gemini the model is placed in the URL path;
for OpenAI-compatible servers it must match the server's configured model name.

## Local-only mode refuses my provider

That is intended. Use Ollama, or disable `GAME_STUDIO_LLM_LOCAL_ONLY` only after
deciding that external content sharing is acceptable.

## Project content is refused

The Game Director requires all three:

```text
GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT=true
include_project_content=true
confirm=true
```

## Schema validation errors during development

Run the focused tests:

```powershell
python -m unittest .\tools\game-studio-mcp\tests\test_llm_v4.py -v
```

Use `schemas.validate(value, schema)` to see exact paths such as
`$.requirements[0].classification`.

## A plan was produced but nothing was built

Correct. The reasoning layer only plans. `llm_build_execution_plan` returns
`executable: false`. Execute the steps through MCP tools, each with its own
permission and confirmation gate, and record evidence. A plan is not a game.

## Secrets appear in a provider error

They should not: errors pass through `redact()`. If you see a credential, treat
it as a bug: rotate the key, then report the exact tool and message (without the
secret) so the redaction pattern can be extended.
