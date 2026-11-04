"""Character rig and animation inspection built on real glTF/GLB parsing.

glTF/GLB is the portable interchange format used by Unity, Godot and Unreal
(through import). FBX internals are intentionally not guessed: FBX rigs are
inspected by importing them in Blender, which this module delegates to.

No animation provider is simulated. Mixamo/Adobe has no public API, so the
module reports that limitation instead of pretending to download clips.
"""

from __future__ import annotations

import json
import os
import struct

from . import secrets
from .util import ToolError, expand, read_json, sha256_file, write_json

HUMANOID_ALIASES = {
    "hips": {"hips", "pelvis", "hip"},
    "spine": {"spine", "spine1", "spine01"},
    "chest": {"chest", "spine2", "upperchest", "spine02"},
    "neck": {"neck"},
    "head": {"head"},
    "left_shoulder": {"leftshoulder", "shoulder_l", "l_shoulder", "clavicle_l"},
    "right_shoulder": {"rightshoulder", "shoulder_r", "r_shoulder", "clavicle_r"},
    "left_upper_arm": {"leftarm", "upperarm_l", "l_upperarm", "leftupperarm"},
    "right_upper_arm": {"rightarm", "upperarm_r", "r_upperarm", "rightupperarm"},
    "left_forearm": {"leftforearm", "lowerarm_l", "l_forearm", "leftlowerarm"},
    "right_forearm": {"rightforearm", "lowerarm_r", "r_forearm", "rightlowerarm"},
    "left_hand": {"lefthand", "hand_l", "l_hand"},
    "right_hand": {"righthand", "hand_r", "r_hand"},
    "left_thigh": {"leftupleg", "thigh_l", "l_thigh", "leftupperleg"},
    "right_thigh": {"rightupleg", "thigh_r", "r_thigh", "rightupperleg"},
    "left_shin": {"leftleg", "calf_l", "l_shin", "leftlowerleg"},
    "right_shin": {"rightleg", "calf_r", "r_shin", "rightlowerleg"},
    "left_foot": {"leftfoot", "foot_l", "l_foot"},
    "right_foot": {"rightfoot", "foot_r", "r_foot"},
    "left_toe": {"lefttoebase", "toe_l", "ball_l", "lefttoe"},
    "right_toe": {"righttoebase", "toe_r", "ball_r", "righttoe"},
}

QUADRUPED_MARKERS = {"frontleft", "frontright", "backleft", "backright",
                     "front_left", "hind_left", "tail", "quadruped"}


def _normalise_bone(name: str) -> str:
    value = (name or "").lower()
    for separator in (":", "|"):
        if separator in value:
            value = value.split(separator)[-1]
    for token in ("mixamorig", "armature", "root", "def-", "org-"):
        value = value.replace(token, "")
    return "".join(ch for ch in value if ch.isalnum())


def _load_gltf_document(path: str) -> tuple[dict, str]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".gltf":
        return read_json(path), "gltf"
    if ext != ".glb":
        raise ToolError("rig inspection currently parses .glb/.gltf directly; "
                        "use inspect_rig_in_blender for .blend or .fbx")
    with open(path, "rb") as handle:
        header = handle.read(12)
        magic, version, _ = struct.unpack("<4sII", header)
        if magic != b"glTF":
            raise ToolError("not a GLB file")
        chunk_length, chunk_type = struct.unpack("<II", handle.read(8))
        if chunk_type != 0x4E4F534A:
            raise ToolError("GLB first chunk is not JSON")
        document = json.loads(handle.read(chunk_length).decode("utf-8").rstrip("\x00 "))
    return document, "glb"


def inspect_rig(path: str) -> dict:
    target = os.path.abspath(expand(path))
    if not os.path.isfile(target):
        raise ToolError(f"file not found: {target}")
    document, container = _load_gltf_document(target)
    nodes = document.get("nodes") or []
    skins = document.get("skins") or []
    joints: list[dict] = []
    joints_by_skin = []
    for index, skin in enumerate(skins):
        names = []
        for joint in skin.get("joints") or []:
            if 0 <= joint < len(nodes):
                name = nodes[joint].get("name") or f"node_{joint}"
                names.append(name)
                joints.append({"node": joint, "name": name, "normalised": _normalise_bone(name)})
        joints_by_skin.append({"index": index, "skeleton": skin.get("skeleton"),
                               "joint_count": len(names), "joints": names})
    normalised = {j["normalised"] for j in joints}
    matched_roles = sorted(role for role, aliases in HUMANOID_ALIASES.items()
                           if normalised & aliases)
    humanoid_ratio = len(matched_roles) / len(HUMANOID_ALIASES)
    quadruped_hits = sorted(marker for marker in QUADRUPED_MARKERS
                            if any(marker in n for n in normalised))
    if quadruped_hits:
        rig_type = "quadruped"
    elif humanoid_ratio >= 0.55:
        rig_type = "humanoid"
    elif joints:
        rig_type = "generic-skeleton"
    else:
        rig_type = "unrigged"
    animations = document.get("animations") or []
    accessors = document.get("accessors") or []
    clips = []
    for index, animation in enumerate(animations):
        duration = 0.0
        for sampler in animation.get("samplers") or []:
            input_accessor = sampler.get("input")
            if input_accessor is None or input_accessor >= len(accessors):
                continue
            maximum = accessors[input_accessor].get("max") or []
            if maximum:
                try:
                    duration = max(duration, float(maximum[0]))
                except (TypeError, ValueError):
                    pass
        targets = []
        for channel in animation.get("channels") or []:
            channel_target = channel.get("target") or {}
            node = channel_target.get("node")
            if node is not None and 0 <= node < len(nodes):
                targets.append({"node": node, "name": nodes[node].get("name"),
                                "path": channel_target.get("path")})
        clips.append({
            "index": index,
            "name": animation.get("name") or f"clip_{index}",
            "duration_seconds": round(duration, 3),
            "channels": len(animation.get("channels") or []),
            "target_nodes": sorted({t["name"] for t in targets if t["name"]}),
        })
    issues, warnings = [], []
    if not skins:
        issues.append("file has no skin/armature")
    if skins and not clips:
        warnings.append("rig has no animation clips")
    if rig_type == "quadruped":
        warnings.append("quadruped/generic rig: do not apply a humanoid animation set")
    return {
        "ok": bool(skins),
        "path": target,
        "container": container,
        "sha256": sha256_file(target),
        "rig_type": rig_type,
        "humanoid_role_coverage": round(humanoid_ratio, 3),
        "matched_humanoid_roles": matched_roles,
        "quadruped_markers": quadruped_hits,
        "skins": joints_by_skin,
        "joint_count": len({j["name"] for j in joints}),
        "animations": clips,
        "issues": issues,
        "warnings": warnings,
        "note": "Classification is heuristic based on joint names. Verify the rig visually "
                "in Blender or the target engine before wiring animation states.",
    }


