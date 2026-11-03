# Blender → Engine Asset Pipeline

Use the Blender version installed on the current machine. Set `BLENDER_EXE` to
its executable path or make `blender` available on `PATH`. The local MCP server
at `tools/blender-mcp/server.py` drives the real Blender process.

## Tooling

### Blender MCP (preferred when connected)

| Tool | Use |
| --- | --- |
| `blender_info` | Version, Python, addons, active file |
| `inspect_blend` | Objects, transforms, meshes, UVs, materials, textures, armatures, actions, missing images |
| `validate_asset` | Triangles, UVs, transforms, missing textures, bones/actions, bounds, budget |
| `export_asset` | glb/gltf/fbx/obj/usdz, transform baking, scale |
| `import_asset` | Import fbx/glb/obj/blend/usd, optionally save .blend |
| `render_preview` | PNG render for visual verification |
| `run_python` | Arbitrary Blender Python in background mode |

Smoke test: `python scripts/test-blender-mcp.py --full` (creates a cube, saves
.blend, validates, exports GLB, renders PNG).

### Headless fallback

```powershell
$blender = if ($env:BLENDER_EXE) { $env:BLENDER_EXE } else { (Get-Command blender -ErrorAction Stop).Source }
& $blender --background in.blend --factory-startup `
  --python job.py --python-exit-code 1
```

Have the script write a JSON result file; do not parse Blender's stdout.

## The 13-step pipeline

1. **Locate and identify** the source (`.blend`, `.fbx`, `.glb`, `.obj`).
2. **Classify**: static mesh / character / rigged / animation / environment / prop.
3. **Licence check**: record source, author, licence, attribution requirements.
   Reject unclear licences for production use.
4. **Inspect** with `inspect_blend`: object count, transforms, scale, hierarchy.
5. **Geometry validation**: triangle budget, zero-area faces, non-manifold,
   loose geometry, duplicated vertices.
6. **UV validation**: at least one UV layer for any textured asset; non-overlapping
   UVs for baked lightmaps.
7. **Material validation**: node setup uses Principled BSDF, image textures have
   resolvable paths (pack them for `.blend` delivery).
8. **Rig/animation validation**: armature bones, skin weights, action frame
   ranges, root motion track presence.
9. **Export**: GLB for engines with good glTF support (Unity, Godot); FBX for
   Unreal or when the project pipeline expects it. Bake rotations/scale.
10. **Engine import settings**: scale factor, axis conversion, import materials,
    generate colliders, animation compression, Avatar rig.
11. **Create reusable asset**: prefab / Blueprint / Godot scene.
12. **Instantiate and verify** in a test scene (render or screenshot).
13. **Record** final paths, triangle counts, material names, licence, and any
    caveats (e.g. "no animations supplied").

## Export settings that avoid classic failures

| Problem | Cause | Fix |
| --- | --- | --- |
| Grey/untextured in engine | texture paths broken or shader unsupported | pack images, use Principled BSDF, export embedded GLB |
| 100× scale | Blender metres vs FBX centimetres | export scale 0.01 for FBX, or set Unity import scale |
| 90° rotation | Y-up vs Z-up mismatch | keep default axis conversion; verify in engine |
| Invisible mesh | flipped normals / backface culling | recalculate normals outside |
| Broken rig | armature not applied, missing weights | parent with automatic weights, check vertex groups |
| No animations | actions not stashed / NLA not exported | stash actions in NLA, enable animation export |
| Huge file | unapplied subdivision / dense mesh | apply modifier, decimate, bake normals |

## Verification that is not optional

- `validate_asset` returns `issues: []` (warnings triaged and recorded).
- The exported file exists with non-zero size.
- The engine import log lists the asset without errors.
- A rendered preview or in-engine screenshot exists.
- The instantiated object's world bounds match the intended size.
- Animation clips appear with the expected names and lengths; if none were
  supplied, say so — do not fabricate clips.

## Materials across engines

- glTF PBR maps to Unity URP/Lit and Godot StandardMaterial3D well.
- Unreal expects FBX + its own material setup; glTF import is plugin-dependent.
- Transparency: set blend mode explicitly in the engine; Blender's `HASHED` does
  not automatically become correct alpha blending.
- Texture colour space: albedo sRGB, normal/roughness/metallic linear.
- Prefer 1K–2K textures for mobile; verify memory impact.

## Collision

Author collision deliberately:

- Unity: simple primitives or a low-poly `_collider` mesh; never use the render
  mesh with 100k triangles as a MeshCollider.
- Unreal: collision primitives or UCX meshes; check "Simple Collision" in the
  Static Mesh editor.
- Godot: `-col` suffixed collision meshes or `CollisionShape3D` with primitives.

Validate by dropping the object onto a test plane and checking it rests without
jitter or penetration.
