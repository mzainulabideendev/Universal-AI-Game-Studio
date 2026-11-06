"""Generate the V5 Unity vertical-slice assets in Blender.

Creates and exports:
  Monkey.fbx    rigged low-poly monkey with Idle, Walk and Jump actions
  Jungle.fbx    jungle terrain, trees, rocks and a river
  Banana.fbx    banana collectible mesh

Run headless:
  blender -b -P scripts/v5-blender-assets.py -- <output-dir>

All geometry is authored here; nothing is downloaded or simulated.
"""

import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

OUT_DIR = os.path.abspath(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else os.path.abspath("validation/unity-jungle-v5/Assets/V5/Art")
os.makedirs(OUT_DIR, exist_ok=True)

RNG = random.Random(20261106)


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions, bpy.data.materials):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name, color, roughness=0.62, metallic=0.0):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def tag(obj, mat, group=None, smooth=True):
    obj.data.materials.append(mat)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    if group:
        vg = obj.vertex_groups.new(name=group)
        vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    return obj


def sphere(name, location, scale, mat, group=None, segments=16, rings=8):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return tag(obj, mat, group)


def cylinder_between(name, start, end, radius, mat, group=None, vertices=10):
    start, end = Vector(start), Vector(end)
    direction = end - start
    length = direction.length
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=length,
                                        location=(start + end) / 2)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return tag(obj, mat, group)