def create_retarget_map(character_path: str, animation_path: str,
                        destination: str | None = None) -> dict:
    character = inspect_rig(character_path)
    animation = inspect_rig(animation_path)
    if not character.get("joint_count") or not animation.get("joint_count"):
        return {"ok": False, "error": "both files must contain a skeleton",
                "character": character.get("issues"), "animation": animation.get("issues")}
    # Build from the original joint lists to keep real node names.
    character_bones = {}
    for skin in character["skins"]:
        for name in skin["joints"]:
            character_bones.setdefault(_normalise_bone(name), name)
    animation_bones = {}
    for skin in animation["skins"]:
        for name in skin["joints"]:
            animation_bones.setdefault(_normalise_bone(name), name)
    mapping, unmatched_source, unmatched_target = [], [], []
    for normalised, source_name in animation_bones.items():
        if normalised in character_bones:
            mapping.append({"source": source_name, "target": character_bones[normalised],
                            "key": normalised, "method": "exact-normalised-name"})
        else:
            unmatched_source.append(source_name)
    matched_targets = {m["target"] for m in mapping}
    unmatched_target = [name for name in character_bones.values() if name not in matched_targets]
    total = max(len(animation_bones), 1)
    coverage = len(mapping) / total
    if character.get("rig_type") != animation.get("rig_type") and \
            "generic" not in (character.get("rig_type"), animation.get("rig_type")):
        compatible = False
        reason = (f"rig types differ: character={character.get('rig_type')}, "
                  f"animation={animation.get('rig_type')}")
    elif coverage < 0.6:
        compatible = False
        reason = f"only {coverage:.0%} of animation bones matched the character skeleton"
    else:
        compatible = True
        reason = f"{coverage:.0%} bone-name coverage"
    result = {
        "ok": compatible,
        "character": {"path": character_path, "rig_type": character.get("rig_type"),
                      "joint_count": character.get("joint_count")},
        "animation": {"path": animation_path, "rig_type": animation.get("rig_type"),
                      "joint_count": animation.get("joint_count"),
                      "clips": animation.get("animations")},
        "coverage": round(coverage, 3),
        "compatible": compatible,
        "reason": reason,
        "mapping": mapping,
        "unmatched_animation_bones": unmatched_source,
        "unmatched_character_bones": unmatched_target,
        "note": "A name map is necessary but not sufficient. Verify rest pose, scale and "
                "axis, then retarget in the engine or Blender and play the clip.",
    }
    if destination:
        path = os.path.abspath(expand(destination))
        write_json(path, result)
        result["written_to"] = path
    return result


def check_compatibility(character_path: str, animation_path: str) -> dict:
    return create_retarget_map(character_path, animation_path)


def list_animation_sources() -> dict:
    return {
        "ok": True,
        "sources": [
            {"id": "mixamo", "state": "manual-only",
             "reason": "Adobe Mixamo has no documented public API. Use the website with an "
                       "authorized account, export FBX/GLB, then validate the rig and clip.",
             "url": "https://www.mixamo.com"},
            {"id": "meshy", "state": "available" if secrets.meshy_key_source() else "not-configured",
             "reason": "Use meshy_animation_library and meshy_create_animation; output is "
                       "for humanoid/biped rigs only. Call meshy_setup_guide if no key is set.",
             "url": "https://docs.meshy.ai/en/api/animation"},
            {"id": "engine-native", "state": "manual",
             "reason": "Unity/Unreal/Godot animation libraries are imported through their own "
                       "editors or package managers.", "url": "https://docs.unity3d.com"},
            {"id": "blender", "state": "available-if-blender-detected",
             "reason": "Author or edit actions in Blender and export glTF/FBX with animations.",
             "url": "https://docs.blender.org"},
        ],
        "provider_note": "This tool never downloads animations from providers without a "
                         "documented API and explicit download permission.",
    }
