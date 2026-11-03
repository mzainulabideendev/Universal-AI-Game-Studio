# Testing, Profiling and Builds

## Evidence ladder

```
configured → implemented → compiles → unit tested → integration/Play tested → built → launched → verified
```

Never jump levels in a report. Each claim needs a command + output/artifact.

## Test matrix

| Layer | Unity | Unreal | Godot |
| --- | --- | --- | --- |
| Compile | `unity build`/editor compile, `dotnet build *.csproj` | `Build.bat` | `godot --headless --editor --quit` |
| Unit | EditMode NUnit | Automation Spec | GUT / headless script |
| Integration | PlayMode tests | Functional tests | Scene-run scripts |
| Smoke | launch player with `-logFile` | `-game -log` | run exported binary with `--verbose` |
| Platform | Windows/Android builds + device | Win64/Android package | export presets |

Zero discovered tests is a failed gate. Report test counts and pass/fail.

## Unity commands (verify flags with `--help`)

```powershell
unity test  "<project>" --mode EditMode --output "<out>\editmode.xml"
unity test  "<project>" --mode PlayMode --output "<out>\playmode.xml"
unity build "<project>" --target StandaloneWindows64 --output-path "<out>"
```

Assertions after each:

- XML exists, `failed="0"`, `total > 0`.
- Build output contains the expected `.exe`/`.apk`, with a fresh timestamp.
- Launch the player, wait for first frame, then read the log for
  `Exception`/`Error`/`NullReference`.

## Profiling

- Unity: Profiler (CPU/GPU/Memory), `ProfilerRecorder` in tests, Frame Debugger.
- Measure frame time at target resolution, not in the editor with vsync off by
  accident. Record avg/p95 frame time and GC alloc per frame.
- Common wins: batching, LOD, occlusion culling, texture compression, shadow
  distance, physics query rate, object pooling.

## Build hygiene

- Increment version/build number before release builds.
- Strip symbols/engine code appropriately; keep mapping files for crash triage.
- Verify bundle identifier, icons, splash, orientation, permissions.
- Android: target API within store policy, ARM64, keystore + signing verified,
  `apksigner verify --print-certs`.
- Windows: check dependencies ship (Mono/IL2CPP data, plugin DLLs), test on a
  clean path, verify graceful exit.
- Archive the build log and SHA-256 of the artifact.

## Reporting template

```
Build:        <path>
Size:         <MB>   SHA256: <hash>
Command:      <exact command>
Exit code:    0
Tests:        EditMode 42/42 passed; PlayMode 7/7 passed
Launch:       started PID 1234, first frame logged, 0 exceptions in 60 s
Limitations:  Android device not attached; on-device gate pending
```
