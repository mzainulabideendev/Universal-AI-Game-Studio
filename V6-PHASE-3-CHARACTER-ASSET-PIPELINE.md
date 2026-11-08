# V6 Phase 3 — Character Models, PBR Textures & Intelligent Asset Generation

Status: **PASS** — machine verdict in `reports/v6-phase3-audit.json`.
The generated character is a stylized procedural, game-ready prototype; it is
not sculpted production art and is not claimed to be AI-generated.

Authorization: Phase 3 only. No commit, push, tag, install, download, paid API
request or Phase 4 environment generation was performed.

> **Repository-state note.** The task expected starting HEAD `b628527`; the
> actual HEAD at the start of this pass was `f239250` (one commit later:
> "Update project specifications and add new character assets for Jungle Monkey
> prototype"). No commits were created.
>
> A **parallel OpenCode session** was actively writing Phase 4 environment code
> and re-registering Phase 4 MCP tools in this same working tree during the
> Phase 3 pass. A snapshot of the Phase 4 files found at the start was preserved
> under `validation/deferred-phase4/`, and the Phase 3-only tree was briefly
> restored for parity checks. Because the parallel session kept writing, the
> final Phase 3 audit was executed in an isolated git worktree pinned to the
> same HEAD with only the Phase 3 changes applied. That audit reports
> **320/320 Phase 3-scoped tests passing** and **92/92** Phase 3 parity. The
> primary tree currently also contains the other session's Phase 4 work (94/94
> tools); that work is not claimed or validated by Phase 3. The audit JSON
> records this under `concurrent_session`. See
> `validation/deferred-phase4/README.md`.

---

## 1. What this phase adds

Phase 2 planned characters, materials, rigs and animations. Phase 3 turns that
plan into executable, evidence-producing work:

| Capability | Module / artifact |
| --- | --- |
| Structured character specification | `game_studio/character_spec.py` |
| Quality tiers with measurable settings | `QUALITY_TIERS` in `character_spec.py` |
| Real Blender build (geometry, UV, PBR, rig, animation, export) | `game_studio/character_pipeline.py` |
| PBR channel and texture validation | `character_pipeline.build_character` / `validate_*` |
| `.blend` / `.glb` / `.gltf` / `.fbx` export validation | `build_character`, `validate_glb`, `validate_gltf` |
| GLB re-import validation | `reimport_and_validate` |
| Asset manifest and provenance | `asset_manifest`, `reports/v6-asset-provenance.json` |
| Provider capability honesty | `character_spec.provider_capability_report` |
| MCP tools | `character_generate_asset`, `character_capabilities` (92 tools / 92 handlers) |
| Reproducible demo | `scripts/v6-phase3-demo.py` |
| Full audit | `scripts/v6-phase3-audit.py` |
| Tests | `tests/test_v6_phase3_character_spec.py`, `tests/test_v6_phase3_pipeline.py` |

Phase 2 agents, V4/V5 implementations, provider adapters, orchestration,
governance and verification code are unchanged.

---

## 2. Architecture

```
character description
        |
        v
Phase 2 Character Agent  --->  deterministic asset_specification (plan only)
        |
        v
character_spec.build_character_spec()
        |  validated by validate_character_spec()
        v
character_pipeline.run_pipeline()
        |-- BUILD_SCRIPT  (single controlled Blender subprocess)
        |     scene reset -> materials -> geometry -> join -> UV unwrap
        |     -> armature -> skin weights -> actions -> save .blend
        |     -> export .glb / .gltf / .fbx -> render preview
        |-- validate_glb() / validate_gltf()   (real file parsing)
        |-- reimport_and_validate()           (second Blender subprocess)
        `-- asset_manifest()                  (provenance + hashes + engines)
        |
        v
