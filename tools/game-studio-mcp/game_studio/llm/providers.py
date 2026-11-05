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

ANTHROPIC_VERSION = "2023-06-01"


class ProviderError(Exception):
    def __init__(self, message: str, *, kind: str = "provider-error",
                 retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.status = status


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
             allow_local: bool = False) -> dict:
    result = http_request(url, method="POST", headers=headers, body=body,
                          timeout=timeout, allow_local=allow_local)
    if result.get("ok"):
        return result
    if result.get("status") is None:
        message = str(result.get("error") or "network request failed")
        kind = "timeout" if "timed out" in message.lower() else "unavailable"
        raise ProviderError(message, kind=kind, retryable=True)
    raise _classify_status(result.get("status"), result.get("payload"))


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
                 max_tokens: int = 2048, temperature: float = 0.2,
                 json_mode: bool = False, timeout: int = 60) -> dict:
        raise NotImplementedError

    def _headers(self) -> dict:
        return {}


class OpenAICompatibleProvider(Provider):
    name = "openai_compatible"

    def _url(self) -> str:
        base = self.cfg["base_url"].rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

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

    def complete(self, messages, *, system=None, max_tokens=2048, temperature=0.2,
                 json_mode=False, timeout=60) -> dict:
        contents = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            contents.append({"role": role,
                             "parts": [{"text": str(message.get("content") or "")}]})
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        result = _request(self._url(), headers=self._headers(), body=body, timeout=timeout)
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
    "ollama": OllamaProvider,
}


def build(cfg: dict) -> Provider:
    provider = _REGISTRY.get(cfg["provider"])
    if not provider:
        raise ProviderError(f"unsupported provider: {cfg['provider']}", kind="config")
    return provider(cfg)
