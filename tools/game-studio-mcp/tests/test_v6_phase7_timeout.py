"""V6 Phase 7 bounded-transport tests (offline only).

Every test here mocks DNS, sockets, TLS and the HTTP response object. No real
connection is opened, no credential is read and no provider request is made.
The tests exist to prove the bounded transport can stop at each stage and that
partial responses are never parsed as JSON.
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import util  # noqa: E402
from game_studio.llm import bounded_http, provider_validation, providers  # noqa: E402

URL = "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"
PUBLIC_IP = "93.184.216.34"


class FakeSock:
    def __init__(self, *, fail=None):
        self.fail = fail
        self.closed = False
        self.timeout = None
        self.sent = b""

    def settimeout(self, value):
        self.timeout = value

    def connect(self, _address):
        if self.fail is not None:
            raise self.fail

    def sendall(self, data):
        self.sent += data

    def shutdown(self, _how):
        pass

    def close(self):
        self.closed = True


class FakeTLS(FakeSock):
    pass


class FakeContext:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def __init__(self, *, fail=None):
        self.fail = fail

    def wrap_socket(self, sock, server_hostname=None):
        if self.fail is not None:
            raise self.fail
        return FakeTLS()


class FakeResponse:
    def __init__(self, _sock, method=None, *, chunks=(), begin_error=None,
                 read_error=None, deadline_holder=None):
        self.status = 200
        self._chunks = list(chunks)
        self._begin_error = begin_error
        self._read_error = read_error
        self._deadline_holder = deadline_holder
        self.closed = False

    def begin(self):
        if self._begin_error is not None:
            raise self._begin_error

    def getheaders(self):
        return [("Content-Type", "application/json")]

    def read(self, _amount):
        if self._deadline_holder is not None:
            deadline = self._deadline_holder[0]
            while not deadline.expired:
                time.sleep(0.005)
            raise OSError("socket closed by watchdog")
        if self._read_error is not None and not self._chunks:
            raise self._read_error
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


class BoundedTransportTests(unittest.TestCase):
    def _patch_transport(self, *, response=None, context=None, connect_fail=None):
        """Patch DNS, socket and TLS so no real connection is made."""
        patches = [
            mock.patch.object(bounded_http, "_resolve",
                              return_value=[(socket.AF_INET, PUBLIC_IP)]),
            mock.patch.object(bounded_http.socket, "socket",
                              return_value=FakeSock(fail=connect_fail)),
            mock.patch.object(bounded_http.ssl, "create_default_context",
                              return_value=context or FakeContext()),
        ]
        if response is not None:
            patches.append(mock.patch.object(bounded_http.http.client,
                                             "HTTPResponse", response))
        return patches

    def _run(self, patches, **kwargs):
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return bounded_http.request(URL, method="POST", body={"a": 1},
                                    headers={"x-goog-api-key": "SECRET-KEY"},
                                    **kwargs)

    def test_dns_timeout_is_bounded(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)
        calls = []

        def slow_lookup(*_args, **_kwargs):
            calls.append(1)
            release.wait(5)
            return []

        with mock.patch.object(bounded_http.socket, "getaddrinfo", slow_lookup):
            started = time.monotonic()
            result = bounded_http.request(URL, deadline_seconds=0.15)
            elapsed = time.monotonic() - started
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_detail"]["kind"], "dns_timeout")
        self.assertEqual(result["error_detail"]["stage"], "dns")
        self.assertTrue(result["error_detail"]["timed_out"])
        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(calls), 1)

    def test_dns_failure_is_reported(self) -> None:
        with mock.patch.object(bounded_http.socket, "getaddrinfo",
                               side_effect=socket.gaierror("no such host")):
            result = bounded_http.request(URL, deadline_seconds=5)
        self.assertEqual(result["error_detail"]["kind"], "dns_failure")
        self.assertFalse(result["error_detail"]["timed_out"])

    def test_connection_timeout_is_reported(self) -> None:
        patches = self._patch_transport(connect_fail=socket.timeout("timed out"))
        result = self._run(patches, deadline_seconds=5, connect_timeout=0.1)
        self.assertEqual(result["error_detail"]["kind"], "connection_timeout")
        self.assertEqual(result["error_detail"]["stage"], "connect")
        self.assertTrue(result["error_detail"]["timed_out"])

    def test_tls_failure_is_reported(self) -> None:
        patches = self._patch_transport(
            context=FakeContext(fail=ssl.SSLError("certificate verify failed")))
        result = self._run(patches, deadline_seconds=5)
        self.assertEqual(result["error_detail"]["kind"], "tls_failure")
        self.assertEqual(result["error_detail"]["stage"], "tls")
        self.assertFalse(result["error_detail"]["timed_out"])

    def test_slow_response_headers_timeout(self) -> None:
        patches = self._patch_transport(
            response=mock.Mock(side_effect=lambda *a, **k: FakeResponse(
                *a, begin_error=socket.timeout("header timeout"), **k)))
        result = self._run(patches, deadline_seconds=5, header_timeout=0.05)
        self.assertEqual(result["error_detail"]["kind"], "http_response_timeout")
        self.assertEqual(result["error_detail"]["stage"], "headers")
        self.assertTrue(result["error_detail"]["timed_out"])

    def test_slow_response_body_timeout_keeps_partial_flag(self) -> None:
        patches = self._patch_transport(
            response=mock.Mock(side_effect=lambda *a, **k: FakeResponse(
                *a, chunks=[b'{"partial":'], read_error=socket.timeout("body timeout"),
                **k)))
        result = self._run(patches, deadline_seconds=5, body_timeout=0.05)
        detail = result["error_detail"]
        self.assertEqual(detail["kind"], "response_body_timeout")
        self.assertEqual(detail["stage"], "body")
        self.assertTrue(detail["timed_out"])
        self.assertTrue(detail["partial_response"])
        self.assertEqual(detail["partial_bytes"], len(b'{"partial":'))
        self.assertIsNone(result.get("payload"))
        self.assertNotIn("json_parse_skipped", result)

    def test_total_deadline_expires_and_stops_blocking_read(self) -> None:
        created = []

        class RecordingDeadline(bounded_http._Deadline):
            def __init__(self, seconds):
                super().__init__(seconds)
                created.append(self)

        def response_factory(*args, **kwargs):
            return FakeResponse(*args, deadline_holder=created, **kwargs)

        patches = self._patch_transport(response=response_factory)
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        with mock.patch.object(bounded_http, "_Deadline", RecordingDeadline):
            started = time.monotonic()
            result = bounded_http.request(URL, deadline_seconds=0.2,
                                          body_timeout=30)
            elapsed = time.monotonic() - started
        self.assertEqual(result["error_detail"]["kind"], "deadline_exceeded")
        self.assertTrue(result["error_detail"]["timed_out"])
        self.assertLess(elapsed, 3.0)
        self.assertIn("total_ms", result["error_detail"]["timing"])
        self.assertNotIn("SECRET-KEY", json.dumps(result))

    def test_watchdog_closes_registered_handle(self) -> None:
        class Handle:
            def __init__(self):
                self.shutdown_called = False
                self.closed = False

            def shutdown(self, _how):
                self.shutdown_called = True

            def close(self):
                self.closed = True

        handle = Handle()
        deadline = bounded_http._Deadline(0.05)
        deadline.start()
        self.addCleanup(deadline.stop)
        deadline.register(handle)
        limit = time.monotonic() + 2.0
        while not handle.closed and time.monotonic() < limit:
            time.sleep(0.005)
        self.assertTrue(deadline.expired)
        self.assertTrue(handle.shutdown_called)
        self.assertTrue(handle.closed)
        self.assertIsNone(deadline._sock)

    def test_valid_fixture_response_is_parsed_with_timing(self) -> None:
        body = json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
        patches = self._patch_transport(
            response=mock.Mock(side_effect=lambda *a, **k: FakeResponse(
                *a, chunks=[body.encode("utf-8")], **k)))
        result = self._run(patches, deadline_seconds=5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["payload"]["candidates"][0]["content"]["parts"][0]["text"],
                         "{}")
        self.assertFalse(result["truncated"])
        for key in ("dns_ms", "connect_ms", "tls_ms", "send_ms", "headers_ms",
                    "body_ms", "total_ms"):
            self.assertIn(key, result["timing"])
        self.assertNotIn("SECRET-KEY", json.dumps(result))

    def test_truncated_body_is_not_parsed_as_json(self) -> None:
        response = mock.Mock(side_effect=lambda *a, **k: FakeResponse(
            *a, chunks=[b'{"candidates": [', b'{"content": "partial"}'], **k))
        patches = self._patch_transport(response=response)
        result = self._run(patches, deadline_seconds=5, max_bytes=10)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["json_parse_skipped"])
        self.assertIsInstance(result["payload"], str)


class UtilDelegationTests(unittest.TestCase):
    def test_deadline_delegates_to_bounded_transport(self) -> None:
        sentinel = {"ok": True, "status": 200, "payload": {}}
        with mock.patch.object(bounded_http, "request",
                               return_value=sentinel) as bounded, \
             mock.patch.object(util, "_validate_url") as validate:
            result = util.http_request(URL, deadline_seconds=12.5,
                                       connect_timeout=1, tls_timeout=2,
                                       header_timeout=3, body_timeout=4)
        self.assertIs(result, sentinel)
        validate.assert_not_called()
        kwargs = bounded.call_args.kwargs
        self.assertEqual(kwargs["deadline_seconds"], 12.5)
        self.assertEqual(kwargs["connect_timeout"], 1)
        self.assertEqual(kwargs["tls_timeout"], 2)
        self.assertEqual(kwargs["header_timeout"], 3)
        self.assertEqual(kwargs["body_timeout"], 4)

    def test_without_deadline_uses_legacy_urllib_path(self) -> None:
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def read(self, _amount):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        with mock.patch.object(util.urllib.request, "urlopen",
                               return_value=Response()) as urlopen, \
             mock.patch.object(bounded_http, "request") as bounded:
            result = util.http_request(URL)
        urlopen.assert_called_once()
        bounded.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["payload"], {"ok": True})


class ProviderIntegrationTests(unittest.TestCase):
    def _adapter(self):
        return providers.GeminiProvider({
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "test-key-not-real",
            "local_provider": False,
            "key_required": True,
        })

    def test_gemini_complete_passes_total_deadline(self) -> None:
        captured = {}

        def fake_http(_url, **kwargs):
            captured.update(kwargs)
            return {"ok": True, "status": 200, "payload": {
                "candidates": [{"content": {"parts": [{"text": "hi"}]},
                                "finishReason": "STOP"}]}}

        with mock.patch.object(providers, "http_request", side_effect=fake_http):
            self._adapter().complete([{"role": "user", "content": "hi"}],
                                     timeout=60)
        self.assertEqual(captured["deadline_seconds"], 60)
        self.assertEqual(captured["connect_timeout"], providers.GEMINI_CONNECT_TIMEOUT)
        self.assertEqual(captured["body_timeout"], providers.GEMINI_BODY_TIMEOUT)

    def test_transport_error_is_not_retried_and_has_no_fallback(self) -> None:
        payload = {"ok": False, "status": None, "url": URL,
                   "error": "TCP connection did not complete",
                   "error_detail": {"kind": "connection_timeout",
                                    "stage": "connect", "timed_out": True,
                                    "elapsed_ms": 12.5, "timing": {"connect_ms": 12.5}}}
        with mock.patch.object(providers, "http_request",
                               return_value=payload) as http:
            with self.assertRaises(providers.ProviderError) as caught:
                self._adapter().complete([{"role": "user", "content": "hi"}])
        self.assertEqual(http.call_count, 1)
        error = caught.exception
        self.assertEqual(error.kind, "connection_timeout")
        self.assertEqual(error.detail["stage"], "connect")
        self.assertTrue(error.detail["timed_out"])
        self.assertFalse(error.detail.get("partial_response"))

    def test_transport_error_never_contains_header_secret(self) -> None:
        payload = {"ok": False, "status": None, "url": URL,
                   "error": "connection failed",
                   "error_detail": {"kind": "connection_failure", "stage": "connect",
                                    "timed_out": False}}
        with mock.patch.object(providers, "http_request", return_value=payload):
            with self.assertRaises(providers.ProviderError) as caught:
                self._adapter().complete([{"role": "user", "content": "hi"}])
        self.assertNotIn("test-key-not-real", str(caught.exception))
        self.assertNotIn("test-key-not-real", json.dumps(caught.exception.detail))


class LiveValidationDetailTests(unittest.TestCase):
    def test_structured_detail_is_surfaced_without_secret(self) -> None:
        class Adapter:
            def complete(self, *_args, **_kwargs):
                raise providers.ProviderError(
                    "response body did not complete",
                    kind="response_body_timeout", retryable=True,
                    detail={"kind": "response_body_timeout", "stage": "body",
                            "timed_out": True, "elapsed_ms": 45.1,
                            "partial_response": True, "partial_bytes": 64,
                            "deadline_seconds": 60,
                            "timing": {"body_ms": 45.0}})

        plan = provider_validation.plan_live_validation()
        authorization = {
            "approved": True, "approved_by": "unit-test",
            "provider": plan["provider"], "model": plan["model"],
            "request_sha256": plan["request"]["request_sha256"],
        }
        with mock.patch.object(provider_validation.llm_providers, "build",
                               return_value=Adapter()), \
             mock.patch.object(provider_validation, "quota") as quota:
            result = provider_validation.execute_live_validation(
                authorization=authorization)
        quota.quota_state.return_value = {}
        error = result["error"]
        self.assertEqual(error["kind"], "response_body_timeout")
        self.assertEqual(error["stage"], "body")
        self.assertTrue(error["timed_out"])
        self.assertTrue(error["partial_response"])
        self.assertEqual(error["partial_bytes"], 64)
        self.assertEqual(error["timing"], {"body_ms": 45.0})
        self.assertFalse(error["retry_attempted"])
        self.assertEqual(result["network_calls"], 1)
        self.assertFalse(result["secrets_recorded"])


if __name__ == "__main__":
    unittest.main()
