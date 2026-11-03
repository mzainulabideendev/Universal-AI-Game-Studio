# Art Direction, Audio and UI/UX

## Art direction

Define before producing assets:

- Style (stylised, realistic, low-poly, pixel), palette, shape language.
- Scale and proportion rules (character height vs door vs vehicle).
- Material language: roughness/metallic ranges, emissive usage.
- Lighting key (sun angle, contrast, fog), post-processing stack.
- Reference sheet of existing project assets to match.

Consistency beats raw fidelity. A coherent low-poly scene reads better than mixed
styles with high-resolution textures.

## 3D graphics checklist

- PBR materials with correct colour space (albedo sRGB, masks linear).
- Texture sizes appropriate to screen size and memory budget.
- Shadow cascades/distances tuned per quality tier.
- Baked GI where static; real-time GI only if budget allows.
- Reflection probes or SSR only where visible.
- Vegetation: density, wind, LOD, billboards at distance.
- Sky/fog gives depth; avoid washing out gameplay silhouettes.
- Particles: bounded counts, pooled, culled off-screen.
- LOD groups on hero assets; occlusion culling baked for dense scenes.
- Post-processing: bloom/vignette/colour grading applied with intent; verify in
  the running build, not just the Scene view.

## 2D graphics checklist

- Consistent sprite resolution and pivot conventions.
- Animation via sprite sheets or skeletal 2D; frame rate matched to game feel.
- Layering: background → parallax → gameplay → foreground → UI.
- Parallax speeds tied to camera, not frame rate.
- Readable silhouettes at gameplay zoom.
- Effects (hit sparks, dust) short, pooled, colour-coded.
- Pixel-perfect camera settings when using pixel art; avoid shimmering.

## Audio

- Bus structure: Master → Music / SFX / UI / Ambience.
- Music: loop points, intro/outro, ducking on menu/pause.
- Ambience per biome with crossfades.
- SFX pooled; one-shots stopped on disable/destroy.
- Spatial audio for 3D: 3D source, rolloff, doppler only where appropriate.
- Mix levels: gameplay-critical cues audible above music.
- Volume settings persist and drive the mixer.
- No audio that keeps playing after scene change, pause, or object destruction.

Licensing: record source and licence for every music/SFX file. Do not ship
unlicensed audio.

## UI/UX

- Hierarchy: Canvas/scaled with safe-area handling for mobile notches.
- Navigation: keyboard/gamepad focus order; pointer/touch targets ≥ 44 px.
- Every button has a real handler; disabled states reflect real availability.
- HUD values bound to the model, updated on change or at a throttled rate.
- Pause actually pauses (time scale or explicit state) and blocks gameplay input.
- Settings: resolution, quality, volume, sensitivity, invert Y, language if
  localised. Persist and apply on load.
- Feedback: hover/press/confirm/error states; loading indicator for async work.
- Accessibility: colour-blind-safe cues, subtitle size, reduced motion/flash,
  remappable controls where feasible.
- Test at 16:9, 21:9, 4:3 and a tall mobile aspect.

## Save/settings

- Versioned schema with migration.
- Atomic write (temp + replace).
- Validate on load; fall back safely on corrupt/outdated data.
- Never store secrets; never claim cloud sync without a tested backend.

## Screen acceptance

| Screen | Evidence required |
| --- | --- |
| Main menu | all buttons act, continue disabled without save |
| Settings | changes apply and persist across restart |
| HUD | values match live game state |
| Pause | gameplay halts, resume restores exact state |
| Results | score/progress match the completed run |
| Game over | restart returns to a clean state |
| Credits | real attributions/licences |
