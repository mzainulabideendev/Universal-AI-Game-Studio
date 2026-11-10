# V6 Phase 5 — Independent Build Identity Verification

**Verdict: PASS**

The reported identical SHA-256 is correct, but it does **not** mean the V6
executable was copied, reused from V5, or misreported. The two `.exe` files are
byte-identical because each is the same generic Unity 6000.6.2f1 Windows player
launcher stub. All game content lives in the `*_Data` folders, and those payloads
are demonstrably different. The V6 executable was built from
`validation/unity-jungle-v6`, contains the Phase 5 gameplay implementation, and
ran a fresh real playthrough during this verification.

## 1. Executable identity

| Item | V5 | V6 Phase 5 |
|---|---|---|
| Path | `validation/builds/v5-windows/JungleMonkey.exe` | `validation/builds/v6-windows/V6JungleMonkey.exe` |
| Exists | Yes | Yes |
| Size | 667,136 bytes | 667,136 bytes |
| SHA-256 (recalculated) | `af88b840e599661ac63fc10ae27ac77dd97cd46b44df8a7ce60eb0dcfacfc99e` | `af88b840e599661ac63fc10ae27ac77dd97cd46b44df8a7ce60eb0dcfacfc99e` |
| Modified (UTC) | 2026-11-06T04:27:09Z | 2026-11-09T04:38:56Z |
| Byte comparison (`fc /b`) | — | **No differences encountered** |

The originally reported V6 hash is accurate. The files really are identical at
the launcher level.

## 2. Why identical launchers are expected

A Unity StandaloneWindows64 `.exe` is a small launcher stub generated from the
Unity player package. Both builds used the same editor version
(`6000.6.2f1`, changeset `770e33f6875c`) and the same target
(`StandaloneWindows64`), so the stub bytes are identical.

Unity also reuses an existing launcher when it is unchanged and rewrites only
the data files. That behavior is visible in both builds:

| Build | Launcher timestamp | Final payload timestamp |
|---|---|---|
| V5 | 2026-11-06T04:27:09Z | 2026-11-06T04:31:06Z (`boot.config`) |
| V6 | 2026-11-09T04:38:56Z | 2026-11-09T04:50:44Z (`level0`), 04:56:33Z (`boot.config`) |

The final V6 build log even states `Not rebuilding Data files -- no changes`,
while still reporting success.

## 3. Payload comparison — the builds are different

| File | V5 | V6 |
|---|---|---|
| `app.info` | 41 bytes, `V5 Jungle Monkey` | 41 bytes, `V6 Jungle Monkey` |
| `boot.config` build GUID | `54f68ea4831f41308cee30dc110733d3` | `1f24c50c14ec4af68961bafbacf9a7c2` |
| `level0` | 16,508 bytes, `9c76347e…a7d79` | 206,984 bytes, `ce141a06…b687` |
| `sharedassets0.assets` | 381,460 bytes, `11cf231a…d007` | 1,840,820 bytes, `08e5fd84…70bd` |
| Runtime assembly | `V5.Runtime.dll`, 14,336 bytes, `219cf981…0caae` | `V6.Runtime.dll`, 64,512 bytes, `cff6c4a4…601c` |
| Total build size | 97,397,842 bytes | 99,723,790 bytes |

Every game-content file differs.

## 4. Build provenance

The V6 build log
(`validation/unity-jungle-v6/Logs/build-windows-final2.log`) records:

```
Unity.exe -batchmode -nographics
  -projectPath D:\MCP\MCP\validation\unity-jungle-v6
  -executeMethod V6.EditorTools.V6Build.BuildWindows
  -quit
  -logFile D:\MCP\MCP\validation\unity-jungle-v6\Logs\build-windows-final2.log
```

Result: `Succeeded`, 0 errors, 16 warnings, output
`D:\MCP\MCP\validation\builds\v6-windows\V6JungleMonkey.exe`, total size
99,723,790 bytes, Unity `6000.6.2f1`.

`ProjectSettings/EditorBuildSettings.asset` for the V6 project lists exactly one
scene: `Assets/V6/Scenes/JungleMonkeyV6.unity` (379,627 bytes, SHA-256
`b35ab31f…220e`).

The V5 build is separately evidenced by `validation/builds/v5-build.json`
(`Succeeded`, 0 errors, 1 warning, output `…\v5-windows\JungleMonkey.exe`,
97,397,842 bytes) and by
`validation/unity-jungle-v5/.game-studio/evidence/source/unity-player-build.provenance.json`.

