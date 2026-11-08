"""V6 Phase 4 environment pipeline tests.

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

from game_studio import environment_pipeline, environment_spec  # noqa: E402
from game_studio.util import ToolError, sha256_file  # noqa: E402

import server  # noqa: E402

BLENDER = r"D:\blender data\blender.exe"
REQUEST = (
    "Create a detailed stylized 3D tropical jungle adventure environment for a "
    "third-person monkey game. Include natural hilly terrain, dense tropical "
    "vegetation, tall trees, grass, ferns, rocks, roots, fallen logs, a flowing "
    "river with river banks, natural sunlight, atmospheric depth, and a clear "
    "playable route."
)
SINGULAR = {"trees": "tree", "bushes": "bush", "ferns": "fern",
            "grass": "grass", "plants": "plant"}


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


def sample_gltf(buffer_uri: str | None = None) -> dict:
    document = {
        "asset": {"version": "2.0", "generator": "test"},
        "accessors": [
            {"count": 900, "type": "VEC3", "min": [-60, -60, 0],
             "max": [60, 60, 9]},
            {"count": 900, "type": "SCALAR"},
        ],
        "images": [{"name": "base", "bufferView": 0}],
        "textures": [{"source": 0}],
        "materials": [{"name": "M", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}}}],
        "meshes": [{"name": "Terrain", "primitives": [
            {"indices": 1, "material": 0, "attributes": {"POSITION": 0}}]}],
        "nodes": [{"name": "Terrain"}],
    }
    if buffer_uri is not None:
        document["buffers"] = [{"uri": buffer_uri, "byteLength": 16}]
    return document


def artifacts(root: Path) -> dict:
    blend = root / "JungleLevel.blend"
    glb = root / "JungleLevel.glb"
    gltf = root / "JungleLevel.gltf"
    fbx = root / "JungleLevel.fbx"
    preview_overview = root / "preview_overview.png"
    preview_spawn = root / "preview_spawn.png"
    layout = root / "environment_layout.json"
    blend.write_bytes(b"BLENDER-test")
    glb.write_bytes(make_glb(sample_gltf()))
    gltf.write_text(json.dumps(sample_gltf()), encoding="utf-8")
    fbx.write_bytes(b"FBX-test")
    make_png(preview_overview, 8, 8)
    make_png(preview_spawn, 8, 8)
    layout.write_text("{}", encoding="utf-8")
    return {"blend": str(blend), "glb": str(glb), "gltf": str(gltf),
            "fbx": str(fbx), "preview_overview": str(preview_overview),
            "preview_spawn": str(preview_spawn), "layout": str(layout)}


def fake_payload(root: Path, spec: dict, *, image_exists: bool = True,
                 height_range: float = 4.0, river_present: bool = True,
                 character: dict | None = None) -> dict:
    resolution = spec["textures"]["resolution"]
    texture_dir = root / "textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    base = texture_dir / "ground_basecolor.png"
    rough = texture_dir / "ground_roughness.png"
    normal = texture_dir / "ground_normal.png"
    for path in (base, rough, normal):
        make_png(path, resolution, resolution)
    paths = artifacts(root)
    images = [
        {"name": "T_Env_Ground_BaseColor", "filepath": str(base),
         "size": [resolution, resolution], "colorspace": "sRGB", "packed": False},
        {"name": "T_Env_Ground_Roughness", "filepath": str(rough),
         "size": [resolution, resolution], "colorspace": "Non-Color",
         "packed": False},
        {"name": "T_Env_Ground_Normal", "filepath": str(normal),
         "size": [resolution, resolution], "colorspace": "Non-Color",
         "packed": False},
    ]
    if not image_exists:
        images[0]["filepath"] = str(texture_dir / "missing.png")
    for image in images:
        image["exists"] = os.path.isfile(image["filepath"])
    channels = {"base_color": "texture", "roughness": "texture",
                "normal": "texture", "metallic": "constant", "ao": "absent",
                "emission": "absent", "opacity": "absent",
                "transmission": "absent"}
    material = {
        "name": "M_Env_Ground", "images": images, "channels": channels,
        "declared_channels": {"base_color": "generated",
                              "roughness": "generated", "normal": "generated",
                              "metallic": "constant", "ao": "absent",
                              "emission": "absent", "opacity": "absent"},
    }
    vegetation_records = []
    counts = {}
    for index, (plural, requested) in enumerate(
            spec["vegetation"]["counts"].items()):
        category = SINGULAR.get(plural, plural)
        counts[category] = requested
        for item in range(requested):
            vegetation_records.append({
                "name": f"{category}_{item:03d}", "category": category,
                "x": (index + 1) * 50.0 + item * 20.0, "y": 0.0,
                "z": 1.0, "scale": 1.0, "rotation_deg": 0.0,
            })
    route = spec["layout"]["route"]
    water = {
        "present": river_present, "width_m": spec["water"]["width_m"],
        "vertices": 147, "faces": 96, "triangles": 192, "banks": 2,
        "water_surface": True, "bed_geometry": True,
        "flow_direction": list(spec["water"]["flow_direction"]),
        "left_boundary": [{"x": -5, "y": -50, "z": 2}],
        "right_boundary": [{"x": 5, "y": -50, "z": 2}],
    }
    lighting = {
        "sun": {"name": "Sun_Key", "energy": 4.0, "elevation_deg": 38.0,
                "azimuth_deg": 52.0, "shadows": True},
        "world": {"sky_color": [0.4, 0.6, 0.8], "ambient_strength": 0.55,
                  "fog_density": 0.018, "fog_color": [0.5, 0.6, 0.6],
                  "volumetric_fog_rendered": False},
        "exposure": 0.0, "view_transform": "AgX",
    }
    layout = {
        "spawn": {"name": "SPAWN_PLAYER", "x": 0.0, "y": -48.0, "z": 3.0,
                  "facing": [0, 1, 0], "clearance_m": 12.0},
        "route": {"width_m": 5.0, "waypoints": [
            {"name": f"ROUTE_WAYPOINT_{i:02d}", "x": point["x"],
             "y": point["y"], "z": 2.0} for i, point in enumerate(route)],
            "max_slope_deg": 8.0, "conflicts": []},
        "landmark": {"name": "LANDMARK_DESTINATION", "x": 0.0, "y": 46.0,
                     "z": 3.0, "type": "jungle_ruins"},
        "spawn_clearance_m": 12.0, "route_conflicts": [],
        "route_max_slope_deg": 8.0, "waypoint_count": len(route),
        "layout_path": paths["layout"],
    }
    collision = {
        "terrain_collider": "Terrain", "walkable_slope_deg": 32.0,
        "obstacles": [{"name": "tree_000", "role": "static_obstacle",
                       "x": 50.0, "y": 0.0, "z": 1.0, "radius": 0.5}],
        "river_boundary": {"name": "River_Water", "width_m": 9.0},
        "navmesh": "metadata only; no runtime navigation system implemented",
    }
    if character is None:
        character = {
            "imported": True, "imported_objects": 4, "meshes": 2,
            "dimensions": [0.9, 0.6, 1.5], "height_m": 1.5,
            "ground_contact_error_m": 0.01, "min_z": 3.0, "max_z": 4.5,
            "spawn_z": 3.0, "intersects_terrain": False,
            "asset_path": spec["character"]["asset_path"],
        }
    return {
        "name": spec["name"], "tier": spec["quality_tier"],
        "profile": spec["profile"],
        "blend": paths["blend"], "glb": paths["glb"], "gltf": paths["gltf"],
        "fbx": paths["fbx"], "preview_overview": paths["preview_overview"],
        "preview_spawn": paths["preview_spawn"],
        "render_error": None, "export_errors": [],
        "terrain": {"vertices": 1089, "triangles": 2048,
                    "non_manifold_edges": 0, "degenerate_faces": 0,
                    "height_min_m": 0.0, "height_max_m": height_range,
                    "height_range_m": height_range, "uv_layers": ["UVMap"],
                    "uv_coverage": 0.82,
                    "materials": ["M_Env_Ground"],
                    "dimensions": [120.0, 120.0, height_range]},
        "vegetation": {"counts": counts, "records": vegetation_records,
                       "instance_count": len(vegetation_records) - 5,
                       "unique_meshes": 11, "placed_colliders": []},
        "props": {"counts": {"rock": spec["rocks"]["count"],
                             "large_rock": spec["rocks"]["large_count"],
                             "fallen_log": spec["props"]["fallen_logs"]},
                  "debris": spec["props"]["debris_count"],
                  "ruin_objects": 6, "records": []},
        "water": water,
        "materials": [material],
        "images": images,
        "textures": [
            {"name": image["name"], "filepath": image["filepath"],
             "size": image["size"], "colorspace": image["colorspace"],
             "packed": False} for image in images
        ],
        "lighting": lighting, "layout": layout, "collision": collision,
        "character": character,
        "counts": {"objects": 120, "meshes": 30, "lights": 1, "cameras": 2,
                   "empties": 12, "instances": 100, "materials": 1,
                   "textures": 3, "triangles_total": 12000},
        "generation": "procedural-blender", "external_assets_used": False,
        "ai_generated": False,
    }


def blender_result(payload: dict, ok: bool = True) -> dict:
    return {"ok": ok, "result": payload, "exit_code": 0, "duration_ms": 2400,
            "stdout_tail": "", "stderr_tail": "",
            "error": None if ok else "failed"}


def build_report(spec: dict, tmp: str, payload: dict, ok: bool = True) -> dict:
    with mock.patch.object(environment_pipeline, "resolve_blender_executable",
                           return_value=BLENDER), \
         mock.patch.object(environment_pipeline.blender, "run_blender",
                           return_value=blender_result(payload, ok=ok)):
        return environment_pipeline.build_environment(
            spec, tmp, timeout=60, blender_exe=BLENDER, preview_size=256)


class BuildStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = environment_spec.build_environment_spec(
            REQUEST, quality_tier="low")

    def test_complete_payload_passes_all_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), self.spec)
            report = build_report(self.spec, tmp, payload)
        self.assertTrue(report["ok"], report["failed_stages"])
        self.assertEqual(report["status"], "built")
        self.assertFalse(report["failed_stages"])
        self.assertEqual(report["stages"]["terrain-validated"]["status"], "passed")
        self.assertEqual(report["stages"]["vegetation-validated"]["status"],
                         "passed")
        self.assertEqual(report["stages"]["water-validated"]["status"], "passed")
        self.assertEqual(report["stages"]["materials-validated"]["status"],
                         "passed")
        self.assertEqual(report["stages"]["character-integrated"]["status"],
                         "passed")

    def test_flat_terrain_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), self.spec, height_range=0.2)
            report = build_report(self.spec, tmp, payload)
        self.assertEqual(report["stages"]["terrain-validated"]["status"], "failed")
        self.assertIn("flat", " ".join(
            report["stages"]["terrain-validated"]["issues"]))
        self.assertNotEqual(report["status"], "built")

    def test_missing_texture_fails_material_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), self.spec, image_exists=False)
            report = build_report(self.spec, tmp, payload)
        self.assertEqual(report["stages"]["materials-validated"]["status"],
                         "failed")
        self.assertTrue(any("missing image" in issue for issue in
                            report["stages"]["materials-validated"]["issues"]))

    def test_missing_river_fails_water_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), self.spec, river_present=False)
            report = build_report(self.spec, tmp, payload)
        self.assertEqual(report["stages"]["water-validated"]["status"], "failed")

    def test_character_intersecting_terrain_fails(self) -> None:
        broken = {"imported": True, "height_m": 1.5,
                  "ground_contact_error_m": 0.5, "intersects_terrain": True}
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), self.spec, character=broken)
            report = build_report(self.spec, tmp, payload)
        self.assertEqual(report["stages"]["character-integrated"]["status"],
                         "failed")
        self.assertTrue(report["stages"]["character-integrated"]["issues"])

    def test_blender_failure_never_reports_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report(self.spec, tmp, {}, ok=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["stages"]["blender-build"]["status"], "failed")

    def test_missing_blender_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(environment_pipeline, "resolve_blender_executable",
                               return_value=None):
            report = environment_pipeline.build_environment(self.spec, tmp)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "failed")

    def test_invalid_specification_is_rejected_before_blender(self) -> None:
        broken = json.loads(json.dumps(self.spec))
        broken["terrain"]["segments"] += 3
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(environment_pipeline.blender, "run_blender") as run:
            with self.assertRaises(ToolError):
                environment_pipeline.build_environment(broken, tmp)
            run.assert_not_called()


class ReimportTests(unittest.TestCase):
    def test_reimport_checks_are_evaluated(self) -> None:
        inspection = {
            "object_count": 60, "mesh_count": 30, "triangle_count": 12000,
            "light_count": 1, "camera_count": 2, "material_count": 8,
            "spawn_marker": True, "waypoint_markers": ["ROUTE_WAYPOINT_00",
                                                       "ROUTE_WAYPOINT_01"],
            "landmark_marker": True, "river_objects": ["River_Water"],
            "missing_images": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            glb = Path(tmp) / "level.glb"
            glb.write_bytes(make_glb(sample_gltf()))
            with mock.patch.object(environment_pipeline,
                                   "resolve_blender_executable",
                                   return_value=BLENDER), \
                 mock.patch.object(environment_pipeline.blender, "run_blender",
                                   return_value=blender_result(inspection)):
                report = environment_pipeline.reimport_and_validate(
                    str(glb), tmp, timeout=60, blender_exe=BLENDER)
        self.assertTrue(report["ok"], report.get("checks"))
        self.assertTrue(all(report["checks"].values()))

    def test_reimport_detects_missing_textures(self) -> None:
        inspection = {"mesh_count": 30, "material_count": 8, "light_count": 1,
                      "camera_count": 1, "spawn_marker": True,
                      "waypoint_markers": ["a", "b"], "landmark_marker": True,
                      "river_objects": ["River_Water"],
                      "missing_images": ["textures/x.png"]}
        with tempfile.TemporaryDirectory() as tmp:
            glb = Path(tmp) / "level.glb"
            glb.write_bytes(make_glb(sample_gltf()))
            with mock.patch.object(environment_pipeline,
                                   "resolve_blender_executable",
                                   return_value=BLENDER), \
                 mock.patch.object(environment_pipeline.blender, "run_blender",
                                   return_value=blender_result(inspection)):
                report = environment_pipeline.reimport_and_validate(
                    str(glb), tmp, timeout=60, blender_exe=BLENDER)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["no_missing_textures"])


class GltfDependencyTests(unittest.TestCase):
    def test_external_buffer_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "level.gltf"
            path.write_text(json.dumps(sample_gltf("level.bin")),
                            encoding="utf-8")
            report = environment_pipeline.validate_gltf(str(path))
            self.assertFalse(report["ok"])
            self.assertIn("level.bin", report["external_buffers"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "level.gltf"
            path.write_text(json.dumps(sample_gltf("level.bin")),
                            encoding="utf-8")
            (Path(tmp) / "level.bin").write_bytes(b"\x00" * 16)
            report = environment_pipeline.validate_gltf(str(path))
        self.assertTrue(report["ok"])
        self.assertEqual(report["external_buffers"], ["level.bin"])


class ManifestTests(unittest.TestCase):
    def test_manifest_records_provenance_dependencies_and_artifacts(self) -> None:
        spec = environment_spec.build_environment_spec(REQUEST, quality_tier="low")
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), spec)
            build = build_report(spec, tmp, payload)
            manifest = environment_pipeline.asset_manifest(spec, build)
        self.assertEqual(manifest["asset_id"], spec["id"])
        self.assertEqual(manifest["asset_type"], "environment")
        self.assertTrue(manifest["procedural"])
        self.assertFalse(manifest["ai_generated"])
        self.assertEqual(manifest["download_status"], "not-downloaded")
        self.assertTrue(manifest["license"])
        self.assertTrue(manifest["dependencies"]["textures"])
        self.assertEqual(manifest["validation"]["build_status"], "built")
        self.assertTrue(manifest["artifacts"])
        for artifact in manifest["artifacts"]:
            self.assertTrue(artifact["sha256"])
            self.assertGreater(artifact["bytes"], 0)
        self.assertEqual(manifest["engine_compatibility"]["unity"]["status"],
                         "export-prepared-unverified")

    def test_engine_compatibility_never_claims_verified_imports(self) -> None:
        compatibility = environment_pipeline.engine_compatibility(
            {"materials": 8, "skins": 0, "animations": 0}, target_engine="unity")
        for engine in ("unity", "godot", "unreal"):
            self.assertFalse(compatibility[engine]["integration_verified"])
            self.assertEqual(compatibility[engine]["status"],
                             "export-prepared-unverified")


class PipelineOrchestrationTests(unittest.TestCase):
    def test_pipeline_marks_completed_only_when_all_required_stages_pass(self) -> None:
        spec = environment_spec.build_environment_spec(REQUEST, quality_tier="low")
        with tempfile.TemporaryDirectory() as tmp:
            payload = fake_payload(Path(tmp), spec)
            with mock.patch.object(environment_pipeline, "build_environment",
                                   return_value={
                                       "status": "built", "ok": True,
                                       "stages": {}, "artifacts": {},
                                       "blender_executed": True,
                                   }), \
                 mock.patch.object(environment_pipeline, "asset_manifest",
                                   return_value={}):
                report = environment_pipeline.run_pipeline(
                    spec, tmp, timeout=60, blender_exe=BLENDER,
                    character_root=str(ROOT.parents[1]))
        # No GLB artifact means re-import cannot pass, so never "completed".
        self.assertNotEqual(report["status"], "completed")
        self.assertFalse(report["ok"])
        self.assertIn("glb-reimported", report["failed_stages"])

    def test_pipeline_reports_partial_when_blend_exists_but_stage_fails(self) -> None:
        spec = environment_spec.build_environment_spec(REQUEST, quality_tier="low")
        with tempfile.TemporaryDirectory() as tmp:
            blend = Path(tmp) / "JungleLevel.blend"
            blend.write_bytes(b"blend")
            with mock.patch.object(environment_pipeline, "build_environment",
                                   return_value={
                                       "status": "partial", "ok": False,
                                       "stages": {"terrain-validated": {
                                           "status": "failed"}},
                                       "artifacts": {"blend": {
                                           "path": str(blend), "exists": True}},
                                       "blender_executed": True,
                                   }), \
                 mock.patch.object(environment_pipeline, "asset_manifest",
                                   return_value={}):
                report = environment_pipeline.run_pipeline(
                    spec, tmp, timeout=60, blender_exe=BLENDER)
        self.assertEqual(report["status"], "partial")
        self.assertFalse(report["ok"])


class SecurityTests(unittest.TestCase):
    def test_spec_and_pipeline_paths_reject_script_injection(self) -> None:
        with self.assertRaises(ValueError):
            environment_spec.build_environment_spec("")
        name = "Jungle'; import os; os.system('x') #"
        spec = environment_spec.build_environment_spec(REQUEST, name=name)
        self.assertNotIn(";", spec["id"])
        self.assertNotIn(" ", spec["id"])

    def test_pipeline_never_downloads_or_uses_external_assets(self) -> None:
        spec = environment_spec.build_environment_spec(REQUEST)
        self.assertEqual(spec["provenance"]["downloads"], [])
        self.assertEqual(spec["provenance"]["external_assets"], [])
        source = Path(environment_pipeline.__file__).read_text(encoding="utf-8")
        for token in ("requests.", "urllib.request", "http://", "https://"):
            self.assertNotIn(token, source)


class McpTests(unittest.TestCase):
    def test_tools_and_handlers_stay_in_parity(self) -> None:
        names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(server.HANDLERS))
        for name in ("environment_generate_asset", "environment_profiles"):
            self.assertIn(name, names)
        for tool in server.TOOLS:
            self.assertEqual(tool["inputSchema"].get("type"), "object")

    def test_generate_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(ToolError):
            server.tool_environment_generate({
                "description": REQUEST, "output_dir": "C:/tmp/env"})

    def test_generate_builds_a_valid_spec_and_calls_the_pipeline(self) -> None:
        with mock.patch.object(server.environment_pipeline, "run_pipeline",
                               return_value={"status": "completed"}) as run:
            result = server.tool_environment_generate({
                "description": REQUEST, "quality_tier": "high",
                "output_dir": "C:/tmp/env", "confirm": True,
                "profile": "tropical_jungle", "lighting": "sunset",
                "target_engine": "godot", "seed": 5})
        self.assertEqual(result["status"], "completed")
        spec = run.call_args.args[0]
        self.assertEqual(environment_spec.validate_environment_spec(spec), [])
        self.assertEqual(spec["quality_tier"], "high")
        self.assertEqual(spec["lighting"]["preset"], "sunset")
        self.assertEqual(spec["export"]["target_engine"], "godot")
        self.assertEqual(spec["provenance"]["seed"], 5)

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            server.tool_environment_generate({
                "description": REQUEST, "profile": "volcano",
                "output_dir": "C:/tmp/env", "confirm": True})

    def test_profiles_tool_reports_partial_profiles(self) -> None:
        report = server.tool_environment_profiles({})
        self.assertEqual(report["fully_implemented"], ["tropical_jungle"])
        self.assertTrue(report["partial_profiles"])

    def test_generate_tool_schema_is_strict(self) -> None:
        tool = next(t for t in server.TOOLS
                    if t["name"] == "environment_generate_asset")
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

    def test_low_tier_environment_builds_exports_and_reimports(self) -> None:
        spec = environment_spec.build_environment_spec(
            REQUEST, quality_tier="low")
        with tempfile.TemporaryDirectory() as tmp:
            report = environment_pipeline.run_pipeline(
                spec, tmp, timeout=900, blender_exe=BLENDER, preview_size=256,
                character_root=str(ROOT.parents[1]))
            self.assertEqual(report["status"], "completed",
                             report.get("failed_stages"))
            build = report["build"]
            self.assertTrue(build["blender_executed"])
            self.assertEqual(build["blender_exit_code"], 0)
            self.assertGreater(build["terrain"]["triangles"], 1000)
            self.assertGreater(build["terrain"]["height_range_m"], 1.0)
            self.assertTrue(build["terrain"]["uv_layers"])
            self.assertGreater(build["vegetation"]["instance_count"], 0)
            self.assertGreater(build["props"]["counts"]["rock"], 0)
            self.assertTrue(build["water"]["present"])
            self.assertGreater(build["water"]["triangles"], 0)
            self.assertEqual(build["water"]["banks"], 2)
            self.assertTrue(build["glb_validation"]["ok"])
            self.assertEqual(build["stages"]["character-integrated"]["status"],
                             "passed")
            self.assertTrue(report["reimport"]["ok"])
            self.assertTrue(build["artifacts"]["preview_overview"]["exists"])
            self.assertTrue(build["artifacts"]["preview_spawn"]["exists"])
            for artifact in build["artifacts"].values():
                self.assertTrue(artifact["sha256"])
            for texture in build["textures"]:
                self.assertEqual(texture["dimensions"], [256, 256])
            channels = build["pbr_channels"]["M_Env_Ground"]
            self.assertEqual(channels["base_color"], "texture")
            self.assertEqual(channels["roughness"], "texture")
            self.assertEqual(channels["normal"], "texture")
            self.assertEqual(channels["ao"], "absent")
            self.assertTrue(report["character_source"]["unchanged"])


if __name__ == "__main__":
    unittest.main()
