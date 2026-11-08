"""V6 Phase 3 character asset pipeline.

Real Blender execution for a procedural stylized monkey: geometry, materials,
procedural PBR images, UV unwrap, armature, skin weights, keyframed actions,
.blend save, GLB/glTF/FBX export, re-import validation and a rendered preview.

Every stage records evidence. A stage that fails is reported as failed; the
pipeline never upgrades a failed Blender operation to success.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path

from . import blender
from . import character_spec
from .util import ToolError, now_iso, sha256_file

DEFAULT_BLENDER_CANDIDATES = (
    r"D:\blender data\blender.exe",
)
REQUIRED_STAGES = (
    "spec-validated", "blender-build", "geometry-validated",
    "materials-validated", "uv-validated", "rig-validated",
    "animations-created", "blend-saved", "glb-exported", "gltf-exported",
    "fbx-exported", "glb-validated", "gltf-validated", "glb-reimported",
    "preview-rendered",
)


def resolve_blender_executable(explicit: str | None = None) -> str | None:
    for candidate in (explicit, os.environ.get("CHARACTER_BLENDER_EXE"),
                      os.environ.get("BLENDER_EXE")):
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    for candidate in DEFAULT_BLENDER_CANDIDATES:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return blender.resolve_blender(explicit)


BUILD_SCRIPT = r"""
import bpy, bmesh, os, math, random, json
from mathutils import Vector

ARGS = ARGS or {}
spec = ARGS['spec']
tier = spec['quality_tier']
seg = int(spec['geometry']['sphere_segments'])
rings = int(spec['geometry']['ring_count'])
tail_segments = int(spec['geometry']['tail_segments'])
finger_count = int(spec['geometry']['finger_count'])
tex_res = int(spec['textures']['resolution'])
uv_angle = float(spec['uv']['angle_limit_deg'])
uv_margin = float(spec['uv']['island_margin'])
seed = int(spec['provenance']['seed'])
fps = int(spec['rigging']['animation_fps'])
animations = [a['name'] for a in spec['animations']]
out_dir = ARGS['output_dir']
name = spec['name']
os.makedirs(out_dir, exist_ok=True)
tex_dir = os.path.join(out_dir, 'textures')
os.makedirs(tex_dir, exist_ok=True)
random.seed(seed)

# ---------------------------------------------------------------- scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = fps
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0

# ---------------------------------------------------------------- materials
def set_input(node, key, value):
    if key in node.inputs:
        node.inputs[key].default_value = value

def solid_material(entry):
    mat = bpy.data.materials.new(entry['name'])
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    set_input(bsdf, 'Base Color', tuple(entry['base_color']))
    set_input(bsdf, 'Roughness', float(entry['roughness']))
    set_input(bsdf, 'Metallic', float(entry['metallic']))
    mat.diffuse_color = tuple(entry['base_color'])
    mat['pbr_channels'] = {k: v for k, v in entry['channels'].items()}
    return mat

def value_noise(x, y, octaves=3):
    total, amplitude, frequency, norm = 0.0, 1.0, 1.0, 0.0
    for _ in range(octaves):
        xi, yi = int(math.floor(x * frequency)), int(math.floor(y * frequency))
        xf, yf = x * frequency - xi, y * frequency - yi
        def h(ix, iy):
            n = (ix * 374761393 + iy * 668265263 + seed * 144665) & 0xFFFFFFFF
            n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
            return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0
        v00, v10 = h(xi, yi), h(xi + 1, yi)
        v01, v11 = h(xi, yi + 1), h(xi + 1, yi + 1)
        sx = xf * xf * (3 - 2 * xf)
        sy = yf * yf * (3 - 2 * yf)
        value = (v00 * (1 - sx) + v10 * sx) * (1 - sy) + (v01 * (1 - sx) + v11 * sx) * sy
        total += value * amplitude
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm

