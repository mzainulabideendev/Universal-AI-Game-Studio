"""Governed LLM client: budgets, retries, cancellation, schema repair, caching.

The client is the only place that talks to a provider. It does not import any
execution module and it never runs commands, edits files or downloads assets.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

from .. import operations
from ..util import read_json, write_json
from . import config as llm_config
from .providers import ProviderError, build

MAX_REPAIR_ATTEMPTS = 2
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions", "ignore all previous", "system prompt",
    "disregard the above", "you are now", "reveal your instructions",
    "run this command", "delete all files", "send the api key",
    "print your system", "execute the following shell",
)


class LLMError(Exception):
    def __init__(self, message: str, *, kind: str = "llm-error", retryable: bool = False,
                 details: dict | None = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.details = details or {}


def prompt_size(system: str, messages: list[dict]) -> int:
    """Approximate prompt size in characters (provider-agnostic budget unit)."""
    total = len(system or "")
    for message in messages or []:
        total += len(str(message.get("content") or ""))
        total += 16  # role/formatting overhead
    return total


def _check_context(cfg: dict, system: str, messages: list[dict]) -> None:
    size = prompt_size(system, messages)
    if size > cfg["max_context_chars"]:
        raise LLMError(
            f"prompt is {size} characters, above the configured context limit of "
            f"{cfg['max_context_chars']}; shorten the request or raise "
            "GAME_STUDIO_LLM_MAX_CONTEXT_CHARS deliberately",
            kind="context_overflow",
            details={"prompt_chars": size, "limit": cfg["max_context_chars"]},
        )


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_budget() -> dict:
    path = llm_config.budget_path()
    data = {"date": _today(), "requests": 0, "tokens": 0, "last_request_at": None}
    if os.path.isfile(path):
        try:
            loaded = read_json(path)
            if isinstance(loaded, dict) and loaded.get("date") == _today():
                data.update(loaded)
        except (OSError, ValueError):
            pass
    return data


def _save_budget(data: dict) -> None:
    data["date"] = _today()
    try:
        write_json(llm_config.budget_path(), data)
    except OSError:
        pass


def budget_status() -> dict:
    cfg = llm_config.load_config()
    data = _read_budget()
    return {
        "date": data["date"],
        "requests_today": data.get("requests", 0),
        "tokens_today": data.get("tokens", 0),
        "max_requests_per_day": cfg["max_requests_per_day"],
        "remaining_today": max(0, cfg["max_requests_per_day"] - data.get("requests", 0)),
        "last_request_at": data.get("last_request_at"),
    }


def _cache_key(cfg: dict, system: str, messages: list[dict], task: str) -> str:
    digest = hashlib.sha256()
    digest.update(cfg["provider"].encode())
    digest.update(cfg["model"].encode())
    digest.update(task.encode())
    digest.update((system or "").encode())
    digest.update(json.dumps(messages, sort_keys=True, default=str).encode())
    return digest.hexdigest()


def _cache_get(key: str) -> dict | None:
    path = os.path.join(llm_config.cache_path(), key + ".json")
    if not os.path.isfile(path):
        return None
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return None
    if isinstance(payload, dict) and payload.get("value"):
        return payload
    return None


def _cache_put(key: str, value: dict, task: str) -> None:
    try:
        os.makedirs(llm_config.cache_path(), exist_ok=True)
        write_json(os.path.join(llm_config.cache_path(), key + ".json"), {
            "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "task": task,
            "value": value,
        })
    except OSError:
        pass


def inspect_prompt_injection(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [marker for marker in PROMPT_INJECTION_MARKERS if marker in lowered]


class LLMClient:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or llm_config.load_config()
        self.provider = build(self.cfg)
        self.session_requests = 0

    # -- budget -----------------------------------------------------------
    def _check_budget(self) -> None:
        cfg = self.cfg
        if cfg["max_requests"] and self.session_requests >= cfg["max_requests"]:
            raise LLMError(
                f"session request budget exhausted ({cfg['max_requests']}); "
                "raise GAME_STUDIO_LLM_MAX_REQUESTS only after reviewing cost",
                kind="budget")
        if cfg["max_requests_per_day"]:
            used = _read_budget().get("requests", 0)
            if used >= cfg["max_requests_per_day"]:
                raise LLMError(
                    f"daily request budget exhausted ({cfg['max_requests_per_day']}); "
                    "no request was sent", kind="budget")

    def _record_request(self, usage: dict | None) -> None:
        self.session_requests += 1
        data = _read_budget()
        data["requests"] = int(data.get("requests", 0)) + 1
        tokens = (usage or {}).get("total_tokens")
        if isinstance(tokens, (int, float)):
            data["tokens"] = int(data.get("tokens", 0)) + int(tokens)
        data["last_request_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        _save_budget(data)

    # -- completion -------------------------------------------------------
    def _call(self, *, system: str, messages: list[dict], max_tokens: int,
              temperature: float, operation_id: str | None) -> dict:
        cfg = self.cfg
        attempt = 0
        last_error: ProviderError | None = None
        while attempt <= cfg["retries"]:
            attempt += 1
            if operation_id and operations.is_cancel_requested(operation_id):
                raise LLMError("LLM request cancelled before sending", kind="cancelled")
            self._check_budget()
            try:
                result = self.provider.complete(
                    messages, system=system, max_tokens=max_tokens,
                    temperature=temperature, json_mode=True,
                    timeout=cfg["timeout_seconds"],
                )
                self._record_request(result.get("usage"))
                return result
            except ProviderError as exc:
                last_error = exc
                if not exc.retryable or attempt > cfg["retries"]:
                    break
                delay = cfg["backoff_seconds"] * (2 ** (attempt - 1))
                if exc.kind == "rate_limit":
                    delay = max(delay, 5.0 * attempt)
                if operation_id:
                    waited = 0.0
                    while waited < delay:
                        if operations.is_cancel_requested(operation_id):
                            raise LLMError("LLM request cancelled during retry backoff",
                                           kind="cancelled")
                        time.sleep(min(0.2, delay - waited))
                        waited += 0.2
                else:
                    time.sleep(delay)
        assert last_error is not None
        raise LLMError(
            llm_config.redact(str(last_error)),
            kind=last_error.kind, retryable=last_error.retryable,
            details={"provider": cfg["provider"], "model": cfg["model"],
                     "attempts": attempt},
        )

    def complete_json(self, *, task: str, system: str, user: str,
                      schema: dict, max_tokens: int | None = None,
                      temperature: float | None = None,
                      operation_id: str | None = None,
                      cacheable: bool = False,
                      redact_user_content: bool = True) -> dict:
        """Request JSON, validate it, and repair a bounded number of times."""
        from . import schemas

        cfg = self.cfg
        allowed, reason = llm_config.provider_allowed(cfg)
        if not allowed:
            raise LLMError(reason or "provider is not available", kind="config")

        messages = [{"role": "user", "content": user}]
        _check_context(cfg, system, messages)
        key = _cache_key(cfg, system, messages, task)
        if cfg["cache_enabled"] and cacheable:
            cached = _cache_get(key)
            if cached:
                return {
                    "ok": True,
                    "data": cached["value"],
                    "source": "cache",
                    "cached_at": cached.get("cached_at"),
                    "usage": None,
                    "repairs": 0,
                }

        budget = max_tokens or cfg["max_tokens"]
        temperature = cfg["temperature"] if temperature is None else temperature
        repairs = 0
        last_errors: list[str] = []
        while repairs <= MAX_REPAIR_ATTEMPTS:
            _check_context(cfg, system, messages)
            result = self._call(system=system, messages=messages,
                                max_tokens=budget, temperature=temperature,
                                operation_id=operation_id)
            text = result.get("text") or ""
            try:
                data = schemas.parse_json(text)
                errors = schemas.validate(data, schema)
            except (ValueError, json.JSONDecodeError) as exc:
                data = None
                errors = [f"invalid JSON: {exc}"]
            if not errors:
                if cfg["cache_enabled"] and cacheable:
                    _cache_put(key, data, task)
                return {
                    "ok": True,
                    "data": data,
                    "source": "provider",
                    "model": result.get("model"),
                    "usage": result.get("usage"),
                    "repairs": repairs,
                    "provider": cfg["provider"],
                }
            last_errors = errors[:20]
            repairs += 1
            if repairs > MAX_REPAIR_ATTEMPTS:
                break
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": text[:12000]},
                {"role": "user", "content": (
                    "Your previous response failed schema validation. Return ONLY a "
                    "corrected JSON object. Errors:\n- " + "\n- ".join(last_errors))},
            ]
        raise LLMError(
            "model output failed schema validation after bounded repair attempts; "
            "invalid output was not accepted",
            kind="invalid_output",
            details={"errors": last_errors,
                     "provider": cfg["provider"], "model": cfg["model"]},
        )

    def complete_text(self, *, system: str, user: str, max_tokens: int | None = None,
                      temperature: float | None = None,
                      operation_id: str | None = None) -> dict:
        allowed, reason = llm_config.provider_allowed(self.cfg)
        if not allowed:
            raise LLMError(reason or "provider is not available", kind="config")
        _check_context(self.cfg, system, [{"role": "user", "content": user}])
        result = self._call(system=system, messages=[{"role": "user", "content": user}],
                            max_tokens=max_tokens or self.cfg["max_tokens"],
                            temperature=(self.cfg["temperature"] if temperature is None
                                         else temperature),
                            operation_id=operation_id)
        return {"ok": True, "text": result.get("text") or "",
                "usage": result.get("usage"),
                "provider": self.cfg["provider"],
                "model": result.get("model") or self.cfg["model"]}
