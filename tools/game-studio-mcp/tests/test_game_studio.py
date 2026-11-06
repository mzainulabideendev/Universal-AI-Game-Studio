"""Offline tests for the Universal AI Game Studio MCP server.

Tests create temporary projects and assets. They do not need Blender, Unity,
Godot, network access or API keys. Live integrations are smoke-tested by the
documented commands in README.md instead of being faked here.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import animations, assets, blender, config, detect, engines, manifest, meshy, projects, secrets, specification, understanding  # noqa: E402
from game_studio.util import ToolError, safe_join  # noqa: E402

import server  # noqa: E402


def make_glb(path: str, *, with_skin: bool = True, with_animation: bool = True,
             bone_names: tuple[str, ...] = (
                 "Hips", "Spine", "Chest", "Neck", "Head",
                 "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
                 "LeftForeArm", "RightForeArm", "LeftHand", "RightHand",
                 "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg",
                 "LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase")) -> str:
    nodes = [{"name": "Root"}]
    if with_skin:
        nodes += [{"name": name} for name in bone_names]
    document: dict = {
        "asset": {"version": "2.0", "generator": "game-studio-test"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
    }
    if with_skin:
        document["skins"] = [{
            "joints": list(range(1, len(nodes))),
            "skeleton": 1,
        }]
    if with_animation:
        document["animations"] = [{
            "name": "Walk",
            "samplers": [{"input": 0, "output": 1, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {"node": 1, "path": "rotation"}}],
        }]
        document["accessors"] = [
            {"componentType": 5126, "count": 2, "type": "SCALAR", "min": [0.0], "max": [1.0]},
            {"componentType": 5126, "count": 2, "type": "VEC4"},
        ]
    raw = json.dumps(document).encode("utf-8")
    padding = (4 - len(raw) % 4) % 4
    raw += b" " * padding
    total = 12 + 8 + len(raw)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total))
        handle.write(struct.pack("<II", len(raw), 0x4E4F534A))
        handle.write(raw)
    return path


class StudioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="game-studio-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = os.path.join(self.temp.name, "studio-home")
        self.env = mock.patch.dict(os.environ, {
            "GAME_STUDIO_HOME": self.home,
            "MESHY_API_KEY": "",
            "SKETCHFAB_TOKEN": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def path(self, *parts: str) -> str:
        return os.path.join(self.temp.name, *parts)

    def make_unity_project(self, name: str = "UnityGame") -> str:
        project = self.path(name)
        os.makedirs(os.path.join(project, "ProjectSettings"))
        os.makedirs(os.path.join(project, "Packages"))
        os.makedirs(os.path.join(project, "Assets", "Scenes"))
        Path(project, "ProjectSettings", "ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.6.2f1\n", encoding="utf-8")
        Path(project, "Packages", "manifest.json").write_text(json.dumps({
            "dependencies": {"com.unity.render-pipelines.universal": "17.0.3"}
        }), encoding="utf-8")
        Path(project, "ProjectSettings", "ProjectSettings.asset").write_text(
            "productName: Test Game\ncompanyName: Test Studio\n"
            "activeInputHandler: 1\n", encoding="utf-8")
        Path(project, "Assets", "Scenes", "Main.unity").write_text("%YAML 1.1\n", encoding="utf-8")
        return project


class UtilTests(StudioTestCase):
    def test_safe_join_blocks_traversal_and_absolute_paths(self) -> None:
        root = self.path("root")
        os.makedirs(root)
        self.assertTrue(safe_join(root, "Assets/a.glb").endswith("a.glb"))
        with self.assertRaises(ToolError):
            safe_join(root, "../escape.glb")
        with self.assertRaises(ToolError):
            safe_join(root, "C:\\Windows\\system.ini")

    def test_config_is_written_outside_repo_and_audit_reads(self) -> None:
        saved = config.save_config({"selected_engine": "unity", "allow_overwrite": True})
        self.assertEqual(saved["selected_engine"], "unity")
        self.assertTrue(os.path.isfile(config.config_path()))
        stored = json.loads(Path(config.config_path()).read_text(encoding="utf-8"))
        self.assertNotIn("meshy_api_key", json.dumps(stored).lower())
        config.audit("test.action", tool="test", details={"value": 1})
        records = config.read_audit()
        self.assertEqual(records[-1]["action"], "test.action")

    def test_config_rejects_unknown_key(self) -> None:
        with self.assertRaises(ValueError):
            config.save_config({"api_key": "should-not-be-stored"})


class DetectAndProjectTests(StudioTestCase):
    def test_discover_project_by_marker(self) -> None:
        project = self.make_unity_project()
        found = detect.discover_projects([self.temp.name])
        self.assertEqual(found[0]["path"], os.path.abspath(project))
        self.assertEqual(found[0]["engine"], "unity")

    def test_unity_project_inspection(self) -> None:
        project = self.make_unity_project()
        result = projects.inspect_game_project(project)
        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "Test Game")
        self.assertEqual(result["render_pipeline"], "urp")
        self.assertEqual(result["input_system"], "new-input-system")
        self.assertEqual(result["structure"]["scene_count"], 1)

    def test_unknown_project_reports_expectations(self) -> None:
        folder = self.path("empty")
        os.makedirs(folder)
        result = projects.inspect_game_project(folder)
        self.assertFalse(result["ok"])
        self.assertIn("expected", result)


class AssetAndAnimationTests(StudioTestCase):
    def test_obj_validation_counts_triangles_and_uvs(self) -> None:
        obj = self.path("tri.obj")
        Path(obj).write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
            "vt 0 0\nvt 1 0\nvt 0 1\n"
            "vn 0 0 1\n"
            "f 1/1/1 2/2/1 3/3/1\n", encoding="utf-8")
        result = assets.validate_asset_file(obj)
        self.assertTrue(result["ok"])
        self.assertEqual(result["format"], "obj")
        self.assertEqual(result["stats"]["triangles"], 1)
        self.assertTrue(result["stats"]["has_uvs"])

    def test_glb_rig_inspection(self) -> None:
        path = make_glb(self.path("rigged.glb"))
        result = animations.inspect_rig(path)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rig_type"], "humanoid")
        self.assertGreaterEqual(result["joint_count"], 5)
        self.assertEqual(result["animations"][0]["name"], "Walk")
        self.assertAlmostEqual(result["animations"][0]["duration_seconds"], 1.0)

    def test_retarget_requires_matching_skeletons(self) -> None:
        character = make_glb(self.path("character.glb"))
        animation = make_glb(self.path("animation.glb"))
        result = animations.create_retarget_map(character, animation)
        self.assertTrue(result["ok"])
        self.assertTrue(result["compatible"])
        self.assertTrue(result["mapping"])

    def test_unrigged_glb_is_reported_not_crashed(self) -> None:
        path = make_glb(self.path("static.glb"), with_skin=False, with_animation=False)
        result = animations.inspect_rig(path)
        self.assertFalse(result["ok"])
        self.assertEqual(result["rig_type"], "unrigged")
        self.assertIn("file has no skin/armature", result["issues"])

    def test_manual_only_provider_is_not_simulated(self) -> None:
        result = assets.search_assets("tree", provider="unity_asset_store")
        section = result["providers"]["unity_asset_store"]
        self.assertFalse(section["ok"])
        self.assertTrue(section["manual_only"])
        self.assertEqual(section["source_url"], "https://assetstore.unity.com")


class MeshyGuardTests(StudioTestCase):
    def test_balance_without_key_is_not_configured(self) -> None:
        result = meshy.balance()
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "not-configured")
        self.assertIn("meshy_setup_guide", result["remediation"])

    def test_generation_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(ToolError):
            meshy.create_text_to_3d("a wooden crate", confirm=False)
        with self.assertRaises(ToolError):
            meshy.create_rigging(input_task_id="abc", confirm=False)
        with self.assertRaises(ToolError):
            meshy.create_animation(rig_task_id="abc", action_id=1, confirm=False)

    def test_animation_library_reports_missing_key_without_network(self) -> None:
        result = meshy.animation_library()
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "not-configured")


class MeshyKeyTests(StudioTestCase):
    def test_setup_guide_has_real_steps_and_status(self) -> None:
        guide = meshy.setup_guide()
        self.assertTrue(guide["ok"])
        self.assertFalse(guide["configured"])
        self.assertIsNone(guide["source"])
        self.assertIn("https://www.meshy.ai/developers/keys",
                      " ".join(guide["steps"]))
        self.assertIn("MESHY_API_KEY", guide["env_var"])
        self.assertIn("meshy_configure_api_key", guide["next_action"])

    def test_save_load_and_clear_local_key(self) -> None:
        saved = secrets.save_meshy_key("msy_test_key_1234567890")
        self.assertTrue(os.path.isfile(saved["path"]))
        self.assertEqual(secrets.meshy_key_source(), "local-file")
        self.assertEqual(secrets.resolve_meshy_key(), "msy_test_key_1234567890")
        self.assertEqual(meshy.api_key(), "msy_test_key_1234567890")

        cleared = meshy.clear_api_key()
        self.assertTrue(cleared["removed_local_file"])
        self.assertFalse(cleared["configured"])
        self.assertIsNone(secrets.meshy_key_source())

    def test_environment_variable_overrides_local_file(self) -> None:
        secrets.save_meshy_key("msy_local_key_1234567890")
        with mock.patch.dict(os.environ, {"MESHY_API_KEY": "msy_env_key_0987654321"}):
            self.assertEqual(secrets.meshy_key_source(), "environment")
            self.assertEqual(secrets.resolve_meshy_key(), "msy_env_key_0987654321")
            cleared = meshy.clear_api_key()
            self.assertTrue(cleared["removed_local_file"])
            self.assertEqual(secrets.meshy_key_source(), "environment")
            self.assertTrue(cleared["configured"])

    def test_local_key_is_used_by_balance(self) -> None:
        secrets.save_meshy_key("msy_local_key_1234567890")
        with mock.patch.object(meshy, "http_request",
                               return_value={"ok": True, "status": 200,
                                             "payload": {"balance": 120}}) as request:
            result = meshy.balance()
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "connected")
        request.assert_called_once()
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(headers.real_headers()["Authorization"],
                         "Bearer msy_local_key_1234567890")
        # The object handed to callers redacts credentials on inspection.
        self.assertEqual(headers["Authorization"], "******")

    def test_configure_validates_then_saves_without_returning_key(self) -> None:
        with mock.patch.object(meshy, "http_request",
                               return_value={"ok": True, "status": 200,
                                             "payload": {"balance": 80}}):
            result = meshy.configure_api_key("msy_new_key_1234567890", confirm=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["saved"])
        self.assertEqual(result["validation"]["credit_balance"], 80)
        self.assertNotIn("msy_new_key_1234567890", json.dumps(result))
        self.assertEqual(secrets.resolve_meshy_key(), "msy_new_key_1234567890")

    def test_configure_rejected_key_is_not_saved(self) -> None:
        with mock.patch.object(meshy, "http_request",
                               return_value={"ok": False, "status": 401,
                                             "payload": {"message": "invalid key"}}):
            result = meshy.configure_api_key("msy_bad_key_1234567890", confirm=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["saved"])
        self.assertEqual(result["status"], 401)
        self.assertFalse(os.path.exists(secrets.meshy_key_file()))

    def test_configure_requires_confirmation(self) -> None:
        with self.assertRaises(ToolError):
            meshy.configure_api_key("msy_test_key_1234567890", confirm=False)
        self.assertFalse(os.path.exists(secrets.meshy_key_file()))

    def test_configure_rejects_control_characters_before_network(self) -> None:
        with self.assertRaises(ToolError):
            secrets.validate_api_key("msy_bad\nkey_1234567890")
        with self.assertRaises(ToolError):
            secrets.validate_api_key("short")

    def test_provider_state_reflects_local_key(self) -> None:
        before = next(p for p in assets.providers()["providers"] if p["id"] == "meshy")
        self.assertEqual(before["state"], "not-configured")
        secrets.save_meshy_key("msy_test_key_1234567890")
        after = next(p for p in assets.providers()["providers"] if p["id"] == "meshy")
        self.assertEqual(after["state"], "configured")
        self.assertEqual(after["setup_tool"], "meshy_setup_guide")


class BlenderBlockoutTests(StudioTestCase):
    def test_render_only_uses_and_removes_temporary_blend(self) -> None:
        out_png = self.path("render.png")
        captured = {}

        def fake_run(script, *, args=None, timeout=900):
            captured.update(args)
            with open(args["save_blend"], "wb") as handle:
                handle.write(b"blend")
            return {"ok": True}

        def fake_render(blend, png, *, confirm_overwrite=False):
            self.assertTrue(os.path.isfile(blend))
            with open(png, "wb") as handle:
                handle.write(b"png")
            return {"ok": True, "result": {"path": png}}

        with mock.patch.object(blender, "run_blender", side_effect=fake_run), \
             mock.patch.object(blender, "render_preview", side_effect=fake_render):
            result = blender.create_environment_blockout(preset="alpine",
                                                         render_png=out_png)
        self.assertTrue(result["ok"], result)
        self.assertIn("render", result["artifacts"])
        self.assertNotIn("blend", result["artifacts"])
        self.assertTrue(os.path.isfile(out_png))
        self.assertFalse(os.path.exists(captured["save_blend"]))


class EngineStagingTests(StudioTestCase):
    def test_stage_and_verify_unity_asset(self) -> None:
        project = self.make_unity_project()
        asset = make_glb(self.path("prop.glb"))
        staged = engines.stage_asset(asset, project, engine="unity", confirm=True)
        self.assertTrue(staged["ok"])
        self.assertTrue(os.path.isfile(staged["destination"]))
        self.assertEqual(staged["import_state"], "staged-not-imported")
        relative = staged["relative_path"]

        before = engines.verify_staged_import(project, relative)
        self.assertFalse(before["ok"])
        self.assertIn(before["state"], ("staged-not-imported", "project-not-imported"))

        # Simulate the import marker Unity writes. The verifier only reports the marker.
        Path(staged["destination"] + ".meta").write_text("fileFormatVersion: 2\n", encoding="utf-8")
        after = engines.verify_staged_import(project, relative)
        self.assertTrue(after["ok"])
        self.assertEqual(after["state"], "imported")
        self.assertTrue(after["evidence"]["hash_matches_staged_source"])

    def test_stage_requires_confirmation_and_respects_overwrite(self) -> None:
        project = self.make_unity_project()
        asset = make_glb(self.path("prop.glb"))
        with self.assertRaises(ToolError):
            engines.stage_asset(asset, project, confirm=False)
        engines.stage_asset(asset, project, relative_path="Imported/prop.glb", confirm=True)
        with self.assertRaises(ToolError):
            engines.stage_asset(asset, project, relative_path="Imported/prop.glb", confirm=True)
        replaced = engines.stage_asset(asset, project, relative_path="Imported/prop.glb",
                                       confirm=True, confirm_overwrite=True)
        self.assertTrue(replaced["ok"])

    def test_stage_rejects_engine_mismatch(self) -> None:
        project = self.make_unity_project()
        asset = make_glb(self.path("prop.glb"))
        with self.assertRaises(ToolError):
            engines.stage_asset(asset, project, engine="godot", confirm=True)

    def test_unreal_automation_is_reported_as_staged_only(self) -> None:
        project = self.path("UnrealGame")
        os.makedirs(os.path.join(project, "Content"))
        Path(project, "UnrealGame.uproject").write_text(
            json.dumps({"FileVersion": 3, "EngineAssociation": "5.4"}), encoding="utf-8")
        result = engines.unreal_stage_only(project)
        self.assertTrue(result["ok"])
        self.assertEqual(result["automation"], "staged-only")
        self.assertIn("build", result["not_supported"])

    def test_engine_build_requires_confirmation_and_arguments(self) -> None:
        project = self.make_unity_project()
        with self.assertRaises(ToolError):
            engines.engine_build("unity", project, target="StandaloneWindows64",
                                 output_path=self.path("Build", "Game.exe"), confirm=False)
        with self.assertRaises(ToolError):
            engines.engine_build("unity", project, confirm=True)


class ServerProtocolTests(StudioTestCase):
    def call(self, name: str, arguments: dict | None = None) -> dict:
        response = server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        self.assertIsNotNone(response)
        return response["result"]

    def test_tools_list_is_unique_and_has_handlers(self) -> None:
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = response["result"]["tools"]
        names = [tool["name"] for tool in tools]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(server.HANDLERS))
        for tool in tools:
            self.assertTrue(tool["description"])
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_unknown_tool_returns_tool_error(self) -> None:
        result = self.call("does_not_exist")
        self.assertTrue(result["isError"])
        self.assertIn("unknown tool", result["content"][0]["text"])

    def test_tool_error_is_clean_json(self) -> None:
        result = self.call("inspect_game_project", {})
        self.assertTrue(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertFalse(payload["ok"])
        self.assertIn("project_path is required", payload["error"])

    def test_initialize_and_ping(self) -> None:
        init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "universal-game-studio")
        self.assertEqual(server.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
                         {"jsonrpc": "2.0", "id": 2, "result": {}})


class UnderstandingTests(StudioTestCase):
    def test_roman_urdu_request_is_understood_and_traceable(self) -> None:
        result = understanding.analyze_request(
            "Bhai ek realistic 3D monkey adventure game banao jungle mein. "
            "Bandar ped par charh sake aur pani mein tair sake.")
        self.assertEqual(result["understanding"]["dimension"], ["3d"])
        self.assertEqual(result["understanding"]["game_genre"], ["adventure"])
        self.assertEqual(result["understanding"]["characters"], ["monkey"])
        self.assertIn("jungle", result["understanding"]["environment"])
        self.assertIn("climbing", result["understanding"]["mechanics"])
        self.assertIn("swimming", result["understanding"]["mechanics"])
        self.assertIn("roman-urdu", result["language"]["detected"])
        self.assertTrue(result["language"]["mixed"])
        self.assertTrue(all(item["source_text"] for item in
                            result["requirements"]["explicit"]))
        self.assertTrue(result["requirements"]["implied"])

    def test_exclusion_is_not_turned_into_a_requirement(self) -> None:
        result = understanding.analyze_request(
            "Make a 3D monkey adventure game in a jungle. No guns.")
        self.assertFalse(any("gun" in item["statement"].lower()
                             for item in result["requirements"]["explicit"]))
        self.assertEqual([item["value"] for item in result["exclusions"]], ["weapons"])
        self.assertEqual(result["conflicts"], [])

    def test_multiple_engines_and_style_conflict_are_reported(self) -> None:
        result = understanding.analyze_request(
            "Make a 2D realistic pixel art platformer in Godot and Unreal. "
            "Without multiplayer.")
        types = {item["type"] for item in result["conflicts"]}
        self.assertIn("multiple_engines", types)
        self.assertIn("art_style_conflict", types)
        self.assertNotIn("requested_and_excluded", types)

    def test_questions_are_material_and_bounded(self) -> None:
        result = understanding.analyze_request("Make a game")
        self.assertLessEqual(len(result["questions"]), 5)
        topics = {item["topic"] for item in result["unresolved"]}
        self.assertIn("engine", topics)
        self.assertIn("dimension", topics)
        self.assertTrue(all(item["material"] for item in result["unresolved"]
                            if item["topic"] in ("engine", "platform", "dimension")))


class SpecificationTests(StudioTestCase):
    def spec(self, **overrides):
        request = overrides.pop("request", (
            "Make a realistic 3D monkey adventure game in a jungle. "
            "The monkey can climb and swim. No guns."))
        return specification.create_specification(
            request=request, project_name="Monkey Quest",
            installed_engines=overrides.pop("installed_engines", ["unity"]),
            **overrides)

    def test_spec_separates_explicit_from_assumptions(self) -> None:
        spec = self.spec(engine="unity", platform="pc")
        explicit = [r for r in spec["requirements"] if r["classification"] == "explicit"]
        self.assertTrue(explicit)
        self.assertIn("assumptions", spec)
        self.assertIn("character-source", {item["topic"] for item in spec["unresolved"]})
        self.assertEqual(spec["status"], "awaiting-approval")

    def test_dependency_graph_is_acyclic_and_ordered(self) -> None:
        spec = self.spec(engine="unity", platform="pc")
        graph = spec["dependency_graph"]
        self.assertEqual(graph["cycles"], [])
        order = graph["topological_order"]
        self.assertEqual(len(order), len(graph["nodes"]))
        position = {node_id: index for index, node_id in enumerate(order)}
        for edge in graph["edges"]:
            self.assertLess(position[edge["from"]], position[edge["to"]])
        self.assertTrue(graph["nodes"][0]["depends_on"] == [])

    def test_requested_but_missing_engine_is_reported(self) -> None:
        spec = self.spec(request="Make a 3D racing game in Unreal.", engine="unreal",
                         installed_engines=["unity"], platform="pc")
        self.assertEqual(spec["engine"]["selected"], "unreal")
        self.assertFalse(spec["engine"]["verified"])
        self.assertIn("not detected", spec["engine"]["warning"])

    def test_non_humanoid_character_gets_a_compatible_rig(self) -> None:
        spec = self.spec(engine="unity", platform="pc")
        monkey = spec["characters"][0]
        self.assertIn("quadruped", monkey["rig_requirement"])
        self.assertIn("humanoid", monkey["retargeting_warning"].lower())
        self.assertIn("climb", monkey["animation_requirements"])
        self.assertEqual(monkey["gameplay_role"], "player")

    def test_acceptance_tests_cover_explicit_requirements(self) -> None:
        spec = self.spec(engine="unity", platform="pc")
        covered = {test["requirement_id"] for test in spec["acceptance_tests"]}
        for requirement in spec["requirements"]:
            if requirement["classification"] == "explicit":
                self.assertIn(requirement["id"], covered)


class ProjectMemoryTests(StudioTestCase):
    def make_spec(self) -> dict:
        return specification.create_specification(
            request="Make a 3D monkey adventure game in a jungle. No guns.",
            project_name="Memory Game", engine="unity", platform="pc", approved=True,
            installed_engines=["unity"])

    def init(self, project: str, spec: dict) -> dict:
        return manifest.init_manifest(project, spec, confirm=True)

    def test_manifest_requires_confirmation_and_is_project_local(self) -> None:
        project = self.make_unity_project("MemoryUnity")
        spec = self.make_spec()
        with self.assertRaises(ToolError):
            manifest.init_manifest(project, spec, confirm=False)
        result = self.init(project, spec)
        self.assertTrue(result["ok"])
        path = os.path.join(project, ".game-studio", "manifest.json")
        self.assertEqual(result["manifest_path"], path)
        self.assertTrue(os.path.isfile(path))
        with self.assertRaises(ToolError):
            self.init(project, spec)

    def test_manifest_survives_reload_with_statuses_and_decisions(self) -> None:
        project = self.make_unity_project("MemoryReload")
        spec = self.make_spec()
        self.init(project, spec)
        requirement_id = spec["requirements"][0]["id"]
        evidence_file = os.path.join(project, "Assets", "test.log")
        Path(evidence_file).write_text("test output\n", encoding="utf-8")
        manifest.update_requirement_status(
            project, requirement_id, "tested",
            evidence=[{"kind": "test", "reference": "Assets/test.log"}], confirm=True)
        manifest.record_decision(project, topic="engine", decision="Unity 6",
                                 approved=True, confirm=True)
        # Simulate a restart: read everything back from disk only.
        progress = manifest.track_progress(project)
        view = manifest.load_manifest_view(project)
        self.assertEqual(progress["coverage"]["tested"], 1)
        self.assertEqual(view["decisions"][0]["decision"], "Unity 6")
        self.assertEqual(view["project_id"], spec["spec_id"])

    def test_status_guards_reject_unsupported_claims(self) -> None:
        project = self.make_unity_project("MemoryGuards")
        spec = self.make_spec()
        self.init(project, spec)
        requirement_id = spec["requirements"][0]["id"]
        with self.assertRaises(ToolError):
            manifest.update_requirement_status(project, requirement_id, "verified",
                                              confirm=True)
        with self.assertRaises(ToolError):
            manifest.update_requirement_status(
                project, requirement_id, "tested",
                evidence=[{"kind": "file", "reference": "Assets/x.log"}], confirm=True)
        with self.assertRaises(ToolError):
            manifest.update_requirement_status(
                project, requirement_id, "verified",
                evidence=[{"kind": "build", "reference": "Builds/missing.exe"}],
                confirm=True)

    def test_comparison_flags_a_tampered_verified_claim(self) -> None:
        project = self.make_unity_project("MemoryTamper")
        spec = self.make_spec()
        self.init(project, spec)
        path = os.path.join(project, ".game-studio", "manifest.json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["requirements"][0]["status"] = "verified"
        data["requirements"][0]["evidence"] = []
        Path(path).write_text(json.dumps(data), encoding="utf-8")
        result = manifest.compare_project_against_requirements(project)
        self.assertEqual(result["overall"], "blocked")
        self.assertIn(data["requirements"][0]["id"], result["invalid_claims"])

    def test_manifest_refuses_credential_like_values(self) -> None:
        project = self.make_unity_project("MemorySecret")
        spec = self.make_spec()
        self.init(project, spec)
        with self.assertRaises(ToolError):
            manifest.record_decision(
                project, topic="provider",
                decision="MESHY_API_KEY=sk-abcdefghijklmnopqrstuvwx",
                confirm=True)


class UnderstandingToolsTests(StudioTestCase):
    def call(self, name: str, arguments: dict) -> dict:
        response = server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        return json.loads(response["result"]["content"][0]["text"])

    def test_analyze_tool_is_read_only_and_returns_classification(self) -> None:
        payload = self.call("analyze_game_request",
                            {"request": "Make a 3D monkey adventure game in a jungle."})
        self.assertTrue(payload["ok"])
        self.assertIn("explicit", payload["requirements"])
        self.assertEqual(payload["understanding"]["characters"], ["monkey"])

    def test_spec_and_manifest_tools_round_trip(self) -> None:
        project = self.make_unity_project("ToolMemory")
        spec = self.call("create_game_specification", {
            "request": "Make a 3D platformer in Unity with 3 levels.",
            "project_name": "Tool Game", "engine": "unity", "platform": "pc",
            "installed_engines": ["unity"], "approved": True,
        })
        self.assertTrue(spec["ok"])
        initialized = self.call("init_project_manifest", {
            "project_path": project, "spec": spec, "confirm": True})
        self.assertTrue(initialized["ok"])
        progress = self.call("track_project_progress", {"project_path": project})
        self.assertEqual(progress["coverage"]["total"], len(spec["requirements"]))
        loaded = self.call("get_project_manifest", {"project_path": project})
        self.assertEqual(loaded["project_id"], spec["spec_id"])

    def test_new_tools_are_registered(self) -> None:
        names = {tool["name"] for tool in server.TOOLS}
        for name in ("analyze_game_request", "create_game_specification",
                     "init_project_manifest", "get_project_manifest",
                     "update_requirement_status", "record_project_decision",
                     "track_project_progress",
                     "compare_project_against_requirements"):
            self.assertIn(name, names)
            self.assertIn(name, server.HANDLERS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
