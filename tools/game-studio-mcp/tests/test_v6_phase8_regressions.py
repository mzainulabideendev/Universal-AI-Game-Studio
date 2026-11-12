"""V6 Phase 8 regression tests for integration and safety fixes (offline only).

Each test targets a gap found during the Phase 8 audit and uses mocked external
boundaries. No provider, socket, credential, download, engine or build is used.
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import assets  # noqa: E402
from game_studio.agents import game_designer  # noqa: E402
from game_studio.agents.coordinator import Orchestrator  # noqa: E402
from game_studio.llm import bounded_http, free_routing, game_spec_pipeline  # noqa: E402

JUNGLE = ("Create a stylized 3D jungle adventure where a monkey collects "
          "bananas and reaches a temple.")
PUBLIC_IP = "93.184.216.34"
URL = "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"


def _tamper(spec: dict) -> dict:
    tampered = json.loads(json.dumps(spec))
    tampered["requirements"][0]["implementation_status"] = "implemented"
    tampered["approval"]["approved"] = True
    tampered["generation_plan"]["human_approved"] = True
    tampered["generation_plan"]["build_started"] = True
    tampered["generation_plan"]["asset_generation_performed"] = True
    tampered["generation_plan"]["steps"][0]["executed"] = True
    tampered["provenance"]["human_approved"] = True
    tampered["generation_performed"] = True
    tampered["phase5_project_modified"] = True
    return tampered


class ApprovalBoundaryRegressionTests(unittest.TestCase):
    def test_every_preapproval_flag_is_rejected(self) -> None:
        spec = game_spec_pipeline.build_specification(JUNGLE)
        report = game_spec_pipeline.validate_spec(_tamper(spec))
        self.assertFalse(report["valid"])
        text = " ".join(report["errors"])
        self.assertIn("implemented", text)
        self.assertIn("approval", text)
        self.assertIn("human_approved", text)
        self.assertIn("build_started", text)
        self.assertIn("asset_generation_performed", text)
        self.assertIn("executed", text)
        self.assertIn("generation_performed", text)
        self.assertIn("phase5_project_modified", text)

    def test_unmodified_specification_stays_valid(self) -> None:
        spec = game_spec_pipeline.build_specification(JUNGLE)
        self.assertTrue(spec["validation"]["valid"], spec["validation"]["errors"])
        self.assertFalse(spec["provenance"]["human_approved"])
        self.assertFalse(spec["generation_plan"]["human_approved"])
        self.assertFalse(spec["generation_plan"]["build_started"])


class TransportRegressionTests(unittest.TestCase):
    class _Sock:
        def settimeout(self, _value):
            pass

        def connect(self, _address):
            pass

        def sendall(self, _data):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    class _TLS(_Sock):
        pass

    class _Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def wrap_socket(self, sock, server_hostname=None):
            return TransportRegressionTests._TLS()

    class _Response:
        status = 200

        def __init__(self, *_args, **_kwargs):
            self.closed = False

        def begin(self):
            pass

        def getheaders(self):
            return [("Content-Type", "application/json")]

        def read(self, _amount):
            # A watchdog-closed socket can surface as a clean EOF on some
            # platforms instead of raising socket.timeout/OSError.
            time.sleep(0.3)
            return b""

        def close(self):
            self.closed = True

    def test_clean_eof_after_deadline_is_a_timeout_not_success(self) -> None:
        with mock.patch.object(bounded_http, "_resolve",
                               return_value=[(socket.AF_INET, PUBLIC_IP)]), \
                mock.patch.object(bounded_http.socket, "socket",
                                  return_value=self._Sock()), \
                mock.patch.object(bounded_http.ssl, "create_default_context",
                                  return_value=self._Context()), \
                mock.patch.object(bounded_http.http.client, "HTTPResponse",
                                  self._Response):
            result = bounded_http.request(URL, method="POST", body={"a": 1},
                                          deadline_seconds=0.15, body_timeout=30)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_detail"]["kind"], "deadline_exceeded")
        self.assertEqual(result["error_detail"]["stage"], "body")
        self.assertTrue(result["error_detail"]["timed_out"])
        self.assertNotIn("payload", result)
        self.assertNotIn("json_parse_skipped", result)


class AssetPathRegressionTests(unittest.TestCase):
    def test_asset_id_and_include_paths_stay_under_target(self) -> None:
        with self.assertRaises(assets.ToolError):
            assets._safe_asset_id("..")
        with self.assertRaises(assets.ToolError):
            assets._safe_asset_id("C:evil")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(assets.ToolError):
                assets._safe_include_target(tmp, "../escape.bin")
            with self.assertRaises(assets.ToolError):
                assets._safe_include_target(tmp, "C:/Windows/evil.bin")
            resolved = assets._safe_include_target(tmp, "textures/ok.png")
            self.assertTrue(resolved.startswith(str(Path(tmp).resolve())))

    def test_polyhaven_include_traversal_is_refused_before_download(self) -> None:
        payload = {
            "glb": {"2k": {"Jungle.glb": {
                "url": "https://dl.polyhaven.org/file/Jungle.glb",
                "size": 10,
                "md5": None,
                "include": {"C:/Windows/evil.bin": {
                    "url": "https://dl.polyhaven.org/file/evil.bin",
                    "size": 1,
                }},
            }}}
        }
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(assets, "http_request",
                                  return_value={"ok": True, "payload": payload}), \
                mock.patch.object(assets, "http_download") as download:
            result = assets.download_polyhaven(
                "safe_asset", confirm=True, destination_dir=tmp)
        self.assertFalse(result["ok"])
        self.assertIn("not allowed", result["error"])
        download.assert_not_called()


class ProviderRoutingRegressionTests(unittest.TestCase):
    def test_paid_openrouter_variant_is_refused(self) -> None:
        decision = free_routing.route(
            "game_design_reasoning", provider="openrouter",
            model="example/paid-model")
        self.assertEqual(decision["mode"], "deterministic")
        self.assertIsNone(decision["selected"])
        self.assertFalse(decision["policy"]["paid_fallback"])
        reasons = [item["reason"] for item in decision["fallback_reasons"]]
        self.assertIn("invalid_model", reasons)

    def test_free_openrouter_variant_remains_eligible(self) -> None:
        candidate = free_routing.evaluate_candidate(
            "openrouter", required=[], model="example/model:free",
            context_chars=None, max_tokens=None, require_known=False,
            discovered=None, explicit=True)
        self.assertIs(candidate["model_eligible"], True)
        self.assertTrue(candidate["free"])
        self.assertFalse(candidate["paid_switch_possible"])


class OrchestrationFailureTests(unittest.TestCase):
    def test_dependency_failure_blocks_dependents(self) -> None:
        with mock.patch.object(game_designer.GameDesignerAgent,
                               "deterministic_output",
                               side_effect=RuntimeError("injected design failure")):
            result = Orchestrator(JUNGLE, installed_engines=["unity"]).run()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_tasks"], ["design"])
        self.assertIn("architecture", result["blocked_tasks"])
        self.assertIn("consolidation", result["blocked_tasks"])
        self.assertFalse(result["executable"])
        self.assertFalse(result["governance"]["writes_performed"])
        for task in result["tasks"]:
            if task["id"] != "design":
                self.assertIn(task["status"], ("blocked", "cancelled"))

    def test_cancellation_produces_explicit_cancelled_results(self) -> None:
        event = threading.Event()
        event.set()
        result = Orchestrator(JUNGLE, installed_engines=["unity"],
                              cancel_event=event).run()
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(result["ok"])
        self.assertFalse(result["executable"])
        self.assertEqual(len(result["cancelled_tasks"]), len(result["tasks"]))
        self.assertTrue(all(task["status"] == "cancelled"
                            for task in result["tasks"]))


class EarlierPhaseRegressionTests(unittest.TestCase):
    def test_all_phase_audits_parse_and_pass(self) -> None:
        expected = {
            "v6-phase3-audit.json": "PASS",
            "v6-phase4-audit.json": "PASS",
            "v6-phase5-audit.json": "PASS_AUTOMATED",
            "v6-phase6-audit.json": "PASS",
            "v6-phase7-audit.json": "PASS_AUTOMATED",
        }
        for name, verdict in expected.items():
            payload = json.loads((REPO / "reports" / name).read_text(encoding="utf-8"))
            self.assertEqual(payload["verdict"], verdict, name)
            self.assertTrue(payload.get("all_criteria_passed", True), name)


if __name__ == "__main__":
    unittest.main()
