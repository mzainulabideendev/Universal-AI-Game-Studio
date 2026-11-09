"""Phase 5 gameplay evidence integration tests.

These tests re-read the Phase 5 evidence on disk and verify that the JSON
reports, build artifact, scene, screenshots and measured performance agree
with each other. They do not run Unity and do not fabricate results.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
CAPTURES = REPORTS / "v6-captures"
EXE = ROOT / "validation" / "builds" / "v6-windows" / "V6JungleMonkey.exe"
SCENE = (ROOT / "validation" / "unity-jungle-v6" / "Assets" / "V6" /
         "Scenes" / "JungleMonkeyV6.unity")

REQUIRED_PLAYMODE = {
    "SceneContainsRealPlayerEnvironmentCameraAndUi",
    "NoMissingScriptsMaterialsOrShaders",
    "PlayerSpawnsOnGroundAndStaysThere",
    "PlayerMovesWhenInputIsApplied",
    "PlayerJumpsRaisesAndLands",
    "DoubleJumpIsRejected",
    "BananaCollectionIncrementsScoreAndHidesObject",
    "ObjectiveProgressAdvancesWithRealCollections",
    "PauseStopsMovementAndResumeRestoresIt",
    "RestartResetsScoreBananasAndPosition",
    "LevelCompletesOnlyAfterAllBananasAndDestination",
    "PlayerCollidesWithSolidObstacle",
    "AnimatorReceivesLocomotionParameters",
    "RiverHazardEndsRunInGameOverState",
    "FallingOutOfBoundsReturnsToCheckpointSafely",
}

SCREENSHOTS = {
    "main_menu": "01-main-menu.png",
    "playing": "02-playing.png",
    "paused": "03-paused.png",
    "level_complete": "04-level-complete.png",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


class Phase5GameplayReportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.integration = load("v6-gameplay-integration.json")
        cls.validation = load("v6-gameplay-validation.json")
        cls.performance = load("v6-gameplay-performance.json")

    def test_reports_describe_the_phase(self) -> None:
        self.assertIn("Phase 5", self.integration["phase"])
        self.assertIn("Phase 5", self.validation["phase"])
        self.assertEqual("PASS", self.validation["verdict"])
        self.assertTrue(self.validation["acceptance"])

    def test_build_artifact_matches_integration_report(self) -> None:
        build = self.integration["build"]
        self.assertEqual("Succeeded", build["result"])
        self.assertEqual(0, build["total_errors"])
        self.assertTrue(EXE.is_file(), "built player is missing")
        self.assertEqual(build["executable"]["sha256"], sha256(EXE))
        self.assertEqual(build["executable"]["bytes"], EXE.stat().st_size)

    def test_scene_matches_integration_report(self) -> None:
        scene = self.integration["scene"]
        self.assertTrue(SCENE.is_file(), "generated scene is missing")
        self.assertEqual(scene["sha256"], sha256(SCENE))
        report = scene["report"]
        self.assertTrue(report["succeeded"])
        self.assertEqual(0, report["missingMaterials"])
        self.assertEqual(0, report["missingShaders"])
        self.assertGreaterEqual(report["collectibles"], 10)
        self.assertGreaterEqual(report["checkpoints"], 1)
        self.assertTrue({"Idle", "Walk", "Run", "Jump"} <=
                        set(report["animatorStates"]))

    def test_playmode_suite_covers_required_gameplay(self) -> None:
        playmode = self.validation["test_runs"]["playmode"]
        self.assertEqual(0, playmode["failed"])
        self.assertEqual(playmode["total"], playmode["passed"])
        self.assertGreaterEqual(playmode["total"], 15)
        names = {case["name"] for case in playmode["cases"]}
        self.assertTrue(REQUIRED_PLAYMODE <= names)

    def test_editmode_suite_passes(self) -> None:
        editmode = self.validation["test_runs"]["editmode"]
        self.assertEqual(0, editmode["failed"])
        self.assertEqual(editmode["total"], editmode["passed"])
        self.assertGreaterEqual(editmode["total"], 16)

    def test_playthrough_completed_with_real_screenshots(self) -> None:
        play = self.integration["automated_playthrough"]
        self.assertTrue(play["level_completed"])
        self.assertTrue(play["auto_play_finished"])
        self.assertGreaterEqual(len(play["checkpoints_reached"]), 1)
        for name, filename in SCREENSHOTS.items():
            path = CAPTURES / filename
            self.assertTrue(path.is_file(), f"missing screenshot {filename}")
            data = path.read_bytes()
            self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
            self.assertGreater(len(data), 10_000)
            self.assertGreater(int.from_bytes(data[16:20], "big"), 0)
            self.assertGreater(int.from_bytes(data[20:24], "big"), 0)
            reported = play["screenshots"][name]
            self.assertEqual(reported["sha256"], sha256(path))

    def test_performance_is_measured_and_consistent(self) -> None:
        self.assertGreater(self.performance["frames"], 0)
        self.assertGreater(self.performance["durationSeconds"], 0)
        self.assertGreater(self.performance["averageFps"], 0)
        self.assertGreater(self.performance["activeTriangles"], 0)
        self.assertGreater(self.performance["activeRenderers"], 0)
        play_perf = self.integration["automated_playthrough"]["performance"]
        self.assertEqual(play_perf["frames"], self.performance["frames"])
        self.assertEqual(play_perf["sha256"],
                         sha256(REPORTS / "v6-gameplay-performance.json"))

    def test_no_requirement_is_claimed_human_verified(self) -> None:
        for requirement in self.validation["requirements"]:
            self.assertNotEqual("verified", requirement["status"])
        self.assertEqual("pending", self.validation["human_review"]["status"])


if __name__ == "__main__":
    unittest.main()
