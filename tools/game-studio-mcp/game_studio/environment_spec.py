"""V6 Phase 4 environment specification and quality profiles.

Pure deterministic data structures. No Blender call and no network access happens
here. This is the contract between the Phase 2 Environment Agent and the Phase 4
Blender environment pipeline.
"""

from __future__ import annotations

import copy
import re

SPEC_SCHEMA_VERSION = 1

# Settings are consumed by the Blender build script, so tiers differ in real
# geometry, instance counts, texture resolution and render cost.
QUALITY_TIERS = {
    "low": {
        "terrain_segments": 33,
        "tree_count": 10,
        "bush_count": 14,
        "fern_count": 24,
        "grass_count": 60,
        "plant_count": 10,
        "rock_count": 10,
        "large_rock_count": 3,
        "log_count": 2,
        "ruin_count": 1,
        "texture_resolution": 256,
        "target_triangles": 45_000,
        "preview_size": 384,
        "render_samples": 8,
        "estimated_memory_mb": 90,
    },
    "medium": {
        "terrain_segments": 65,
        "tree_count": 22,
        "bush_count": 30,
        "fern_count": 55,
        "grass_count": 140,
        "plant_count": 22,
        "rock_count": 20,
        "large_rock_count": 6,
        "log_count": 4,
        "ruin_count": 1,
        "texture_resolution": 512,
        "target_triangles": 120_000,
        "preview_size": 640,
        "render_samples": 16,
        "estimated_memory_mb": 180,
    },
    "high": {
        "terrain_segments": 97,
        "tree_count": 38,
        "bush_count": 50,
        "fern_count": 90,
        "grass_count": 240,
        "plant_count": 36,
        "rock_count": 32,
        "large_rock_count": 9,
        "log_count": 6,
        "ruin_count": 2,
        "texture_resolution": 1024,
        "target_triangles": 260_000,
        "preview_size": 768,
        "render_samples": 32,
        "estimated_memory_mb": 320,
    },
}

EXPORT_FORMATS = ("blend", "glb", "gltf", "fbx")

# Profiles define the environmental character. Implementation levels are honest:
# only the tropical jungle is fully demonstrated in Phase 4.
ENVIRONMENT_PROFILES = {
    "tropical_jungle": {
        "name": "Tropical Jungle",
        "implemented_level": "full",
        "terrain_amplitude": 6.0,
        "hill_count": 3,
        "river": True,
        "river_width": 9.0,
        "tree_multiplier": 1.0,
        "ground_cover_multiplier": 1.0,
        "rock_multiplier": 1.0,
        "ruins": True,
        "fog_density": 0.018,
        "sun_elevation_deg": 38,
        "sun_azimuth_deg": 52,
        "ground_palette": [0.18, 0.24, 0.10],
    },
    "dense_rainforest": {
        "name": "Dense Rainforest",
        "implemented_level": "partial",
        "terrain_amplitude": 5.0,
        "hill_count": 2,
        "river": True,
        "river_width": 7.0,
        "tree_multiplier": 1.6,
        "ground_cover_multiplier": 1.5,
        "rock_multiplier": 0.7,
        "ruins": False,
        "fog_density": 0.026,
        "sun_elevation_deg": 30,
        "sun_azimuth_deg": 70,
        "ground_palette": [0.12, 0.20, 0.08],
    },
    "tropical_river_valley": {
        "name": "Tropical River Valley",
        "implemented_level": "partial",
        "terrain_amplitude": 9.0,
        "hill_count": 4,
        "river": True,
        "river_width": 14.0,
        "tree_multiplier": 0.9,
        "ground_cover_multiplier": 1.1,
        "rock_multiplier": 1.2,
        "ruins": False,
        "fog_density": 0.020,
        "sun_elevation_deg": 34,
        "sun_azimuth_deg": 44,
        "ground_palette": [0.20, 0.23, 0.12],
    },
    "mountain_jungle": {
        "name": "Mountain Jungle",
        "implemented_level": "partial",
        "terrain_amplitude": 16.0,
        "hill_count": 5,
        "river": False,
        "river_width": 0.0,
        "tree_multiplier": 0.8,
        "ground_cover_multiplier": 0.8,
        "rock_multiplier": 1.8,
        "ruins": False,
        "fog_density": 0.012,
        "sun_elevation_deg": 46,
        "sun_azimuth_deg": 60,
        "ground_palette": [0.17, 0.20, 0.11],
    },
    "forest_clearing": {
        "name": "Forest Clearing",
        "implemented_level": "partial",
        "terrain_amplitude": 2.5,
        "hill_count": 1,
        "river": False,
        "river_width": 0.0,
        "tree_multiplier": 0.35,
        "ground_cover_multiplier": 1.4,
        "rock_multiplier": 0.6,
        "ruins": False,
        "fog_density": 0.010,
        "sun_elevation_deg": 42,
        "sun_azimuth_deg": 35,
        "ground_palette": [0.23, 0.28, 0.12],
    },
    "jungle_ruins": {
        "name": "Jungle Ruins",
        "implemented_level": "partial",
        "terrain_amplitude": 4.0,
        "hill_count": 2,
        "river": False,
        "river_width": 0.0,
        "tree_multiplier": 0.9,
        "ground_cover_multiplier": 0.7,
        "rock_multiplier": 1.3,
        "ruins": True,
        "fog_density": 0.016,
        "sun_elevation_deg": 36,
        "sun_azimuth_deg": 48,
        "ground_palette": [0.19, 0.21, 0.12],
    },
}