reports/v6-character-pipeline.json
reports/v6-character-validation.json
reports/v6-asset-provenance.json
```

A stage is reported `passed` only when the underlying file or Blender result
supports it. Failed Blender execution is never upgraded to success. The pipeline
runs one memory-intensive Blender job at a time.

### Quality tiers

Tiers are real, measurable settings read by the Blender script:

| Setting | Low | Medium | High |
| --- | ---: | ---: | ---: |
| Sphere segments / rings | 16 / 8 | 24 / 12 | 32 / 16 |
| Tail segments | 5 | 7 | 9 |
| Fingers per hand | 2 | 3 | 4 |
| Texture resolution | 256 | 512 | 1024 |
| Target triangles | 8,000 | 25,000 | 60,000 |
| LOD levels | 2 | 3 | 4 |
| Bone target | 18 | 22 | 26 |
| UV angle limit | 60° | 66° | 70° |
| UV island margin | 0.01 | 0.02 | 0.025 |
| Animation FPS | 24 | 30 | 30 |

`validate_character_spec` rejects specs whose texture, geometry or bone settings
do not match the declared tier.

---

## 3. Character creation

The character is assembled from Blender primitives into one mesh:

- torso, pelvis, chest;
- head, muzzle, brow ridge, nose, mouth;
- two eye whites, irises and pupils;
- outer and inner ears;
- upper arms, forearms, hands and fingers;
- thighs, shins, feet and toes;
- a tapered tail chain (for primate characters).

Each part is tagged with a material and a `game_studio_part` custom property.
Transforms are applied, normals are smoothed, and all parts are joined into the
`JungleMonkey` mesh before UV unwrapping. The body covers a complete humanoid
layout with hands and feet; it is deliberately a game-ready prototype, not a
sculpted hero asset.

Deterministic medium-tier demonstration result:

| Metric | Value |
| --- | --- |
| Vertices | 7,974 |
| Triangles | 15,688 |
| Non-manifold edges | 0 |
| Loose vertices | 0 |
| Degenerate faces | 0 |
| Materials | 7 |
| Bones / vertex groups | 23 / 23 |
| Boned vertices (non-zero weight) | 100% |
| Bounds (X/Y/Z, m) | 0.90 / 0.99 / 1.69 |
| Exported actions | `Idle`, `Walk`, `Run`, `Jump` |

The audit independently re-runs a **low** tier build (3,938 vertices / 7,632
triangles, 256² textures) to prove the tier settings genuinely change output.

---

## 4. UV mapping

- Blender `smart_project` runs on the joined mesh with a tier-specific angle
  limit and island margin, followed by `pack_islands` when available.
- UV layer presence is required, and coverage is measured by rasterising the
  real UV triangles onto a 64×64 grid.
- A missing UV layer or coverage ≤ 5% fails `geometry-validated` and
  `uv-validated`.
- Medium-tier coverage measured 15.04% (0.1504) in the committed demo; low tier
  measured 31.59% in the audit build. This is normal for a compact multi-part
  primitive unwrap and is reported, not inflated.

---

## 5. PBR texture and material handling

### Channels

| Channel | Implementation | Honest state |
| --- | --- | --- |
| Base Color / Albedo | Procedural PNG, sRGB | texture |
| Roughness | Procedural PNG, Non-Color | texture |
| Normal | Sobel-derived normal PNG, Non-Color | texture |
| Metallic | Numeric BSDF input | constant |
| Ambient Occlusion | Not computed | absent |
| Emission | Not required | absent |
| Opacity | Fully opaque (alpha = 1) | absent |

Base-color, roughness and normal images are locally generated from seeded value
noise. They are **not** scans, painted textures or AI output. No normal map is
claimed to represent physically measured surface detail.

### Materials

Seven Principled BSDF materials are created and assigned by role: fur, skin,
eye white, iris, pupil, nose and inner ear. The fur material wires the three
image textures to the correct shader inputs and uses a Normal Map node for the
normal texture.

### Validation

`materials-validated` checks:

- declared `generated` channels are actually image-linked;
- declared `constant` channels are not silently replaced;
- every referenced image file exists;
- base color is sRGB and roughness/normal are Non-Color;
- texture dimensions equal the tier resolution.

`uv-validated` and the texture block verify PNG readability, dimensions, file
size and SHA-256. Channel states are derived from the live shader graph
(including following the Normal Map node), not from material names. Opacity is
derived from the Alpha input rather than `blend_method`, because Blender 4.2+
may report `DITHERED` for a fully opaque material.

---

## 6. Rigging and animation readiness

The armature contains a root, pelvis, spine, chest, neck, head, two ears, arms,
hands, legs, feet, and a three-bone tail chain (23 bones). Skinning uses Blender
automatic weights; any unweighted vertex is deterministically assigned to the
nearest bone so exported meshes have no unskinned vertices.

Rig validation checks:

- an armature exists with at least six bones;
- every vertex has a non-zero skin weight (weighted ratio ≥ 90%; demo = 100%);
- vertex groups exist;
- the mesh has an armature modifier;
- re-import reports an armature, a skinned mesh and animated actions.

Four short keyframed actions are created and exported: idle, walk, run and jump.
They are procedural rotation clips, not hand-animated performances. The
specification library also supports landing, turn, collect and hit reaction.

---

## 7. Export pipeline

Each build exports:

| Format | Validation |
| --- | --- |
| `.blend` | exists, non-zero, hashed; packed textures |
| `.glb` | container parsed; meshes, primitives, triangles, materials, images, animations, skins, joints, bounds |
| `.gltf` | JSON parsed; external `.bin` byte length and external image references checked |
| `.fbx` | exists, non-zero, hashed; FBX internals are not parsed |

All artifacts record path, existence, bytes and SHA-256. The GLB is re-imported
into a genuinely empty Blender scene and checked for mesh, materials, UVs,
armature, skinned mesh, actions and missing images. A failed re-import makes the
pipeline `partial`.

Committed demo hashes:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `JungleMonkey.blend` | 1,013,753 | `eca11b8536d2ef9ad500bede8a187dd6fdf63bba9e819e8f8091d3515d6b532c` |
| `JungleMonkey.glb` | 1,310,604 | `fc15a9847a3b5f58fced125f81c3521261d92f71278a882698cef711b03bb58b` |
| `JungleMonkey.gltf` | 90,026 | `1c201ef9bcc30c9c59243b51fa1a2f4a047e2ed97be1e634dbbca91730e7ec63` |
| `JungleMonkey.fbx` | 1,513,628 | `634e2e64276c80194881c13c25d8cb70c6083f36431b38a65126303fa60b9cf6` |
| `preview.png` | 464,480 | `5dab449d49124a224fbed85bea54646da2b0fd88de6754a51118e8d46decdc9e` |

GLB bytes can differ between independent runs (Blender writes run-specific
binary data); the `.gltf` JSON hash is stable because it is generated from the
same deterministic geometry and metadata. Reports record the hashes of the run
they describe, and the audit re-hashes the files on disk.

The asset manifest records source, generation method, creator, license,
attribution, dependencies, artifact hashes, texture hashes, validation status and
engine compatibility labels.

---

## 8. Engine compatibility

Files are **export-prepared and structurally validated**, not imported into an
engine during Phase 3:

| Engine | Prepared formats | Status |
| --- | --- | --- |
| Unity | FBX, GLB, glTF | `export-prepared-unverified` |
| Godot | GLB, glTF | `export-prepared-unverified` |
| Unreal | FBX, glTF (plugin) | `export-prepared-unverified` |

No claim of working Unity, Godot or Unreal import is made from the mere
existence of a file. The V5 Unity project is not modified by Phase 3.

---

## 9. Asset discovery, provenance and licensing

Existing Phase 1/Poly Haven/Sketchfab/Meshy adapters remain the asset-discovery
path. They report provider-level and per-asset license data, attribution
requirements, download status and validation state. Public accessibility is not
treated as commercial permission.

Phase 3 does **not** download, acquire or ship any third-party asset. The
character and its textures are original procedural project content
(`project-original-1.0`); attribution is not required.
`reports/v6-asset-provenance.json` records that no external asset or AI
generation was used, and hashes the pipeline/validation reports it describes.

If a future request needs an external asset, the exact source, license, file and
reason must be reported and authorized first.

---

## 10. Provider capability limitations

Provider capability is explicit and never inferred from a provider name:

- Phase 1 LLM adapters: text reasoning `supported`; image, texture,
  image-to-texture and material generation `unsupported`; image analysis
  `unknown`.
- Meshy: mesh generation `supported` but `paid: true` and `authorized: false`;
  it is not used in Phase 3.
- No external image/texture/3D generator is configured or authorized.
- Local Blender provides mesh, texture and material generation.

The Character Agent still emits a plan (`assets_generated: false`,
`textures_generated: false`). Only the pipeline, with real Blender execution,
produces files. `character_capabilities` reports the missing capabilities
honestly.

---

## 11. Phase 2 integration

- The Character Agent emits a validated `asset_specification`.
- The Game Director/coordinator remain planning-only; they do not mark planned
  assets as generated.
- The pipeline consumes the spec and returns evidence.
- The QA Agent can consume the validation report and stage statuses.
- The Game Director status distinguishes planned, generated, acquired, existing,
  failed and missing-capability assets through the pipeline report and manifest.

Demonstration classification:

- procedurally generated geometry: **yes**
- existing imported geometry: no
- AI-generated asset: no
- external acquired asset: no
- placeholder-only asset: no (complete rigged, UV-mapped, textured prototype, but
  not production-ready)

---

## 12. Performance

- One Blender subprocess at a time; no concurrent memory-heavy builds.
- Blender runs with factory settings in an isolated scene.
- Medium-tier demo: 512² textures, 15,688 triangles, 23 bones; measured ~18 s
  Blender build and ~22 s wall clock on the development hardware
  (Ryzen 5 4500U, 16 GB RAM, integrated graphics).
- Fresh low-tier audit build: 3,938 vertices / 7,632 triangles / 256² textures,
  ~26 s including export, re-import and preview.
- Preview render is intentionally small (256–720 px) and uses the first
  available render engine.
- Timeouts are explicit (default 1200 s pipeline, 900 s audit build).

---

## 13. Tests

- All pre-existing tests (267) remain passing.
- 53 new Phase 3 tests cover specifications, tiers, capabilities, agent
  integration, GLB/glTF parsing, material/channel validation, missing textures,
  color spaces, UV and geometry failures, rigging, animation detection, export
  evidence, re-import, provenance, manifests, MCP parity, security and V4/V5
  hashes.
- Total in the Phase 3 suite: **320 passing**.
- Unit tests mock Blender; one integration test
  (`RealBlenderIntegrationTests`) executes the real local Blender and is
  separated by name.

Run:

```powershell
python -m unittest discover -s .\tools\game-studio-mcp\tests -v
```

---

## 14. Reproduction

```powershell
# Real Blender build + evidence reports (writes validation/ and reports/)
python .\scripts\v6-phase3-demo.py --confirm