def join(objects, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.object
    joined.name = name
    return joined


def build_monkey():
    fur = material("MonkeyFur", (0.32, 0.19, 0.10))
    fur_light = material("MonkeyMuzzle", (0.70, 0.52, 0.34))
    dark = material("MonkeyEyes", (0.02, 0.02, 0.02), roughness=0.25)

    parts = [
        sphere("Body", (0, 0, 1.02), (0.34, 0.28, 0.46), fur, "spine"),
        sphere("Chest", (0, -0.03, 1.28), (0.30, 0.24, 0.26), fur, "chest"),
        sphere("Head", (0, -0.02, 1.65), (0.31, 0.29, 0.30), fur, "head"),
        sphere("Muzzle", (0, -0.25, 1.56), (0.19, 0.14, 0.15), fur_light, "head"),
        sphere("EarL", (0.32, 0.00, 1.70), (0.12, 0.055, 0.13), fur, "head"),
        sphere("EarR", (-0.32, 0.00, 1.70), (0.12, 0.055, 0.13), fur, "head"),
        sphere("EyeL", (0.11, -0.27, 1.73), (0.045, 0.035, 0.05), dark, "head", 12, 6),
        sphere("EyeR", (-0.11, -0.27, 1.73), (0.045, 0.035, 0.05), dark, "head", 12, 6),
    ]

    for side, sign in (("L", 1), ("R", -1)):
        parts += [
            cylinder_between(f"UpperArm{side}", (0.30 * sign, 0, 1.38),
                             (0.45 * sign, -0.02, 1.10), 0.085, fur, f"upper_arm.{side}"),
            cylinder_between(f"LowerArm{side}", (0.45 * sign, -0.02, 1.10),
                             (0.52 * sign, -0.06, 0.84), 0.075, fur, f"lower_arm.{side}"),
            sphere(f"Hand{side}", (0.53 * sign, -0.07, 0.80), (0.10, 0.09, 0.09),
                   fur_light, f"lower_arm.{side}", 12, 6),
            cylinder_between(f"Thigh{side}", (0.15 * sign, 0, 0.86),
                             (0.16 * sign, -0.01, 0.54), 0.11, fur, f"thigh.{side}"),
            cylinder_between(f"Shin{side}", (0.16 * sign, -0.01, 0.54),
                             (0.17 * sign, -0.03, 0.22), 0.085, fur, f"shin.{side}"),
            sphere(f"Foot{side}", (0.17 * sign, -0.10, 0.16), (0.13, 0.20, 0.075),
                   fur_light, f"shin.{side}", 12, 6),
        ]

    # Tail: a chain of spheres, all weighted to the tail bone.
    for index in range(6):
        t = index / 5.0
        parts.append(sphere(
            f"Tail{index}",
            (0.0, 0.28 + 0.30 * t, 0.92 + 0.42 * math.sin(t * 1.7)),
            (0.075 - 0.03 * t, 0.075 - 0.03 * t, 0.075 - 0.03 * t),
            fur, "tail", 12, 6))

    monkey = join(parts, "Monkey")

    arm_data = bpy.data.armatures.new("MonkeyRig")
    arm_obj = bpy.data.objects.new("MonkeyRig", arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    bones = {}

    def bone(name, head, tail, parent=None):
        eb = arm_data.edit_bones.new(name)
        eb.head = head
        eb.tail = tail
        if parent:
            eb.parent = bones[parent]
            eb.use_connect = False
        bones[name] = eb

    bone("root", (0, 0, 0), (0, 0, 0.2))
    bone("hips", (0, 0, 0.82), (0, 0, 1.0), "root")
    bone("spine", (0, 0, 1.0), (0, 0, 1.28), "hips")
    bone("chest", (0, 0, 1.28), (0, 0, 1.44), "spine")
    bone("head", (0, 0, 1.44), (0, 0, 1.84), "chest")
    bone("tail", (0, 0.25, 0.95), (0, 0.62, 1.35), "hips")
    for side, sign in (("L", 1), ("R", -1)):
        bone(f"upper_arm.{side}", (0.30 * sign, 0, 1.38), (0.45 * sign, -0.02, 1.10), "chest")
        bone(f"lower_arm.{side}", (0.45 * sign, -0.02, 1.10), (0.53 * sign, -0.06, 0.82),
             f"upper_arm.{side}")
        bone(f"thigh.{side}", (0.15 * sign, 0, 0.86), (0.16 * sign, -0.01, 0.54), "hips")
        bone(f"shin.{side}", (0.16 * sign, -0.01, 0.54), (0.17 * sign, -0.03, 0.22),
             f"thigh.{side}")
    bpy.ops.object.mode_set(mode="OBJECT")

    monkey.parent = arm_obj
    modifier = monkey.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm_obj

    arm_obj.animation_data_create()

    def set_action(name, frames):
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        arm_obj.animation_data.action = action
        for frame, poses in frames:
            bpy.context.scene.frame_set(frame)
            for bone_name, rotation in poses.items():
                pose_bone = arm_obj.pose.bones[bone_name]
                pose_bone.rotation_mode = "XYZ"
                pose_bone.rotation_euler = rotation
                pose_bone.keyframe_insert("rotation_euler", frame=frame)
        return action

    deg = math.radians
    set_action("Idle", [
        (1, {"head": (0, 0, 0), "tail": (deg(8), 0, 0), "chest": (deg(1), 0, 0)}),
        (30, {"head": (deg(-4), 0, deg(3)), "tail": (deg(-6), 0, deg(8)), "chest": (deg(-2), 0, 0)}),
        (60, {"head": (0, 0, 0), "tail": (deg(8), 0, 0), "chest": (deg(1), 0, 0)}),
    ])
    set_action("Walk", [
        (1, {"thigh.L": (deg(28), 0, 0), "thigh.R": (deg(-28), 0, 0),
             "upper_arm.L": (deg(-30), 0, 0), "upper_arm.R": (deg(30), 0, 0),
             "tail": (deg(10), 0, deg(12))}),
        (15, {"thigh.L": (deg(-28), 0, 0), "thigh.R": (deg(28), 0, 0),
              "upper_arm.L": (deg(30), 0, 0), "upper_arm.R": (deg(-30), 0, 0),
              "tail": (deg(10), 0, deg(-12))}),
        (30, {"thigh.L": (deg(28), 0, 0), "thigh.R": (deg(-28), 0, 0),
              "upper_arm.L": (deg(-30), 0, 0), "upper_arm.R": (deg(30), 0, 0),
              "tail": (deg(10), 0, deg(12))}),
    ])
    set_action("Jump", [
        (1, {"thigh.L": (deg(35), 0, 0), "thigh.R": (deg(35), 0, 0),
             "shin.L": (deg(-55), 0, 0), "shin.R": (deg(-55), 0, 0),
             "upper_arm.L": (deg(40), 0, 0), "upper_arm.R": (deg(40), 0, 0)}),
        (8, {"thigh.L": (deg(-15), 0, 0), "thigh.R": (deg(-15), 0, 0),
             "shin.L": (deg(25), 0, 0), "shin.R": (deg(25), 0, 0),
             "upper_arm.L": (deg(-70), 0, 0), "upper_arm.R": (deg(-70), 0, 0)}),
        (30, {"thigh.L": (deg(0), 0, 0), "thigh.R": (deg(0), 0, 0),
              "shin.L": (deg(0), 0, 0), "shin.R": (deg(0), 0, 0),
              "upper_arm.L": (deg(0), 0, 0), "upper_arm.R": (deg(0), 0, 0)}),
    ])

    arm_obj.animation_data.action = bpy.data.actions["Idle"]
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 60
    bpy.context.scene.frame_set(1)
    return monkey, arm_obj


def build_jungle():
    ground = material("JungleGround", (0.16, 0.34, 0.12), roughness=0.9)
    trunk = material("TreeTrunk", (0.28, 0.16, 0.08), roughness=0.85)
    leaf_a = material("CanopyA", (0.08, 0.42, 0.14), roughness=0.8)
    leaf_b = material("CanopyB", (0.12, 0.55, 0.18), roughness=0.8)
    rock_mat = material("Rock", (0.34, 0.34, 0.36), roughness=0.9)
    water = material("River", (0.06, 0.30, 0.55), roughness=0.15, metallic=0.1)

    objects = []
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    plane = bpy.context.object
    plane.name = "Terrain"
    tag(plane, ground)
    objects.append(plane)

    # River strip.
    bpy.ops.mesh.primitive_plane_add(size=1, location=(10, 0, 0.03))
    river = bpy.context.object
    river.name = "River"
    river.scale = (4.0, 38.0, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    tag(river, water)
    objects.append(river)

    # Trees.
    for index in range(46):
        angle = RNG.uniform(0, math.tau)
        radius = RNG.uniform(7, 34)
        x = math.cos(angle) * radius
        y = math.sin(angle) * radius
        if abs(x - 10) < 5:  # keep the river clear
            x += 10
        # Keep a clear spawn/run corridor so the camera and player are visible.
        if abs(x) < 8 and -10 < y < 30:
            continue
        height = RNG.uniform(2.6, 5.2)
        trunk_obj = cylinder_between(f"Trunk{index}", (x, y, 0), (x, y, height),
                                     RNG.uniform(0.16, 0.30), trunk, vertices=7)
        objects.append(trunk_obj)
        for layer in range(3):
            canopy = sphere(
                f"Canopy{index}_{layer}",
                (x + RNG.uniform(-0.5, 0.5), y + RNG.uniform(-0.5, 0.5),
                 height + layer * 0.65),
                (RNG.uniform(1.2, 2.0), RNG.uniform(1.2, 2.0), RNG.uniform(0.9, 1.4)),
                leaf_a if layer % 2 == 0 else leaf_b, segments=12, rings=6)
            objects.append(canopy)

    # Rocks.
    for index in range(22):
        angle = RNG.uniform(0, math.tau)
        radius = RNG.uniform(4, 32)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        if abs(x) < 7 and -10 < y < 30:
            continue
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0,
                                              location=(x, y, RNG.uniform(0.1, 0.35)))
        rock = bpy.context.object
        rock.name = f"Rock{index}"
        rock.scale = (RNG.uniform(0.4, 1.1), RNG.uniform(0.4, 1.1), RNG.uniform(0.3, 0.7))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        tag(rock, rock_mat, smooth=False)
        objects.append(rock)

    # Simple ferns / bushes near the play area.
    for index in range(24):
        angle = RNG.uniform(0, math.tau)
        radius = RNG.uniform(3, 22)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        if abs(x) < 7 and -10 < y < 30:
            continue
        bush = sphere(f"Bush{index}", (x, y, 0.25),
                      (RNG.uniform(0.35, 0.8), RNG.uniform(0.35, 0.8), RNG.uniform(0.2, 0.45)),
                      leaf_b, segments=10, rings=5)
        objects.append(bush)

    return join(objects, "JungleEnvironment")


def build_banana():
    yellow = material("BananaYellow", (0.95, 0.78, 0.08), roughness=0.5)
    tip = material("BananaTip", (0.35, 0.22, 0.05), roughness=0.7)
    parts = []
    for index in range(7):
        t = index / 6.0
        angle = (t - 0.5) * 1.7
        x = math.sin(angle) * 0.26
        y = math.cos(angle) * 0.10
        z = 0.06 * math.cos((t - 0.5) * math.pi)
        parts.append(sphere(f"BananaBody{index}", (x, y, z),
                            (0.085, 0.070, 0.070), yellow, segments=10, rings=6))
    parts.append(sphere("BananaTipA", (-0.26, 0.02, 0.05), (0.045, 0.04, 0.04), tip, None, 8, 5))
    parts.append(sphere("BananaTipB", (0.26, 0.02, 0.05), (0.045, 0.04, 0.04), tip, None, 8, 5))
    return join(parts, "Banana")


def export_fbx(objects, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z",
        axis_up="Y",
        object_types={"ARMATURE", "MESH"},
        bake_anim=True,
        bake_anim_use_all_actions=True,
        bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0,
        add_leaf_bones=False,
        mesh_smooth_type="FACE",
    )


def main():
    stats = {}
    reset_scene()
    monkey, arm = build_monkey()
    export_fbx([monkey, arm], os.path.join(OUT_DIR, "Monkey.fbx"))
    stats["monkey"] = {
        "vertices": len(monkey.data.vertices),
        "triangles": sum(len(p.vertices) - 2 for p in monkey.data.polygons),
        "bones": len(arm.data.bones),
        "actions": [action.name for action in bpy.data.actions],
    }

    reset_scene()
    jungle = build_jungle()
    export_fbx([jungle], os.path.join(OUT_DIR, "Jungle.fbx"))
    stats["jungle"] = {
        "vertices": len(jungle.data.vertices),
        "triangles": sum(len(p.vertices) - 2 for p in jungle.data.polygons),
        "materials": [mat.name for mat in jungle.data.materials],
    }

    reset_scene()
    banana = build_banana()
    export_fbx([banana], os.path.join(OUT_DIR, "Banana.fbx"))
    stats["banana"] = {
        "vertices": len(banana.data.vertices),
        "triangles": sum(len(p.vertices) - 2 for p in banana.data.polygons),
    }

    stats["output_dir"] = OUT_DIR
    with open(os.path.join(OUT_DIR, "..", "..", "..", "v5-blender-assets.json"), "w",
              encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2)
    print("V5_ASSETS_OK " + json.dumps(stats))


if __name__ == "__main__":
    main()