LIGHTING_PRESETS = {
    "daylight": {"sun_elevation_deg": 55, "sun_azimuth_deg": 45,
                 "sun_energy": 4.0, "ambient_strength": 0.55,
                 "sky_color": [0.42, 0.62, 0.82], "fog_color": [0.55, 0.68, 0.66]},
    "morning": {"sun_elevation_deg": 22, "sun_azimuth_deg": 80,
                "sun_energy": 3.2, "ambient_strength": 0.45,
                "sky_color": [0.72, 0.66, 0.52], "fog_color": [0.72, 0.70, 0.58]},
    "sunset": {"sun_elevation_deg": 12, "sun_azimuth_deg": 255,
               "sun_energy": 3.6, "ambient_strength": 0.38,
               "sky_color": [0.78, 0.42, 0.26], "fog_color": [0.74, 0.50, 0.38]},
    "overcast": {"sun_elevation_deg": 60, "sun_azimuth_deg": 30,
                 "sun_energy": 1.6, "ambient_strength": 0.75,
                 "sky_color": [0.62, 0.66, 0.68], "fog_color": [0.66, 0.69, 0.68]},
}

PBR_CHANNELS = ("base_color", "normal", "roughness", "metallic", "ao",
                "emission", "opacity")


def _material(name, role, base_color, roughness, metallic=0.0, textured=False,
              channels=None, color_spaces=None, transmission=0.0, alpha=1.0):
    return {
        "name": name,
        "role": role,
        "base_color": [float(value) for value in base_color],
        "roughness": float(roughness),
        "metallic": float(metallic),
        "transmission": float(transmission),
        "alpha": float(alpha),
        "textured": bool(textured),
        "channels": channels or {channel: "absent" for channel in PBR_CHANNELS},
        "color_spaces": color_spaces or {},
    }


DEFAULT_MATERIALS = (
    _material(
        "M_Env_Ground", "terrain", [0.18, 0.24, 0.10], 0.86, textured=True,
        channels={
            "base_color": "generated", "roughness": "generated",
            "normal": "generated", "metallic": "constant",
            "ao": "absent", "emission": "absent", "opacity": "absent",
        },
        color_spaces={"base_color": "sRGB", "roughness": "Non-Color",
                      "normal": "Non-Color"},
    ),
    _material("M_Env_Grass", "ground_cover", [0.16, 0.31, 0.08], 0.82),
    _material("M_Env_Leaf", "canopy", [0.10, 0.28, 0.07], 0.72),
    _material("M_Env_Leaf_Light", "canopy_variation", [0.22, 0.40, 0.10], 0.68),
    _material("M_Env_Bark", "tree_trunk", [0.22, 0.14, 0.08], 0.90),
    _material("M_Env_Rock", "rock", [0.30, 0.29, 0.26], 0.84),
    _material("M_Env_Rock_Mossy", "rock_variation", [0.22, 0.27, 0.16], 0.88),
    _material("M_Env_Wood", "fallen_wood", [0.26, 0.17, 0.09], 0.88),
    _material("M_Env_Stone", "ruins", [0.38, 0.36, 0.31], 0.80),
    _material("M_Env_WetGround", "river_bank", [0.13, 0.14, 0.08], 0.42),
    _material("M_Env_Water", "water", [0.06, 0.22, 0.26], 0.08, metallic=0.0,
              transmission=0.55, alpha=0.82),
    _material("M_Env_Root", "roots", [0.20, 0.13, 0.07], 0.92),
)