## 5. The V6 payload really contains Phase 5

Independent string extraction from the shipped binaries found:

**`V6.Runtime.dll`** — `PlayerMovement`, `CollectibleManager`, `AutoPlayDriver`,
`LevelManager`, `GameStateController`, `ObjectiveManager`, `UIManager`,
`DestinationZone`, `CheckpointManager`. It also embeds the PDB path:

```
D:\MCP\MCP\validation\unity-jungle-v6\Library\Bee\artifacts\1900b0aP.dag\V6.Runtime.pdb
```

**V6 `level0`** — `JungleEnvironment`, `DestinationAnchor`, `BANANAS  0 / 10`,
`BananaText`, `Banana_00`, `Banana_01`, `Checkpoint_00`, `Checkpoint_01`,
`Checkpoints`, `SPAWN_PLAYER`, `Mouse: orbit camera`.

**V5 for comparison** — `V5.Runtime.dll` contains only the V5 demo driver and
none of the V6 gameplay types; its embedded PDB path points at
`validation/unity-jungle-v5`. V5 `level0` lacks `DestinationAnchor` and the
checkpoint markers.

## 6. Fresh runtime test

The V6 executable was started as an independent fresh process:

```
V6JungleMonkey.exe -v6autoplay -v6seconds 30
  -v6capture reports\v6-build-identity-captures
  -v6perf reports\v6-phase5-build-identity-perf.json
  -logFile reports\v6-phase5-build-identity-player.log
```

Result: exit code 0. The log shows real scene validation, a live playthrough,
checkpoint progression, level completion and a clean quit:

- `V6_SCENE_VALID {"passed":true,"issues":[],"collectibles":10,...}`
- `[V6] Checkpoint 0 reached`
- `[V6] Checkpoint 1 reached`
- level-complete screenshot captured
- `[V6] AutoPlay finished; quitting`
- `[V6] GameManager initialized bananas=10 spawn=(0.00, 3.80, 48.00)`

Performance snapshot (1280×720, Ultra): 1,286 frames over 24.39 s, average
52.73 FPS, p95 frame 16.71 ms, 1% low 4.15 FPS, captured
2026-11-09T05:21:46Z.

Fresh screenshots (new directory, new timestamps and hashes):

| Capture | Bytes | SHA-256 |
|---|---|---|
| `reports/v6-build-identity-captures/01-main-menu.png` | 368,372 | `5656e06d…ac20c` |
| `reports/v6-build-identity-captures/02-playing.png` | 349,014 | `d348643e…94440` |
| `reports/v6-build-identity-captures/03-paused.png` | 259,120 | `b9f0be6a…201ba` |
| `reports/v6-build-identity-captures/04-level-complete.png` | 142,811 | `893c0363…68b1e` |

The `02-playing.png` capture shows the V6 UI (`BANANAS 1 / 10`,
`OBJECTIVE Bananas 1/10 · Reach the ruins`), the player character, banana
collectibles and the jungle environment.

## 7. V5 preservation

All 15 protected artifacts from `reports/v6-phase0-baseline.json` were re-hashed
and match exactly: 13 V5 artifacts and both V4 test files. The V5 executable is
still 667,136 bytes with SHA-256 `af88b840…c99e`, and every V5 document,
scene, evidence file and build artifact is unchanged.

## 8. Conclusion

| Check | Result |
|---|---|
| Both executables exist | PASS |
| SHA-256 independently recalculated | PASS — identical, correctly reported |
| Byte-for-byte comparison | PASS — identical |
| Build logs and timestamps inspected | PASS |
| V6 build produced from `validation/unity-jungle-v6` | PASS |
| Scene and gameplay assets inspected | PASS |
| V6 contains Phase 5 gameplay | PASS |
| V6 executable runs a real gameplay test | PASS |
| Fresh screenshots captured | PASS |
| V5 and protected artifacts unchanged | PASS |

**No wrong executable was copied or reused.** The shared hash is the expected
Unity launcher stub; V6 is a separate, genuine Phase 5 build.

## Limitations

- Automated playthrough, not a human playtest.
- Draw-call reporting was unavailable (`-1`).
- First-run sample includes a multi-second shader compilation hitch.
- No files were committed, pushed, tagged, installed or downloaded; no V5 file
  was overwritten; no paid API calls were made.
