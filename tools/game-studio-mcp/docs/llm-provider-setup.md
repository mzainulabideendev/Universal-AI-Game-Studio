# LLM provider setup

No provider is contacted unless it is configured, permitted by policy, and the
call passes `confirm=true`. A provider being configured is never reported as
working; `llm_status` reports `configured` and `live_verified: null` until a real
verification request succeeds.

## Supported providers

| Provider id | API shape | Credential | Local? | Adapter status |
| --- | --- | --- | --- | --- |
| `openai` | `POST /chat/completions` | `OPENAI_API_KEY` or `GAME_STUDIO_LLM_API_KEY` | no | implemented, wire-format tested, live unverified |
| `openai_compatible` | `POST /chat/completions` | `GAME_STUDIO_LLM_API_KEY` | depends on endpoint | implemented, wire-format tested |
| `anthropic` | `POST /messages` | `ANTHROPIC_API_KEY` or shared key | no | implemented, wire-format tested, live unverified |
| `gemini` | `POST /models/<model>:generateContent` | `GEMINI_API_KEY` or shared key | no | implemented, wire-format tested, live unverified |
| `ollama` | `POST /api/chat` on loopback | none | yes | implemented, wire-format tested, live requires a running Ollama |

`openai_compatible` covers LM Studio, vLLM, llama.cpp servers, Together,
Groq, OpenRouter and similar endpoints that implement the OpenAI chat API.

## Configuration

Configuration resolves in this order (first non-empty wins):

1. environment variables;
2. `%APPDATA%\UniversalAIGameStudio\llm.json` (or the platform equivalent);
3. built-in defaults.

Recommended environment variables:

```text
GAME_STUDIO_LLM_PROVIDER=ollama
GAME_STUDIO_LLM_MODEL=llama3.1
GAME_STUDIO_LLM_BASE_URL=http://127.0.0.1:11434
```

Hosted example:

```text
GAME_STUDIO_LLM_PROVIDER=openai
GAME_STUDIO_LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=...            # never commit
```

Never put a real key in the repository. Copy
[`llm.env.example`](llm.env.example) and load it from your shell or MCP client
environment. `.env` files are not read automatically.

## Optional local model

```powershell
ollama pull llama3.1
ollama serve
$env:GAME_STUDIO_LLM_PROVIDER = "ollama"
$env:GAME_STUDIO_LLM_MODEL = "llama3.1"
```

Then call `llm_test_provider` with `confirm=true`. It sends one tiny request and
reports reachability only.

## Budgets and timeouts

| Variable | Default | Effect |
| --- | --- | --- |
| `GAME_STUDIO_LLM_TIMEOUT` | `60` | per-request timeout (seconds) |
| `GAME_STUDIO_LLM_CONNECT_TIMEOUT` | `10` | connection timeout |
| `GAME_STUDIO_LLM_MAX_TOKENS` | `4096` | max output tokens per request |
| `GAME_STUDIO_LLM_MAX_CONTEXT_CHARS` | `64000` | prompt size limit; oversized prompts are refused before sending |
| `GAME_STUDIO_LLM_MAX_REQUESTS` | `20` | per-process request budget |
| `GAME_STUDIO_LLM_MAX_REQUESTS_PER_DAY` | `200` | persistent daily budget |
| `GAME_STUDIO_LLM_RETRIES` | `2` | bounded exponential-backoff retries |
| `GAME_STUDIO_LLM_BACKOFF` | `1.5` | base backoff seconds |

Rate-limit responses (HTTP 429) get a longer backoff and are retried within the
same bound. Authentication errors are not retried.

## Privacy modes

```text
GAME_STUDIO_LLM_LOCAL_ONLY=true
```

refuses every hosted provider. This is checked before any request is sent.

```text
GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT=false   # default
```

means project code and structure are never sent automatically. The Game Director
requires both the flag and an explicit `include_project_content=true`.

## Paid usage

A configured provider can incur cost. The server never sends a request merely
because a key exists: every `llm_*` tool requires `confirm=true`. MCP tool steps
that spend credits (Meshy) are marked `requires_paid_approval` and
`allowed_by_default: false` in execution plans.

## Caching

`GAME_STUDIO_LLM_CACHE=true` enables a local cache for prompts explicitly marked
cacheable. Cached entries live under the external config directory, not the
repository, and contain no credentials. Disable the cache for sensitive content.