ENVIRONMENT_SPEC_SCHEMA = {
    "type": "object",
    "required": [
        "schema_version", "id", "name", "description", "profile",
        "implemented_level", "quality_tier", "terrain", "vegetation", "rocks",
        "props", "water", "materials", "textures", "lighting", "layout",
        "collision", "performance", "character", "export", "provenance",
    ],
    "properties": {
        "schema_version": {"type": "integer"},
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "profile": {"type": "string"},
        "implemented_level": {"type": "string"},
        "quality_tier": {"type": "string", "enum": list(QUALITY_TIERS)},
        "terrain": {"type": "object"},
        "vegetation": {"type": "object"},
        "rocks": {"type": "object"},
        "props": {"type": "object"},
        "water": {"type": "object"},
        "materials": {"type": "array"},
        "textures": {"type": "object"},
        "lighting": {"type": "object"},
        "layout": {"type": "object"},
        "collision": {"type": "object"},
        "performance": {"type": "object"},
        "character": {"type": "object"},
        "export": {"type": "object"},
        "provenance": {"type": "object"},
    },
}


def quality_settings(tier: str | None) -> tuple[dict, str]:
    key = (tier or "medium").strip().lower()
    if key not in QUALITY_TIERS:
        raise ValueError(f"quality_tier must be one of {list(QUALITY_TIERS)}")
    return copy.deepcopy(QUALITY_TIERS[key]), key


def profile_settings(name: str | None) -> tuple[dict, str]:
    key = (name or "tropical_jungle").strip().lower()
    if key not in ENVIRONMENT_PROFILES:
        raise ValueError(f"profile must be one of {list(ENVIRONMENT_PROFILES)}")
    return copy.deepcopy(ENVIRONMENT_PROFILES[key]), key


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "environment"


def infer_profile(description: str) -> str:
    text = (description or "").lower()
    if "river valley" in text or ("river" in text and "valley" in text):
        return "tropical_river_valley"
    if "mountain" in text:
        return "mountain_jungle"
    if "rainforest" in text:
        return "dense_rainforest"
    if "clearing" in text:
        return "forest_clearing"
    if "ruin" in text:
        return "jungle_ruins"
    return "tropical_jungle"


def infer_lighting(description: str) -> str:
    text = (description or "").lower()
    if "sunset" in text or "dusk" in text:
        return "sunset"
    if "morning" in text or "dawn" in text:
        return "morning"
    if "overcast" in text or "cloudy" in text or "rain" in text:
        return "overcast"
    return "daylight"


