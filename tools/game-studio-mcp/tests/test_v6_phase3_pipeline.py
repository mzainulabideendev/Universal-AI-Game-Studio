"""V6 Phase 3 character pipeline tests.

Unit tests mock the Blender subprocess and validate stage/evidence logic
offline. One integration test executes the real local Blender install when it
is present and is explicitly marked by name.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_studio import character_pipeline, character_spec  # noqa: E402
from game_studio.util import ToolError  # noqa: E402

import server  # noqa: E402

BLENDER = r"D:\blender data\blender.exe"
REQUEST = (
    "Create a stylized 3D jungle monkey character for a professional third-person "
    "adventure game with expressive eyes, brown fur, hands, feet and idle, walk, "
    "run and jump animations."
)


def make_png(path: Path, width: int, height: int) -> None:
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b""))


def make_glb(gltf: dict, bin_chunk: bytes = b"") -> bytes:
    payload = json.dumps(gltf).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    body = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    if bin_chunk:
        bin_chunk += b"\x00" * ((4 - len(bin_chunk) % 4) % 4)
        body += struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def sample_gltf() -> dict:
    return {
        "asset": {"version": "2.0", "generator": "test"},
        "accessors": [
            {"count": 9, "type": "VEC3", "min": [-1, -1, -1], "max": [1, 1, 1]},
            {"count": 9, "type": "SCALAR"},
        ],
        "images": [{"name": "base", "bufferView": 0}],
        "textures": [{"source": 0}],
        "materials": [{"name": "M", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "meshes": [{"name": "Mesh", "primitives": [
            {"indices": 1, "material": 0, "attributes": {"POSITION": 0}}]}],
        "animations": [{"name": "Idle", "channels": [], "samplers": []}],
        "skins": [{"joints": [0, 1, 2]}],
        "nodes": [{"name": "root"}],
    }


def artifacts(root: Path) -> dict:
    blend = root / "JungleMonkey.blend"
    glb = root / "JungleMonkey.glb"
    gltf = root / "JungleMonkey.gltf"
    fbx = root / "JungleMonkey.fbx"
    preview = root / "preview.png"
    blend.write_bytes(b"BLENDER-test")
    glb.write_bytes(make_glb(sample_gltf()))
    gltf.write_text(json.dumps(sample_gltf()), encoding="utf-8")
    fbx.write_bytes(b"FBX-test")
    make_png(preview, 8, 8)
    return {"blend": str(blend), "glb": str(glb), "gltf": str(gltf),
            "fbx": str(fbx), "preview": str(preview)}


def fake_payload(root: Path, spec: dict, *, colorspace: str = "sRGB",
                 image_exists: bool = True) -> dict:
    texture = root / "textures" / "monkey_fur_basecolor.png"
    make_png(texture, spec["textures"]["resolution"], spec["textures"]["resolution"])
    paths = artifacts(root)
    anims = []
    for animation in spec["animations"]:
        anims.append({"name": animation["name"].title(), "frame_range": [1.0, 20.0],
                      "fcurves": 3})
    return {
        "name": spec["name"], "tier": spec["quality_tier"],
        "blend": paths["blend"], "glb": paths["glb"], "gltf": paths["gltf"],
        "fbx": paths["fbx"],
        "preview": paths["preview"], "render_engine": "BLENDER_EEVEE_NEXT",
        "render_error": None, "export_errors": [],
        "geometry": {
            "vertices": 1000, "polygons": 900, "triangles": 1800,
            "non_manifold_edges": 0, "loose_vertices": 0, "degenerate_faces": 0,
            "materials": 2, "uv_layers": ["UVMap"], "uv_coverage": 0.42,
        },
        "rig": {
            "armature": "Armature", "bones": 10,
            "bone_names": ["root", "pelvis", "spine", "head"],
            "weight_mode": "automatic", "weighted_vertices": 1000,
            "weighted_ratio": 1.0, "min_weight_sum": 1.0, "max_weight_sum": 1.0,
            "vertex_groups": 10, "mesh_parent": "Armature",
            "armature_modifier": True,
        },
        "animations": anims,
        "requested_animations": [a["name"] for a in spec["animations"]],
        "materials": [
            {
                "name": "M_Monkey_Fur",
                "node_types": ["BSDF_PRINCIPLED", "TEX_IMAGE"],
                "images": [{
                    "name": "T_Monkey_Fur_BaseColor",
                    "filepath": str(texture),
                    "exists": image_exists,
                    "size": [spec["textures"]["resolution"]] * 2,
                    "colorspace": colorspace,
                    "packed": False,
                }],
                "channels": {"base_color": "texture", "roughness": "texture",
                             "normal": "texture", "metallic": "constant",
                             "ao": "absent", "emission": "absent",
                             "opacity": "absent"},
                "declared_channels": {
                    "base_color": "generated", "roughness": "generated",
                    "normal": "generated", "metallic": "constant",
                    "ao": "absent", "emission": "absent", "opacity": "absent",
                },
            },
            {
                "name": "M_Monkey_Skin", "node_types": ["BSDF_PRINCIPLED"],
                "images": [], "channels": {key: "absent" for key in (
                    "base_color", "roughness", "normal", "metallic", "ao",
                    "emission", "opacity")},
                "declared_channels": {key: "absent" for key in (
                    "base_color", "roughness", "normal", "metallic", "ao",
                    "emission", "opacity")},
            },
        ],
        "images": [{"name": "T_Monkey_Fur_BaseColor", "filepath": str(texture),
                    "size": [spec["textures"]["resolution"]] * 2,
                    "packed": False, "colorspace": colorspace,
                    "missing": not image_exists}],
        "textures_dir": str(root / "textures"),
        "bounds": {"dimensions": [0.9, 0.6, 1.6]},
        "quality": {"sphere_segments": spec["geometry"]["sphere_segments"],
                    "texture_resolution": spec["textures"]["resolution"]},
        "seed": spec["provenance"]["seed"],
        "generation": "procedural-blender", "external_assets_used": False,
    }


def blender_result(payload: dict, ok: bool = True) -> dict:
    return {"ok": ok, "result": payload, "exit_code": 0, "duration_ms": 1200,
            "stdout_tail": "", "stderr_tail": "", "error": None if ok else "failed"}


class GlbParserTests(unittest.TestCase):
    def test_valid_glb_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.glb"
            path.write_bytes(make_glb(sample_gltf()))
            result = character_pipeline.validate_glb(str(path))
        self.assertTrue(result["ok"])
        self.assertEqual(result["meshes"], 1)
        self.assertEqual(result["triangles"], 3)
        self.assertEqual(result["materials"], 1)
        self.assertEqual(result["animations"], 1)
        self.assertEqual(result["skins"], 1)
        self.assertEqual(result["joints"], 3)
        self.assertTrue(result["sha256"])

    def test_missing_file_is_reported(self) -> None:
        result = character_pipeline.validate_glb("Z:/does/not/exist.glb")
        self.assertFalse(result["ok"])
        self.assertIn("does not exist", result["errors"][0])

    def test_non_glb_and_empty_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.glb"
            bad.write_bytes(b"not a glb")
            result = character_pipeline.validate_glb(str(bad))
            self.assertFalse(result["ok"])
            empty = Path(tmp) / "empty.glb"
            empty.write_bytes(b"")
            self.assertFalse(character_pipeline.validate_glb(str(empty))["ok"])

    def test_missing_external_image_is_an_error(self) -> None:
        gltf = sample_gltf()
        gltf["images"] = [{"uri": "textures/missing.png"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.glb"
            path.write_bytes(make_glb(gltf))
            result = character_pipeline.validate_glb(str(path))
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing external images" in error
                            for error in result["errors"]))

    def test_png_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.png"
            make_png(path, 256, 128)
            self.assertEqual(character_pipeline.png_dimensions(str(path)), (256, 128))
            text = Path(tmp) / "t.txt"
            text.write_text("nope")
            self.assertIsNone(character_pipeline.png_dimensions(str(text)))


class GltfParserTests(unittest.TestCase):
    def test_separated_gltf_with_external_buffer_and_image_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = sample_gltf()
            document["buffers"] = [{"uri": "JungleMonkey.bin", "byteLength": 4}]
            document["images"] = [{"uri": "textures/base.png"}]
            make_png(root / "textures" / "base.png", 8, 8)
            (root / "JungleMonkey.bin").write_bytes(b"\x00" * 4)
            path = root / "JungleMonkey.gltf"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = character_pipeline.validate_gltf(str(path))
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["buffers"], 1)
        self.assertEqual(result["external_buffers"], ["JungleMonkey.bin"])
        self.assertEqual(result["triangles"], 3)
        self.assertEqual(result["skins"], 1)

    def test_separated_gltf_reports_missing_buffer_and_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = sample_gltf()
            document["buffers"] = [{"uri": "missing.bin", "byteLength": 4}]
            document["images"] = [{"uri": "textures/missing.png"}]
            path = root / "x.gltf"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = character_pipeline.validate_gltf(str(path))
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing external buffers" in error
                            for error in result["errors"]))
        self.assertTrue(any("missing external images" in error
                            for error in result["errors"]))

    def test_invalid_gltf_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.gltf"
            path.write_text("{not json", encoding="utf-8")
            result = character_pipeline.validate_gltf(str(path))
        self.assertFalse(result["ok"])
        self.assertTrue(any("invalid glTF JSON" in error
                            for error in result["errors"]))


class BuildStageTests(unittest.TestCase):
    def _build(self, *, colorspace="sRGB", image_exists=True, run_ok=True,
               payload_mutator=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
        payload = fake_payload(root, spec, colorspace=colorspace,
                               image_exists=image_exists)
        if payload_mutator:
            payload_mutator(payload)
        with mock.patch.object(character_pipeline, "resolve_blender_executable",
                               return_value=BLENDER), \
             mock.patch.object(character_pipeline.blender, "run_blender",
                               return_value=blender_result(payload, ok=run_ok)):
            return character_pipeline.build_character(spec, str(root))

    def test_build_collects_real_stage_evidence(self) -> None:
        report = self._build()
        self.assertEqual(report["status"], "built")
        self.assertTrue(report["ok"])
        self.assertFalse(report["failed_stages"])
        for stage in ("geometry-validated", "materials-validated",
                      "uv-validated", "rig-validated", "animations-created",
                      "blend-saved", "glb-exported", "gltf-exported",
                      "fbx-exported", "glb-validated", "gltf-validated",
                      "preview-rendered"):
            self.assertEqual(report["stages"][stage]["status"], "passed", stage)
        self.assertTrue(report["glb_validation"]["ok"])
        self.assertFalse(report["ai_generated"])
        self.assertFalse(report["external_assets_used"])

    def test_wrong_texture_colorspace_fails_validation(self) -> None:
        report = self._build(colorspace="Linear")
        self.assertEqual(report["status"], "partial")
        self.assertIn("materials-validated", report["failed_stages"])
        self.assertTrue(any("colorspace" in issue for issue in
                            report["stages"]["materials-validated"]["issues"]))

    def test_missing_texture_file_fails_validation(self) -> None:
        report = self._build(image_exists=False)
        self.assertIn("materials-validated", report["failed_stages"])
        self.assertTrue(any("missing image" in issue for issue in
                            report["stages"]["materials-validated"]["issues"]))

    def test_declared_texture_that_is_constant_fails(self) -> None:
        def mutate(payload):
            payload["materials"][0]["channels"]["normal"] = "absent"
        report = self._build(payload_mutator=mutate)
        self.assertIn("materials-validated", report["failed_stages"])

    def test_missing_uv_map_fails_geometry(self) -> None:
        def mutate(payload):
            payload["geometry"]["uv_layers"] = []
            payload["geometry"]["uv_coverage"] = 0.0
        report = self._build(payload_mutator=mutate)
        self.assertIn("geometry-validated", report["failed_stages"])
        self.assertIn("uv-validated", report["failed_stages"])

    def test_unweighted_mesh_fails_rig(self) -> None:
        def mutate(payload):
            payload["rig"]["weighted_ratio"] = 0.4
        report = self._build(payload_mutator=mutate)
        self.assertIn("rig-validated", report["failed_stages"])

    def test_requested_animation_missing_fails(self) -> None:
        def mutate(payload):
            payload["animations"] = [{"name": "Idle", "frame_range": [1, 10],
                                      "fcurves": 2}]
        report = self._build(payload_mutator=mutate)
        self.assertIn("animations-created", report["failed_stages"])

    def test_blender_failure_never_reports_success(self) -> None:
        report = self._build(run_ok=False)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["ok"])
        self.assertIn("blender-build", report["stages"])

    def test_missing_blender_executable(self) -> None:
        spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(character_pipeline, "resolve_blender_executable",
                               return_value=None):
            report = character_pipeline.build_character(spec, tmp)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "failed")
        self.assertIn("not found", report["errors"][0])

    def test_invalid_specification_is_rejected_before_blender(self) -> None:
        spec = character_spec.build_character_spec(REQUEST)
        spec["quality_tier"] = "cinematic"
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(character_pipeline.blender, "run_blender") as run:
            with self.assertRaises(ToolError):
                character_pipeline.build_character(spec, tmp)
            run.assert_not_called()


class ReimportTests(unittest.TestCase):
    def test_reimport_checks_are_derived_from_real_inspection(self) -> None:
        inspection = {
            "imported_objects": ["JungleMonkey", "Armature"],
            "mesh_count": 1,
            "meshes": [{"name": "JungleMonkey", "materials": ["M"],
                        "uv_layers": ["UVMap"], "armature_modifiers": ["ARMATURE"]}],
            "triangles": 1800, "armature_count": 1, "bone_count": 10,
            "actions": [{"name": "Idle", "fcurves": 3}],
            "animated_actions": ["Idle"], "material_count": 1,
            "missing_images": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            glb = Path(tmp) / "x.glb"
            glb.write_bytes(make_glb(sample_gltf()))
            with mock.patch.object(character_pipeline, "resolve_blender_executable",
                                   return_value=BLENDER), \
                 mock.patch.object(character_pipeline.blender, "run_blender",
                                   return_value=blender_result(inspection)):
                report = character_pipeline.reimport_and_validate(str(glb), tmp)
        self.assertTrue(report["ok"])
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["metrics"]["triangles"], 1800)

    def test_missing_uv_or_skin_fails_reimport(self) -> None:
        inspection = {
            "imported_objects": ["JungleMonkey"], "mesh_count": 1,
            "meshes": [{"name": "JungleMonkey", "materials": [], "uv_layers": [],
                        "armature_modifiers": []}],
            "armature_count": 0, "bone_count": 0, "actions": [],
            "animated_actions": [], "material_count": 0, "missing_images": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            glb = Path(tmp) / "x.glb"
            glb.write_bytes(make_glb(sample_gltf()))
            with mock.patch.object(character_pipeline, "resolve_blender_executable",
                                   return_value=BLENDER), \
                 mock.patch.object(character_pipeline.blender, "run_blender",
                                   return_value=blender_result(inspection)):
                report = character_pipeline.reimport_and_validate(str(glb), tmp)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["imported_materials"])
        self.assertFalse(report["checks"]["imported_armature"])
        self.assertFalse(report["checks"]["skinned_mesh"])


class ManifestTests(unittest.TestCase):
    def test_manifest_captures_provenance_hashes_and_engine_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
            payload = fake_payload(root, spec)
            build = {
                "status": "built", "blender_executed": True,
                "blender_executable": BLENDER, "blender_exit_code": 0,
                "failed_stages": [],
                "artifacts": {name: character_pipeline._artifact_entry(path)
                              for name, path in artifacts(root).items()},
                "textures": [], "glb_validation": character_pipeline.validate_glb(
                    artifacts(root)["glb"]),
                "stages": {name: {"status": "passed"} for name in (
                    "geometry-validated", "materials-validated", "rig-validated",
                    "animations-created", "uv-validated")},
            }
            manifest = character_pipeline.asset_manifest(
                spec, build, reimport={"ok": True})
        self.assertEqual(manifest["license_id"], "project-original-1.0")
        self.assertFalse(manifest["attribution_required"])
        self.assertFalse(manifest["ai_generated"])
        self.assertTrue(manifest["procedural"])
        self.assertEqual(manifest["download_status"], "not-downloaded")
        for artifact in manifest["artifacts"]:
            self.assertTrue(artifact["sha256"])
            self.assertGreater(artifact["bytes"], 0)
        for engine in ("unity", "godot", "unreal"):
            entry = manifest["engine_compatibility"][engine]
            self.assertFalse(entry["integration_verified"])
            self.assertEqual(entry["status"], "export-prepared-unverified")
            self.assertTrue(entry["rig"])
            self.assertTrue(entry["animations"])

    def test_manifest_does_not_upgrade_a_failed_build(self) -> None:
        spec = character_spec.build_character_spec(REQUEST)
        manifest = character_pipeline.asset_manifest(
            spec, {"status": "partial", "failed_stages": ["materials-validated"],
                   "artifacts": {}, "textures": [], "stages": {}},
            reimport={"ok": False})
        self.assertEqual(manifest["validation"]["build_status"], "partial")
        self.assertFalse(manifest["validation"]["reimport"])
        self.assertEqual(manifest["validation"]["materials"], None)


class PipelineOrchestrationTests(unittest.TestCase):
    def test_pipeline_completes_only_when_every_required_stage_passes(self) -> None:
        spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
        stages = {name: {"status": "passed"} for name in character_pipeline.REQUIRED_STAGES}
        build = {
            "status": "built", "artifacts": {
                "blend": {"exists": True, "path": "a.blend"},
                "glb": {"exists": True, "path": "a.glb"},
                "preview": {"exists": True, "path": "preview.png"},
            },
            "stages": dict(stages), "glb_validation": {"ok": True},
            "blender_executed": True,
        }
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(character_pipeline, "build_character",
                               return_value=build), \
             mock.patch.object(character_pipeline, "reimport_and_validate",
                               return_value={"ok": True, "checks": {}}):
            report = character_pipeline.run_pipeline(spec, tmp)
        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["ok"])
        self.assertFalse(report["generation_classification"]["ai_generated_assets"])
        self.assertFalse(report["generation_classification"]["production_ready"])

    def test_pipeline_is_partial_when_reimport_fails(self) -> None:
        spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
        stages = {name: {"status": "passed"} for name in character_pipeline.REQUIRED_STAGES}
        build = {
            "status": "built", "artifacts": {
                "blend": {"exists": True, "path": "a.blend"},
                "glb": {"exists": True, "path": "a.glb"},
                "preview": {"exists": True, "path": "preview.png"},
            },
            "stages": dict(stages), "glb_validation": {"ok": True},
            "blender_executed": True,
        }
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(character_pipeline, "build_character",
                               return_value=build), \
             mock.patch.object(character_pipeline, "reimport_and_validate",
                               return_value={"ok": False, "checks": {
                                   "imported_uvs": False}}):
            report = character_pipeline.run_pipeline(spec, tmp)
        self.assertEqual(report["status"], "partial")
        self.assertFalse(report["ok"])
        self.assertIn("glb-reimported", report["failed_stages"])

    def test_pipeline_rejects_an_invalid_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ToolError):
                character_pipeline.run_pipeline({"id": "bad"}, tmp)


class McpTests(unittest.TestCase):
    def test_tools_and_handlers_stay_in_parity(self) -> None:
        names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(server.HANDLERS))
        for name in ("character_generate_asset", "character_capabilities"):
            self.assertIn(name, names)
        for tool in server.TOOLS:
            self.assertEqual(tool["inputSchema"].get("type"), "object")

    def test_generate_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(ToolError):
            server.tool_character_generate({
                "description": REQUEST, "output_dir": "C:/tmp/x"})

    def test_generate_builds_a_valid_spec_and_calls_the_pipeline(self) -> None:
        with mock.patch.object(server.character_pipeline, "run_pipeline",
                               return_value={"status": "completed"}) as run:
            result = server.tool_character_generate({
                "description": REQUEST, "quality_tier": "high",
                "output_dir": "C:/tmp/x", "confirm": True,
                "animations": ["idle", "walk"], "target_engine": "godot"})
        self.assertEqual(result["status"], "completed")
        spec = run.call_args.args[0]
        self.assertEqual(character_spec.validate_character_spec(spec), [])
        self.assertEqual(spec["quality_tier"], "high")
        self.assertEqual([a["name"] for a in spec["animations"]], ["idle", "walk"])
        self.assertEqual(spec["export"]["target_engine"], "godot")

    def test_unknown_quality_tier_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            server.tool_character_generate({
                "description": REQUEST, "quality_tier": "ultra",
                "output_dir": "C:/tmp/x", "confirm": True})

    def test_capability_tool_reports_unauthorized_generators(self) -> None:
        report = server.tool_character_capabilities({})
        self.assertIn("image_generation", report["authorized_missing"])
        self.assertEqual(report["authorized_external_generators"], [])

    def test_generate_tool_schema_is_strict(self) -> None:
        tool = next(t for t in server.TOOLS
                    if t["name"] == "character_generate_asset")
        schema = tool["inputSchema"]
        self.assertEqual(schema["required"],
                         ["description", "output_dir", "confirm"])
        self.assertEqual(schema["properties"]["quality_tier"]["enum"],
                         ["low", "medium", "high"])
        self.assertEqual(schema["properties"]["target_engine"]["enum"],
                         ["unity", "godot", "unreal"])


class ProtectedBaselineTests(unittest.TestCase):
    def test_v4_and_v5_protected_hashes_are_unchanged(self) -> None:
        baseline = json.loads((ROOT.parents[1] / "reports" /
                               "v6-phase0-baseline.json").read_text(encoding="utf-8"))
        from game_studio.util import sha256_file
        v4 = baseline["v4_checkpoint"]["files"]
        for relative, entry in v4.items():
            self.assertEqual(sha256_file(str(ROOT.parents[1] / relative)),
                             entry["sha256"], relative)
        v5 = baseline["v5_checkpoint"]["artifacts"]
        for relative, entry in v5.items():
            path = ROOT.parents[1] / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(sha256_file(str(path)), entry["sha256"], relative)


@unittest.skipUnless(os.path.isfile(BLENDER), "real Blender is not installed")
class RealBlenderIntegrationTests(unittest.TestCase):
    """Executes Blender for real. This is integration evidence, not a mock."""

    def test_low_tier_character_builds_exports_and_reimports(self) -> None:
        spec = character_spec.build_character_spec(REQUEST, quality_tier="low")
        with tempfile.TemporaryDirectory() as tmp:
            report = character_pipeline.run_pipeline(
                spec, tmp, timeout=900, blender_exe=BLENDER, preview_size=256)
            self.assertEqual(report["status"], "completed",
                             report.get("failed_stages"))
            build = report["build"]
            self.assertTrue(build["blender_executed"])
            self.assertEqual(build["blender_exit_code"], 0)
            self.assertGreater(build["geometry"]["triangles"], 1000)
            self.assertTrue(build["rig"]["armature_modifier"])
            self.assertGreaterEqual(build["rig"]["weighted_ratio"], 0.99)
            self.assertTrue(build["glb_validation"]["ok"])
            self.assertGreaterEqual(build["glb_validation"]["animations"], 4)
            self.assertEqual(build["glb_validation"]["skins"], 1)
            names = set(build["glb_validation"]["animation_names"])
            self.assertEqual(names, {"Idle", "Walk", "Run", "Jump"})
            dims = character_pipeline.png_dimensions(
                build["artifacts"]["preview"]["path"])
            self.assertIsNotNone(dims)
            for artifact in build["artifacts"].values():
                self.assertTrue(artifact["exists"])
                self.assertGreater(artifact["bytes"], 0)
                self.assertTrue(artifact["sha256"])
            textures = build["textures"]
            self.assertEqual(len(textures), 3)
            for texture in textures:
                self.assertEqual(texture["dimensions"], [256, 256])
            channels = build["pbr_channels"]["M_Monkey_Fur"]
            self.assertEqual(channels["base_color"], "texture")
            self.assertEqual(channels["roughness"], "texture")
            self.assertEqual(channels["normal"], "texture")
            self.assertEqual(channels["ao"], "absent")
            self.assertTrue(report["reimport"]["ok"])
            self.assertTrue(report["reimport"]["checks"]["skinned_mesh"])
            self.assertEqual(
                set(report["reimport"]["metrics"]["animated_actions"]),
                {"Idle", "Walk", "Run", "Jump"})


if __name__ == "__main__":
    unittest.main()
