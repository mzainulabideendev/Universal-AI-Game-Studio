"""V6 Phase 9 release-candidate tests (offline only).

Covers the bounded DNS resolver pool, Windows asset-path hardening, URL and
provider-error redaction, malformed-header handling and preservation of the
three Phase 8 fixes. No provider, socket, credential, download, engine or build
is used: every external boundary is mocked or an in-process fixture.
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import assets, util  # noqa: E402
from game_studio.llm import bounded_http, game_spec_pipeline, providers  # noqa: E402

JUNGLE = ("Create a stylized 3D jungle adventure where a monkey collects "
          "bananas and reaches a temple.")
PUBLIC_IP = "93.184.216.34"
URL = "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"


def _deadline(seconds: float) -> bounded_http._Deadline:
    return bounded_http._Deadline(seconds)


def _pool_infos(ip: str, port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class BoundedResolverTests(unittest.TestCase):
    def test_dns_success_uses_the_pool(self) -> None:
        calls = []

        def resolver(host, port, **kwargs):
            calls.append((host, port, kwargs))
            return _pool_infos(PUBLIC_IP, port)

        pool = bounded_http._ResolverPool(2, resolver=resolver)
        self.addCleanup(pool.shutdown)
        infos = pool.resolve("example.invalid", 443, _deadline(1.0))
        self.assertEqual(infos[0][4][0], PUBLIC_IP)
        self.assertEqual(calls[0][0], "example.invalid")
        self.assertEqual(calls[0][2].get("type"), socket.SOCK_STREAM)

    def test_dns_failure_is_structured(self) -> None:
        def resolver(_host, _port, **_kwargs):
            raise socket.gaierror("no such host")

        pool = bounded_http._ResolverPool(2, resolver=resolver)
        self.addCleanup(pool.shutdown)
        with self.assertRaises(bounded_http._BoundedError) as ctx:
            pool.resolve("missing.invalid", 443, _deadline(1.0))
        self.assertEqual(ctx.exception.kind, "dns_failure")
        self.assertEqual(ctx.exception.stage, "dns")
        self.assertFalse(ctx.exception.timed_out)

    def test_dns_timeout_stops_waiting_without_claiming_cancellation(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)

        def resolver(_host, _port, **_kwargs):
            release.wait(5)
            return []

        pool = bounded_http._ResolverPool(2, resolver=resolver)
        self.addCleanup(pool.shutdown)
        started = time.monotonic()
        with self.assertRaises(bounded_http._BoundedError) as ctx:
            pool.resolve("hung.invalid", 443, _deadline(0.15))
        elapsed = time.monotonic() - started
        self.assertEqual(ctx.exception.kind, "dns_timeout")
        self.assertTrue(ctx.exception.timed_out)
        self.assertIn("abandoned, not cancelled", str(ctx.exception))
        self.assertLess(elapsed, 2.0)
        stats = pool.stats()
        self.assertEqual(stats["in_flight"], 1)
        self.assertEqual(stats["abandoned"], 1)
        self.assertLessEqual(stats["alive_threads"], 2)

    def test_repeated_timeouts_do_not_accumulate_workers(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)

        def resolver(_host, _port, **_kwargs):
            release.wait(5)
            return []

        pool = bounded_http._ResolverPool(2, resolver=resolver)
        self.addCleanup(pool.shutdown)
        for _ in range(2):
            with self.assertRaises(bounded_http._BoundedError) as ctx:
                pool.resolve("hung.invalid", 443, _deadline(0.1))
            self.assertEqual(ctx.exception.kind, "dns_timeout")

        started = time.monotonic()
        for _ in range(5):
            with self.assertRaises(bounded_http._BoundedError) as ctx:
                pool.resolve("hung.invalid", 443, _deadline(0.1))
            self.assertEqual(ctx.exception.kind, "dns_capacity_exhausted")
            self.assertFalse(ctx.exception.timed_out)
        self.assertLess(time.monotonic() - started, 1.0)
        stats = pool.stats()
        self.assertEqual(stats["threads"], 2)
        self.assertLessEqual(stats["alive_threads"], 2)
        self.assertEqual(stats["in_flight"], 2)

        release.set()
        self.assertTrue(_wait_until(lambda: pool.stats()["in_flight"] == 0))
        self.assertEqual(pool.stats()["abandoned"], 0)

    def test_abandoned_worker_is_released_after_completion(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)

        def resolver(_host, _port, **_kwargs):
            release.wait(5)
            return _pool_infos(PUBLIC_IP, 443)

        pool = bounded_http._ResolverPool(1, resolver=resolver)
        self.addCleanup(pool.shutdown)
        with self.assertRaises(bounded_http._BoundedError):
            pool.resolve("slow.invalid", 443, _deadline(0.1))
        self.assertEqual(pool.stats()["abandoned"], 1)
        release.set()
        self.assertTrue(_wait_until(lambda: pool.stats()["in_flight"] == 0))
        self.assertEqual(pool.stats()["abandoned"], 0)
        self.assertEqual(pool.resolve("ok.invalid", 443, _deadline(1.0))[0][4][0],
                         PUBLIC_IP)

    def test_success_after_a_previous_timeout(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)
        calls = {"count": 0}

        def resolver(_host, _port, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                release.wait(5)
            return _pool_infos(PUBLIC_IP, 443)

        pool = bounded_http._ResolverPool(1, resolver=resolver)
        self.addCleanup(pool.shutdown)
        with self.assertRaises(bounded_http._BoundedError):
            pool.resolve("first.invalid", 443, _deadline(0.1))
        release.set()
        self.assertTrue(_wait_until(lambda: pool.stats()["in_flight"] == 0))
        infos = pool.resolve("second.invalid", 443, _deadline(1.0))
        self.assertEqual(infos[0][4][0], PUBLIC_IP)

    def test_deadline_is_propagated_to_the_resolver(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)

        def resolver(_host, _port, **_kwargs):
            release.wait(5)
            return []

        pool = bounded_http._ResolverPool(1, resolver=resolver)
        self.addCleanup(pool.shutdown)
        started = time.monotonic()
        with self.assertRaises(bounded_http._BoundedError):
            pool.resolve("slow.invalid", 443, _deadline(0.2))
        self.assertLess(time.monotonic() - started, 1.5)

    def test_idle_workers_terminate_on_shutdown(self) -> None:
        pool = bounded_http._ResolverPool(
            2, resolver=lambda _h, p, **_k: _pool_infos(PUBLIC_IP, p))
        pool.resolve("example.invalid", 443, _deadline(1.0))
        report = pool.shutdown()
        self.assertEqual(report["threads"], 2)
        self.assertTrue(report["terminated"])
        self.assertEqual(report["hung_workers_remaining"], 0)

    def test_hung_worker_termination_is_not_claimed(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)

        def resolver(_host, _port, **_kwargs):
            release.wait(5)
            return []

        pool = bounded_http._ResolverPool(1, resolver=resolver)
        with self.assertRaises(bounded_http._BoundedError):
            pool.resolve("hung.invalid", 443, _deadline(0.1))
        report = pool.shutdown(join_timeout=0.2)
        self.assertFalse(report["terminated"])
        self.assertGreaterEqual(report["hung_workers_remaining"], 1)
        release.set()

    def test_resolver_pool_capacity_is_static(self) -> None:
        pool = bounded_http._ResolverPool(3, resolver=lambda _h, p, **_k: [])
        self.assertEqual(pool.stats()["max_workers"], 3)
        pool.shutdown()


class RedactionTests(unittest.TestCase):
    def test_url_userinfo_and_query_secrets_are_redacted(self) -> None:
        safe = bounded_http._redact_url(
            "https://user:pass@example.invalid/path?key=SECRET123&q=1")
        self.assertNotIn("pass", safe)
        self.assertNotIn("SECRET123", safe)
        self.assertIn("q=1", safe)
        self.assertEqual(bounded_http._redact_url(URL), URL)

    def test_credential_url_is_rejected_without_echoing_the_secret(self) -> None:
        result = bounded_http.request(
            "https://user:supersecret@example.invalid/x", deadline_seconds=1)
        self.assertFalse(result["ok"])
        text = json.dumps(result)
        self.assertNotIn("supersecret", text)

    def test_provider_error_detail_is_redacted(self) -> None:
        error = providers._classify_status(
            400, {"error": {"message": "bad key sk-abcdefghijklmnopqrst"}})
        self.assertNotIn("sk-abcdefghijklmnopqrst", str(error))
        self.assertIn("[REDACTED]", str(error))

    def test_redacted_headers_cover_extended_secret_keys(self) -> None:
        headers = util.RedactedHeaders({
            "Authorization": "Bearer a", "Proxy-Authorization": "Basic b",
            "Cookie": "session=c", "X-Auth-Token": "d", "X-Request-Id": "visible",
        })
        for key in ("Authorization", "Proxy-Authorization", "Cookie", "X-Auth-Token"):
            self.assertEqual(headers[key], util.RedactedHeaders.REDACTED)
        self.assertEqual(headers["X-Request-Id"], "visible")
        self.assertEqual(headers.real_headers()["Cookie"], "session=c")


class AssetPathHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="v6p9-assets-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))

    def test_safe_provider_path_is_accepted(self) -> None:
        target = assets._safe_include_target(self.root, "textures/ok.png")
        self.assertTrue(target.endswith("ok.png"))

    def test_traversal_absolute_and_windows_unsafe_paths_are_refused(self) -> None:
        cases = [
            "../escape.bin", "C:/Windows/evil.bin", "foo:stream", "CON",
            "nul.txt", "com1", "a./b", "a /b", "a//b", "bad\x00name", "",
        ]
        for relative in cases:
            with self.subTest(relative=relative):
                with self.assertRaises(util.ToolError):
                    assets._safe_include_target(self.root, relative)

    def test_download_filename_is_validated(self) -> None:
        with self.assertRaises(util.ToolError):
            assets._safe_relative_asset_path("model:stream.glb",
                                             label="download filename")
        self.assertEqual(
            assets._safe_relative_asset_path("model.glb", label="download filename"),
            "model.glb")


class TransportHardeningTests(unittest.TestCase):
    def test_validate_url_rejects_embedded_credentials_before_dns(self) -> None:
        with mock.patch.object(util.socket, "getaddrinfo") as lookup:
            with self.assertRaises(util.ToolError):
                util._validate_url("https://user:pass@example.invalid/")
        lookup.assert_not_called()

    def test_bounded_transport_rejects_cgnat_and_unspecified(self) -> None:
        for address in ("100.64.0.1", "0.0.0.0", "::"):
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            with self.subTest(address=address):
                with self.assertRaises(bounded_http._BoundedError):
                    bounded_http._reject_private([(family, address)])
        bounded_http._reject_private([(socket.AF_INET, PUBLIC_IP)])

    def test_http_download_rejects_malformed_content_length(self) -> None:
        class Response:
            headers = {"Content-Length": "not-a-number", "Content-Type": "model/gltf-binary"}

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self, _amount):
                return b"data"

        with tempfile.TemporaryDirectory() as root:
            destination = str(Path(root) / "asset.glb")
            with mock.patch.object(util, "_validate_url"), \
                    mock.patch.object(util.urllib.request, "urlopen",
                                      return_value=Response()):
                result = util.http_download("https://example.invalid/asset.glb",
                                            destination)
            self.assertFalse(result["ok"])
            self.assertIn("invalid Content-Length", result["error"])
            self.assertFalse(Path(destination).exists())

    def test_http_download_rejects_negative_content_length(self) -> None:
        class Response:
            headers = {"Content-Length": "-1"}

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self, _amount):
                return b"data"

        with tempfile.TemporaryDirectory() as root:
            destination = str(Path(root) / "asset.glb")
            with mock.patch.object(util, "_validate_url"), \
                    mock.patch.object(util.urllib.request, "urlopen",
                                      return_value=Response()):
                result = util.http_download("https://example.invalid/asset.glb",
                                            destination)
            self.assertFalse(result["ok"])
            self.assertIn("negative Content-Length", result["error"])


class Phase8PreservationTests(unittest.TestCase):
    def test_pre_approved_plan_is_still_rejected(self) -> None:
        spec = game_spec_pipeline.build_specification(JUNGLE)
        tampered = json.loads(json.dumps(spec))
        tampered["requirements"][0]["implementation_status"] = "implemented"
        tampered["generation_plan"]["human_approved"] = True
        tampered["provenance"]["human_approved"] = True
        tampered["generation_performed"] = True
        report = game_spec_pipeline.validate_spec(tampered)
        self.assertFalse(report["valid"])
        self.assertIn("implemented", " ".join(report["errors"]))

    def test_polyhaven_download_still_uses_safe_join(self) -> None:
        source = Path(assets.__file__).read_text(encoding="utf-8")
        self.assertIn("_safe_include_target(", source)
        self.assertIn("_safe_relative_asset_path(", source)

    def test_deadline_eof_guard_is_still_present(self) -> None:
        source = Path(bounded_http.__file__).read_text(encoding="utf-8")
        self.assertIn("deadline expired before the body completed", source)


if __name__ == "__main__":
    unittest.main()