# Full audit: tests, protection hashes, parity, fresh Blender build, verdict
python .\scripts\v6-phase3-audit.py
```

No network access is required or performed.

The audit runs the whole discovered test suite and therefore expects a
**Phase 3-only tree**. If a later phase (for example the parallel Phase 4 work
described above) has registered additional MCP tools, the Phase 2 parity test
still asserts the Phase 3 count of 92 and will fail for that later phase's
reason — not because Phase 3 regressed. For a clean Phase 3 verdict, run the
audit from a worktree pinned to `f239250` with only the Phase 3 changes applied.
The committed audit was produced that way.



---

## 15. Known limitations and blockers

1. The character is a procedural prototype assembled from primitives. It is not
   sculpted or production-ready art.
2. AO, emission and opacity maps are not generated; they are reported absent.
   Metallic is a constant, not a texture.
3. The normal map is derived from procedural height noise (Sobel), not authored
   or scanned surface detail.
4. Animations are short procedural keyframe clips, not authored performances.
5. No engine import was executed; engine compatibility is export-prepared and
   structurally validated only.
6. No AI image/texture/3D provider is configured or authorized. Meshy remains
   paid and unauthorized.
7. FBX internals are not parsed; only existence, size and hash are validated.
8. The repository started one commit ahead of the expected baseline (`f239250`
   vs `b628527`) because of pre-existing work; this is reported, not hidden.
9. Phase 4 environment work found in the working tree remains deferred and
   unvalidated under `validation/deferred-phase4/`.