def build_environment_spec(description: str, *, name: str = "JungleLevel",
                           quality_tier: str = "medium",
                           profile: str | None = None,
                           lighting: str | None = None,
                           target_engine: str = "unity",
                           character_path: str | None = None,
                           seed: int = 20261108) -> dict:
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description must be a non-empty string")
    tier, tier_key = quality_settings(quality_tier)
    profile_key = (profile or infer_profile(description)).strip().lower()
    profile_data, profile_key = profile_settings(profile_key)
    lighting_key = (lighting or infer_lighting(description)).strip().lower()
    if lighting_key not in LIGHTING_PRESETS:
        raise ValueError(f"lighting must be one of {list(LIGHTING_PRESETS)}")
    light = copy.deepcopy(LIGHTING_PRESETS[lighting_key])

    # Profile-specific lighting tweaks, still deterministic.
    if lighting_key == "daylight":
        light["sun_elevation_deg"] = profile_data["sun_elevation_deg"]
        light["sun_azimuth_deg"] = profile_data["sun_azimuth_deg"]
    light["fog_density"] = profile_data["fog_density"]

    materials = copy.deepcopy(list(DEFAULT_MATERIALS))
    palette = profile_data["ground_palette"]
    materials[0]["base_color"] = [float(v) for v in palette]

    trees = max(1, int(round(tier["tree_count"] * profile_data["tree_multiplier"])))
    bushes = max(1, int(round(tier["bush_count"] * profile_data["ground_cover_multiplier"])))
    ferns = max(1, int(round(tier["fern_count"] * profile_data["ground_cover_multiplier"])))
    grass = max(1, int(round(tier["grass_count"] * profile_data["ground_cover_multiplier"])))
    plants = max(1, int(round(tier["plant_count"] * profile_data["ground_cover_multiplier"])))
    rocks = max(1, int(round(tier["rock_count"] * profile_data["rock_multiplier"])))
    large_rocks = max(1, int(round(tier["large_rock_count"] * profile_data["rock_multiplier"])))
    logs = max(1, int(round(tier["log_count"] * profile_data["rock_multiplier"])))
    ruins = tier["ruin_count"] if profile_data["ruins"] else 0

    terrain_size = 120.0
    spawn = {"x": 0.0, "y": -48.0, "facing": [0.0, 1.0, 0.0]}
    landmark = {"x": 0.0, "y": 46.0, "type": "jungle_ruins" if ruins else "ancient_tree"}
    route = []
    for index in range(9):
        y = -48.0 + index * (82.0 / 8.0)
        route.append({"x": round(3.0 * _sin((y + 60.0) * 0.06), 3),
                      "y": round(y, 3), "order": index})

    spec = {
        "schema_version": SPEC_SCHEMA_VERSION,
        "id": f"env-{_slug(name)}-{profile_key}-{tier_key}",
        "name": name,
        "description": description.strip(),
        "profile": profile_key,
        "profile_name": profile_data["name"],
        "implemented_level": profile_data["implemented_level"],
        "quality_tier": tier_key,
        "style": "stylized-realistic tropical adventure",
        "terrain": {
            "size_x_m": terrain_size,
            "size_y_m": terrain_size,
            "segments": tier["terrain_segments"],
            "amplitude_m": profile_data["terrain_amplitude"],
            "hill_count": profile_data["hill_count"],
            "base_elevation_m": 2.2,
            "spawn_flat_radius_m": 11.0,
            "route_flat_radius_m": 7.0,
            "route_width_m": 5.0,
            "uv": "world_scaled_grid_uv",
            "material": "M_Env_Ground",
            "collision": "terrain_mesh_collider",
        },
        "vegetation": {
            "density": round((trees + bushes + ferns + grass + plants) / (terrain_size ** 2), 5),
            "min_spacing_m": {"tree": 5.0, "bush": 2.8, "fern": 2.0,
                              "grass": 1.2, "plant": 2.5},
            "slope_limit_deg": {"tree": 28.0, "bush": 32.0, "fern": 30.0,
                                "grass": 34.0, "plant": 30.0},
            "counts": {"trees": trees, "bushes": bushes, "ferns": ferns,
                       "grass": grass, "plants": plants},
            "variation": {"scale": [0.75, 1.35], "rotation_deg": [0.0, 360.0]},
            "instancing": "linked_mesh_instances",
            "route_clearance_m": 5.0,
        },
        "rocks": {
            "count": rocks, "large_count": large_rocks,
            "min_spacing_m": 3.0, "slope_limit_deg": 42.0,
            "collision": "static_obstacle",
            "variation": {"scale": [0.6, 1.8], "rotation_deg": [0.0, 360.0]},
        },
        "props": {
            "fallen_logs": logs, "ruin_clusters": ruins,
            "debris_count": max(4, rocks // 2),
            "roots": max(4, trees // 3),
            "collision": "static_obstacle",
        },
        "water": {
            "present": bool(profile_data["river"]),
            "type": "river",
            "width_m": float(profile_data["river_width"]),
            "depth_m": [0.4, 1.4],
            "length_m": terrain_size - 8.0,
            "flow_direction": [0.0, 1.0, 0.0],
            "banks": True,
            "water_surface": True,
            "bed_geometry": True,
            "collision_boundary": True,
            "physics": "visual-only; no swimming interaction implemented",
            "material": "M_Env_Water",
        },
        "materials": materials,
        "textures": {
            "resolution": tier["texture_resolution"],
            "format": "PNG",
            "generation_method": "procedural-local-blender",
            "maps_generated": ["base_color", "roughness", "normal"],
            "maps_constant": ["metallic"],
            "maps_absent": {
                "ao": "no physically measured ambient occlusion was computed",
                "emission": "not required by the environment description",
                "opacity": "opaque materials except the visual water surface",
            },
            "color_spaces": {"base_color": "sRGB", "roughness": "Non-Color",
                             "normal": "Non-Color"},
        },
        "lighting": {
            "preset": lighting_key,
            **light,
            "shadows": True,
            "exposure": 0.0,
            "view_transform": "AgX",
            "atmosphere": "world_haze_and_distance_fog_metadata",
            "volumetric_fog_rendered": False,
        },
        "layout": {
            "spawn": spawn,
            "route": route,
            "route_width_m": 5.0,
            "landmark": landmark,
            "playable_area": {"center": [0.0, 0.0], "radius_m": 55.0},
            "unit_scale": "meters",
            "forward_axis": "-Z",
            "up_axis": "Y",
        },
        "collision": {
            "terrain_collider": True,
            "obstacle_colliders": True,
            "river_boundary": bool(profile_data["river"]),
            "walkable_slope_deg": 32.0,
            "spawn_clearance_m": 3.0,
            "route_clearance_m": 2.5,
            "navigation": "metadata prepared; no navmesh runtime implemented",
        },
        "performance": {
            "target_triangles": tier["target_triangles"],
            "estimated_memory_mb": tier["estimated_memory_mb"],
            "memory_label": "estimated, not measured",
            "preview_size": tier["preview_size"],
            "render_samples": tier["render_samples"],
            "instancing": True,
            "max_simultaneous_blender_jobs": 1,
        },
        "character": {
            "place": True,
            "asset_path": character_path or "validation/v6-character-pipeline/JungleMonkey.glb",
            "expected_height_m": [1.1, 2.0],
            "face_route": True,
            "validate_ground_contact": True,
            "preserve_source": True,
        },
        "export": {
            "target_engine": (target_engine or "unity").lower(),
            "formats": list(EXPORT_FORMATS),
            "units": "meters",
            "forward_axis": "-Z",
            "up_axis": "Y",
            "include_character": True,
            "include_collision_metadata": True,
            "require_reimport": True,
        },
        "provenance": {
            "source": "generated-locally",
            "generation_method": "procedural-blender",
            "creator": "Universal AI Game Studio",
            "license": "Original project asset (no third-party content)",
            "license_id": "project-original-1.0",
            "attribution_required": False,
            "external_assets": [],
            "downloads": [],
            "ai_generated": False,
            "seed": seed,
        },
    }
    return spec


def _sin(value: float) -> float:
    import math
    return math.sin(value)


def validate_environment_spec(spec: object) -> list[str]:
    if not isinstance(spec, dict):
        return ["$: environment specification must be a JSON object"]
    errors: list[str] = []
    for key in ENVIRONMENT_SPEC_SCHEMA["required"]:
        if key not in spec:
            errors.append(f"$.{key}: is required")
    if errors:
        return errors
    tier = spec.get("quality_tier")
    if tier not in QUALITY_TIERS:
        return [f"$.quality_tier: unknown tier {tier!r}"]
    if spec.get("profile") not in ENVIRONMENT_PROFILES:
        errors.append(f"$.profile: unknown profile {spec.get('profile')!r}")
    expected = QUALITY_TIERS[tier]
    if spec["terrain"].get("segments") != expected["terrain_segments"]:
        errors.append("$.terrain.segments: does not match the declared tier")
    if spec["textures"].get("resolution") != expected["texture_resolution"]:
        errors.append("$.textures.resolution: does not match the declared tier")
    if spec["performance"].get("target_triangles") != expected["target_triangles"]:
        errors.append("$.performance.target_triangles: does not match the declared tier")
    terrain = spec["terrain"]
    if float(terrain.get("size_x_m") or 0) <= 0 or float(
            terrain.get("size_y_m") or 0) <= 0:
        errors.append("$.terrain: dimensions must be positive")
    if float(terrain.get("amplitude_m") or 0) <= 0:
        errors.append("$.terrain.amplitude_m: must be positive")
    spawn = spec["layout"].get("spawn") or {}
    if not all(key in spawn for key in ("x", "y")):
        errors.append("$.layout.spawn: requires x and y")
    elif abs(float(spawn["x"])) > float(terrain["size_x_m"]) / 2 or abs(
            float(spawn["y"])) > float(terrain["size_y_m"]) / 2:
        errors.append("$.layout.spawn: outside terrain bounds")
    if len(spec["layout"].get("route") or []) < 2:
        errors.append("$.layout.route: at least two waypoints are required")
    counts = (spec["vegetation"].get("counts") or {})
    if not counts.get("trees"):
        errors.append("$.vegetation.counts.trees: at least one tree is required")
    water = spec["water"]
    if water.get("present") and float(water.get("width_m") or 0) <= 0:
        errors.append("$.water.width_m: a present river needs a positive width")
    if not spec["materials"]:
        errors.append("$.materials: at least one material is required")
    if not spec["export"].get("formats"):
        errors.append("$.export.formats: at least one format is required")
    if spec["provenance"].get("source") == "external" and not spec[
            "provenance"].get("license"):
        errors.append("$.provenance.license: external assets require a license")
    return errors


def spec_from_agent_output(output: dict, *, quality_tier: str = "medium",
                           target_engine: str = "unity",
                           character_path: str | None = None) -> dict:
    """Adapt Phase 2 Environment Agent output into an executable spec."""
    if not isinstance(output, dict) or not output.get("summary"):
        raise ValueError("environment agent output is missing a summary")
    environment = str(output.get("environment") or "tropical jungle")
    terrain = output.get("terrain") or {}
    water = output.get("water") or {}
    text = " ".join(str(value) for value in (
        environment, terrain.get("approach", ""), output.get("summary", "")))
    if water.get("present"):
        text += " river water"
    name = "JungleLevel"
    return build_environment_spec(
        text, name=name, quality_tier=quality_tier,
        profile=infer_profile(environment), target_engine=target_engine,
        character_path=character_path)


def profile_report() -> dict:
    return {
        "schema_version": SPEC_SCHEMA_VERSION,
        "profiles": {
            key: {
                "name": value["name"],
                "implemented_level": value["implemented_level"],
                "river": value["river"],
                "ruins": value["ruins"],
                "terrain_amplitude_m": value["terrain_amplitude"],
                "notes": ("Fully demonstrated by the Phase 4 tropical jungle build."
                          if value["implemented_level"] == "full"
                          else "Reusable profile parameters exist; not separately "
                               "demonstrated or validated in Phase 4."),
            }
            for key, value in ENVIRONMENT_PROFILES.items()
        },
        "quality_tiers": {
            key: {
                "terrain_segments": value["terrain_segments"],
                "tree_count": value["tree_count"],
                "texture_resolution": value["texture_resolution"],
                "target_triangles": value["target_triangles"],
                "estimated_memory_mb": value["estimated_memory_mb"],
            }
            for key, value in QUALITY_TIERS.items()
        },
        "fully_implemented": [key for key, value in ENVIRONMENT_PROFILES.items()
                              if value["implemented_level"] == "full"],
        "partial_profiles": [key for key, value in ENVIRONMENT_PROFILES.items()
                             if value["implemented_level"] != "full"],
        "lighting_presets": list(LIGHTING_PRESETS),
    }
