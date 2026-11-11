"""Concrete provider adapters with a single common interface.

Every adapter returns ``{"text", "usage", "model", "raw_meta"}`` or raises
``ProviderError``. No adapter pretends a request succeeded.

Provider APIs differ, so each adapter maps its own wire format:

* OpenAI / OpenAI-compatible: ``POST /chat/completions``
* Anthropic: ``POST /messages`` with ``x-api-key``
* Gemini: ``POST /models/<model>:generateContent``
* Ollama: ``POST /api/chat`` on loopback
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

from ..util import RedactedHeaders, http_request
from .capabilities import model_capabilities, unknown_model_capabilities

ANTHROPIC_VERSION = "2023-06-01"

# Gemini uses the bounded transport. The total deadline is the caller's
# ``timeout``; these per-stage budgets only cap individual phases and can never
# extend the overall deadline.
GEMINI_CONNECT_TIMEOUT = 10.0
GEMINI_TLS_TIMEOUT = 10.0
GEMINI_HEADER_TIMEOUT = 30.0
GEMINI_BODY_TIMEOUT = 45.0


class ProviderError(Exception):
    def __init__(self, message: str, *, kind: str = "provider-error",
                 retryable: bool = False, status: int | None = None,
                 detail: dict | None = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.status = status
        self.detail = detail or {}


def _classify_status(status: int | None, body: object) -> ProviderError:
    detail = ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("type") or "")
        elif error:
            detail = str(error)
        else:
            detail = str(body.get("message") or body.get("detail") or "")
    elif isinstance(body, str):
        detail = body[:400]
    detail = detail.strip() or "provider returned an error"
    if status == 401 or status == 403:
        return ProviderError(f"authentication failed: {detail}", kind="auth", status=status)
    if status == 429:
        return ProviderError(f"rate limited: {detail}", kind="rate_limit",
                             retryable=True, status=status)
    if status == 404:
        return ProviderError(f"model or endpoint not found: {detail}", kind="not_found",
                             status=status)
    if status in (400, 422):
        return ProviderError(f"invalid request: {detail}", kind="invalid_request",
                             status=status)
    if status and status >= 500:
        return ProviderError(f"provider unavailable ({status}): {detail}",
                             kind="unavailable", retryable=True, status=status)
    if status and status >= 400:
        return ProviderError(f"provider error ({status}): {detail}", kind="provider-error",
                             status=status)
    return ProviderError(detail, kind="provider-error")


def _request(url: str, *, headers: dict, body: dict, timeout: int,
             allow_local: bool = False,
             deadline_seconds: float | None = None,
             connect_timeout: float | None = None,
             tls_timeout: float | None = None,
             header_timeout: float | None = None,
             body_timeout: float | None = None) -> dict:
    transport: dict = {}
    if deadline_seconds is not None:
        transport.update({
            "deadline_seconds": deadline_seconds,
            "connect_timeout": connect_timeout,
            "tls_timeout": tls_timeout,
            "header_timeout": header_timeout,
            "body_timeout": body_timeout,
        })
        transport = {key: value for key, value in transport.items()
                     if value is not None}
    result = http_request(url, method="POST", headers=headers, body=body,
                          timeout=timeout, allow_local=allow_local, **transport)
    if result.get("ok"):
        return result
    if result.get("status") is None:
        raise _transport_error(result)
    raise _classify_status(result.get("status"), result.get("payload"))


def _request_get(url: str, *, headers: dict, timeout: int,
                 allow_local: bool = False,
                 deadline_seconds: float | None = None,
                 connect_timeout: float | None = None,
                 tls_timeout: float | None = None,
                 header_timeout: float | None = None,
                 body_timeout: float | None = None) -> dict:
    transport: dict = {}
    if deadline_seconds is not None:
        transport.update({
            "deadline_seconds": deadline_seconds,
            "connect_timeout": connect_timeout,
            "tls_timeout": tls_timeout,
            "header_timeout": header_timeout,
            "body_timeout": body_timeout,
        })
        transport = {key: value for key, value in transport.items()
                     if value is not None}
    result = http_request(url, method="GET", headers=headers, timeout=timeout,
                          allow_local=allow_local, **transport)
    if result.get("ok"):
        return result
    if result.get("status") is None:
        raise _transport_error(result)
    raise _classify_status(result.get("status"), result.get("payload"))


def _transport_error(result: dict) -> ProviderError:
    """Map a bounded-transport failure to a structured ProviderError."""
    detail = result.get("error_detail")
    detail = dict(detail) if isinstance(detail, dict) else {}
    message = str(result.get("error") or "network request failed")
    kind = detail.get("kind")
    if not kind:
        kind = "timeout" if "timed out" in message.lower() else "unavailable"
    return ProviderError(message, kind=str(kind), retryable=True, detail=detail)


def _model_entry(model_id: str, *, provider: str, name: str | None = None,
                 created: object = None, owned_by: str | None = None,
                 capabilities: dict | None = None,
                 raw_meta: dict | None = None) -> dict:
    return {
        "id": model_id,
        "name": name or model_id,
        "provider": provider,
        "created": created,
        "owned_by": owned_by,
        "capabilities": capabilities or unknown_model_capabilities(),
        "source": "live-discovery",
        "raw_meta": raw_meta or {},
    }



def _usage_openai(payload: dict) -> dict:
    usage = payload.get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


class Provider:
    name = "base"
    local = False

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def complete(self, messages: list[dict], *, system: str | None = None,
                 max_tokens: int = 2048, temperature: float | None = 0.2,
                 json_mode: bool = False, timeout: int = 60) -> dict:
        raise NotImplementedError

    def _headers(self) -> dict:
        return {}

    def list_models(self, *, timeout: int = 15) -> dict:
        """Return documented models. Adapters that cannot list raise ProviderError."""
        raise ProviderError(
            f"model listing is not implemented for provider {self.name!r}",
            kind="unsupported")

    def health(self, *, timeout: int = 10) -> dict:
        """Probe reachability with the documented model-list endpoint."""
        try:
            listing = self.list_models(timeout=timeout)
        except ProviderError as exc:
            return {
                "ok": False,
                "provider": self.name,
                "reachable": False,
                "state": exc.kind,
                "retryable": bool(exc.retryable),
                "error": str(exc),
                "live_verified": False,
            }
        return {
            "ok": True,
            "provider": self.name,
            "reachable": True,
            "state": "reachable",
            "model_count": listing.get("count", 0),
            "source": listing.get("source"),
            "live_verified": True,
            "note": "Reachability was verified by a real model-list request.",
        }


class OpenAICompatibleProvider(Provider):
    name = "openai_compatible"

    def _url(self) -> str:
        base = self.cfg["base_url"].rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def _models_url(self) -> str:
        base = self.cfg["base_url"].rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        return base + "/models"

    def list_models(self, *, timeout: int = 15) -> dict:
        result = _request_get(self._models_url(), headers=self._headers(), timeout=timeout)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON model list",
                                kind="invalid_response")
        items = payload.get("data")
        if not isinstance(items, list):
            raise ProviderError("model list response has no data array",
                                kind="invalid_response")
        models = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            models.append(_model_entry(
                model_id.strip(), provider=self.name,
                created=item.get("created"), owned_by=item.get("owned_by"),
                raw_meta={"object": item.get("object")}))
        return {"ok": True, "provider": self.name, "source": "live-discovery",
                "endpoint": self._models_url(), "models": models, "count": len(models),
                "capability_metadata_exposed": False}

    def _headers(self) -> dict:
        key = self.cfg.get("api_key")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        return RedactedHeaders(headers)

    def complete(self, messages, *, system=None, max_tokens=2048, temperature=0.2,
                 json_mode=False, timeout=60) -> dict:
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        body: dict = {
            "model": self.cfg["model"],
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        result = _request(self._url(), headers=self._headers(), body=body,
                          timeout=timeout)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON content", kind="invalid_response")
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("provider response has no message content",
                                kind="invalid_response")
        if isinstance(text, list):
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
        return {"text": text or "", "usage": _usage_openai(payload),
                "model": payload.get("model") or self.cfg["model"],
                "raw_meta": {"finish_reason": (payload.get("choices") or [{}])[0].get(
                    "finish_reason")}}


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"


class AnthropicProvider(Provider):
    name = "anthropic"

    def _url(self) -> str:
        return self.cfg["base_url"].rstrip("/") + "/messages"

    def _headers(self) -> dict:
        headers = {
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        key = self.cfg.get("api_key")
        if key:
            headers["x-api-key"] = key
        return RedactedHeaders(headers)

    def _models_url(self) -> str:
        return self.cfg["base_url"].rstrip("/") + "/models?limit=100"

    def list_models(self, *, timeout: int = 15) -> dict:
        result = _request_get(self._models_url(), headers=self._headers(), timeout=timeout)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON model list",
                                kind="invalid_response")
        items = payload.get("data")
        if not isinstance(items, list):
            raise ProviderError("model list response has no data array",
                                kind="invalid_response")
        models = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            models.append(_model_entry(
                model_id.strip(), provider=self.name,
                name=item.get("display_name"), created=item.get("created_at"),
                raw_meta={"type": item.get("type")}))
        return {"ok": True, "provider": self.name, "source": "live-discovery",
                "endpoint": self._models_url(), "models": models, "count": len(models),
                "capability_metadata_exposed": False}

    def complete(self, messages, *, system=None, max_tokens=2048, temperature=0.2,
                 json_mode=False, timeout=60) -> dict:
        body: dict = {
            "model": self.cfg["model"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system
        result = _request(self._url(), headers=self._headers(), body=body,
                          timeout=timeout)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON content", kind="invalid_response")
        blocks = payload.get("content") or []
        text = "".join(block.get("text", "") for block in blocks
                       if isinstance(block, dict) and block.get("type") == "text")
        usage = payload.get("usage") or {}
        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
                "total_tokens": (usage.get("input_tokens") or 0) +
                                (usage.get("output_tokens") or 0) or None,
            },
            "model": payload.get("model") or self.cfg["model"],
            "raw_meta": {"stop_reason": payload.get("stop_reason")},
        }


class GeminiProvider(Provider):
    name = "gemini"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        key = self.cfg.get("api_key")
        if key:
            headers["x-goog-api-key"] = key
        return RedactedHeaders(headers)

    def _url(self) -> str:
        base = self.cfg["base_url"].rstrip("/")
        return f"{base}/models/{urllib.parse.quote(self.cfg['model'])}:generateContent"

    def _models_url(self) -> str:
        return self.cfg["base_url"].rstrip("/") + "/models?pageSize=200"

    def list_models(self, *, timeout: int = 15) -> dict:
        result = _request_get(
            self._models_url(), headers=self._headers(), timeout=timeout,
            deadline_seconds=timeout,
            connect_timeout=GEMINI_CONNECT_TIMEOUT,
            tls_timeout=GEMINI_TLS_TIMEOUT,
            header_timeout=GEMINI_HEADER_TIMEOUT,
            body_timeout=GEMINI_BODY_TIMEOUT)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON model list",
                                kind="invalid_response")
        items = payload.get("models")
        if not isinstance(items, list):
            raise ProviderError("model list response has no models array",
                                kind="invalid_response")
        models = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                continue
            model_id = raw_name.strip()
            if model_id.startswith("models/"):
                model_id = model_id[len("models/"):]
            methods = item.get("supportedGenerationMethods")
            methods = [str(m) for m in methods] if isinstance(methods, list) else []
            text_state = "supported" if "generateContent" in methods else None
            window = None
            if isinstance(item.get("inputTokenLimit"), int):
                window = {"state": "supported", "value": item["inputTokenLimit"]}
            models.append(_model_entry(
                model_id, provider=self.name,
                name=item.get("displayName"),
                capabilities=model_capabilities(text_generation=text_state,
                                                context_window=window),
                raw_meta={
                    "supported_generation_methods": methods[:20],
                    "output_token_limit": item.get("outputTokenLimit"),
                }))
        return {"ok": True, "provider": self.name, "source": "live-discovery",
                "endpoint": self._models_url(), "models": models, "count": len(models),
                "capability_metadata_exposed": True,
                "capability_source": "supportedGenerationMethods and inputTokenLimit"}

    def complete(self, messages, *, system=None, max_tokens=2048,
                 temperature: float | None = 0.2, json_mode=False,
                 timeout=60) -> dict:
        contents = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            contents.append({"role": role,
                             "parts": [{"text": str(message.get("content") or "")}]})
        generation: dict = {"maxOutputTokens": max_tokens}
        # Gemini 3.6+ no longer supports temperature/top_p/top_k; omit the field
        # entirely instead of sending a value that the API silently ignores.
        if temperature is not None:
            generation["temperature"] = temperature
        body: dict = {"contents": contents, "generationConfig": generation}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        result = _request(self._url(), headers=self._headers(), body=body,
                          timeout=timeout, deadline_seconds=timeout,
                          connect_timeout=GEMINI_CONNECT_TIMEOUT,
                          tls_timeout=GEMINI_TLS_TIMEOUT,
                          header_timeout=GEMINI_HEADER_TIMEOUT,
                          body_timeout=GEMINI_BODY_TIMEOUT)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON content", kind="invalid_response")
        candidates = payload.get("candidates") or []
        if not candidates:
            feedback = payload.get("promptFeedback") or {}
            raise ProviderError(f"no candidates returned: {feedback}", kind="invalid_response")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        usage = payload.get("usageMetadata") or {}
        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            },
            "model": self.cfg["model"],
            "raw_meta": {"finish_reason": candidates[0].get("finishReason")},
        }


class OllamaProvider(Provider):
    name = "ollama"
    local = True

    def _url(self) -> str:
        return self.cfg["base_url"].rstrip("/") + "/api/chat"

    def _models_url(self) -> str:
        return self.cfg["base_url"].rstrip("/") + "/api/tags"

    def list_models(self, *, timeout: int = 15) -> dict:
        result = _request_get(self._models_url(), headers={"Content-Type": "application/json"},
                              timeout=timeout, allow_local=True)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("Ollama returned non-JSON model list",
                                kind="invalid_response")
        items = payload.get("models")
        if not isinstance(items, list):
            raise ProviderError("Ollama tags response has no models array",
                                kind="invalid_response")
        models = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = item.get("model") or item.get("name")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            models.append(_model_entry(
                model_id.strip(), provider=self.name,
                name=item.get("name") or model_id,
                created=item.get("modified_at"),
                raw_meta={"size": item.get("size"),
                          "family": details.get("family"),
                          "parameter_size": details.get("parameter_size"),
                          "quantization_level": details.get("quantization_level"),
                          "capabilities_exposed": False}))
        return {"ok": True, "provider": self.name, "source": "live-discovery",
                "endpoint": self._models_url(), "models": models, "count": len(models),
                "capability_metadata_exposed": False,
                "note": ("Ollama tags do not declare tool/JSON/image support. Model-level "
                         "capabilities remain unknown; do not assume they exist.")}

    def complete(self, messages, *, system=None, max_tokens=2048, temperature=0.2,
                 json_mode=False, timeout=60) -> dict:
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        body: dict = {
            "model": self.cfg["model"],
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        result = _request(self._url(), headers={"Content-Type": "application/json"},
                          body=body, timeout=timeout, allow_local=True)
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ProviderError("provider returned non-JSON content", kind="invalid_response")
        message = payload.get("message") or {}
        return {
            "text": message.get("content") or "",
            "usage": {
                "prompt_tokens": payload.get("prompt_eval_count"),
                "completion_tokens": payload.get("eval_count"),
                "total_tokens": (payload.get("prompt_eval_count") or 0) +
                                (payload.get("eval_count") or 0) or None,
            },
            "model": payload.get("model") or self.cfg["model"],
            "raw_meta": {"done": payload.get("done"),
                         "done_reason": payload.get("done_reason")},
        }


_REGISTRY = {
    "openai": OpenAIProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": OpenAICompatibleProvider,
    "openrouter": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
}


def build(cfg: dict) -> Provider:
    provider = _REGISTRY.get(cfg["provider"])
    if not provider:
        raise ProviderError(f"unsupported provider: {cfg['provider']}", kind="config")
    return provider(cfg)
