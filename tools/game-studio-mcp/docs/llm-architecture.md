# LLM reasoning architecture

Universal AI Game Studio separates **reasoning** from **execution**.

```text
User's natural language (English · Urdu · Roman Urdu · mixed)
        |
        v
LLM reasoning layer  (game_studio/llm/*)
  understand · analyse ambiguity · reason about engine · architecture
  · review · validate · trace · plan
        |
        v
Deterministic core  (understanding.py · specification.py · manifest.py)
  classification · dependency graph · milestones · requirements · evidence
        |
        v
Governance + approval layer  (governance.py)
  execution modes · permissions · confirm gates · paid approval
        |
        v
MCP tools  (server.py)
  Blender · Meshy · assets · animation · Unity · Unreal · Godot
        |
        v
Real operations + evidence  (verification.py)
```

## Hard boundary

The LLM **cannot**:

- run shell commands, scripts or arbitrary filesystem operations;
- download assets or spend credits;
- edit project files;
- mark a requirement implemented, tested or verified;
- grant itself permissions or change execution mode.

The LLM **can**:

- understand free-form requests and preserve the user's wording;
- classify requirements (explicit, implied, technical, optional, unresolved,
  conflict, excluded);
- identify technical dependencies and risks;
- recommend an engine and explain the trade-offs;
- draft a structured specification and architecture;
- ask at most five material clarification questions;
- propose an implementation roadmap.

Every execution still goes through an MCP tool, its allow-list, the governance
policy and its own `confirm` gate.

## Modules

| Module | Responsibility | Executes anything? |
| --- | --- | --- |
| `llm/config.py` | provider/model/timeout/budget/privacy configuration, secret redaction | no |
| `llm/providers.py` | OpenAI, OpenAI-compatible, Anthropic, Gemini, Ollama adapters | HTTP provider calls only |
| `llm/client.py` | budgets, retries, rate-limit handling, cancellation checks, context limit, schema validation/repair, optional cache | provider HTTP only |
| `llm/schemas.py` | versioned JSON schemas and a dependency-free validator | no |
| `llm/reasoning.py` | understanding, ambiguity, engine reasoning, architecture, review, validation, provider verification | no |
| `llm/traceability.py` | requirement → specification → manifest trace map | no |
| `llm/planning.py` | deterministic mapping from a specification to governed MCP tool steps | no |
| `llm/director.py` | AI Game Director entry point | no |

## Two operating modes

**New project mode.** The LLM understands the request, extracts classified
requirements, recommends an engine, drafts a specification, and produces a
dependency graph and milestones. The deterministic builder owns the structural
parts so a malformed model response cannot corrupt them.

**Existing project mode.** The Game Director inspects the real project and
manifest (via `inspect_game_project` and `track_progress`) and grounds its
roadmap in that evidence. Sending project content to a provider requires
`GAME_STUDIO_LLM_ALLOW_PROJECT_CONTENT=true` **and** `include_project_content=true`
**and** `confirm=true`.

## Fallback

If no provider is configured, the user has not approved an external request, the
provider fails, output cannot be repaired, or the context limit is exceeded, the
deterministic parser (`understanding.py`) is used. The response always says:

```json
{
  "source": "deterministic-fallback",
  "degraded": true,
  "fallback_reason": "..."
}
```

The fallback is not presented as LLM understanding. It is keyword/heuristic based
and may miss nuance.

## Deterministic vs model-owned fields

| Field | Owner | Reason |
| --- | --- | --- |
| requirement classification & ids | LLM or deterministic parser | reasoning |
| dependency graph | `specification.py` | must stay valid |
| milestones A–G | `specification.py` | stable gates |
| acceptance tests | `specification.py` | stable evidence target |
| engine selection record | `specification.py` (LLM may recommend) | needs detection |
| overview / risks / narrative | LLM (advisory) | reasoning |
| execution steps | `planning.py` | safety |
| requirement status | `verification.py` only | evidence |

## Trust model

Every LLM response distinguishes:

- **verified facts** — e.g. "the original request text is reproduced verbatim";
- **model assumptions** — labelled as assumptions, never approved requirements;
- **unverified claims** — all technical recommendations until a tool and a test
  confirm them.

A generated plan is never evidence of implementation.
