"""V6 Phase 4 environment asset pipeline.

Real Blender execution for a stylized tropical jungle: terrain, vegetation,
rocks, props, ruins, river, PBR ground textures, lighting/atmosphere, collision
metadata, Phase 3 character integration, previews and .blend/.glb/.gltf/.fbx
exports with re-import validation.

Every stage records evidence. A failed Blender stage is never upgraded to
success, and planning data is never reported as generated content.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path

from . import blender
from . import environment_spec
from .character_pipeline import (
    png_dimensions,
    resolve_blender_executable,
    validate_glb,
    validate_gltf,
)
from .util import ToolError, sha256_file

REQUIRED_STAGES = (
    "spec-validated", "blender-build", "terrain-validated",
    "vegetation-validated", "props-validated", "water-validated",
    "materials-validated", "lighting-validated", "layout-validated",
    "collision-validated", "character-integrated", "blend-saved",
    "glb-exported", "gltf-exported", "fbx-exported", "glb-validated",
    "gltf-validated", "glb-reimported", "previews-rendered",
)

BUILD_SCRIPT = r'''
import bpy, bmesh, os, math, random, json
import logging
from mathutils import Vector, Matrix

# The harness captures stdout through an OS pipe that is only drained after the
# process exits. The glTF exporter emits thousands of INFO lines which can fill
# that pipe and deadlock. Suppress INFO-level logging for the build session.
logging.disable(logging.CRITICAL)

ARGS = ARGS or {}
spec = ARGS['spec']
out_dir = ARGS['output_dir']
character_path = ARGS.get('character_path') or ''
os.makedirs(out_dir, exist_ok=True)
tex_dir = os.path.join(out_dir, 'textures')
os.makedirs(tex_dir, exist_ok=True)

seed = int(spec['provenance']['seed'])
quality = spec['quality_tier']
terrain_spec = spec['terrain']
size_x = float(terrain_spec['size_x_m'])
size_y = float(terrain_spec['size_y_m'])
segments = int(terrain_spec['segments'])
amplitude = float(terrain_spec['amplitude_m'])
base_elevation = float(terrain_spec['base_elevation_m'])
spawn_flat = float(terrain_spec['spawn_flat_radius_m'])
route_flat = float(terrain_spec['route_flat_radius_m'])
route_width = float(terrain_spec['route_width_m'])
profile = spec['profile']
water_spec = spec['water']
water_present = bool(water_spec.get('present'))
river_width = float(water_spec.get('width_m') or 0.0)
tex_res = int(spec['textures']['resolution'])
preview_size = int(ARGS.get('preview_size') or spec['performance']['preview_size'])
render_samples = int(spec['performance']['render_samples'])
random.seed(seed)

spawn = spec['layout']['spawn']
sx, sy = float(spawn['x']), float(spawn['y'])
landmark = spec['layout']['landmark']
lx, ly = float(landmark['x']), float(landmark['y'])

def clamp(value, low, high):
    return low if value < low else (high if value > high else value)

def smooth(t):
    return t * t * (3.0 - 2.0 * t)

def value_noise(x, y, octaves=4):
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for _ in range(octaves):
        xi, yi = int(math.floor(x * freq)), int(math.floor(y * freq))
        xf, yf = x * freq - xi, y * freq - yi
        def h(ix, iy):
            n = (ix * 374761393 + iy * 668265263 + seed * 144665) & 0xFFFFFFFF
            n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
            return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0
        v00, v10 = h(xi, yi), h(xi + 1, yi)
        v01, v11 = h(xi, yi + 1), h(xi + 1, yi + 1)
        u, v = smooth(xf), smooth(yf)
        value = (v00 * (1 - u) + v10 * u) * (1 - v) + (v01 * (1 - u) + v11 * u) * v
        total += value * amp
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm

def route_x(y):
    return 3.0 * math.sin((y + 60.0) * 0.06)

def river_center(y):
    return 30.0 + 5.0 * math.sin(y * 0.05)

def raw_height(x, y):
    n = value_noise((x + 100.0) * 0.032, (y + 100.0) * 0.032, 4)
    fine = value_noise((x + 100.0) * 0.11, (y + 100.0) * 0.11, 2)
    h = base_elevation + amplitude * (n - 0.5) + amplitude * 0.35 * (fine - 0.5)
    hill_count = int(terrain_spec.get('hill_count') or 3)
    for index in range(hill_count):
        angle = index * 2.399963 + 0.7
        cx = math.cos(angle) * (size_x * 0.30)
        cy = math.sin(angle) * (size_y * 0.28)
        radius = 700.0 + index * 140.0
        h += (2.6 + index * 0.5) * math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / radius)
    if water_present:
        distance = abs(x - river_center(y))
        h -= 3.4 * math.exp(-(distance / max(2.0, river_width * 0.72)) ** 2)
    return h

spawn_height_raw = raw_height(sx, sy)

def terrain_height(x, y):
    h = raw_height(x, y)
    ds = math.sqrt((x - sx) ** 2 + (y - sy) ** 2)
    w = clamp(1.0 - ds / spawn_flat, 0.0, 1.0)
    w = w * w
    h = h * (1.0 - w) + spawn_height_raw * w
    if abs(y) <= size_y * 0.42:
        rx = route_x(y)
        rh = raw_height(rx, y)
        dr = abs(x - rx)
        wr = clamp(1.0 - dr / route_flat, 0.0, 1.0)
        wr = 0.9 * wr * wr
        h = h * (1.0 - wr) + rh * wr
    return h

def terrain_slope_deg(x, y, step=1.5):
    hx = terrain_height(x + step, y) - terrain_height(x - step, y)
    hy = terrain_height(x, y + step) - terrain_height(x, y - step)
    return math.degrees(math.atan(math.sqrt(hx * hx + hy * hy) / (2.0 * step)))

def route_distance(x, y):
    return abs(x - route_x(y)) if abs(y) <= size_y * 0.42 else 1e9

spawn_z = terrain_height(sx, sy)

# ---------------------------------------------------------------- scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 30
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.resolution_x = preview_size
scene.render.resolution_y = preview_size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except Exception:
    try:
        scene.render.engine = 'BLENDER_EEVEE'
    except Exception:
        pass

root_collection = bpy.data.collections.new('JungleLevel')
scene.collection.children.link(root_collection)
library_collection = bpy.data.collections.new('_ASSET_LIBRARY')
scene.collection.children.link(library_collection)
library_collection.hide_render = True
library_collection.hide_viewport = True

def link_object(ob, collection=None):
    target = collection or root_collection
    if ob.name not in target.objects:
        target.objects.link(ob)

# ---------------------------------------------------------------- textures
print('STAGE textures start', flush=True)
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

base_pixels = [0.0] * (tex_res * tex_res * 4)
rough_pixels = [0.0] * (tex_res * tex_res * 4)
normal_pixels = [0.0] * (tex_res * tex_res * 4)
height_field = [0.0] * (tex_res * tex_res)
palette = spec['materials'][0]['base_color']
for y in range(tex_res):
    for x in range(tex_res):
        u = x / max(1, tex_res - 1)
        v = y / max(1, tex_res - 1)
        n = value_noise(u * 11.0, v * 11.0, 4)
        fine = value_noise(u * 47.0, v * 47.0, 2)
        soil = value_noise(u * 5.0 + 13.0, v * 5.0 + 7.0, 2)
        mix = clamp(n * 0.65 + fine * 0.35, 0.0, 1.0)
        idx = y * tex_res + x
        height_field[idx] = mix
        i = idx * 4
        base_pixels[i] = palette[0] * (0.55 + 0.70 * mix) + soil * 0.05
        base_pixels[i + 1] = palette[1] * (0.55 + 0.70 * mix) + soil * 0.04
        base_pixels[i + 2] = palette[2] * (0.50 + 0.65 * mix)
        base_pixels[i + 3] = 1.0
        r = 0.72 + 0.22 * fine
        rough_pixels[i] = r
        rough_pixels[i + 1] = r
        rough_pixels[i + 2] = r
        rough_pixels[i + 3] = 1.0
for y in range(tex_res):
    for x in range(tex_res):
        idx = y * tex_res + x
        left = height_field[y * tex_res + max(0, x - 1)]
        right = height_field[y * tex_res + min(tex_res - 1, x + 1)]
        down = height_field[max(0, y - 1) * tex_res + x]
        up = height_field[min(tex_res - 1, y + 1) * tex_res + x]
        dx = (left - right) * 2.4
        dy = (down - up) * 2.4
        length = math.sqrt(dx * dx + dy * dy + 1.0)
        i = idx * 4
        normal_pixels[i] = dx / length * 0.5 + 0.5
        normal_pixels[i + 1] = dy / length * 0.5 + 0.5
        normal_pixels[i + 2] = 1.0 / length * 0.5 + 0.5
        normal_pixels[i + 3] = 1.0

base_img = save_image('T_Env_Ground_BaseColor', base_pixels,
                      os.path.join(tex_dir, 'ground_basecolor.png'), 'sRGB')
rough_img = save_image('T_Env_Ground_Roughness', rough_pixels,
                       os.path.join(tex_dir, 'ground_roughness.png'), 'Non-Color')
normal_img = save_image('T_Env_Ground_Normal', normal_pixels,
                        os.path.join(tex_dir, 'ground_normal.png'), 'Non-Color')

# ---------------------------------------------------------------- materials
def set_input(node, key, value):
    socket = node.inputs.get(key)
    if socket is not None:
        socket.default_value = value

materials = {}
for entry in spec['materials']:
    mat = bpy.data.materials.new(entry['name'])
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    base_rgba = tuple(entry['base_color']) + (1.0,)
    set_input(bsdf, 'Base Color', base_rgba)
    set_input(bsdf, 'Roughness', float(entry['roughness']))
    set_input(bsdf, 'Metallic', float(entry['metallic']))
    if entry.get('transmission'):
        set_input(bsdf, 'Transmission Weight', float(entry['transmission']))
        set_input(bsdf, 'Transmission', float(entry['transmission']))
    if entry.get('alpha', 1.0) < 1.0:
        set_input(bsdf, 'Alpha', float(entry['alpha']))
        try:
            mat.blend_method = 'BLEND'
        except Exception:
            pass
    if entry['name'] == 'M_Env_Ground':
        base_node = nt.nodes.new('ShaderNodeTexImage')
        base_node.name = 'BaseColorTexture'
        base_node.image = base_img
        nt.links.new(base_node.outputs['Color'], bsdf.inputs['Base Color'])
        rough_node = nt.nodes.new('ShaderNodeTexImage')
        rough_node.name = 'RoughnessTexture'
        rough_node.image = rough_img
        nt.links.new(rough_node.outputs['Color'], bsdf.inputs['Roughness'])
        normal_node = nt.nodes.new('ShaderNodeTexImage')
        normal_node.name = 'NormalTexture'
        normal_node.image = normal_img
        normal_map = nt.nodes.new('ShaderNodeNormalMap')
        normal_map.name = 'NormalMap'
        set_input(normal_map, 'Strength', 0.7)
        nt.links.new(normal_node.outputs['Color'], normal_map.inputs['Color'])
        nt.links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])
    mat['pbr_channels'] = dict(entry['channels'])
    mat.diffuse_color = base_rgba
    materials[entry['name']] = mat

# ---------------------------------------------------------------- terrain
print('STAGE terrain start', flush=True)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=segments, y_subdivisions=segments,
                                size=size_x, location=(0, 0, 0))
terrain = bpy.context.active_object
terrain.name = 'Terrain'
terrain.data.name = 'TerrainMesh'
if size_x != size_y:
    terrain.scale.y = size_y / size_x
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for vertex in terrain.data.vertices:
    x, y = vertex.co.x, vertex.co.y
    vertex.co.z = terrain_height(x, y)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')
if not terrain.data.uv_layers:
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.01)
    bpy.ops.object.mode_set(mode='OBJECT')
terrain.data.materials.append(materials['M_Env_Ground'])
terrain['game_studio_role'] = 'terrain'
terrain['collision_role'] = 'terrain_collider'
terrain['walkable'] = True
for poly in terrain.data.polygons:
    poly.use_smooth = True

terrain.data.calc_loop_triangles()
heights = [v.co.z for v in terrain.data.vertices]
terrain_min_z, terrain_max_z = min(heights), max(heights)
bm = bmesh.new()
bm.from_mesh(terrain.data)
non_manifold = sum(1 for edge in bm.edges if not edge.is_manifold)
degenerate = sum(1 for face in bm.faces if face.calc_area() < 1e-9)
bm.free()
uv_layer = terrain.data.uv_layers.active
uv_coverage = 0.0
if uv_layer:
    area = 0.0
    for poly in terrain.data.polygons:
        loops = list(poly.loop_indices)
        if len(loops) < 3:
            continue
        pts = [uv_layer.data[index].uv for index in loops]
        sub = 0.0
        for index in range(len(pts)):
            a = pts[index]
            b = pts[(index + 1) % len(pts)]
            sub += a.x * b.y - b.x * a.y
        area += abs(sub) * 0.5
    uv_coverage = min(1.0, area)

# ---------------------------------------------------------------- geometry helpers
placed_colliders = []
vegetation_records = []
prop_records = []
unique_meshes = 0
instance_count = 0

def activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob

def apply_transform(ob):
    activate(ob)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

def assign_material(ob, material_name):
    ob.data.materials.append(materials[material_name])

def join_objects(objects, name):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    return joined

def add_cylinder(name_value, radius, depth, location, material, vertices=8,
                 rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                        depth=depth, location=location,
                                        rotation=rotation)
    ob = bpy.context.active_object
    ob.name = name_value
    apply_transform(ob)
    assign_material(ob, material)
    return ob

def add_icosphere(name_value, radius, location, material, subdivisions=1,
                  scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius,
                                          location=location)
    ob = bpy.context.active_object
    ob.name = name_value
    ob.scale = scale
    apply_transform(ob)
    assign_material(ob, material)
    return ob

def make_tree_mesh(variant):
    height = 5.5 + variant * 1.4
    parts = []
    trunk = add_cylinder('tree_trunk', 0.22 + variant * 0.05, height * 0.62,
                         (0, 0, height * 0.31), 'M_Env_Bark', 7)
    parts.append(trunk)
    for index in range(2):
        angle = 0.8 + index * 1.7 + variant * 0.4
        branch = add_cylinder(
            'tree_branch', 0.10, height * 0.34,
            (math.cos(angle) * 0.55, math.sin(angle) * 0.55, height * 0.62),
            'M_Env_Bark', 6, rotation=(math.radians(55), 0, angle))
        parts.append(branch)
    canopy_specs = [
        (0.0, 0.0, height * 0.84, 1.9 + variant * 0.25, 1.25),
        (0.95, 0.25, height * 0.72, 1.35, 0.95),
        (-0.85, -0.30, height * 0.76, 1.25, 0.90),
        (0.10, 0.85, height * 0.70, 1.15, 0.85),
    ]
    for index, (cx, cy, cz, radius, zscale) in enumerate(canopy_specs):
        material = 'M_Env_Leaf_Light' if index == 1 else 'M_Env_Leaf'
        canopy = add_icosphere('tree_canopy', radius, (cx, cy, cz), material,
                               subdivisions=1, scale=(1.0, 1.0, zscale))
        parts.append(canopy)
    tree = join_objects(parts, 'TreeBase_%d' % variant)
    tree.data.name = 'TreeMesh_%d' % variant
    return tree

def make_bush_mesh(variant):
    parts = []
    for index in range(3):
        angle = index * 2.1 + variant
        radius = 0.65 + index * 0.12
        bush = add_icosphere(
            'bush_part', radius,
            (math.cos(angle) * 0.45, math.sin(angle) * 0.45, 0.45 + index * 0.12),
            'M_Env_Leaf', 1, scale=(1.0, 1.0, 0.8))
        parts.append(bush)
    bush_obj = join_objects(parts, 'BushBase_%d' % variant)
    bush_obj.data.name = 'BushMesh_%d' % variant
    return bush_obj

def make_fern_mesh(variant):
    parts = []
    for index in range(6):
        angle = index * math.pi / 3.0 + variant * 0.3
        leaf = add_icosphere(
            'fern_leaf', 0.42,
            (math.cos(angle) * 0.28, math.sin(angle) * 0.28, 0.30),
            'M_Env_Grass', 1, scale=(0.20, 0.95, 0.06))
        leaf.rotation_euler = (math.radians(22), 0, angle)
        apply_transform(leaf)
        parts.append(leaf)
    fern = join_objects(parts, 'FernBase_%d' % variant)
    fern.data.name = 'FernMesh_%d' % variant
    return fern

def make_grass_mesh(variant):
    parts = []
    for index in range(5):
        angle = index * 1.2566 + variant * 0.4
        blade = add_icosphere(
            'grass_blade', 0.28,
            (math.cos(angle) * 0.16, math.sin(angle) * 0.16, 0.22),
            'M_Env_Grass', 1, scale=(0.08, 0.42, 0.04))
        blade.rotation_euler = (math.radians(16), 0, angle)
        apply_transform(blade)
        parts.append(blade)
    grass = join_objects(parts, 'GrassBase_%d' % variant)
    grass.data.name = 'GrassMesh_%d' % variant
    return grass

def make_plant_mesh(variant):
    parts = []
    for index in range(4):
        angle = index * math.pi / 2.0 + variant * 0.5
        leaf = add_icosphere(
            'plant_leaf', 0.55,
            (math.cos(angle) * 0.30, math.sin(angle) * 0.30, 0.34),
            'M_Env_Leaf_Light', 1, scale=(0.22, 1.15, 0.05))
        leaf.rotation_euler = (math.radians(18), 0, angle)
        apply_transform(leaf)
        parts.append(leaf)
    plant = join_objects(parts, 'PlantBase_%d' % variant)
    plant.data.name = 'PlantMesh_%d' % variant
    return plant

def make_rock_mesh(variant, large=False):
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2 if large else 1,
        radius=1.0 if large else 0.7, location=(0, 0, 0))
    rock = bpy.context.active_object
    rock.name = 'RockBase_%d_%s' % (variant, 'large' if large else 'small')
    for vertex in rock.data.vertices:
        factor = 0.78 + 0.32 * value_noise(vertex.co.x * 2.3 + variant,
                                           vertex.co.y * 2.3, 2)
        vertex.co.x *= factor
        vertex.co.y *= factor
        vertex.co.z = max(-0.30, vertex.co.z * factor * 0.72)
    assign_material(rock, 'M_Env_Rock_Mossy' if variant % 2 else 'M_Env_Rock')
    rock.data.name = 'RockMesh_%d_%s' % (variant, 'large' if large else 'small')
    return rock

def make_log_mesh(variant):
    parts = []
    log = add_cylinder('log_body', 0.34, 4.2, (0, 0, 0.34), 'M_Env_Wood', 9,
                       rotation=(0, math.radians(90), variant * 0.6))
    parts.append(log)
    branch = add_cylinder('log_branch', 0.13, 1.0, (0.9, 0.2, 0.6),
                          'M_Env_Wood', 6, rotation=(0, math.radians(60), 0.4))
    parts.append(branch)
    fallen = join_objects(parts, 'LogBase_%d' % variant)
    fallen.data.name = 'LogMesh_%d' % variant
    return fallen

def make_ruin_cluster(index):
    objects = []
    base_x, base_y = lx, ly
    ground = terrain_height(base_x, base_y)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(base_x, base_y, ground + 0.25))
    platform = bpy.context.active_object
    platform.name = 'RuinPlatform_%d' % index
    platform.scale = (3.2, 3.2, 0.5)
    apply_transform(platform)
    assign_material(platform, 'M_Env_Stone')
    objects.append(platform)
    for pillar_index in range(4):
        angle = pillar_index * math.pi / 2.0
        px = base_x + math.cos(angle) * 2.4
        py = base_y + math.sin(angle) * 2.4
        pz = terrain_height(px, py)
        pillar = add_cylinder('RuinPillar_%d_%d' % (index, pillar_index), 0.36,
                              2.6, (px, py, pz + 1.3), 'M_Env_Stone', 7)
        objects.append(pillar)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(base_x, base_y, ground + 2.8))
    lintel = bpy.context.active_object
    lintel.name = 'RuinLintel_%d' % index
    lintel.scale = (2.2, 0.6, 0.35)
    apply_transform(lintel)
    assign_material(lintel, 'M_Env_Stone')
    objects.append(lintel)
    return objects

def make_root_mesh(variant):
    parts = []
    for index in range(3):
        angle = index * 2.094 + variant * 0.5
        root = add_cylinder(
            'root_part', 0.08, 0.9,
            (math.cos(angle) * 0.28, math.sin(angle) * 0.28, 0.18),
            'M_Env_Root', 5, rotation=(math.radians(72), 0, angle))
        parts.append(root)
    root_obj = join_objects(parts, 'RootBase_%d' % variant)
    root_obj.data.name = 'RootMesh_%d' % variant
    return root_obj

# ---------------------------------------------------------------- placement
print('STAGE placement start', flush=True)
def choose_points(category, count, min_spacing, max_slope,
                  route_clearance=5.0, spawn_clearance=8.0,
                  avoid_river=True, extra_check=None):
    points = []
    attempts = 0
    limit = max(400, count * 140)
    half_x = size_x * 0.5 - 6.0
    half_y = size_y * 0.5 - 6.0
    while len(points) < count and attempts < limit:
        attempts += 1
        x = random.uniform(-half_x, half_x)
        y = random.uniform(-half_y, half_y)
        if avoid_river and water_present:
            if abs(x - river_center(y)) < river_width * 0.5 + 2.2:
                continue
        if route_distance(x, y) < route_clearance:
            continue
        if math.sqrt((x - sx) ** 2 + (y - sy) ** 2) < spawn_clearance:
            continue
        if terrain_slope_deg(x, y) > max_slope:
            continue
        if extra_check and not extra_check(x, y):
            continue
        ok = True
        for point in points:
            if math.sqrt((x - point['x']) ** 2 + (y - point['y']) ** 2) < min_spacing:
                ok = False
                break
        if not ok:
            continue
        points.append({'x': x, 'y': y, 'z': terrain_height(x, y),
                       'attempts': attempts})
    return points

def place_instances(base_ob, category, points, scale_range, collision_role,
                    radius, material_done=True):
    global instance_count
    placed = []
    if not points:
        return placed
    for index, point in enumerate(points):
        scale = random.uniform(scale_range[0], scale_range[1])
        rotation = random.uniform(0.0, math.tau)
        if index == 0:
            ob = base_ob
            ob.name = '%s_%03d' % (category, index)
            unique = True
        else:
            ob = bpy.data.objects.new('%s_%03d' % (category, index), base_ob.data)
            link_object(ob)
            unique = False
        ob.location = (point['x'], point['y'], point['z'])
        ob.rotation_euler = (0, 0, rotation)
        ob.scale = (scale, scale, scale)
        ob['game_studio_role'] = category
        ob['collision_role'] = collision_role
        ob['placement_radius'] = round(radius * scale, 3)
        ob['terrain_z'] = round(point['z'], 4)
        placed.append(ob)
        collider = {
            'name': ob.name, 'category': category, 'role': collision_role,
            'x': round(point['x'], 3), 'y': round(point['y'], 3),
            'z': round(point['z'], 3), 'radius': round(radius * scale, 3),
        }
        placed_colliders.append(collider)
        vegetation_records.append({
            'name': ob.name, 'category': category, 'x': round(point['x'], 3),
            'y': round(point['y'], 3), 'z': round(point['z'], 4),
            'scale': round(scale, 3), 'rotation_deg': round(math.degrees(rotation), 2),
        })
        if not unique:
            instance_count += 1
    return placed

# vegetation bases (3 variants each) then deterministic placement
veg_counts = spec['vegetation']['counts']
spacing = spec['vegetation']['min_spacing_m']
slope_limits = spec['vegetation']['slope_limit_deg']
scale_range = spec['vegetation']['variation']['scale']

tree_points = choose_points('tree', int(veg_counts['trees']), spacing['tree'],
                            slope_limits['tree'], route_clearance=5.5,
                            spawn_clearance=9.0)
for variant in range(3):
    subset = tree_points[variant::3]
    base = make_tree_mesh(variant)
    place_instances(base, 'tree', subset, scale_range, 'static_obstacle', 0.55)
    unique_meshes += 1

bush_points = choose_points('bush', int(veg_counts['bushes']), spacing['bush'],
                            slope_limits['bush'], route_clearance=4.5,
                            spawn_clearance=7.0)
for variant in range(2):
    subset = bush_points[variant::2]
    base = make_bush_mesh(variant)
    place_instances(base, 'bush', subset, [0.8, 1.35], 'static_obstacle', 0.45)
    unique_meshes += 1

fern_points = choose_points('fern', int(veg_counts['ferns']), spacing['fern'],
                            slope_limits['fern'], route_clearance=3.2,
                            spawn_clearance=5.0)
for variant in range(2):
    subset = fern_points[variant::2]
    base = make_fern_mesh(variant)
    place_instances(base, 'fern', subset, [0.75, 1.25], 'none', 0.2)
    unique_meshes += 1

grass_points = choose_points('grass', int(veg_counts['grass']), spacing['grass'],
                             slope_limits['grass'], route_clearance=2.6,
                             spawn_clearance=4.0)
for variant in range(2):
    subset = grass_points[variant::2]
    base = make_grass_mesh(variant)
    place_instances(base, 'grass', subset, [0.7, 1.4], 'none', 0.12)
    unique_meshes += 1

plant_points = choose_points('plant', int(veg_counts['plants']), spacing['plant'],
                             slope_limits['plant'], route_clearance=3.5,
                             spawn_clearance=5.5)
for variant in range(2):
    subset = plant_points[variant::2]
    base = make_plant_mesh(variant)
    place_instances(base, 'plant', subset, [0.8, 1.3], 'static_obstacle', 0.25)
    unique_meshes += 1

root_points = choose_points('roots', max(4, int(veg_counts['trees']) // 3), 2.5,
                            34.0, route_clearance=4.0, spawn_clearance=6.0)
for variant in range(2):
    subset = root_points[variant::2]
    base = make_root_mesh(variant)
    place_instances(base, 'roots', subset, [0.7, 1.2], 'none', 0.2)
    unique_meshes += 1

# ---------------------------------------------------------------- rocks / props
print('STAGE props start', flush=True)
rock_spec = spec['rocks']
rock_points = choose_points('rock', int(rock_spec['count']),
                            float(rock_spec['min_spacing_m']),
                            float(rock_spec['slope_limit_deg']),
                            route_clearance=4.0, spawn_clearance=7.0)
for variant in range(2):
    subset = rock_points[variant::2]
    base = make_rock_mesh(variant, large=False)
    place_instances(base, 'rock', subset, [0.55, 1.35], 'static_obstacle', 0.55)
    unique_meshes += 1

large_points = choose_points('large_rock', int(rock_spec['large_count']), 6.0,
                             42.0, route_clearance=6.0, spawn_clearance=9.0)
for variant in range(2):
    subset = large_points[variant::2]
    base = make_rock_mesh(variant + 2, large=True)
    place_instances(base, 'large_rock', subset, [0.9, 1.6], 'static_obstacle', 1.3)
    unique_meshes += 1

log_points = choose_points('fallen_log', int(spec['props']['fallen_logs']), 5.0,
                           20.0, route_clearance=6.0, spawn_clearance=8.0)
for variant in range(2):
    subset = log_points[variant::2]
    base = make_log_mesh(variant)
    place_instances(base, 'fallen_log', subset, [0.8, 1.3], 'static_obstacle', 1.35)
    unique_meshes += 1

# jungle debris: small stones near the river and route edges
debris_points = choose_points('debris', int(spec['props']['debris_count']), 1.8,
                              40.0, route_clearance=2.0, spawn_clearance=4.0,
                              avoid_river=False)
for index, point in enumerate(debris_points):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.18 + (index % 3) * 0.05,
                                          location=(point['x'], point['y'], point['z'] + 0.08))
    debris = bpy.context.active_object
    debris.name = 'Debris_%03d' % index
    assign_material(debris, 'M_Env_Rock')
    debris['game_studio_role'] = 'debris'
    debris['collision_role'] = 'none'
    prop_records.append({'name': debris.name, 'category': 'debris',
                         'x': round(point['x'], 3), 'y': round(point['y'], 3)})

# landmark ruins
ruin_objects = []
for index in range(int(spec['props'].get('ruin_clusters') or 1)):
    for ob in make_ruin_cluster(index):
        ruin_objects.append(ob)
        ob['game_studio_role'] = 'ruins'
        ob['collision_role'] = 'static_obstacle'
        placed_colliders.append({
            'name': ob.name, 'category': 'ruins', 'role': 'static_obstacle',
            'x': round(ob.location.x, 3), 'y': round(ob.location.y, 3),
            'z': round(ob.location.z, 3),
            'radius': 1.2 if 'Pillar' in ob.name else 2.8,
        })

# ---------------------------------------------------------------- river
print('STAGE river start', flush=True)
river_report = {'present': water_present, 'width_m': river_width}
if water_present:
    river_segments = 48
    columns = 3
    verts = []
    faces = []
    left_boundary = []
    right_boundary = []
    y_start, y_end = -size_y * 0.48, size_y * 0.48
    for row in range(river_segments + 1):
        y = y_start + (y_end - y_start) * row / river_segments
        cx = river_center(y)
        bed = raw_height(cx, y)
        water_z = bed + 0.55
        for column in range(columns):
            offset = (column - 1) * river_width * 0.5
            x = cx + offset
            wave = 0.03 * math.sin(y * 0.7 + column * 1.3)
            verts.append((x, y, water_z + wave))
        if row > 0:
            base_index = row * columns
            prev = (row - 1) * columns
            for column in range(columns - 1):
                faces.append((prev + column, prev + column + 1,
                              base_index + column + 1, base_index + column))
        left_boundary.append({'x': round(cx - river_width * 0.5, 3),
                              'y': round(y, 3), 'z': round(water_z, 3)})
        right_boundary.append({'x': round(cx + river_width * 0.5, 3),
                               'y': round(y, 3), 'z': round(water_z, 3)})
    mesh = bpy.data.meshes.new('RiverMesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    river = bpy.data.objects.new('River_Water', mesh)
    link_object(river)
    river.data.materials.append(materials['M_Env_Water'])
    river['game_studio_role'] = 'water_surface'
    river['collision_role'] = 'river_boundary'
    river['flow_direction'] = list(water_spec['flow_direction'])
    river['river_width_m'] = river_width
    river['physics'] = 'visual-only; no swimming interaction'
    river.data.calc_loop_triangles()
    # wet bank strips
    for side, boundary in (('L', left_boundary), ('R', right_boundary)):
        bank_verts = []
        bank_faces = []
        for index, point in enumerate(boundary):
            inner = point
            direction = -1.0 if side == 'L' else 1.0
            outer = {'x': point['x'] + direction * 1.6, 'y': point['y'],
                     'z': terrain_height(point['x'] + direction * 1.6, point['y']) + 0.05}
            bank_verts.append((inner['x'], inner['y'], inner['z'] + 0.02))
            bank_verts.append((outer['x'], outer['y'], outer['z']))
            if index > 0:
                base_index = index * 2
                prev = (index - 1) * 2
                bank_faces.append((prev, prev + 1, base_index + 1, base_index))
        bank_mesh = bpy.data.meshes.new('RiverBankMesh_%s' % side)
        bank_mesh.from_pydata(bank_verts, [], bank_faces)
        bank_mesh.update()
        bank = bpy.data.objects.new('RiverBank_%s' % side, bank_mesh)
        link_object(bank)
        bank.data.materials.append(materials['M_Env_WetGround'])
        bank['game_studio_role'] = 'river_bank'
        bank['collision_role'] = 'walkable'
    river_report.update({
        'vertices': len(verts), 'faces': len(faces),
        'triangles': len(faces) * 2,
        'flow_direction': list(water_spec['flow_direction']),
        'banks': 2, 'water_surface': True, 'bed_geometry': True,
        'left_boundary': left_boundary, 'right_boundary': right_boundary,
        'centerline': [{'x': round(river_center(y), 3), 'y': round(y, 3)}
                       for y in [y_start + (y_end - y_start) * i / 12
                                 for i in range(13)]],
    })
    placed_colliders.append({'name': 'River_Water', 'category': 'river',
                             'role': 'river_boundary', 'x': round(river_center(0), 3),
                             'y': 0.0, 'z': 0.0, 'radius': river_width * 0.5})

# ---------------------------------------------------------------- layout markers
def add_empty(name_value, location, role):
    empty = bpy.data.objects.new(name_value, None)
    link_object(empty)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = 1.5
    empty.location = location
    empty['game_studio_role'] = role
    return empty

spawn_marker = add_empty('SPAWN_PLAYER', (sx, sy, spawn_z + 0.02), 'player_spawn')
spawn_marker['facing'] = list(spawn['facing'])
waypoints = []
route = spec['layout']['route']
for index, point in enumerate(route):
    z = terrain_height(float(point['x']), float(point['y']))
    waypoint = add_empty('ROUTE_WAYPOINT_%02d' % index,
                         (float(point['x']), float(point['y']), z + 0.05),
                         'route_waypoint')
    waypoint['order'] = index
    waypoints.append({'name': waypoint.name, 'x': round(float(point['x']), 3),
                      'y': round(float(point['y']), 3), 'z': round(z, 4)})
landmark_z = terrain_height(lx, ly)
landmark_marker = add_empty('LANDMARK_DESTINATION', (lx, ly, landmark_z + 0.05),
                            'landmark')

# route slope and clearance
route_slope_max = 0.0
for point in route:
    route_slope_max = max(route_slope_max,
                          terrain_slope_deg(float(point['x']), float(point['y'])))
route_conflicts = []
for collider in placed_colliders:
    for point in route:
        dx = collider['x'] - float(point['x'])
        dy = collider['y'] - float(point['y'])
        if math.sqrt(dx * dx + dy * dy) < 2.5 + collider['radius']:
            route_conflicts.append({'collider': collider['name'],
                                    'waypoint': point.get('order')})
            break
spawn_clearance = 1e9
for collider in placed_colliders:
    distance = math.sqrt((collider['x'] - sx) ** 2 + (collider['y'] - sy) ** 2) - collider['radius']
    spawn_clearance = min(spawn_clearance, distance)

# ---------------------------------------------------------------- lighting
print('STAGE lighting start', flush=True)
light_spec = spec['lighting']
bpy.ops.object.light_add(type='SUN', location=(0, 0, 40))
sun = bpy.context.active_object
sun.name = 'Sun_Key'
sun.data.energy = float(light_spec['sun_energy'])
sun.data.angle = math.radians(2.5)
try:
    sun.data.use_shadow = True
except Exception:
    pass
sun.rotation_euler = (math.radians(90.0 - float(light_spec['sun_elevation_deg'])),
                      0.0, math.radians(float(light_spec['sun_azimuth_deg'])))
sun['game_studio_role'] = 'sun_light'

world = bpy.data.worlds.new('JungleWorld') if not scene.world else scene.world
scene.world = world
world.use_nodes = True
nt = world.node_tree
background = nt.nodes.get('Background')
if background:
    sky = light_spec['sky_color']
    set_input(background, 'Color', (float(sky[0]), float(sky[1]), float(sky[2]), 1.0))
    set_input(background, 'Strength', float(light_spec['ambient_strength']))
world['fog_density'] = float(light_spec['fog_density'])
world['fog_color'] = list(light_spec['fog_color'])
world['atmosphere'] = light_spec['atmosphere']
world['volumetric_fog_rendered'] = False
scene.view_settings.exposure = float(light_spec['exposure'])
try:
    scene.view_settings.view_transform = light_spec['view_transform']
except Exception:
    pass
scene.render.film_transparent = False

# ---------------------------------------------------------------- cameras
def add_camera(name_value, location, target, lens=32.0):
    camera_data = bpy.data.cameras.new(name_value)
    camera_data.lens = lens
    camera = bpy.data.objects.new(name_value, camera_data)
    link_object(camera)
    camera.location = location
    direction = Vector(target) - Vector(location)
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    camera['game_studio_role'] = 'inspection_camera'
    return camera

overview_camera = add_camera('CAM_Overview', (72, -82, 56), (0, 0, 6), 34.0)
spawn_camera = add_camera('CAM_Spawn', (sx, sy - 8.0, spawn_z + 3.2),
                          (sx, sy + 16.0, spawn_z + 1.4), 28.0)
scene.camera = overview_camera

# ---------------------------------------------------------------- character
print('STAGE character start', flush=True)
character_report = {'imported': False, 'asset_path': character_path}
if character_path and os.path.isfile(character_path):
    before = set(ob.name for ob in bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=character_path)
    imported = [ob for ob in bpy.data.objects if ob.name not in before]
    roots = [ob for ob in imported if ob.parent is None or ob.parent not in imported]
    meshes = [ob for ob in imported if ob.type == 'MESH']
    if meshes:
        depsgraph = bpy.context.evaluated_depsgraph_get()

        def world_bounds():
            bounds = [1e9, -1e9, 1e9, -1e9, 1e9, -1e9]
            for ob in meshes:
                evaluated = ob.evaluated_get(depsgraph)
                for corner in evaluated.bound_box:
                    world = evaluated.matrix_world @ Vector(corner)
                    bounds[0] = min(bounds[0], world.x)
                    bounds[1] = max(bounds[1], world.x)
                    bounds[2] = min(bounds[2], world.y)
                    bounds[3] = max(bounds[3], world.y)
                    bounds[4] = min(bounds[4], world.z)
                    bounds[5] = max(bounds[5], world.z)
            return bounds

        raw = world_bounds()
        source_height = raw[5] - raw[4]
        low, high = spec['character']['expected_height_m']
        target_height = min(float(high), max(float(low), 1.6))
        scale_factor = (target_height / source_height
                        if source_height > 1e-6 else 1.0)
        scale_factor = min(2.5, max(0.25, scale_factor))
        for root in roots:
            root.matrix_world = (Matrix.Translation((sx, sy, 0.0))
                                 @ Matrix.Rotation(math.pi, 4, 'Z')
                                 @ Matrix.Scale(scale_factor, 4)
                                 @ root.matrix_world)
        bpy.context.view_layer.update()
        min_x, max_x, min_y, max_y, min_z, max_z = world_bounds()
        delta_z = spawn_z - min_z
        for root in roots:
            root.matrix_world = Matrix.Translation((0.0, 0.0, delta_z)) @ root.matrix_world
        bpy.context.view_layer.update()
        min_z += delta_z
        max_z += delta_z
        ground_samples = [terrain_height(min_x, min_y), terrain_height(max_x, min_y),
                          terrain_height(min_x, max_y), terrain_height(max_x, max_y),
                          terrain_height(sx, sy)]
        ground_max = max(ground_samples)
        character_report.update({
            'imported': True,
            'imported_objects': len(imported),
            'meshes': len(meshes),
            'dimensions': [round(max_x - min_x, 3), round(max_y - min_y, 3),
                           round(max_z - min_z, 3)],
            'height_m': round(max_z - min_z, 3),
            'source_height_m': round(source_height, 3),
            'scale_factor': round(scale_factor, 4),
            'target_height_m': round(target_height, 3),
            'ground_contact_error_m': round(abs(min_z - spawn_z), 4),
            'min_z': round(min_z, 4), 'max_z': round(max_z, 4),
            'spawn_z': round(spawn_z, 4),
            'intersects_terrain': bool(min_z < ground_max - 0.1),
            'ground_max_under_bounds': round(ground_max, 4),
            'actions': [action.name for action in bpy.data.actions],
            'source_sha256': __import__('hashlib').sha256(
                open(character_path, 'rb').read()).hexdigest(),
        })
    else:
        character_report['error'] = 'no mesh found in character asset'
else:
    character_report['error'] = 'character asset not found: %s' % character_path

# ---------------------------------------------------------------- validate terrain helpers
terrain_stats = {
    'vertices': len(terrain.data.vertices),
    'triangles': len(terrain.data.loop_triangles),
    'non_manifold_edges': non_manifold,
    'degenerate_faces': degenerate,
    'height_min_m': round(terrain_min_z, 4),
    'height_max_m': round(terrain_max_z, 4),
    'height_range_m': round(terrain_max_z - terrain_min_z, 4),
    'uv_layers': [uv.name for uv in terrain.data.uv_layers],
    'uv_coverage': round(uv_coverage, 4),
    'materials': [slot.material.name for slot in terrain.material_slots if slot.material],
    'dimensions': [round(v, 3) for v in terrain.dimensions],
}

# ---------------------------------------------------------------- material audit
def linked_node(node, key):
    if node is None:
        return None
    socket = node.inputs.get(key)
    if socket is None or not socket.is_linked:
        return None
    return socket.links[0].from_node

def image_upstream(node, key):
    source = linked_node(node, key)
    if source is None:
        return False
    if source.type == 'TEX_IMAGE':
        return True
    if key == 'Normal' and source.type == 'NORMAL_MAP':
        color_source = linked_node(source, 'Color')
        return bool(color_source and color_source.type == 'TEX_IMAGE')
    return False

material_report = []
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    images = []
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            img = node.image
            images.append({
                'name': img.name, 'filepath': img.filepath,
                'exists': bool(img.packed_file) or os.path.isfile(bpy.path.abspath(img.filepath)),
                'size': list(img.size), 'colorspace': img.colorspace_settings.name,
                'packed': bool(img.packed_file),
            })
    channels = {}
    if bsdf:
        alpha_socket = bsdf.inputs.get('Alpha')
        alpha = float(alpha_socket.default_value) if alpha_socket else 1.0
        transmission_socket = bsdf.inputs.get('Transmission Weight') or bsdf.inputs.get('Transmission')
        transmission = float(transmission_socket.default_value) if transmission_socket else 0.0
        channels = {
            'base_color': 'texture' if image_upstream(bsdf, 'Base Color') else 'constant',
            'roughness': 'texture' if image_upstream(bsdf, 'Roughness') else 'constant',
            'normal': 'texture' if image_upstream(bsdf, 'Normal') else 'absent',
            'metallic': 'texture' if image_upstream(bsdf, 'Metallic') else 'constant',
            'ao': 'absent',
            'emission': 'constant' if bsdf.inputs.get('Emission Strength') and float(
                bsdf.inputs['Emission Strength'].default_value) > 0 else 'absent',
            'opacity': 'texture' if image_upstream(bsdf, 'Alpha') else (
                'constant' if alpha < 0.999 else 'absent'),
            'transmission': 'constant' if transmission > 0 else 'absent',
        }
    material_report.append({
        'name': mat.name, 'images': images, 'channels': channels,
        'declared_channels': dict(mat.get('pbr_channels', {})),
    })

# ---------------------------------------------------------------- save + export + render
print('STAGE save/export start', flush=True)
for img in (base_img, rough_img, normal_img):
    try:
        img.pack()
    except Exception:
        pass

blend_path = os.path.join(out_dir, 'JungleLevel.blend')
print('STAGE save blend', flush=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

# Exporting and rendering run in separate Blender processes from the saved
# .blend (see EXPORT_SCRIPT / RENDER_SCRIPT). A long-lived procedural session
# proved unreliable for chained exports in background mode, and the harness
# captures stdout through a pipe that is drained only after the process exits.
export_errors = []
render_error = None
preview_overview = os.path.join(out_dir, 'preview_overview.png')
preview_spawn = os.path.join(out_dir, 'preview_spawn.png')
# ---------------------------------------------------------------- layout sidecar
layout_document = {
    'schema_version': 1,
    'level': spec['name'], 'profile': profile, 'quality_tier': quality,
    'units': 'meters', 'up_axis': 'Z', 'forward_axis': '-Z',
    'terrain': {'size_x_m': size_x, 'size_y_m': size_y,
                'height_min_m': round(terrain_min_z, 4),
                'height_max_m': round(terrain_max_z, 4)},
    'spawn': {'name': 'SPAWN_PLAYER', 'x': sx, 'y': sy, 'z': round(spawn_z + 0.02, 4),
              'facing': list(spawn['facing']), 'clearance_m': round(spawn_clearance, 3)},
    'route': {'width_m': route_width, 'waypoints': waypoints,
              'max_slope_deg': round(route_slope_max, 3),
              'conflicts': route_conflicts},
    'landmark': {'name': 'LANDMARK_DESTINATION', 'x': lx, 'y': ly,
                 'z': round(landmark_z, 4), 'type': landmark.get('type')},
    'collision': {
        'terrain_collider': 'Terrain',
        'walkable_slope_deg': float(spec['collision']['walkable_slope_deg']),
        'obstacles': [c for c in placed_colliders if c['role'] == 'static_obstacle'],
        'river_boundary': ({'name': 'River_Water', 'width_m': river_width,
                            'flow_direction': list(water_spec['flow_direction'])}
                           if water_present else None),
        'navmesh': 'metadata only; no runtime navigation system implemented',
    },
    'river': river_report,
    'character': character_report,
    'performance': {
        'terrain_vertices': len(terrain.data.vertices),
        'terrain_triangles': len(terrain.data.loop_triangles),
        'object_count': len(bpy.data.objects),
        'instance_count': instance_count,
        'unique_meshes': unique_meshes,
        'material_count': len(material_report),
        'texture_count': 3,
        'estimated_memory_mb': spec['performance']['estimated_memory_mb'],
        'memory_label': 'estimated, not measured',
    },
}
layout_path = os.path.join(out_dir, 'environment_layout.json')
with open(layout_path, 'w', encoding='utf-8') as handle:
    json.dump(layout_document, handle, indent=2)

scene_objects = [ob for ob in bpy.data.objects]
mesh_count = sum(1 for ob in scene_objects if ob.type == 'MESH')
light_count = sum(1 for ob in scene_objects if ob.type == 'LIGHT')
camera_count = sum(1 for ob in scene_objects if ob.type == 'CAMERA')
empty_count = sum(1 for ob in scene_objects if ob.type == 'EMPTY')
total_triangles = 0
for ob in scene_objects:
    if ob.type == 'MESH':
        ob.data.calc_loop_triangles()
        total_triangles += len(ob.data.loop_triangles)

__mcp_result = {
    'name': spec['name'], 'tier': quality, 'profile': profile,
    'blend': blend_path,
    'glb': os.path.join(out_dir, 'JungleLevel.glb'),
    'gltf': os.path.join(out_dir, 'JungleLevel.gltf'),
    'fbx': os.path.join(out_dir, 'JungleLevel.fbx'),
    'preview_overview': preview_overview if os.path.isfile(preview_overview) else None,
    'preview_spawn': preview_spawn if os.path.isfile(preview_spawn) else None,
    'render_error': render_error, 'export_errors': export_errors,
    'terrain': terrain_stats,
    'vegetation': {
        'counts': {name: sum(1 for r in vegetation_records if r['category'] == name)
                   for name in ('tree', 'bush', 'fern', 'grass', 'plant', 'roots')},
        'records': vegetation_records,
        'instance_count': instance_count,
        'unique_meshes': unique_meshes,
        'placed_colliders': placed_colliders,
    },
    'props': {
        'counts': {name: sum(1 for r in vegetation_records if r['category'] == name)
                   for name in ('rock', 'large_rock', 'fallen_log')},
        'debris': len(debris_points), 'ruin_objects': len(ruin_objects),
        'records': prop_records,
    },
    'water': river_report,
    'materials': material_report,
    'images': [
        {'name': img.name, 'filepath': img.filepath, 'size': list(img.size),
         'colorspace': img.colorspace_settings.name, 'packed': bool(img.packed_file)}
        for img in (base_img, rough_img, normal_img)
    ],
    'lighting': {
        'sun': {'name': sun.name, 'energy': float(sun.data.energy),
                'elevation_deg': float(light_spec['sun_elevation_deg']),
                'azimuth_deg': float(light_spec['sun_azimuth_deg']),
                'shadows': bool(getattr(sun.data, 'use_shadow', True))},
        'world': {'sky_color': list(light_spec['sky_color']),
                  'ambient_strength': float(light_spec['ambient_strength']),
                  'fog_density': float(light_spec['fog_density']),
                  'fog_color': list(light_spec['fog_color']),
                  'volumetric_fog_rendered': False},
        'exposure': float(scene.view_settings.exposure),
        'view_transform': scene.view_settings.view_transform,
    },
    'layout': {
        'spawn': layout_document['spawn'], 'route': layout_document['route'],
        'landmark': layout_document['landmark'], 'layout_path': layout_path,
        'spawn_clearance_m': round(spawn_clearance, 3),
        'route_conflicts': route_conflicts,
        'route_max_slope_deg': round(route_slope_max, 3),
        'waypoint_count': len(waypoints),
    },
    'collision': layout_document['collision'],
    'character': character_report,
    'counts': {
        'objects': len(scene_objects), 'meshes': mesh_count, 'lights': light_count,
        'cameras': camera_count, 'empties': empty_count,
        'instances': instance_count,
        'materials': len(material_report), 'textures': 3,
        'triangles_total': total_triangles,
    },
    'generation': 'procedural-blender',
    'external_assets_used': False,
    'ai_generated': False,
}
'''

EXPORT_SCRIPT = r'''
import bpy, os, sys, traceback
import logging
logging.disable(logging.CRITICAL)

ARGS = ARGS or {}
blend_path = ARGS['blend']
output_dir = ARGS['output_dir']
fmt = ARGS['format']

bpy.ops.wm.open_mainfile(filepath=blend_path)
errors = []
output_path = None
if fmt == 'glb':
    output_path = os.path.join(output_dir, 'JungleLevel.glb')
    bpy.ops.export_scene.gltf(filepath=output_path, export_format='GLB',
                              use_selection=False, export_apply=False,
                              export_yup=True, export_animations=False,
                              export_skins=False, export_cameras=True,
                              export_lights=True, export_extras=True)
elif fmt == 'gltf':
    output_path = os.path.join(output_dir, 'JungleLevel.gltf')
    bpy.ops.export_scene.gltf(filepath=output_path,
                              export_format='GLTF_SEPARATE',
                              use_selection=False, export_apply=False,
                              export_yup=True, export_animations=False,
                              export_skins=False, export_cameras=True,
                              export_lights=True, export_extras=True)
elif fmt == 'fbx':
    output_path = os.path.join(output_dir, 'JungleLevel.fbx')
    bpy.ops.export_scene.fbx(filepath=output_path, use_selection=False,
                             apply_scale_options='FBX_SCALE_ALL', bake_anim=False,
                             bake_anim_use_all_actions=False, axis_forward='-Z',
                             axis_up='Y', path_mode='COPY', embed_textures=True)
else:
    raise RuntimeError('unsupported export format: ' + fmt)

__mcp_result = {
    'format': fmt, 'output_path': output_path,
    'exists': bool(output_path and os.path.isfile(output_path)),
    'bytes': os.path.getsize(output_path) if output_path and os.path.isfile(output_path) else 0,
    'errors': errors,
}
'''

RENDER_SCRIPT = r'''
import bpy, os
import logging
logging.disable(logging.CRITICAL)

ARGS = ARGS or {}
blend_path = ARGS['blend']
output_dir = ARGS['output_dir']
preview_size = int(ARGS.get('preview_size') or 640)
samples = int(ARGS.get('samples') or 16)

bpy.ops.wm.open_mainfile(filepath=blend_path)
scene = bpy.context.scene
scene.render.engine = scene.render.engine or 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = preview_size
scene.render.resolution_y = preview_size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'taa_render_samples'):
    scene.eevee.taa_render_samples = samples

render_error = None
rendered = {}
def render_camera(name, path):
    camera = bpy.data.objects.get(name)
    if camera is None:
        raise RuntimeError('camera not found: ' + name)
    scene.camera = camera
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    rendered[name] = path if os.path.isfile(path) else None

try:
    render_camera('CAM_Overview', os.path.join(output_dir, 'preview_overview.png'))
    render_camera('CAM_Spawn', os.path.join(output_dir, 'preview_spawn.png'))
except Exception as exc:
    render_error = '%s: %s' % (type(exc).__name__, exc)

bpy.ops.wm.save_as_mainfile(filepath=blend_path)
__mcp_result = {'rendered': rendered, 'render_error': render_error}
'''

REIMPORT_SCRIPT = r'''
import bpy, os, math
from mathutils import Vector

ARGS = ARGS or {}
source = ARGS['source']
save_path = ARGS.get('save_blend')
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(source)[1].lower()
if ext in ('.glb', '.gltf'):
    bpy.ops.import_scene.gltf(filepath=source)
elif ext == '.fbx':
    bpy.ops.import_scene.fbx(filepath=source)
else:
    raise RuntimeError('unsupported re-import format: ' + ext)

objects = list(bpy.data.objects)
meshes = [ob for ob in objects if ob.type == 'MESH']
lights = [ob for ob in objects if ob.type == 'LIGHT']
cameras = [ob for ob in objects if ob.type == 'CAMERA']
armatures = [ob for ob in objects if ob.type == 'ARMATURE']
actions = [a.name for a in bpy.data.actions if a.fcurves or getattr(a, 'layers', None)]
material_names = sorted({ms.material.name for ob in meshes for ms in ob.material_slots
                         if ms.material})
missing_images = [img.filepath for img in bpy.data.images
                  if not img.packed_file and img.filepath
                  and not os.path.isfile(bpy.path.abspath(img.filepath))]
triangles = 0
for ob in meshes:
    ob.data.calc_loop_triangles()
    triangles += len(ob.data.loop_triangles)
if save_path:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)

__mcp_result = {
    'object_count': len(objects),
    'mesh_count': len(meshes),
    'triangle_count': triangles,
    'light_count': len(lights),
    'camera_count': len(cameras),
    'armature_count': len(armatures),
    'material_count': len(material_names),
    'materials': material_names,
    'actions': actions,
    'spawn_marker': any(ob.name.startswith('SPAWN_PLAYER') for ob in objects),
    'waypoint_markers': [ob.name for ob in objects if ob.name.startswith('ROUTE_WAYPOINT')],
    'landmark_marker': any(ob.name.startswith('LANDMARK_DESTINATION') for ob in objects),
    'river_objects': [ob.name for ob in objects if ob.name.startswith('River')],
    'missing_images': missing_images,
    'saved': save_path,
}
'''


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _artifact_entry(path: str) -> dict:
    exists = bool(path) and os.path.isfile(path)
    return {
        "path": path,
        "exists": exists,
        "bytes": os.path.getsize(path) if exists else 0,
        "sha256": sha256_file(path) if exists else None,
    }


def _resolve_character_path(spec: dict, root: str) -> str:
    raw = ((spec.get("character") or {}).get("asset_path") or "").strip()
    if not raw:
        return ""
    if os.path.isabs(raw):
        return os.path.abspath(raw)
    candidate = os.path.abspath(os.path.join(root, raw))
    if os.path.isfile(candidate):
        return candidate
    fallback = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..", raw))
    return fallback if os.path.isfile(fallback) else candidate


def _channel_report(materials: list[dict]) -> dict:
    return {material["name"]: material.get("channels") or {}
            for material in materials}


def build_environment(spec: dict, output_dir: str, *, timeout: int = 1200,
                      blender_exe: str | None = None,
                      preview_size: int | None = None,
                      character_root: str | None = None) -> dict:
    errors = environment_spec.validate_environment_spec(spec)
    if errors:
        raise ToolError(f"environment specification is invalid: {errors}")
    executable = resolve_blender_executable(blender_exe)
    out = os.path.abspath(output_dir)
    os.makedirs(out, exist_ok=True)
    if not executable:
        return {
            "ok": False, "status": "failed",
            "stages": {"blender-build": {"status": "failed",
                                         "error": "Blender executable not found"}},
            "errors": ["Blender executable not found"], "spec_id": spec["id"],
            "artifacts": {},
        }
    character_path = _resolve_character_path(
        spec, character_root or os.getcwd())
    if character_path and not os.path.isfile(character_path):
        character_path = ""
    size = preview_size or int(spec["performance"]["preview_size"])
    result = blender.run_blender(
        BUILD_SCRIPT,
        args={"spec": spec, "output_dir": out, "character_path": character_path,
              "preview_size": size},
        timeout=timeout, blender_exe=executable, factory=True)
    report = {
        "ok": False, "status": "failed", "spec_id": spec["id"],
        "blender_executable": executable, "blender_executed": True,
        "blender_exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"), "output_dir": out,
        "blender_result_ok": result.get("ok", False), "errors": [], "warnings": [],
        "stages": {}, "artifacts": {},
        "stdout_tail": result.get("stdout_tail", ""),
        "stderr_tail": result.get("stderr_tail", ""),
        "character_asset_path": character_path,
    }
    if not result.get("ok"):
        report["errors"].append(result.get("error") or "Blender environment build failed")
        report["stages"]["blender-build"] = {"status": "failed",
                                             "error": report["errors"][-1]}
        return report
    payload = result.get("result") or {}
    report["blender_result"] = payload

    # Export and render from the saved .blend in isolated Blender processes.
    export_results = {}
    export_errors = list(payload.get("export_errors") or [])
    blend_file = payload.get("blend") or os.path.join(out, "JungleLevel.blend")
    if os.path.isfile(blend_file):
        for fmt in ("glb", "gltf", "fbx"):
            exported = blender.run_blender(
                EXPORT_SCRIPT,
                args={"blend": blend_file, "output_dir": out, "format": fmt},
                timeout=min(timeout, 600), blender_exe=executable, factory=True)
            export_results[fmt] = exported
            if not exported.get("ok"):
                export_errors.append(
                    f"{fmt}: {exported.get('error') or 'export process failed'}")
            else:
                detail = (exported.get("result") or {})
                if not detail.get("exists"):
                    export_errors.append(f"{fmt}: output file was not created")
        render_result = blender.run_blender(
            RENDER_SCRIPT,
            args={"blend": blend_file, "output_dir": out,
                  "preview_size": size,
                  "samples": int(spec["performance"]["render_samples"])},
            timeout=min(timeout, 900), blender_exe=executable, factory=True)
    else:
        render_result = {"ok": False, "error": "blend file was not created"}
    render_detail = render_result.get("result") or {}
    payload["export_errors"] = export_errors
    payload["render_error"] = (render_detail.get("render_error")
                               or (None if render_result.get("ok")
                                   else render_result.get("error")))
    report["export_processes"] = {name: {"ok": value.get("ok"),
                                         "exit_code": value.get("exit_code"),
                                         "duration_ms": value.get("duration_ms"),
                                         "error": value.get("error")}
                                  for name, value in export_results.items()}
    report["render_process"] = {
        "ok": render_result.get("ok"),
        "exit_code": render_result.get("exit_code"),
        "duration_ms": render_result.get("duration_ms"),
        "error": render_result.get("error"),
        "render_error": payload.get("render_error"),
    }

    paths = {
        "blend": payload.get("blend") or os.path.join(out, "JungleLevel.blend"),
        "glb": payload.get("glb") or os.path.join(out, "JungleLevel.glb"),
        "gltf": payload.get("gltf") or os.path.join(out, "JungleLevel.gltf"),
        "fbx": payload.get("fbx") or os.path.join(out, "JungleLevel.fbx"),
        "preview_overview": payload.get("preview_overview")
        or os.path.join(out, "preview_overview.png"),
        "preview_spawn": payload.get("preview_spawn")
        or os.path.join(out, "preview_spawn.png"),
        "layout": payload.get("layout", {}).get("layout_path")
        or os.path.join(out, "environment_layout.json"),
    }
    report["artifacts"] = {name: _artifact_entry(path) for name, path in paths.items()}
    for name, entry in report["artifacts"].items():
        if not entry["exists"] or entry["bytes"] <= 0:
            report["errors"].append(f"{name} artifact missing or empty: {entry['path']}")

    terrain = payload.get("terrain") or {}
    vegetation = payload.get("vegetation") or {}
    props = payload.get("props") or {}
    water = payload.get("water") or {}
    materials = payload.get("materials") or []
    images = payload.get("images") or []
    lighting = payload.get("lighting") or {}
    layout = payload.get("layout") or {}
    collision = payload.get("collision") or {}
    character = payload.get("character") or {}

    # terrain
    terrain_issues = []
    if int(terrain.get("triangles") or 0) < 1000:
        terrain_issues.append("terrain has too few triangles")
    if float(terrain.get("height_range_m") or 0) < 1.0:
        terrain_issues.append("terrain is effectively flat")
    if int(terrain.get("degenerate_faces") or 0) > 0:
        terrain_issues.append("terrain has degenerate faces")
    if not terrain.get("uv_layers") or float(terrain.get("uv_coverage") or 0) < 0.5:
        terrain_issues.append("terrain UV map missing or coverage too low")
    if "M_Env_Ground" not in (terrain.get("materials") or []):
        terrain_issues.append("terrain ground material not assigned")
    report["stages"]["terrain-validated"] = {
        "status": "passed" if not terrain_issues else "failed",
        "issues": terrain_issues, **terrain,
    }
    report["terrain"] = terrain

    # vegetation
    requested = {key: int(value) for key, value in
                 (spec["vegetation"].get("counts") or {}).items()}
    actual_counts = vegetation.get("counts") or {}
    category_map = {"trees": "tree", "bushes": "bush", "ferns": "fern",
                    "grass": "grass", "plants": "plant"}
    vegetation_issues = []
    for requested_name, expected in requested.items():
        actual_name = category_map.get(requested_name, requested_name)
        actual = int(actual_counts.get(actual_name) or 0)
        if actual < max(1, int(expected * 0.85)):
            vegetation_issues.append(
                f"{actual_name}: placed {actual} of requested {expected}")
    if int(vegetation.get("instance_count") or 0) <= 0:
        vegetation_issues.append("no linked-mesh instances were created")
    records = vegetation.get("records") or []
    categorized = {}
    for record in records:
        categorized.setdefault(record["category"], []).append(record)
    min_spacing_issues = []
    for category, points in categorized.items():
        required = float((spec["vegetation"].get("min_spacing_m") or {}).get(category) or 0)
        if required <= 0:
            continue
        for index, first in enumerate(points):
            for second in points[index + 1:]:
                distance = ((first["x"] - second["x"]) ** 2
                            + (first["y"] - second["y"]) ** 2) ** 0.5
                if distance < required * 0.85:
                    min_spacing_issues.append(
                        {"category": category, "pair": [first["name"], second["name"]],
                         "distance": round(distance, 3), "required": required})
    if min_spacing_issues:
        vegetation_issues.append(
            f"{len(min_spacing_issues)} vegetation spacing violations")
    route_conflicts = layout.get("route_conflicts") or []
    if route_conflicts:
        vegetation_issues.append(f"{len(route_conflicts)} route obstruction(s)")
    report["stages"]["vegetation-validated"] = {
        "status": "passed" if not vegetation_issues else "failed",
        "issues": vegetation_issues, "requested": requested,
        "counts": actual_counts, "instance_count": vegetation.get("instance_count"),
        "unique_meshes": vegetation.get("unique_meshes"),
        "spacing_violations": min_spacing_issues[:20],
        "route_conflicts": route_conflicts[:20],
        "records": len(records),
    }
    report["vegetation"] = vegetation

    # props
    prop_issues = []
    prop_counts = props.get("counts") or {}
    if int(prop_counts.get("rock") or 0) <= 0:
        prop_issues.append("no small rocks generated")
    if int(prop_counts.get("large_rock") or 0) <= 0:
        prop_issues.append("no large rocks generated")
    if int(prop_counts.get("fallen_log") or 0) <= 0:
        prop_issues.append("no fallen logs generated")
    if int(props.get("ruin_objects") or 0) <= 0:
        prop_issues.append("no ruins or landmark props generated")
    report["stages"]["props-validated"] = {
        "status": "passed" if not prop_issues else "failed",
        "issues": prop_issues, **{key: value for key, value in props.items()
                                  if key != "records"},
    }
    report["props"] = props

    # water
    water_issues = []
    if spec["water"].get("present"):
        if not water.get("present"):
            water_issues.append("river was requested but not generated")
        if int(water.get("triangles") or 0) <= 0:
            water_issues.append("river has no geometry")
        if not water.get("water_surface"):
            water_issues.append("river water surface missing")
        if not water.get("banks"):
            water_issues.append("river banks missing")
        if not water.get("left_boundary") or not water.get("right_boundary"):
            water_issues.append("river boundary metadata missing")
        if not water.get("flow_direction"):
            water_issues.append("river flow direction missing")
    report["stages"]["water-validated"] = {
        "status": "passed" if not water_issues else "failed",
        "issues": water_issues,
        "present": bool(water.get("present")),
        "width_m": water.get("width_m"),
        "vertices": water.get("vertices"), "triangles": water.get("triangles"),
        "banks": water.get("banks"), "flow_direction": water.get("flow_direction"),
        "physics": "visual-only; no swimming interaction implemented",
    }
    report["water"] = water

    # materials and textures
    material_issues = []
    channels = _channel_report(materials)
    for material in materials:
        declared = material.get("declared_channels") or {}
        actual = material.get("channels") or {}
        for channel, expected in declared.items():
            if expected == "generated" and actual.get(channel) != "texture":
                material_issues.append(
                    f"{material['name']}: {channel} declared generated but is "
                    f"{actual.get(channel)}")
        for image in material.get("images") or []:
            if not image.get("exists"):
                material_issues.append(
                    f"{material['name']}: missing image {image.get('filepath')}")
            name = image.get("name") or ""
            expected_space = "sRGB" if "BaseColor" in name else (
                "Non-Color" if ("Roughness" in name or "Normal" in name) else None)
            if expected_space and image.get("colorspace") != expected_space:
                material_issues.append(
                    f"{name}: colorspace {image.get('colorspace')} != {expected_space}")
    texture_files = []
    for image in images:
        path = image.get("filepath") or ""
        if not path:
            continue
        resolved = path
        if resolved.startswith("//"):
            resolved = os.path.join(out, resolved[2:])
        if not os.path.isfile(resolved):
            material_issues.append(f"missing texture file: {path}")
            continue
        dimensions = png_dimensions(resolved)
        expected = (spec["textures"]["resolution"], spec["textures"]["resolution"])
        if dimensions != expected:
            material_issues.append(f"{os.path.basename(resolved)}: {dimensions} != {expected}")
        texture_files.append({
            "path": resolved, "dimensions": list(dimensions or []),
            "bytes": os.path.getsize(resolved), "sha256": sha256_file(resolved),
            "colorspace": image.get("colorspace"),
        })
    if len(texture_files) < 3:
        material_issues.append("fewer than three ground textures were written")
    report["stages"]["materials-validated"] = {
        "status": "passed" if not material_issues else "failed",
        "issues": material_issues, "materials": len(materials),
        "channels": channels, "textures": texture_files,
    }
    report["materials"] = materials
    report["textures"] = texture_files
    report["pbr_channels"] = channels

    # lighting
    light_issues = []
    sun = lighting.get("sun") or {}
    world = lighting.get("world") or {}
    if float(sun.get("energy") or 0) <= 0:
        light_issues.append("sun light energy missing")
    if not sun.get("shadows"):
        light_issues.append("sun shadows disabled")
    if not world.get("sky_color"):
        light_issues.append("world sky color missing")
    if float(world.get("fog_density") or 0) <= 0:
        light_issues.append("fog/atmosphere density missing")
    report["stages"]["lighting-validated"] = {
        "status": "passed" if not light_issues else "failed",
        "issues": light_issues, **lighting,
        "volumetric_fog_rendered": False,
    }
    report["lighting"] = lighting

    # layout
    layout_issues = []
    spawn_info = layout.get("spawn") or {}
    if not spawn_info.get("name"):
        layout_issues.append("spawn marker missing")
    if int(layout.get("waypoint_count") or 0) < 2:
        layout_issues.append("route waypoints missing")
    if not layout.get("landmark"):
        layout_issues.append("landmark missing")
    if float(layout.get("spawn_clearance_m") or 0) < float(
            spec["collision"]["spawn_clearance_m"]):
        layout_issues.append("spawn clearance below requirement")
    if int(layout.get("route_max_slope_deg") or 0) > float(
            spec["collision"]["walkable_slope_deg"]) + 2:
        layout_issues.append("route slope exceeds walkable limit")
    if layout.get("route_conflicts"):
        layout_issues.append("route is obstructed")
    report["stages"]["layout-validated"] = {
        "status": "passed" if not layout_issues else "failed",
        "issues": layout_issues, **layout,
    }
    report["layout"] = layout

    # collision
    collision_issues = []
    if not collision.get("terrain_collider"):
        collision_issues.append("terrain collider missing")
    if not collision.get("obstacles"):
        collision_issues.append("no obstacle collision metadata")
    if spec["collision"].get("river_boundary") and not collision.get("river_boundary"):
        collision_issues.append("river boundary metadata missing")
    if float(layout.get("spawn_clearance_m") or 0) < float(
            spec["collision"]["spawn_clearance_m"]):
        collision_issues.append("spawn is not clear")
    report["stages"]["collision-validated"] = {
        "status": "passed" if not collision_issues else "failed",
        "issues": collision_issues,
        "terrain_collider": collision.get("terrain_collider"),
        "obstacle_count": len(collision.get("obstacles") or []),
        "river_boundary": collision.get("river_boundary"),
        "walkable_slope_deg": collision.get("walkable_slope_deg"),
        "navigation": collision.get("navmesh"),
    }
    report["collision"] = collision

    # character integration
    character_issues = []
    if spec["character"].get("place"):
        if not character.get("imported"):
            character_issues.append(character.get("error") or "character not imported")
        else:
            low, high = spec["character"]["expected_height_m"]
            if not (float(low) <= float(character.get("height_m") or 0) <= float(high)):
                character_issues.append(
                    f"character height {character.get('height_m')} outside {low}-{high} m")
            contact_error = character.get("ground_contact_error_m")
            if contact_error is None or float(contact_error) > 0.2:
                character_issues.append("character is not grounded at spawn")
            if character.get("intersects_terrain"):
                character_issues.append("character intersects terrain")
    report["stages"]["character-integrated"] = {
        "status": "passed" if not character_issues else "failed",
        "issues": character_issues, **character,
    }
    report["character"] = character

    report["counts"] = payload.get("counts") or {}
    report["generation"] = "procedural-blender"
    report["external_assets_used"] = False
    report["ai_generated"] = False
    report["classifications"] = {
        "procedurally_generated_geometry": True,
        "imported_existing_geometry": bool(character.get("imported")),
        "imported_character_asset": bool(character.get("imported")),
        "ai_generated_assets": False,
        "external_acquired_assets": False,
        "placeholder_asset": False,
        "production_ready": False,
        "water_physics_implemented": False,
        "navigation_runtime_implemented": False,
        "quality_classification": "stylized-procedural-jungle-level",
    }

    report["stages"]["spec-validated"] = {"status": "passed", "issues": []}
    report["stages"]["blender-build"] = {
        "status": "passed", "exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"),
    }
    report["stages"]["blend-saved"] = {
        "status": "passed" if report["artifacts"]["blend"]["exists"] else "failed",
        "artifact": report["artifacts"]["blend"],
    }
    for role in ("glb", "gltf", "fbx"):
        report["stages"][f"{role}-exported"] = {
            "status": "passed" if report["artifacts"][role]["exists"] else "failed",
            "artifact": report["artifacts"][role],
        }
    report["stages"]["previews-rendered"] = {
        "status": "passed" if all(
            report["artifacts"][name]["exists"]
            for name in ("preview_overview", "preview_spawn")) else "failed",
        "artifacts": [report["artifacts"]["preview_overview"],
                      report["artifacts"]["preview_spawn"]],
        "error": payload.get("render_error"),
    }

    glb_validation = validate_glb(paths["glb"])
    gltf_validation = validate_gltf(paths["gltf"])
    report["glb_validation"] = glb_validation
    report["gltf_validation"] = gltf_validation
    report["stages"]["glb-validated"] = {
        "status": "passed" if glb_validation["ok"] else "failed",
        "errors": glb_validation["errors"], "warnings": glb_validation["warnings"],
        "triangles": glb_validation.get("triangles"),
        "materials": glb_validation.get("materials"),
        "images": glb_validation.get("images"),
        "animations": glb_validation.get("animations"),
        "skins": glb_validation.get("skins"),
        "nodes": glb_validation.get("nodes"),
    }
    report["stages"]["gltf-validated"] = {
        "status": "passed" if gltf_validation["ok"] else "failed",
        "errors": gltf_validation["errors"], "warnings": gltf_validation["warnings"],
        "triangles": gltf_validation.get("triangles"),
        "materials": gltf_validation.get("materials"),
        "buffers": gltf_validation.get("buffers"),
        "external_buffers": gltf_validation.get("external_buffers"),
    }
    failed = [name for name, stage in report["stages"].items()
              if stage.get("status") == "failed"]
    report["failed_stages"] = failed
    report["status"] = "built" if not failed else (
        "partial" if report["artifacts"]["blend"]["exists"] else "failed")
    report["ok"] = report["status"] == "built"
    report["generated_at"] = _now()
    return report


def reimport_and_validate(glb_path: str, output_dir: str, *, timeout: int = 600,
                          blender_exe: str | None = None) -> dict:
    executable = resolve_blender_executable(blender_exe)
    if not executable:
        return {"ok": False, "error": "Blender executable not found",
                "checks": {}}
    if not os.path.isfile(glb_path):
        return {"ok": False, "error": f"GLB does not exist: {glb_path}",
                "checks": {}}
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
        "ok": False, "glb": os.path.abspath(glb_path),
        "reimport_blend": reimport_blend, "blender_exit_code": imported.get("exit_code"),
        "duration_ms": imported.get("duration_ms"), "inspection": None, "checks": {},
    }
    if not imported.get("ok"):
        report["error"] = imported.get("error") or "re-import failed"
        return report
    inspection = imported.get("result") or {}
    report["inspection"] = inspection
    checks = {
        "imported_meshes": int(inspection.get("mesh_count") or 0) >= 5,
        "imported_materials": int(inspection.get("material_count") or 0) >= 5,
        "imported_lights": int(inspection.get("light_count") or 0) >= 1,
        "imported_cameras": int(inspection.get("camera_count") or 0) >= 1,
        "spawn_marker": bool(inspection.get("spawn_marker")),
        "route_markers": len(inspection.get("waypoint_markers") or []) >= 2,
        "landmark_marker": bool(inspection.get("landmark_marker")),
        "river_objects": len(inspection.get("river_objects") or []) >= 1,
        "no_missing_textures": not inspection.get("missing_images"),
    }
    report["checks"] = checks
    report["ok"] = all(checks.values())
    if not report["ok"]:
        report["error"] = "re-import checks failed: " + ", ".join(
            name for name, value in checks.items() if not value)
    return report


def engine_compatibility(glb_validation: dict, *, target_engine: str) -> dict:
    common = {
        "export_prepared": True,
        "integration_verified": False,
        "materials": bool(glb_validation.get("materials")),
        "rig": bool(glb_validation.get("skins")),
        "animations": bool(glb_validation.get("animations")),
        "note": ("Exports are structurally validated. No engine import was "
                 "executed in Phase 4."),
    }
    return {
        "unity": {**common, "formats": ["fbx", "glb", "gltf"],
                  "status": "export-prepared-unverified",
                  "notes": ["FBX is the primary Unity path; GLB/glTF import with "
                            "Unity glTF support.", "No Unity editor import was run."]},
        "godot": {**common, "formats": ["glb", "gltf"],
                  "status": "export-prepared-unverified",
                  "notes": ["glTF/GLB is Godot's native path; not imported here."]},
        "unreal": {**common, "formats": ["fbx", "gltf"],
                   "status": "export-prepared-unverified",
                   "notes": ["FBX is the usual path; glTF needs the import plugin."]},
        "target": target_engine,
    }


def asset_manifest(spec: dict, build: dict, *, reimport: dict | None = None,
                   created_at: str | None = None) -> dict:
    artifacts = []
    for name, entry in (build.get("artifacts") or {}).items():
        artifacts.append({
            "role": name, "format": os.path.splitext(entry.get("path") or "")[1].lstrip("."),
            **entry,
        })
    textures = []
    for texture in build.get("textures") or []:
        textures.append({"role": "texture", "format": "png", **texture})
    terrain = build.get("terrain") or {}
    vegetation = build.get("vegetation") or {}
    props = build.get("props") or {}
    water = build.get("water") or {}
    character = build.get("character") or {}
    provenance = {
        "asset_id": spec["id"], "name": spec["name"], "asset_type": "environment",
        "profile": spec["profile"], "quality_tier": spec["quality_tier"],
        "source": spec["provenance"]["source"],
        "generation_method": spec["provenance"]["generation_method"],
        "creator": spec["provenance"]["creator"],
        "license": spec["provenance"]["license"],
        "license_id": spec["provenance"]["license_id"],
        "attribution_required": spec["provenance"]["attribution_required"],
        "external_assets": spec["provenance"]["external_assets"],
        "downloads": spec["provenance"]["downloads"],
        "download_status": "not-downloaded",
        "ai_generated": False, "procedural": True,
        "blender_executed": build.get("blender_executed", False),
        "dependencies": {
            "blender": build.get("blender_executable"),
            "blender_exit_code": build.get("blender_exit_code"),
            "textures": [texture["path"] for texture in textures],
            "character_asset": character.get("asset_path"),
            "gltf_external_buffers": (build.get("gltf_validation") or {}).get(
                "external_buffers") or [],
            "gltf_external_images": (build.get("gltf_validation") or {}).get(
                "external_images") or [],
        },
        "validation": {
            "build_status": build.get("status"),
            "failed_stages": build.get("failed_stages", []),
            "terrain": build.get("stages", {}).get("terrain-validated", {}).get("status"),
            "vegetation": build.get("stages", {}).get(
                "vegetation-validated", {}).get("status"),
            "props": build.get("stages", {}).get("props-validated", {}).get("status"),
            "water": build.get("stages", {}).get("water-validated", {}).get("status"),
            "materials": build.get("stages", {}).get(
                "materials-validated", {}).get("status"),
            "lighting": build.get("stages", {}).get("lighting-validated", {}).get("status"),
            "layout": build.get("stages", {}).get("layout-validated", {}).get("status"),
            "collision": build.get("stages", {}).get(
                "collision-validated", {}).get("status"),
            "character": build.get("stages", {}).get(
                "character-integrated", {}).get("status"),
            "glb": (build.get("glb_validation") or {}).get("ok"),
            "gltf": (build.get("gltf_validation") or {}).get("ok"),
            "reimport": (reimport or {}).get("ok"),
        },
        "engine_compatibility": engine_compatibility(
            build.get("glb_validation") or {},
            target_engine=spec["export"]["target_engine"]),
        "content": {
            "terrain": terrain,
            "vegetation_counts": vegetation.get("counts"),
            "vegetation_instances": vegetation.get("instance_count"),
            "unique_vegetation_meshes": vegetation.get("unique_meshes"),
            "prop_counts": props.get("counts"),
            "debris": props.get("debris"),
            "ruin_objects": props.get("ruin_objects"),
            "river": {"present": water.get("present"), "width_m": water.get("width_m"),
                      "triangles": water.get("triangles"),
                      "physics": "visual-only"},
            "character": {"imported": character.get("imported"),
                          "height_m": character.get("height_m"),
                          "ground_contact_error_m": character.get(
                              "ground_contact_error_m")},
        },
        "artifacts": artifacts, "textures": textures,
        "created_at": created_at or _now(), "schema_version": 1,
    }
    return provenance


def run_pipeline(spec: dict, output_dir: str, *, timeout: int = 1200,
                 blender_exe: str | None = None, preview_size: int | None = None,
                 character_root: str | None = None) -> dict:
    errors = environment_spec.validate_environment_spec(spec)
    if errors:
        raise ToolError(f"environment specification is invalid: {errors}")
    char_path = _resolve_character_path(spec, character_root or os.getcwd())
    source_hash_before = sha256_file(char_path) if char_path and os.path.isfile(char_path) else None
    build = build_environment(spec, output_dir, timeout=timeout,
                              blender_exe=blender_exe, preview_size=preview_size,
                              character_root=character_root)
    reimport = None
    stages = dict(build.get("stages") or {})
    if build.get("artifacts", {}).get("glb", {}).get("exists"):
        reimport = reimport_and_validate(
            build["artifacts"]["glb"]["path"], output_dir,
            timeout=min(timeout, 600), blender_exe=blender_exe)
        stages["glb-reimported"] = {
            "status": "passed" if reimport.get("ok") else "failed",
            "checks": reimport.get("checks"), "error": reimport.get("error"),
        }
    else:
        stages["glb-reimported"] = {"status": "failed",
                                    "error": "no GLB to re-import"}
    source_hash_after = sha256_file(char_path) if char_path and os.path.isfile(char_path) else None
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
        "ok": status == "completed", "status": status,
        "phase": "V6 Phase 4 - environment generation",
        "generated_at": _now(), "spec": spec,
        "spec_validation": {"valid": True, "errors": []},
        "build": build, "reimport": reimport, "stages": stages,
        "failed_stages": all_failed, "manifest": manifest, "provenance": manifest,
        "character_source": {
            "path": char_path,
            "sha256_before": source_hash_before,
            "sha256_after": source_hash_after,
            "unchanged": source_hash_before == source_hash_after,
        },
        "classifications": build.get("classifications"),
        "limitations": [
            "The level is a stylized procedural prototype, not hand-authored art.",
            "Water is a visual surface with boundary metadata; swimming and water "
            "physics are not implemented.",
            "Navigation metadata is prepared; no runtime navmesh system is implemented.",
            "Fog is configured as world haze plus scene metadata; volumetric fog is "
            "not rendered in the EEVEE preview.",
            "Engine integration is export-prepared and structurally validated only.",
            "No AI asset provider was contacted; no external assets were downloaded.",
        ],
    }
    return report