def save_image(name_value, pixels, path, colorspace):
    img = bpy.data.images.new(name_value, width=tex_res, height=tex_res, alpha=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(pixels)
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    img.filepath = path
    img.reload()
    return img

# Real local procedural PBR maps. These are generated images, not photographs,
# not scans and not AI output. AO/emission/opacity are honestly absent.
base_pixels = [0.0] * (tex_res * tex_res * 4)
rough_pixels = [0.0] * (tex_res * tex_res * 4)
normal_pixels = [0.0] * (tex_res * tex_res * 4)
height = [0.0] * (tex_res * tex_res)
for y in range(tex_res):
    for x in range(tex_res):
        u = x / max(1, tex_res - 1)
        v = y / max(1, tex_res - 1)
        n = value_noise(u * 9.0, v * 9.0, 4)
        fine = value_noise(u * 41.0, v * 41.0, 2)
        fur = max(0.0, min(1.0, n * 0.7 + fine * 0.3))
        idx = (y * tex_res + x)
        height[idx] = fur
        i = idx * 4
        base_pixels[i] = 0.18 + 0.20 * fur
        base_pixels[i + 1] = 0.10 + 0.12 * fur
        base_pixels[i + 2] = 0.045 + 0.06 * fur
        base_pixels[i + 3] = 1.0
        r = 0.60 + 0.25 * fine
        rough_pixels[i] = r
        rough_pixels[i + 1] = r
        rough_pixels[i + 2] = r
        rough_pixels[i + 3] = 1.0
for y in range(tex_res):
    for x in range(tex_res):
        idx = y * tex_res + x
        left = height[y * tex_res + max(0, x - 1)]
        right = height[y * tex_res + min(tex_res - 1, x + 1)]
        down = height[max(0, y - 1) * tex_res + x]
        up = height[min(tex_res - 1, y + 1) * tex_res + x]
        dx = (left - right) * 2.2
        dy = (down - up) * 2.2
        length = math.sqrt(dx * dx + dy * dy + 1.0)
        i = idx * 4
        normal_pixels[i] = dx / length * 0.5 + 0.5
        normal_pixels[i + 1] = dy / length * 0.5 + 0.5
        normal_pixels[i + 2] = 1.0 / length * 0.5 + 0.5
        normal_pixels[i + 3] = 1.0

base_img = save_image('T_Monkey_Fur_BaseColor', base_pixels,
                      os.path.join(tex_dir, 'monkey_fur_basecolor.png'), 'sRGB')
rough_img = save_image('T_Monkey_Fur_Roughness', rough_pixels,
                       os.path.join(tex_dir, 'monkey_fur_roughness.png'), 'Non-Color')
normal_img = save_image('T_Monkey_Fur_Normal', normal_pixels,
                        os.path.join(tex_dir, 'monkey_fur_normal.png'), 'Non-Color')

materials = {}
for entry in spec['materials']:
    if entry['name'] == 'M_Monkey_Fur':
        mat = bpy.data.materials.new(entry['name'])
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get('Principled BSDF')
        set_input(bsdf, 'Base Color', tuple(entry['base_color']))
        set_input(bsdf, 'Roughness', float(entry['roughness']))
        set_input(bsdf, 'Metallic', float(entry['metallic']))
        base_node = nt.nodes.new('ShaderNodeTexImage')
        base_node.name = 'BaseColorTexture'
        base_node.image = base_img
        nt.links.new(base_node.outputs['Color'], bsdf.inputs['Base Color'])
        rough_node = nt.nodes.new('ShaderNodeTexImage')
        rough_node.name = 'RoughnessTexture'
        rough_node.image = rough_img
        nt.links.new(rough_node.outputs['Color'], bsdf.inputs['Roughness'])
        tex_node = nt.nodes.new('ShaderNodeTexImage')
        tex_node.name = 'NormalTexture'
        tex_node.image = normal_img
        normal_node = nt.nodes.new('ShaderNodeNormalMap')
        normal_node.name = 'NormalMap'
        set_input(normal_node, 'Strength', 0.8)
        nt.links.new(tex_node.outputs['Color'], normal_node.inputs['Color'])
        nt.links.new(normal_node.outputs['Normal'], bsdf.inputs['Normal'])
        mat.diffuse_color = tuple(entry['base_color'])
        mat['pbr_channels'] = dict(entry['channels'])
        materials[entry['name']] = mat
    else:
        materials[entry['name']] = solid_material(entry)

# ---------------------------------------------------------------- geometry
parts = []

def activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob

def smooth(ob):
    for poly in ob.data.polygons:
        poly.use_smooth = True

def add_sphere(label, location, scale, material, segments=None, ring_count=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=int(segments or seg), ring_count=int(ring_count or rings),
        radius=1.0, location=location)
    ob = bpy.context.active_object
    ob.name = label
    ob.scale = scale
    activate(ob)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(ob)
    ob.data.materials.append(materials[material])
    ob['game_studio_part'] = label
    parts.append(ob)
    return ob

def add_capsule(label, start, end, radius, material, vertices=None):
    a, b = Vector(start), Vector(end)
    delta = b - a
    length = delta.length
    midpoint = a + delta * 0.5
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=int(vertices or max(8, seg // 2)), radius=radius, depth=length,
        location=midpoint)
    ob = bpy.context.active_object
    ob.name = label
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(delta.normalized())
    activate(ob)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    smooth(ob)
    ob.data.materials.append(materials[material])
    ob['game_studio_part'] = label
    parts.append(ob)
    # rounded joints keep the silhouette game-like instead of open tubes
    add_sphere(label + '_joint_a', start, (radius, radius, radius), material,
               max(8, seg // 2), max(6, rings // 2))
    add_sphere(label + '_joint_b', end, (radius, radius, radius), material,
               max(8, seg // 2), max(6, rings // 2))
    return ob

FUR = 'M_Monkey_Fur'
SKIN = 'M_Monkey_Skin'
EYE = 'M_Monkey_EyeWhite'
IRIS = 'M_Monkey_Iris'
PUPIL = 'M_Monkey_Pupil'
NOSE = 'M_Monkey_Nose'
INNER = 'M_Monkey_InnerEar'

# torso / pelvis / chest
add_sphere('Torso', (0, 0, 1.02), (0.30, 0.22, 0.34), FUR)
add_sphere('Pelvis', (0, 0, 0.74), (0.25, 0.19, 0.20), FUR)
add_sphere('Chest', (0, -0.01, 1.22), (0.27, 0.20, 0.20), FUR)
# head and face
add_sphere('Head', (0, 0, 1.47), (0.24, 0.22, 0.23), FUR)
add_sphere('Muzzle', (0, -0.20, 1.40), (0.15, 0.12, 0.11), SKIN)
add_sphere('BrowRidge', (0, -0.17, 1.53), (0.19, 0.08, 0.06), FUR)
add_sphere('Nose', (0, -0.315, 1.43), (0.055, 0.035, 0.04), NOSE)
add_sphere('Mouth', (0, -0.305, 1.35), (0.075, 0.02, 0.018), NOSE)
for side, sx in (('L', 1), ('R', -1)):
    add_sphere('EyeWhite_' + side, (0.085 * sx, -0.195, 1.50), (0.058, 0.045, 0.058), EYE)
    add_sphere('Iris_' + side, (0.085 * sx, -0.235, 1.50), (0.030, 0.016, 0.030), IRIS)
    add_sphere('Pupil_' + side, (0.085 * sx, -0.247, 1.50), (0.013, 0.010, 0.013), PUPIL)
    add_sphere('Ear_' + side, (0.235 * sx, 0.0, 1.50), (0.045, 0.085, 0.095), FUR)
    add_sphere('InnerEar_' + side, (0.255 * sx, -0.01, 1.50), (0.022, 0.050, 0.058), INNER)
    # arms: shoulder -> elbow -> wrist
    shoulder = (0.295 * sx, 0.0, 1.24)
    elbow = (0.375 * sx, -0.02, 0.99)
    wrist = (0.355 * sx, -0.06, 0.77)
    add_capsule('UpperArm_' + side, shoulder, elbow, 0.075, FUR)
    add_capsule('Forearm_' + side, elbow, wrist, 0.060, FUR)
    add_sphere('Hand_' + side, wrist, (0.070, 0.060, 0.085), SKIN)
    for f in range(finger_count):
        fx = 0.355 * sx + (f - (finger_count - 1) / 2.0) * 0.035
        add_sphere('Finger_%s_%d' % (side, f), (fx, -0.085, 0.685),
                   (0.018, 0.020, 0.055), SKIN, max(8, seg // 3), max(6, rings // 3))
    # legs: hip -> knee -> ankle
    hip = (0.145 * sx, 0.0, 0.72)
    knee = (0.155 * sx, -0.01, 0.43)
    ankle = (0.150 * sx, 0.0, 0.15)
    add_capsule('Thigh_' + side, hip, knee, 0.095, FUR)
    add_capsule('Shin_' + side, knee, ankle, 0.070, FUR)
    add_sphere('Foot_' + side, (0.150 * sx, -0.06, 0.075), (0.085, 0.145, 0.065), SKIN)
    for t in range(3):
        tx = 0.150 * sx + (t - 1) * 0.045
        add_sphere('Toe_%s_%d' % (side, t), (tx, -0.185, 0.055),
                   (0.028, 0.045, 0.030), SKIN, max(8, seg // 3), max(6, rings // 3))

# tail: genuine geometry chain, decreasing radius
if tail_segments > 0:
    for i in range(tail_segments):
        k = i / max(1, tail_segments - 1)
        tx = 0.0
        ty = 0.16 + k * 0.46
        tz = 0.74 + math.sin(k * math.pi * 0.9) * 0.30 - k * 0.05
        radius = 0.055 * (1.0 - 0.70 * k)
        add_sphere('Tail_%02d' % i, (tx, ty, tz), (radius, radius * 1.25, radius), FUR,
                   max(8, seg // 2), max(6, rings // 2))

# ---------------------------------------------------------------- join + UV
bpy.ops.object.select_all(action='DESELECT')
for ob in parts:
    ob.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
character = bpy.context.active_object
character.name = 'JungleMonkey'
character.data.name = 'JungleMonkeyMesh'
bpy.context.scene.cursor.location = (0, 0, 0)
bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
character['game_studio_role'] = 'player_character'
character['game_studio_quality_tier'] = tier
character['game_studio_generation'] = 'procedural-blender'

activate(character)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(uv_angle),
                         island_margin=uv_margin, correct_aspect=True,
                         scale_to_bounds=False)
bpy.ops.mesh.select_all(action='SELECT')
try:
    bpy.ops.uv.pack_islands(margin=uv_margin, rotate=True)
except Exception:
    pass
bpy.ops.object.mode_set(mode='OBJECT')

# UV coverage (rasterised at 64x64 from real UV triangles)
uv_layer = character.data.uv_layers.active
coverage = 0.0
if uv_layer:
    grid = 64
    covered = bytearray(grid * grid)
    me = character.data
    me.calc_loop_triangles()
    uv_data = uv_layer.data
    for tri in me.loop_triangles:
        pts = [uv_data[li].uv for li in tri.loops]
        minx = max(0, int(min(p.x for p in pts) * grid) - 1)
        maxx = min(grid - 1, int(max(p.x for p in pts) * grid) + 1)
        miny = max(0, int(min(p.y for p in pts) * grid) - 1)
        maxy = min(grid - 1, int(max(p.y for p in pts) * grid) + 1)
        ax, ay = pts[0].x, pts[0].y
        bx, by = pts[1].x, pts[1].y
        cx, cy = pts[2].x, pts[2].y
        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denom) < 1e-12:
            continue
        for gy in range(miny, maxy + 1):
            for gx in range(minx, maxx + 1):
                px = (gx + 0.5) / grid
                py = (gy + 0.5) / grid
                w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
                w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
                w2 = 1.0 - w0 - w1
                if w0 >= -1e-6 and w1 >= -1e-6 and w2 >= -1e-6:
                    covered[gy * grid + gx] = 1
    coverage = sum(covered) / (grid * grid)

# ---------------------------------------------------------------- armature
bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
arm = bpy.context.active_object
arm.name = 'Armature_JungleMonkey'
arm.data.name = 'Skeleton_JungleMonkey'
bones = arm.data.edit_bones
bones.remove(bones[0])

def bone(name_value, head, tail, parent=None, connected=False):
    b = bones.new(name_value)
    b.head = head
    b.tail = tail
    if parent is not None:
        b.parent = bones[parent]
        b.use_connect = connected
    return b

bone('root', (0, 0, 0.0), (0, 0, 0.18))
bone('pelvis', (0, 0, 0.62), (0, 0, 0.82), 'root')
bone('spine', (0, 0, 0.82), (0, 0, 1.06), 'pelvis', True)
bone('chest', (0, 0, 1.06), (0, 0, 1.26), 'spine', True)
bone('neck', (0, 0, 1.26), (0, 0, 1.36), 'chest', True)
bone('head', (0, 0, 1.36), (0, 0, 1.66), 'neck', True)
for side, sx in (('L', 1), ('R', -1)):
    bone('ear.' + side, (0.20 * sx, 0, 1.50), (0.30 * sx, 0, 1.53), 'head')
    bone('upper_arm.' + side, (0.295 * sx, 0, 1.24), (0.375 * sx, -0.02, 0.99), 'chest')
    bone('forearm.' + side, (0.375 * sx, -0.02, 0.99), (0.355 * sx, -0.06, 0.77), 'upper_arm.' + side, True)
    bone('hand.' + side, (0.355 * sx, -0.06, 0.77), (0.355 * sx, -0.10, 0.64), 'forearm.' + side, True)
    bone('thigh.' + side, (0.145 * sx, 0, 0.72), (0.155 * sx, -0.01, 0.43), 'pelvis')
    bone('shin.' + side, (0.155 * sx, -0.01, 0.43), (0.150 * sx, 0, 0.15), 'thigh.' + side, True)
    bone('foot.' + side, (0.150 * sx, 0, 0.15), (0.150 * sx, -0.19, 0.06), 'shin.' + side, True)
if tail_segments > 0:
    prev = 'pelvis'
    for i in range(min(3, tail_segments)):
        k = (i + 1) / min(3, tail_segments)
        head_p = (0, 0.16 + (k - 0.33) * 0.46, 0.74 + math.sin((k - 0.33) * math.pi * 0.9) * 0.30)
        tail_p = (0, 0.16 + k * 0.46, 0.74 + math.sin(k * math.pi * 0.9) * 0.30)
        bone('tail.%02d' % (i + 1), head_p, tail_p, prev, i > 0)
        prev = 'tail.%02d' % (i + 1)
bpy.ops.object.mode_set(mode='OBJECT')

# automatic weights, with deterministic nearest-bone fallback
bpy.ops.object.select_all(action='DESELECT')
character.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
weight_mode = 'automatic'
try:
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
except Exception:
    weight_mode = 'fallback'
if not character.vertex_groups:
    weight_mode = 'fallback'
if weight_mode == 'fallback':
    for b in arm.data.bones:
        if b.name not in character.vertex_groups:
            character.vertex_groups.new(name=b.name)
    segments = []
    for b in arm.data.bones:
        segments.append((b.name, b.head_local.copy(), b.tail_local.copy()))
    for v in character.data.vertices:
        p = v.co
        best = None
        best_dist = 1e18
        for bone_name, head, tail in segments:
            ab = tail - head
            length2 = ab.length_squared
            t = 0.0 if length2 == 0 else max(0.0, min(1.0, (p - head).dot(ab) / length2))
            closest = head + ab * t
            dist = (p - closest).length
            if dist < best_dist:
                best_dist = dist
                best = bone_name
        character.vertex_groups[best].add([v.index], 1.0, 'REPLACE')
    modifier = character.modifiers.get('Armature') or character.modifiers.new('Armature', 'ARMATURE')
    modifier.object = arm
    character.parent = arm
    character.matrix_parent_inverse = arm.matrix_world.inverted()

# Complete any unweighted vertices deterministically. Automatic bone-heat can
# leave interior/overlapping vertices unweighted; they are assigned to the
# nearest bone so the exported rig has no unskinned vertices.
for b in arm.data.bones:
    if b.name not in character.vertex_groups:
        character.vertex_groups.new(name=b.name)
segments = [(b.name, b.head_local.copy(), b.tail_local.copy()) for b in arm.data.bones]
for v in character.data.vertices:
    if sum(g.weight for g in v.groups) > 1e-6:
        continue
    p = v.co
    best, best_dist = None, 1e18
    for bone_name, head, tail in segments:
        ab = tail - head
        length2 = ab.length_squared
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, (p - head).dot(ab) / length2))
        dist = (p - (head + ab * t)).length
        if dist < best_dist:
            best, best_dist = bone_name, dist
    character.vertex_groups[best].add([v.index], 1.0, 'REPLACE')

# weight validation
weighted = 0
min_sum = 1e9
max_sum = -1e9
for v in character.data.vertices:
    total = sum(g.weight for g in v.groups)
    if total > 1e-6:
        weighted += 1
    min_sum = min(min_sum, total)
    max_sum = max(max_sum, total)
weighted_ratio = weighted / max(1, len(character.data.vertices))

# ---------------------------------------------------------------- animations
pose = arm.pose
arm.animation_data_create()
action_report = []
def key_rot(bone_name, frame, xyz):
    pb = pose.bones[bone_name]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = xyz
    pb.keyframe_insert(data_path='rotation_euler', frame=frame)

def count_fcurves(act):
    try:
        return len(act.fcurves)
    except AttributeError:
        pass
    total = 0
    for layer in act.layers:
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', []):
                total += len(bag.fcurves)
    return total

def build_action(action_name, frames, keys):
    act = bpy.data.actions.new(action_name)
    act.use_fake_user = True
    arm.animation_data.action = act
    for frame, values in keys:
        for bone_name, xyz in values.items():
            key_rot(bone_name, frame, xyz)
    # ensure the action reports a real frame range and keyframes
    action_report.append({'name': act.name, 'frame_range': [float(v) for v in act.frame_range],
                          'fcurves': count_fcurves(act)})
    return act

if 'idle' in animations:
    build_action('Idle', 60, [
        (1, {'chest': (0, 0, 0), 'head': (0, 0, 0)}),
        (30, {'chest': (math.radians(2), 0, math.radians(3)), 'head': (math.radians(-3), 0, math.radians(4))}),
        (60, {'chest': (0, 0, 0), 'head': (0, 0, 0)}),
    ])
if 'walk' in animations:
    build_action('Walk', 25, [
        (1, {'thigh.L': (math.radians(-22), 0, 0), 'thigh.R': (math.radians(22), 0, 0), 'upper_arm.L': (math.radians(18), 0, 0)}),
        (7, {'thigh.L': (0, 0, 0), 'thigh.R': (0, 0, 0), 'upper_arm.L': (0, 0, 0)}),
        (13, {'thigh.L': (math.radians(22), 0, 0), 'thigh.R': (math.radians(-22), 0, 0), 'upper_arm.L': (math.radians(-18), 0, 0)}),
        (19, {'thigh.L': (0, 0, 0), 'thigh.R': (0, 0, 0), 'upper_arm.L': (0, 0, 0)}),
        (25, {'thigh.L': (math.radians(-22), 0, 0), 'thigh.R': (math.radians(22), 0, 0), 'upper_arm.L': (math.radians(18), 0, 0)}),
    ])
if 'run' in animations:
    build_action('Run', 19, [
        (1, {'thigh.L': (math.radians(-45), 0, 0), 'thigh.R': (math.radians(45), 0, 0), 'upper_arm.L': (math.radians(40), 0, 0), 'chest': (math.radians(8), 0, 0)}),
        (6, {'thigh.L': (math.radians(10), 0, 0), 'thigh.R': (math.radians(-10), 0, 0), 'upper_arm.L': (math.radians(-20), 0, 0)}),
        (11, {'thigh.L': (math.radians(45), 0, 0), 'thigh.R': (math.radians(-45), 0, 0), 'upper_arm.L': (math.radians(-40), 0, 0)}),
        (16, {'thigh.L': (math.radians(-10), 0, 0), 'thigh.R': (math.radians(10), 0, 0), 'upper_arm.L': (math.radians(20), 0, 0)}),
        (19, {'thigh.L': (math.radians(-45), 0, 0), 'thigh.R': (math.radians(45), 0, 0), 'upper_arm.L': (math.radians(40), 0, 0), 'chest': (math.radians(8), 0, 0)}),
    ])
if 'jump' in animations:
    build_action('Jump', 30, [
        (1, {'root': (0, 0, 0), 'thigh.L': (0, 0, 0), 'thigh.R': (0, 0, 0)}),
        (8, {'thigh.L': (math.radians(35), 0, 0), 'thigh.R': (math.radians(35), 0, 0), 'chest': (math.radians(-12), 0, 0)}),
        (16, {'thigh.L': (math.radians(-20), 0, 0), 'thigh.R': (math.radians(-20), 0, 0), 'chest': (math.radians(10), 0, 0)}),
        (24, {'thigh.L': (math.radians(25), 0, 0), 'thigh.R': (math.radians(25), 0, 0)}),
        (30, {'thigh.L': (0, 0, 0), 'thigh.R': (0, 0, 0), 'chest': (0, 0, 0)}),
    ])
arm.animation_data.action = bpy.data.actions.get('Idle') or (
    bpy.data.actions[0] if bpy.data.actions else None)

# ---------------------------------------------------------------- lighting/camera
bpy.ops.object.light_add(type='AREA', location=(2.2, -2.6, 2.6))
key = bpy.context.active_object
key.name = 'KeyLight'
key.data.energy = 420.0
key.data.size = 2.4
key.rotation_euler = (math.radians(38), 0, math.radians(40))
bpy.ops.object.light_add(type='AREA', location=(-2.4, -1.6, 1.4))
fill = bpy.context.active_object
fill.name = 'FillLight'
fill.data.energy = 160.0
fill.data.size = 3.0
fill.rotation_euler = (math.radians(70), 0, math.radians(-50))
bpy.ops.object.camera_add(location=(1.85, -2.75, 1.60))
cam = bpy.context.active_object
cam.name = 'PreviewCamera'
target = Vector((0, 0, 0.82))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 52
scene.camera = cam
world = bpy.data.worlds.new('World')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.09, 0.14, 0.10, 1.0)
    bg.inputs['Strength'].default_value = 0.55
scene.render.resolution_x = ARGS.get('preview_width', 720)
scene.render.resolution_y = ARGS.get('preview_height', 720)
scene.render.film_transparent = False

# ---------------------------------------------------------------- topology
me = character.data
me.calc_loop_triangles()
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
loose = sum(1 for v in bm.verts if not v.link_edges)
degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
bm.free()
triangles = len(me.loop_triangles)

# ---------------------------------------------------------------- material audit
def linked_node(node, key):
    if node is None:
        return None
    socket = node.inputs.get(key)
    if socket is None or not socket.is_linked:
        return None
    return socket.links[0].from_node

def image_upstream(node, key):
    # True only when the socket is fed (possibly via Normal Map) by an image.
    source = linked_node(node, key)
    if source is None:
        return False
    if source.type == 'TEX_IMAGE':
        return True
    if key == 'Normal' and source.type == 'NORMAL_MAP':
        color_source = linked_node(source, 'Color')
        return bool(color_source and color_source.type == 'TEX_IMAGE')
    return False

def emission_is_on(bsdf):
    strength_socket = bsdf.inputs.get('Emission Strength')
    strength = float(strength_socket.default_value) if strength_socket else 0.0
    color_socket = bsdf.inputs.get('Emission Color') or bsdf.inputs.get('Emission')
    color = tuple(color_socket.default_value)[:3] if color_socket else (0.0, 0.0, 0.0)
    return strength > 0.0 and max(color) > 0.0

material_report = []
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    nodes = list(mat.node_tree.nodes)
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    images = []
    for node in nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            img = node.image
            images.append({
                'name': img.name,
                'filepath': img.filepath,
                'exists': bool(img.packed_file) or os.path.isfile(bpy.path.abspath(img.filepath)),
                'size': list(img.size),
                'colorspace': img.colorspace_settings.name,
                'packed': bool(img.packed_file),
            })
    channels = {}
    if bsdf:
        alpha_socket = bsdf.inputs.get('Alpha')
        alpha = float(alpha_socket.default_value) if alpha_socket else 1.0
        # ``mat.blend_method`` is not a reliable opacity indicator in Blender 4.2+
        # (it can report DITHERED for an opaque material), so read the real
        # shader inputs instead of guessing from the render method.
        channels = {
            'base_color': 'texture' if image_upstream(bsdf, 'Base Color') else 'constant',
            'roughness': 'texture' if image_upstream(bsdf, 'Roughness') else 'constant',
            'normal': 'texture' if image_upstream(bsdf, 'Normal') else 'absent',
            'metallic': 'texture' if image_upstream(bsdf, 'Metallic') else 'constant',
            'ao': 'absent',
            'emission': ('texture' if image_upstream(bsdf, 'Emission Color')
                         or image_upstream(bsdf, 'Emission')
                         else ('constant' if emission_is_on(bsdf) else 'absent')),
            'opacity': ('texture' if image_upstream(bsdf, 'Alpha')
                        else ('constant' if alpha < 0.999 else 'absent')),
        }
    material_report.append({
        'name': mat.name, 'node_types': sorted({n.type for n in nodes}),
        'images': images, 'channels': channels,
        'declared_channels': dict(mat.get('pbr_channels', {})),
    })

# pack images so the .blend is self-contained, then save
for img in (base_img, rough_img, normal_img):
    try:
        img.pack()
    except Exception:
        pass
blend_path = os.path.join(out_dir, name + '.blend')
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

# ---------------------------------------------------------------- exports
def export_glb():
    kwargs = dict(filepath=os.path.join(out_dir, name + '.glb'),
                  export_format='GLB', use_selection=False, export_apply=True,
                  export_yup=True, export_animations=True,
                  export_animation_mode='ACTIONS', export_skins=True,
                  export_cameras=False, export_lights=False)
    bpy.ops.export_scene.gltf(**kwargs)

def export_gltf():
    kwargs = dict(filepath=os.path.join(out_dir, name + '.gltf'),
                  export_format='GLTF_SEPARATE', use_selection=False,
                  export_apply=True, export_yup=True, export_animations=True,
                  export_animation_mode='ACTIONS', export_skins=True,
                  export_cameras=False, export_lights=False)
    bpy.ops.export_scene.gltf(**kwargs)

def export_fbx():
    bpy.ops.export_scene.fbx(
        filepath=os.path.join(out_dir, name + '.fbx'), use_selection=False,
        apply_scale_options='FBX_SCALE_ALL', bake_anim=True,
        bake_anim_use_all_actions=True, axis_forward='-Z', axis_up='Y',
        path_mode='COPY', embed_textures=True)

export_errors = []
for label, fn in (('glb', export_glb), ('gltf', export_gltf),
                  ('fbx', export_fbx)):
    try:
        fn()
    except Exception as exc:
        export_errors.append('%s: %s: %s' % (label, type(exc).__name__, exc))

# ---------------------------------------------------------------- render
render_path = os.path.join(out_dir, 'preview.png')
render_engine = None
render_error = None
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
for candidate in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'):
    if candidate not in engines:
        continue
    try:
        scene.render.engine = candidate
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = render_path
        bpy.ops.render.render(write_still=True)
        if os.path.isfile(render_path) and os.path.getsize(render_path) > 0:
            render_engine = candidate
            break
    except Exception as exc:
        render_error = '%s: %s' % (type(exc).__name__, exc)
if render_engine is None:
    render_error = render_error or 'no render engine produced an image'

# ---------------------------------------------------------------- result
images_report = []
for img in bpy.data.images:
    images_report.append({
        'name': img.name, 'filepath': img.filepath,
        'size': list(img.size), 'packed': bool(img.packed_file),
        'colorspace': img.colorspace_settings.name,
        'missing': (not img.packed_file) and bool(img.filepath) and not os.path.isfile(bpy.path.abspath(img.filepath)),
    })
anim_data = [{'name': a.name, 'frame_range': [float(v) for v in a.frame_range],
              'fcurves': count_fcurves(a)} for a in bpy.data.actions]
__mcp_result = {
    'name': name, 'tier': tier, 'blend': blend_path,
    'blend_bytes': os.path.getsize(blend_path) if os.path.isfile(blend_path) else 0,
    'glb': os.path.join(out_dir, name + '.glb'),
    'gltf': os.path.join(out_dir, name + '.gltf'),
    'fbx': os.path.join(out_dir, name + '.fbx'),
    'preview': render_path if render_engine else None,
    'render_engine': render_engine, 'render_error': render_error,
    'export_errors': export_errors,
    'geometry': {
        'vertices': len(me.vertices), 'polygons': len(me.polygons),
        'triangles': triangles, 'non_manifold_edges': non_manifold,
        'loose_vertices': loose, 'degenerate_faces': degenerate,
        'materials': len(character.material_slots),
        'uv_layers': [uv.name for uv in me.uv_layers],
        'uv_coverage': round(coverage, 4),
    },
    'rig': {
        'armature': arm.name, 'bones': len(arm.data.bones),
        'bone_names': [b.name for b in arm.data.bones],
        'weight_mode': weight_mode, 'weighted_vertices': weighted,
        'weighted_ratio': round(weighted_ratio, 4),
        'min_weight_sum': round(min_sum, 4), 'max_weight_sum': round(max_sum, 4),
        'vertex_groups': len(character.vertex_groups),
        'mesh_parent': character.parent.name if character.parent else None,
        'armature_modifier': bool(character.modifiers.get('Armature')),
    },
    'animations': anim_data, 'requested_animations': animations,
    'materials': material_report, 'images': images_report,
    'textures_dir': tex_dir,
    'bounds': {
        'dimensions': [round(v, 4) for v in character.dimensions],
    },
    'quality': {
        'sphere_segments': seg, 'ring_count': rings,
        'tail_segments': tail_segments, 'finger_count': finger_count,
        'texture_resolution': tex_res, 'target_triangles': spec['geometry']['target_triangles'],
    },
    'seed': seed,
    'generation': 'procedural-blender',
    'external_assets_used': False,
}
"""


REIMPORT_SCRIPT = r"""
import bpy, os

ARGS = ARGS or {}
source = ARGS['source']
save_path = ARGS.get('save_blend')

# A genuinely empty scene: the default startup Cube (and its material) would
# otherwise be counted as imported geometry.
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(source)[1].lower()
if ext in ('.glb', '.gltf'):
    bpy.ops.import_scene.gltf(filepath=source)
elif ext == '.fbx':
    bpy.ops.import_scene.fbx(filepath=source)
else:
    raise RuntimeError('unsupported re-import format: ' + ext)


def helper_collection(ob):
    # The glTF importer adds bone-shape objects to 'glTF_not_exported'.
    return any(c.name == 'glTF_not_exported' for c in ob.users_collection)


def count_fcurves(act):
    try:
        return len(act.fcurves)
    except AttributeError:
        pass
    total = 0
    for layer in act.layers:
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', []):
                total += len(bag.fcurves)
    return total


objects = [ob for ob in bpy.data.objects if not helper_collection(ob)]
meshes = [ob for ob in objects if ob.type == 'MESH']
armatures = [ob for ob in objects if ob.type == 'ARMATURE']

mesh_report = []
triangles = 0
for ob in meshes:
    me = ob.data
    me.calc_loop_triangles()
    triangles += len(me.loop_triangles)
    mesh_report.append({
        'name': ob.name,
        'vertices': len(me.vertices),
        'triangles': len(me.loop_triangles),
        'uv_layers': [uv.name for uv in me.uv_layers],
        'materials': [ms.material.name for ms in ob.material_slots if ms.material],
        'parent': ob.parent.name if ob.parent else None,
        'armature_modifiers': [m.type for m in ob.modifiers if m.type == 'ARMATURE'],
        'vertex_groups': len(ob.vertex_groups),
    })

actions = [{'name': act.name,
            'frame_range': [float(v) for v in act.frame_range],
            'fcurves': count_fcurves(act)} for act in bpy.data.actions]

missing_images = []
for img in bpy.data.images:
    if img.packed_file:
        continue
    if img.filepath and not os.path.isfile(bpy.path.abspath(img.filepath)):
        missing_images.append(img.filepath)

material_names = sorted(m.name for m in bpy.data.materials if m.users > 0)
bone_count = sum(len(a.data.bones) for a in armatures)

# A real action must have keyframes, not just a name.
animated_actions = [a for a in actions if a['fcurves'] > 0]

if save_path:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)

__mcp_result = {
    'imported_objects': [ob.name for ob in objects],
    'helper_objects': [ob.name for ob in bpy.data.objects if helper_collection(ob)],
    'meshes': mesh_report,
    'mesh_count': len(meshes),
    'triangles': triangles,
    'armatures': [{'name': a.name, 'bones': len(a.data.bones)} for a in armatures],
    'armature_count': len(armatures),
    'bone_count': bone_count,
    'actions': actions,
    'animated_actions': [a['name'] for a in animated_actions],
    'materials': material_names,
    'material_count': len(material_names),
    'missing_images': missing_images,
    'saved': save_path or None,
}
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def png_dimensions(path: str) -> tuple[int, int] | None:
    try:
        with open(path, "rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


def _gltf_document_report(path: str, gltf: dict, result: dict) -> dict:
    """Validate a decoded glTF 2.0 document (used by .glb and .gltf)."""
    images = gltf.get("images") or []
    textures = gltf.get("textures") or []
    materials = gltf.get("materials") or []
    meshes = gltf.get("meshes") or []
    animations = gltf.get("animations") or []
    skins = gltf.get("skins") or []
    accessors = gltf.get("accessors") or []

    embedded = 0
    external = []
    for image in images:
        if "bufferView" in image:
            embedded += 1
        elif image.get("uri"):
            external.append(image["uri"])
    missing_images = [uri for uri in external
                      if not uri.startswith("data:")
                      and not os.path.isfile(os.path.join(os.path.dirname(path), uri))]
    if missing_images:
        result["errors"].append(f"missing external images: {missing_images}")

    buffers = gltf.get("buffers") or []
    missing_buffers = []
    for buffer in buffers:
        uri = buffer.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        buffer_path = os.path.join(os.path.dirname(path), uri)
        if not os.path.isfile(buffer_path):
            missing_buffers.append(uri)
        elif buffer.get("byteLength") is not None and os.path.getsize(
                buffer_path) != int(buffer["byteLength"]):
            result["warnings"].append(
                f"buffer byteLength differs from file size: {uri}")
    if missing_buffers:
        result["errors"].append(f"missing external buffers: {missing_buffers}")

    triangle_count = 0
    primitive_count = 0
    for mesh in meshes:
        for primitive in mesh.get("primitives") or []:
            primitive_count += 1
            index_accessor = primitive.get("indices")
            if index_accessor is not None and index_accessor < len(accessors):
                triangle_count += int(accessors[index_accessor].get("count", 0)) // 3
            elif primitive.get("attributes", {}).get("POSITION") is not None:
                triangle_count += int(accessors[
                    primitive["attributes"]["POSITION"]].get("count", 0)) // 3

    pos_min = pos_max = None
    for mesh in meshes:
        for primitive in mesh.get("primitives") or []:
            position = (primitive.get("attributes") or {}).get("POSITION")
            if position is not None and position < len(accessors):
                acc = accessors[position]
                if acc.get("min") and acc.get("max"):
                    pos_min = acc["min"] if pos_min is None else [
                        min(a, b) for a, b in zip(pos_min, acc["min"])]
                    pos_max = acc["max"] if pos_max is None else [
                        max(a, b) for a, b in zip(pos_max, acc["max"])]

    joints = sum(len(skin.get("joints") or []) for skin in skins)
    result.update({
        "meshes": len(meshes),
        "primitives": primitive_count,
        "triangles": triangle_count,
        "materials": len(materials),
        "textures": len(textures),
        "images": len(images),
        "embedded_images": embedded,
        "external_images": external,
        "buffers": len(buffers),
        "external_buffers": [b.get("uri") for b in buffers
                             if b.get("uri") and not b["uri"].startswith("data:")],
        "animations": len(animations),
        "animation_names": [a.get("name") for a in animations],
        "skins": len(skins),
        "joints": joints,
        "nodes": len(gltf.get("nodes") or []),
        "bounds_min": pos_min,
        "bounds_max": pos_max,
        "generator": (gltf.get("asset") or {}).get("generator"),
    })
    if not meshes:
        result["errors"].append("no meshes in export")
    if not materials:
        result["warnings"].append("no materials in export")
    if not animations:
        result["warnings"].append("no animations in export")
    if not skins:
        result["warnings"].append("no skins/rig in export")
    result["ok"] = not result["errors"]
    return result


def validate_gltf(path: str) -> dict:
    """Validate a separated .gltf JSON file plus its external buffers/images."""
    result = {"ok": False, "path": path, "errors": [], "warnings": []}
    if not os.path.isfile(path):
        result["errors"].append("file does not exist")
        return result
    size = os.path.getsize(path)
    result.update({"bytes": size, "sha256": sha256_file(path)})
    if size <= 0:
        result["errors"].append("file is empty")
        return result
    try:
        gltf = json.loads(Path(path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        result["errors"].append(f"invalid glTF JSON: {exc}")
        return result
    if not isinstance(gltf, dict):
        result["errors"].append("glTF root must be an object")
        return result
    version = (gltf.get("asset") or {}).get("version")
    result["version"] = version
    if not str(version or "").startswith("2"):
        result["errors"].append(f"unsupported glTF version: {version!r}")
    return _gltf_document_report(path, gltf, result)


def validate_glb(path: str) -> dict:
    """Parse a real GLB container without external libraries."""
    result = {"ok": False, "path": path, "errors": [], "warnings": []}
    if not os.path.isfile(path):
        result["errors"].append("file does not exist")
        return result
    size = os.path.getsize(path)
    result.update({"bytes": size, "sha256": sha256_file(path)})
    if size <= 0:
        result["errors"].append("file is empty")
        return result
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"glTF":
        result["errors"].append("not a GLB container")
        return result
    version, total = struct.unpack("<II", data[4:12])
    result["version"] = version
    result["declared_length"] = total
    if total != len(data):
        result["warnings"].append("declared length differs from file size")
    offset = 12
    gltf = None
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack("<II", data[offset:offset + 8])
        chunk = data[offset + 8:offset + 8 + chunk_length]
        if chunk_type == 0x4E4F534A:
            try:
                gltf = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                result["errors"].append(f"invalid JSON chunk: {exc}")
        offset += 8 + chunk_length
    if gltf is None:
        result["errors"].append("no JSON chunk")
        return result
    return _gltf_document_report(path, gltf, result)


def _resolve_texture_path(output_dir: str, raw: str) -> str:
    """Resolve Blender image paths, including '//textures/...' relative paths."""
    value = (raw or "").replace("\\", "/")
    if value.startswith("//"):
        value = value[2:]
    if not value:
        return ""
    if os.path.isabs(value):
        return value
    return os.path.normpath(os.path.join(output_dir, value))


def _artifact_entry(path: str) -> dict:
    exists = os.path.isfile(path)
    return {
        "path": os.path.abspath(path),
        "exists": exists,
        "bytes": os.path.getsize(path) if exists else 0,
        "sha256": sha256_file(path) if exists else None,
    }


def build_character(spec: dict, output_dir: str, *, timeout: int = 1200,
                    blender_exe: str | None = None,
                    preview_size: int = 720) -> dict:
    """Execute the real Blender build. Returns a stage report with evidence."""
    errors = character_spec.validate_character_spec(spec)
    if errors:
        raise ToolError(f"character specification is invalid: {errors}")
    out = os.path.abspath(output_dir)
    os.makedirs(out, exist_ok=True)
    executable = resolve_blender_executable(blender_exe)
    if not executable:
        return {
            "ok": False,
            "status": "failed",
            "stages": {"blender-build": {"status": "failed",
                                          "error": "Blender executable not found"}},
            "errors": ["Blender executable not found"],
            "spec_id": spec["id"],
        }
    result = blender.run_blender(
        BUILD_SCRIPT,
        args={"spec": spec, "output_dir": out, "preview_width": preview_size,
              "preview_height": preview_size},
        timeout=timeout, blender_exe=executable, factory=True)
    report = {
        "ok": False,
        "status": "failed",
        "spec_id": spec["id"],
        "blender_executable": executable,
        "blender_executed": True,
        "blender_version": None,
        "blender_exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"),
        "output_dir": out,
        "blender_result_ok": result.get("ok", False),
        "errors": [],
        "warnings": [],
        "stages": {},
        "artifacts": {},
        "stdout_tail": result.get("stdout_tail", ""),
        "stderr_tail": result.get("stderr_tail", ""),
    }
    if not result.get("ok"):
        report["errors"].append(result.get("error") or "Blender build failed")
        report["stages"]["blender-build"] = {"status": "failed",
                                              "error": report["errors"][-1]}
        return report

    payload = result.get("result") or {}
    report["blender_result"] = payload
    geometry = payload.get("geometry") or {}
    rig = payload.get("rig") or {}
    animations = payload.get("animations") or []
    materials = payload.get("materials") or []
    images = payload.get("images") or []

    blend_path = payload.get("blend") or os.path.join(out, spec["name"] + ".blend")
    glb_path = payload.get("glb") or os.path.join(out, spec["name"] + ".glb")
    gltf_path = payload.get("gltf") or os.path.join(out, spec["name"] + ".gltf")
    fbx_path = payload.get("fbx") or os.path.join(out, spec["name"] + ".fbx")
    preview_path = payload.get("preview") or os.path.join(out, "preview.png")
    report["artifacts"] = {
        "blend": _artifact_entry(blend_path),
        "glb": _artifact_entry(glb_path),
        "gltf": _artifact_entry(gltf_path),
        "fbx": _artifact_entry(fbx_path),
        "preview": _artifact_entry(preview_path),
    }
    for name, path in (("blend", blend_path), ("glb", glb_path),
                       ("gltf", gltf_path), ("fbx", fbx_path),
                       ("preview", preview_path)):
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            report["errors"].append(f"{name} artifact missing or empty: {path}")

    # geometry
    uv_ok = bool(geometry.get("uv_layers")) and float(
        geometry.get("uv_coverage") or 0) > 0.05
    geometry_issues = []
    if not geometry.get("triangles"):
        geometry_issues.append("no triangles")
    if int(geometry.get("degenerate_faces") or 0) > 0:
        geometry_issues.append(f"{geometry['degenerate_faces']} degenerate faces")
    if not uv_ok:
        geometry_issues.append("UV map missing or coverage too low")
    report["stages"]["geometry-validated"] = {
        "status": "passed" if not geometry_issues else "failed",
        "issues": geometry_issues,
        "triangles": geometry.get("triangles"),
        "vertices": geometry.get("vertices"),
        "non_manifold_edges": geometry.get("non_manifold_edges"),
        "uv_coverage": geometry.get("uv_coverage"),
        "uv_layers": geometry.get("uv_layers"),
    }

    # materials / PBR channels
    material_issues = []
    channel_report = {}
    for material in materials:
        declared = material.get("declared_channels") or {}
        actual = material.get("channels") or {}
        for channel, expected in declared.items():
            if expected == "generated" and actual.get(channel) != "texture":
                material_issues.append(
                    f"{material['name']}: {channel} declared generated but is "
                    f"{actual.get(channel)}")
            if expected == "constant" and actual.get(channel) not in ("constant",):
                material_issues.append(
                    f"{material['name']}: {channel} declared constant but is "
                    f"{actual.get(channel)}")
        for image in material.get("images") or []:
            if not image.get("exists"):
                material_issues.append(
                    f"{material['name']}: missing image {image.get('filepath')}")
            expected_space = None
            if "BaseColor" in (image.get("name") or ""):
                expected_space = "sRGB"
            elif any(key in (image.get("name") or "") for key in ("Roughness", "Normal")):
                expected_space = "Non-Color"
            if expected_space and image.get("colorspace") != expected_space:
                material_issues.append(
                    f"{image['name']}: colorspace {image.get('colorspace')} "
                    f"!= {expected_space}")
        channel_report[material["name"]] = actual
    if not materials:
        material_issues.append("no materials")
    report["stages"]["materials-validated"] = {
        "status": "passed" if not material_issues else "failed",
        "issues": material_issues,
        "materials": len(materials),
        "channels": channel_report,
    }

    # UV + texture file dimensions
    texture_issues = []
    texture_files = []
    for image in images:
        path = image.get("filepath") or ""
        if not path or image.get("missing"):
            if image.get("name", "").startswith("T_"):
                texture_issues.append(f"missing texture file: {path}")
            continue
        resolved = _resolve_texture_path(out, path)
        if os.path.isfile(resolved) and image.get("name", "").startswith("T_"):
            dimensions = png_dimensions(resolved)
            if dimensions is None:
                texture_issues.append(f"{resolved}: not a readable PNG")
            else:
                expected = (spec["textures"]["resolution"],
                            spec["textures"]["resolution"])
                if dimensions != expected:
                    texture_issues.append(
                        f"{os.path.basename(resolved)}: {dimensions} != {expected}")
                texture_files.append({
                    "path": resolved, "dimensions": list(dimensions),
                    "bytes": os.path.getsize(resolved),
                    "sha256": sha256_file(resolved),
                    "colorspace": image.get("colorspace"),
                })
    report["stages"]["uv-validated"] = {
        "status": "passed" if uv_ok else "failed",
        "uv_coverage": geometry.get("uv_coverage"),
        "uv_layers": geometry.get("uv_layers"),
    }
    if texture_issues:
        report["errors"].extend(texture_issues)
    report["textures"] = texture_files
    report["pbr_channels"] = channel_report

    # rig
    weighted_ratio = float(rig.get("weighted_ratio") or 0)
    rig_issues = []
    if not rig.get("armature"):
        rig_issues.append("no armature")
    if int(rig.get("bones") or 0) < 6:
        rig_issues.append("insufficient bones")
    if weighted_ratio < 0.9:
        rig_issues.append(f"only {weighted_ratio:.1%} of vertices are weighted")
    if not rig.get("vertex_groups"):
        rig_issues.append("no vertex groups")
    report["stages"]["rig-validated"] = {
        "status": "passed" if not rig_issues else "failed",
        "issues": rig_issues,
        "bones": rig.get("bones"),
        "bone_names": rig.get("bone_names"),
        "weight_mode": rig.get("weight_mode"),
        "weighted_ratio": weighted_ratio,
        "min_weight_sum": rig.get("min_weight_sum"),
        "max_weight_sum": rig.get("max_weight_sum"),
        "vertex_groups": rig.get("vertex_groups"),
        "mesh_parent": rig.get("mesh_parent"),
        "armature_modifier": rig.get("armature_modifier"),
    }

    requested = set(spec["animations"][i]["name"].lower()
                    for i in range(len(spec["animations"])))
    created = {str(item.get("name")).lower() for item in animations}
    animation_issues = []
    for name in requested:
        if name not in created:
            animation_issues.append(f"requested animation {name!r} was not created")
    for item in animations:
        if int(item.get("fcurves") or 0) <= 0:
            animation_issues.append(f"{item.get('name')} has no fcurves")
    report["stages"]["animations-created"] = {
        "status": "passed" if not animation_issues else "failed",
        "issues": animation_issues,
        "actions": animations,
        "requested": sorted(requested),
    }

    report["stages"]["spec-validated"] = {"status": "passed", "issues": []}
    report["stages"]["blender-build"] = {
        "status": "passed" if result.get("ok") else "failed",
        "exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"),
    }
    report["stages"]["blend-saved"] = {
        "status": "passed" if report["artifacts"]["blend"]["exists"] else "failed",
        "artifact": report["artifacts"]["blend"],
    }
    report["stages"]["glb-exported"] = {
        "status": "passed" if report["artifacts"]["glb"]["exists"] else "failed",
        "artifact": report["artifacts"]["glb"],
    }
    report["stages"]["gltf-exported"] = {
        "status": "passed" if report["artifacts"]["gltf"]["exists"] else "failed",
        "artifact": report["artifacts"]["gltf"],
    }
    report["stages"]["fbx-exported"] = {
        "status": "passed" if report["artifacts"]["fbx"]["exists"] else "failed",
        "artifact": report["artifacts"]["fbx"],
    }
    report["stages"]["preview-rendered"] = {
        "status": "passed" if report["artifacts"]["preview"]["exists"] else "failed",
        "artifact": report["artifacts"]["preview"],
        "engine": payload.get("render_engine"),
        "error": payload.get("render_error"),
    }

    # GLB container validation
    glb_validation = validate_glb(glb_path)
    report["glb_validation"] = glb_validation
    report["stages"]["glb-validated"] = {
        "status": "passed" if glb_validation["ok"] else "failed",
        "errors": glb_validation["errors"],
        "warnings": glb_validation["warnings"],
        "triangles": glb_validation.get("triangles"),
        "materials": glb_validation.get("materials"),
        "images": glb_validation.get("images"),
        "animations": glb_validation.get("animations"),
        "skins": glb_validation.get("skins"),
        "joints": glb_validation.get("joints"),
    }

    # Separated .gltf JSON validation (external .bin + image references)
    gltf_validation = validate_gltf(gltf_path)
    report["gltf_validation"] = gltf_validation
    report["stages"]["gltf-validated"] = {
        "status": "passed" if gltf_validation["ok"] else "failed",
        "errors": gltf_validation["errors"],
        "warnings": gltf_validation["warnings"],
        "triangles": gltf_validation.get("triangles"),
        "materials": gltf_validation.get("materials"),
        "buffers": gltf_validation.get("buffers"),
        "external_buffers": gltf_validation.get("external_buffers"),
        "animations": gltf_validation.get("animations"),
        "skins": gltf_validation.get("skins"),
        "joints": gltf_validation.get("joints"),
    }

    report["quality"] = payload.get("quality") or {
        "sphere_segments": spec["geometry"]["sphere_segments"],
        "texture_resolution": spec["textures"]["resolution"],
    }
    report["geometry"] = geometry
    report["rig"] = rig
    report["animations"] = animations
    report["materials"] = materials
    report["bounds"] = payload.get("bounds", {})
    report["generation"] = "procedural-blender"
    report["external_assets_used"] = False
    report["ai_generated"] = False

    failed = [name for name, stage in report["stages"].items()
              if stage.get("status") == "failed"]
    if "blend-loaded" not in report["stages"]:
        report["stages"]["blend-loaded"] = {"status": "pending"}
    if not failed:
        report["status"] = "built"
    else:
        report["status"] = "partial" if report["artifacts"]["blend"]["exists"] else "failed"
    report["ok"] = report["status"] == "built"
    report["failed_stages"] = failed
    report["generated_at"] = _now()
    return report


def reimport_and_validate(glb_path: str, output_dir: str, *,
                          timeout: int = 600,
                          blender_exe: str | None = None) -> dict:
    """Import the exported GLB into a truly empty scene and inspect the result."""
    executable = resolve_blender_executable(blender_exe)
    if not executable:
        return {"ok": False, "error": "Blender executable not found",
                "stages": {"glb-reimported": {"status": "failed"}}}
    if not os.path.isfile(glb_path):
        return {"ok": False, "error": f"GLB does not exist: {glb_path}"}
    os.makedirs(output_dir, exist_ok=True)
    reimport_blend = os.path.join(output_dir, "reimport_validation.blend")
    if os.path.exists(reimport_blend):
        try:
            os.remove(reimport_blend)
        except OSError:
            pass
    imported = blender.run_blender(
        REIMPORT_SCRIPT,
        args={"source": os.path.abspath(glb_path), "save_blend": reimport_blend},
        timeout=timeout, blender_exe=executable, factory=True)
    report = {
        "ok": False,
        "glb": os.path.abspath(glb_path),
        "reimport_blend": reimport_blend,
        "blender_executable": executable,
        "blender_exit_code": imported.get("exit_code"),
        "duration_ms": imported.get("duration_ms"),
        "import": imported,
        "inspection": None,
        "reimported": [],
    }
    if not imported.get("ok"):
        report["error"] = imported.get("error") or "re-import failed"
        return report
    inspection = imported.get("result") or {}
    report["inspection"] = inspection
    report["reimported"] = inspection.get("imported_objects") or []
    mesh_report = inspection.get("meshes") or []
    checks = {
        "imported_meshes": inspection.get("mesh_count", 0) > 0,
        "imported_materials": any(mesh.get("materials") for mesh in mesh_report),
        "imported_uvs": any(mesh.get("uv_layers") for mesh in mesh_report),
        "imported_armature": inspection.get("armature_count", 0) > 0,
        "animated_actions": len(inspection.get("animated_actions") or []) > 0,
        "skinned_mesh": any(mesh.get("armature_modifiers") for mesh in mesh_report),
        "no_missing_textures": not inspection.get("missing_images"),
    }
    report["checks"] = checks
    report["metrics"] = {
        "meshes": inspection.get("mesh_count"),
        "triangles": inspection.get("triangles"),
        "materials": inspection.get("material_count"),
        "bones": inspection.get("bone_count"),
        "actions": [a.get("name") for a in inspection.get("actions") or []],
        "animated_actions": inspection.get("animated_actions"),
        "missing_images": inspection.get("missing_images"),
    }
    report["ok"] = all(checks.values())
    if not report["ok"]:
        report["error"] = "re-import checks failed: " + ", ".join(
            name for name, value in checks.items() if not value)
    return report


def render_missing_preview(blend_path: str, preview_path: str, *,
                           width: int = 720, height: int = 720,
                           timeout: int = 600,
                           blender_exe: str | None = None) -> dict:
    if os.path.isfile(preview_path) and os.path.getsize(preview_path) > 0:
        return {"ok": True, "already_rendered": True,
                "artifact": _artifact_entry(preview_path)}
    executable = resolve_blender_executable(blender_exe)
    if not executable:
        return {"ok": False, "error": "Blender executable not found"}
    rendered = blender.render_preview(blend_path, preview_path, width=width,
                                      height=height, confirm_overwrite=True)
    return {
        "ok": bool(rendered.get("ok")) and os.path.isfile(preview_path),
        "result": rendered.get("result") if rendered.get("ok") else rendered,
        "artifact": _artifact_entry(preview_path),
    }


def engine_compatibility(glb_validation: dict, *, target_engine: str) -> dict:
    has_skin = bool(glb_validation.get("skins"))
    has_anim = bool(glb_validation.get("animations"))
    has_materials = bool(glb_validation.get("materials"))
    common = {
        "export_prepared": True,
        "integration_verified": False,
        "materials": has_materials,
        "rig": has_skin,
        "animations": has_anim,
        "note": ("Files are export-prepared and structurally validated. Engine "
                 "import was not executed in Phase 3."),
    }
    return {
        "unity": {
            **common,
            "formats": ["fbx", "glb", "gltf"],
            "status": "export-prepared-unverified",
            "notes": ["FBX is the primary Unity path; GLB/glTF also import with Unity "
                      "glTF support.", "No Unity editor import was run."],
        },
        "godot": {
            **common,
            "formats": ["glb", "gltf"],
            "status": "export-prepared-unverified",
            "notes": ["glTF/GLB is Godot's native interchange path.",
                      "No Godot import was run in Phase 3."],
        },
        "unreal": {
            **common,
            "formats": ["fbx", "gltf"],
            "status": "export-prepared-unverified",
            "notes": ["FBX is the usual Unreal path; glTF import requires the "
                      "glTF Exporter/Importer plugin.", "No Unreal import was run."],
        },
        "target": target_engine,
    }


def asset_manifest(spec: dict, build: dict, *, reimport: dict | None = None,
                   created_at: str | None = None) -> dict:
    artifacts = []
    for name, entry in (build.get("artifacts") or {}).items():
        artifacts.append({
            "role": name,
            "format": os.path.splitext(entry.get("path") or "")[1].lstrip("."),
            **entry,
        })
    textures = []
    for texture in build.get("textures") or []:
        textures.append({
            "role": "texture",
            "format": "png",
            **texture,
        })
    provenance = {
        "asset_id": spec["id"],
        "name": spec["name"],
        "asset_type": "character",
        "character_type": spec["character_type"],
        "source": spec["provenance"]["source"],
        "generation_method": spec["provenance"]["generation_method"],
        "creator": spec["provenance"]["creator"],
        "license": spec["provenance"]["license"],
        "license_id": spec["provenance"]["license_id"],
        "attribution_required": spec["provenance"]["attribution_required"],
        "external_assets": spec["provenance"]["external_assets"],
        "downloads": spec["provenance"]["downloads"],
        "download_status": "not-downloaded",
        "ai_generated": False,
        "procedural": True,
        "blender_executed": build.get("blender_executed", False),
        "dependencies": {
            "blender": build.get("blender_executable"),
            "blender_exit_code": build.get("blender_exit_code"),
            "textures": [texture["path"] for texture in textures],
            "gltf_external_buffers": (build.get("gltf_validation") or {}).get(
                "external_buffers") or [],
            "gltf_external_images": (build.get("gltf_validation") or {}).get(
                "external_images") or [],
        },
        "validation": {
            "build_status": build.get("status"),
            "failed_stages": build.get("failed_stages", []),
            "glb": (build.get("glb_validation") or {}).get("ok"),
            "gltf": (build.get("gltf_validation") or {}).get("ok"),
            "reimport": (reimport or {}).get("ok"),
            "geometry": build.get("stages", {}).get(
                "geometry-validated", {}).get("status"),
            "materials": build.get("stages", {}).get(
                "materials-validated", {}).get("status"),
            "rig": build.get("stages", {}).get("rig-validated", {}).get("status"),
            "animations": build.get("stages", {}).get(
                "animations-created", {}).get("status"),
            "uv": build.get("stages", {}).get("uv-validated", {}).get("status"),
        },
        "engine_compatibility": engine_compatibility(
            build.get("glb_validation") or {},
            target_engine=spec["export"]["target_engine"]),
        "artifacts": artifacts,
        "textures": textures,
        "created_at": created_at or _now(),
        "schema_version": 1,
    }
    return provenance


def run_pipeline(spec: dict, output_dir: str, *, timeout: int = 1200,
                 blender_exe: str | None = None,
                 preview_size: int = 720) -> dict:
    errors = character_spec.validate_character_spec(spec)
    if errors:
        raise ToolError(f"character specification is invalid: {errors}")
    build = build_character(spec, output_dir, timeout=timeout,
                            blender_exe=blender_exe, preview_size=preview_size)
    reimport = None
    stages = dict(build.get("stages") or {})
    if build.get("artifacts", {}).get("glb", {}).get("exists"):
        reimport = reimport_and_validate(
            build["artifacts"]["glb"]["path"], output_dir, timeout=min(timeout, 600),
            blender_exe=blender_exe)
        stages["glb-reimported"] = {
            "status": "passed" if reimport.get("ok") else "failed",
            "checks": reimport.get("checks"),
            "error": reimport.get("error"),
        }
    else:
        stages["glb-reimported"] = {"status": "failed",
                                    "error": "no GLB to re-import"}

    preview = build.get("artifacts", {}).get("preview") or {}
    if not preview.get("exists") and build.get("artifacts", {}).get("blend", {}).get("exists"):
        rendered = render_missing_preview(
            build["artifacts"]["blend"]["path"], preview["path"] if preview.get("path")
            else os.path.join(output_dir, "preview.png"),
            width=preview_size, height=preview_size, timeout=min(timeout, 600),
            blender_exe=blender_exe)
        stages["preview-rendered"] = {
            "status": "passed" if rendered.get("ok") else "failed",
            "artifact": rendered.get("artifact"), "result": rendered.get("result"),
        }
        if rendered.get("artifact"):
            build.setdefault("artifacts", {})["preview"] = rendered["artifact"]

    build["stages"] = stages
    failed = [name for name in REQUIRED_STAGES
              if (stages.get(name) or {}).get("status") != "passed"]
    leaked = [name for name in stages
              if name not in REQUIRED_STAGES and stages[name].get("status") == "failed"]
    all_failed = sorted(set(failed + leaked))
    status = "completed" if not all_failed else (
        "partial" if build.get("artifacts", {}).get("blend", {}).get("exists")
        else "failed")
    manifest = asset_manifest(spec, build, reimport=reimport)
    report = {
        "ok": status == "completed",
        "status": status,
        "phase": "V6 Phase 3 - character asset pipeline",
        "generated_at": _now(),
        "spec": spec,
        "spec_validation": {"valid": True, "errors": []},
        "build": build,
        "reimport": reimport,
        "stages": stages,
        "failed_stages": all_failed,
        "manifest": manifest,
        "provenance": manifest,
        "generation_classification": {
            "procedurally_generated_geometry": True,
            "imported_existing_geometry": False,
            "ai_generated_assets": False,
            "external_acquired_assets": False,
            "placeholder_asset": False,
            "production_ready": False,
            "quality_classification": "stylized-procedural-game-ready-prototype",
        },
        "limitations": [
            "Geometry is procedurally assembled from primitives with real UVs, "
            "materials, skin weights and keyframed actions; it is not sculpted "
            "production character art.",
            "Base color, roughness and normal maps are locally generated from "
            "procedural noise. No painted or scanned texture set exists.",
            "AO, emission and opacity maps are absent and are reported as absent.",
            "Animations are short procedural keyframe clips, not hand-animated "
            "performances.",
            "No AI asset provider was contacted. Meshy is paid and unauthorized.",
            "Engine integration is export-prepared only; no engine import was run.",
        ],
    }
    return report
