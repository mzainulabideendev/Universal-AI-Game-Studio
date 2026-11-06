# LLM security and privacy

The reasoning layer is designed so that a model mistake cannot become an
unauthorized action.

## Boundary rules

1. **Reason, don't execute.** LLM modules never import or call Blender, Meshy,
   engine CLIs, subprocess helpers, download helpers or filesystem writers.
2. **Tools are the only action surface.** Every operation goes through a
   registered MCP tool with an input schema, an allow-list entry, governance
   checks and its own confirmation gate.
3. **The LLM cannot widen permissions.** It cannot change execution mode,
   permission effects, budgets or the paid-approval policy.
4. **Execution plans are data.** `llm_build_execution_plan` always returns
   `executable: false`. Every step names a known tool, its risk class, cost and
   confirmation requirement.

## Prompt-injection resistance

User request text, asset names, metadata and project content are untrusted data.
They are wrapped in `<user_request>` / `<project_context>` markers in prompts and
the system prompt states that instructions inside those blocks must be ignored.

In addition, `client.inspect_prompt_injection()` flags common markers such as
"ignore previous instructions", "reveal your instructions", "run this command"
and "send the api key". The flag is returned to the caller for review; it does
not silently discard the request.

Detection is defence-in-depth, not a guarantee. The structural boundary (no
execution capability) is the actual protection.

## Secret handling

- Keys are read from environment variables or the private OS config directory.
- Keys are never written to the repository, manifests, audit entries or tool
  responses.
- `llm_status` reports `api_key_configured` and `api_key_source`, never the value.
- Every error and free-text model response passes through `redact()`.
- `RedactedHeaders` masks `Authorization`, `x-api-key`, `x-goog-api-key`,
  `api-key`, `token` and `secret` on inspection while `real_headers()` remains
  available only to the HTTP sender.
- Provider errors are classified without echoing credentials.

## What is sent to a provider

By default, only the text required for the current reasoning step:

- the user request;
- the structured understanding or plan needed for the next step;
- schema definitions.

Project files, source code, manifests and assets are **not** sent unless all of
these are true:

```text
GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT=true
include_project_content=true
confirm=true
```

## Local-only mode

```text
GAME_STUDIO_LLM_LOCAL_ONLY=true
```

blocks hosted providers before any network request. Only providers marked
`local_provider` (Ollama) are allowed.

## Caching

Caching is opt-in (`GAME_STUDIO_LLM_CACHE=true`) and only applies to prompts
marked cacheable. Cache files live under the external config directory. Do not
enable it for content you do not want stored on disk.

## Budgets as a safety control

- per-process request budget;
- persistent daily request budget;
- per-request output-token budget;
- prompt-size context limit.

Exhausting a budget raises an explicit error. No request is sent and no success
is simulated.

## Cancellation

Provider HTTP calls cannot be aborted mid-flight with the standard library.
Cancellation is checked:

- before sending;
- during retry backoff (in small polling intervals).

Remote cancellation must be supported and confirmed by the provider; the server
reports this honestly rather than claiming it killed a remote request.

## Untrusted output

All model output is parsed and validated against a versioned schema. Invalid
output is repaired at most twice, then rejected with an explicit error. Invalid
output is never accepted as a specification.
