"""Real, read-only detection of game-development software and projects.

Detection never installs anything. A finding is ``verified`` only when the
executable exists (and, where cheap, reports a version). A folder name alone is
reported as ``detected`` so callers can distinguish "installed" from "usable".
"""

from __future__ import annotations

import glob
import json
import os
import platform as platform_module
import shutil
import sys
import time
from pathlib import Path

from . import config
from .util import (
    command_version,
    expand,
    file_stats,
    first_existing,
    platform_name,
    run_command,
    sorted_subdirs,
    which_first,
)

SKIP_DIRS = {
    "$recycle.bin", "system volume information", "windows", "winsxs", "node_modules",
    "appdata", "library", "temp", "obj", "binaries", "intermediate", "saved",
    ".git", "__pycache__", "packages", "programdata", "recovery", "perflogs",
}

EXE_NAMES = {
    "blender": {
        "windows": ["blender.exe"],
        "macos": ["Blender"],
        "linux": ["blender"],
    },
    "godot": {
        "windows": ["Godot_v4.exe", "godot.exe", "Godot.exe"],
        "macos": ["Godot"],
        "linux": ["godot", "godot4", "godot3"],
    },
}


# --------------------------------------------------------------------------
# bounded filesystem search
# --------------------------------------------------------------------------
def search_for_files(names: list[str], roots: list[str], *, max_depth: int = 3,
                     budget_seconds: float = 12.0) -> list[str]:
    """Breadth-first, time-bounded search for file names under given roots."""
    matches: list[str] = []
    deadline = time.time() + budget_seconds
    wanted = {name.lower() for name in names}
    queue = [(os.path.abspath(root), 0) for root in roots if root and os.path.isdir(root)]
    visited: set[str] = set()
    while queue:
        if time.time() > deadline:
            break
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if time.time() > deadline:
                        break
                    try:
                        if entry.is_file() and entry.name.lower() in wanted:
                            matches.append(entry.path)
                        elif entry.is_dir() and depth < max_depth and \
                                entry.name.lower() not in SKIP_DIRS and \
                                not entry.name.startswith("."):
                            queue.append((entry.path, depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue
        if len(matches) >= 10:
            break
    return matches


# --------------------------------------------------------------------------
# hardware
# --------------------------------------------------------------------------
def _windows_hardware() -> dict:
    script = (
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$cs=Get-CimInstance Win32_ComputerSystem;"
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "$gpu=@(Get-CimInstance Win32_VideoController | ForEach-Object {"
        "[pscustomobject]@{name=$_.Name;driver=$_.DriverVersion;adapterRamMB="
        "if($_.AdapterRAM){[math]::Round($_.AdapterRAM/1MB)}else{$null}}});"
        "[pscustomobject]@{os=$os.Caption;osVersion=$os.Version;"
        "cpu=$cpu.Name;ramGB=[math]::Round($cs.TotalPhysicalMemory/1GB,1);gpus=$gpu}"
        "|ConvertTo-Json -Compress"
    )
    result = run_command(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=30)
    data: dict = {}
    if result.get("ok"):
        try:
            data = json.loads((result.get("stdout") or "").strip() or "{}")
        except json.JSONDecodeError:
            data = {}
    gpus = data.get("gpus") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    return {
        "os": data.get("os") or platform_module.platform(),
        "os_version": data.get("osVersion") or platform_module.version(),
        "cpu": (data.get("cpu") or platform_module.processor() or "unknown").strip(),
        "ram_gb": data.get("ramGB"),
        "gpus": gpus,
    }


def _posix_hardware() -> dict:
    gpus: list[dict] = []
    if sys.platform == "linux":
        try:
            for card in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
                vendor_path = card
                device_path = os.path.join(os.path.dirname(card), "device")
                vendor = open(vendor_path, encoding="utf-8").read().strip()
                device = open(device_path, encoding="utf-8").read().strip()
                gpus.append({"vendor_id": vendor, "device_id": device})
        except OSError:
            pass
    elif sys.platform == "darwin":
        result = run_command(["system_profiler", "SPDisplaysDataType", "-json"], timeout=30)
        if result.get("ok"):
            try:
                payload = json.loads(result.get("stdout") or "{}")
                for item in payload.get("SPDisplaysDataType", []):
                    gpus.append({"name": item.get("sppci_model"), "vendor": item.get("spdisplays_vendor")})
            except (json.JSONDecodeError, AttributeError):
                pass
    return {
        "os": platform_module.platform(),
        "os_version": platform_module.release(),
        "cpu": platform_module.processor() or platform_module.machine(),
        "ram_gb": None,
        "gpus": gpus,
    }


def _memory_gb() -> float | None:
    try:
        import ctypes
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullTotalPhys / (1024 ** 3), 1)
        elif sys.platform == "linux":
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return round(int(line.split()[1]) / (1024 ** 2), 1)
    except Exception:
        return None
    return None


def inspect_system() -> dict:
    base = _windows_hardware() if os.name == "nt" else _posix_hardware()
    if base.get("ram_gb") is None:
        base["ram_gb"] = _memory_gb()
    disks = []
    seen = set()
    for candidate in (os.path.abspath(os.sep), Path.home().anchor or os.path.abspath(os.sep)):
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            usage = shutil.disk_usage(candidate)
            disks.append({
                "path": candidate,
                "free_gb": round(usage.free / (1024 ** 3), 1),
                "total_gb": round(usage.total / (1024 ** 3), 1),
            })
        except OSError:
            continue
    if os.name == "nt":
        for drive in "CDEFGH":
            root = f"{drive}:\\"
            if root in seen or not os.path.isdir(root):
                continue
            try:
                usage = shutil.disk_usage(root)
                disks.append({
                    "path": root,
                    "free_gb": round(usage.free / (1024 ** 3), 1),
                    "total_gb": round(usage.total / (1024 ** 3), 1),
                })
            except OSError:
                continue
    base.update({
        "platform": platform_name(),
        "machine": platform_module.machine(),
        "python": platform_module.python_version(),
        "logical_cores": os.cpu_count(),
        "disks": disks,
    })
    return base


# --------------------------------------------------------------------------
# installations
# --------------------------------------------------------------------------
def unity_editor_roots() -> list[str]:
    roots = []
    env = os.environ
    if os.name == "nt":
        for base in (env.get("ProgramFiles"), env.get("ProgramFiles(x86)")):
            if base:
                roots += [os.path.join(base, "Unity", "Hub", "Editor"),
                          os.path.join(base, "Unity", "Editor")]
        roots += [r"D:\Unity\Hub\Editor", r"C:\Unity\Hub\Editor"]
    elif sys.platform == "darwin":
        roots += ["/Applications/Unity/Hub/Editor", "/Applications/Unity"]
    else:
        roots += ["~/Unity/Hub/Editor", "/opt/unity/editors", "/opt/Unity/Editor"]
    return [expand(r) for r in roots if expand(r) and os.path.isdir(expand(r))]


def unity_executable(version_dir: str) -> str | None:
    return first_existing([
        os.path.join(version_dir, "Editor", "Unity.exe"),
        os.path.join(version_dir, "Unity.exe"),
        os.path.join(version_dir, "Unity.app", "Contents", "MacOS", "Unity"),
        os.path.join(version_dir, "Editor", "Unity"),
    ])


def detect_unity(config_data: dict | None = None) -> dict:
    cfg = config_data or config.load_config()
    editors = []
    roots = unity_editor_roots()
    override = cfg.get("unity_exe")
    if override and os.path.isfile(override):
        editors.append({
            "version": os.path.basename(os.path.dirname(os.path.dirname(override))) or "custom",
            "path": override,
            "state": "verified",
            "version_source": "configured path",
            "root": os.path.dirname(override),
        })
    for root in roots:
        for version_dir in sorted_subdirs(root):
            exe = unity_executable(version_dir)
            name = os.path.basename(version_dir.rstrip("\\/"))
            if not exe:
                editors.append({
                    "version": name, "path": None, "state": "broken",
                    "version_source": "install folder",
                    "root": version_dir,
                    "evidence": "version folder exists but no Unity executable found",
                })
                continue
            playback = os.path.join(version_dir, "Editor", "Data", "PlaybackEngines")
            modules = [os.path.basename(p) for p in sorted_subdirs(playback)] if os.path.isdir(playback) else []
            editors.append({
                "version": name,
                "path": exe,
                "state": "verified",
                "version_source": "install folder name",
                "root": version_dir,
                "modules": modules,
                "evidence": "Unity executable present",
            })
    # De-duplicate by real path.
    unique = {}
    for editor in editors:
        key = os.path.normcase(editor.get("path") or editor.get("root") or "")
        unique.setdefault(key, editor)
    editors = list(unique.values())
    cli = which_first(
        ["unity"],
        [
            expand(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Unity", "bin", "unity.exe")),
            expand(os.path.join(os.environ.get("ProgramFiles", ""), "Unity", "bin", "unity.exe")),
        ],
    )
    cli_version = command_version([cli, "--version"], timeout=25) if cli else None
    return {
        "state": "verified" if any(e["state"] == "verified" for e in editors) else
                 ("broken" if editors else "not-found"),
        "editors": editors,
        "roots_scanned": roots,
        "cli": {"path": cli, "version": cli_version} if cli else None,
    }


def detect_unreal(config_data: dict | None = None) -> dict:
    cfg = config_data or config.load_config()
    roots = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), "D:\\Epic Games", "C:\\Epic Games",
                     "D:\\Program Files\\Epic Games"):
            if base:
                roots.append(expand(os.path.join(base, "Epic Games")) if os.path.isdir(expand(os.path.join(base, "Epic Games"))) else None)
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\EpicGames\Unreal Engine") as key:
                        index = 0
                        while True:
                            try:
                                name = winreg.EnumKey(key, index)
                            except OSError:
                                break
                            index += 1
                            try:
                                with winreg.OpenKey(key, name) as sub:
                                    location, _ = winreg.QueryValueEx(sub, "InstalledDirectory")
                                    roots.append(location)
                            except OSError:
                                continue
                except OSError:
                    continue
        except ImportError:
            pass
    elif sys.platform == "darwin":
        roots.append("/Users/Shared/Epic Games")
    else:
        roots += [expand("~/UnrealEngine"), expand("~/Epic Games")]
    roots = sorted({r for r in roots if r and os.path.isdir(r)})
    installs = []
    for root in roots:
        candidates = [d for d in sorted_subdirs(root) if os.path.basename(d).startswith("UE_")]
        if os.path.basename(root) == "UnrealEngine":
            candidates.append(root)
        for install in candidates:
            cmd = first_existing([
                os.path.join(install, "Engine", "Binaries", "Win64", "UnrealEditor-Cmd.exe"),
                os.path.join(install, "Engine", "Binaries", "Mac", "UnrealEditor-Cmd"),
                os.path.join(install, "Engine", "Binaries", "Linux", "UnrealEditor-Cmd"),
            ])
            installs.append({
                "version": os.path.basename(install),
                "path": cmd,
                "root": install,
                "state": "verified" if cmd else "broken",
                "evidence": "UnrealEditor-Cmd present" if cmd else "engine folder without UnrealEditor-Cmd",
            })
    override = cfg.get("unreal_editor_cmd")
    if override and os.path.isfile(override):
        installs.append({"version": "configured", "path": override, "root": os.path.dirname(override),
                         "state": "verified", "evidence": "configured path"})
    return {"state": "verified" if installs and any(i["state"] == "verified" for i in installs)
            else ("broken" if installs else "not-found"),
            "installs": installs, "roots_scanned": roots}


def detect_godot(config_data: dict | None = None) -> dict:
    cfg = config_data or config.load_config()
    candidates = [
        cfg.get("godot_exe"),
        which_first(EXE_NAMES["godot"][platform_name()]),
    ]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            candidates += glob.glob(os.path.join(base, "Godot", "**", "Godot*.exe"), recursive=True)[:10]
            candidates += glob.glob(os.path.join(base, "Programs", "Godot", "**", "Godot*.exe"), recursive=True)[:10]
        candidates += [r"D:\Godot\Godot_v4.exe"]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Godot.app/Contents/MacOS/Godot"]
    else:
        candidates += ["/usr/bin/godot", "/usr/local/bin/godot", "/snap/bin/godot",
                       expand("~/Applications/Godot")]
    found = first_existing([c for c in candidates if c])
    if not found:
        # A short bounded search prevents a full-disk crawl.
        roots = [os.environ.get("ProgramFiles"), "D:\\"] if os.name == "nt" else [str(Path.home())]
        hits = search_for_files(EXE_NAMES["godot"][platform_name()], [r for r in roots if r],
                                max_depth=2, budget_seconds=6)
        found = hits[0] if hits else None
    if not found:
        return {"state": "not-found", "executables": []}
    version = command_version([found, "--version"], timeout=20)
    return {"state": "verified" if version else "detected",
            "executables": [{"path": found, "version": version,
                             "state": "verified" if version else "detected"}]}


def detect_blender(config_data: dict | None = None) -> dict:
    cfg = config_data or config.load_config()
    candidates = [cfg.get("blender_exe"), os.environ.get("BLENDER_EXE"),
                  which_first(EXE_NAMES["blender"][platform_name()])]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidates += glob.glob(os.path.join(base, "Blender Foundation", "*", "blender.exe"))
        candidates += [r"D:\blender data\blender.exe"]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Blender.app/Contents/MacOS/Blender"]
    else:
        candidates += ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"]
    found = first_existing([c for c in candidates if c])
    if not found:
        roots = []
        if os.name == "nt":
            roots = [os.environ.get("ProgramFiles"), "D:\\", "C:\\"]
        hits = search_for_files(EXE_NAMES["blender"][platform_name()],
                                [r for r in roots if r], max_depth=3, budget_seconds=12)
        found = hits[0] if hits else None
    if not found:
        return {"state": "not-found", "executables": []}
    version = command_version([found, "--version"], timeout=30)
    return {"state": "verified" if version else "detected",
            "executables": [{"path": found, "version": version,
                             "state": "verified" if version else "detected"}]}


def detect_toolchains() -> dict:
    findings = []
    specs = [
        ("Python", ["python", "python3"], ["--version"], "toolchain"),
        ("Node.js", ["node"], ["--version"], "toolchain"),
        ("Git", ["git"], ["--version"], "toolchain"),
        ("Git LFS", ["git"], ["lfs", "version"], "toolchain"),
        ("Java", ["java"], ["-version"], "toolchain"),
        (".NET SDK", ["dotnet"], ["--list-sdks"], "toolchain"),
    ]
    for name, names, args, category in specs:
        path = which_first(names)
        version = command_version([path] + args, timeout=20) if path else None
        findings.append({
            "name": name, "category": category, "path": path,
            "version": version,
            "state": "verified" if path and version else ("broken" if path else "not-found"),
        })
    ide = None
    if os.name == "nt":
        vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                               "Microsoft Visual Studio", "Installer", "vswhere.exe")
        if os.path.isfile(vswhere):
            result = run_command([vswhere, "-products", "*", "-format", "json"], timeout=25)
            if result.get("ok"):
                try:
                    for item in json.loads(result.get("stdout") or "[]"):
                        findings.append({
                            "name": item.get("displayName") or "Visual Studio",
                            "category": "ide",
                            "path": item.get("productPath"),
                            "version": item.get("installationVersion"),
                            "state": "verified",
                        })
                except json.JSONDecodeError:
                    pass
    code = which_first(["code"], [os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                               "Programs", "Microsoft VS Code", "Code.exe")])
    if code:
        ide = {"name": "Visual Studio Code", "path": code,
               "version": command_version([code, "--version"], timeout=20),
               "state": "verified"}
        findings.append(ide)
    return {"findings": findings}


def detect_engine_cli(engine: str) -> str | None:
    """Return the version-independent CLI used to drive an engine, if present."""
    engine = (engine or "").lower()
    if engine == "unity":
        return which_first(
            ["unity"],
            [
                expand(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Unity", "bin", "unity.exe")),
                expand(os.path.join(os.environ.get("ProgramFiles", ""), "Unity", "bin", "unity.exe")),
            ],
        )
    if engine == "godot":
        detected = detect_godot()
        executables = detected.get("executables") or []
        return executables[0]["path"] if executables else None
    if engine == "unreal":
        detected = detect_unreal()
        installs = detected.get("installs") or []
        for install in installs:
            if install.get("path") and install.get("state") == "verified":
                return install["path"]
        return None
    return None


def detect_meshy() -> dict:
    from . import secrets
    source = secrets.meshy_key_source()
    if not source:
        return {"state": "not-configured",
                "reason": "No Meshy API key is configured",
                "setup_tool": "meshy_setup_guide",
                "configure_options": [
                    "Set MESHY_API_KEY in the MCP server environment, then reconnect.",
                    "Call meshy_configure_api_key with confirm=true to validate and save "
                    "the key in the studio's private config directory.",
                ]}
    return {"state": "configured", "source": source,
            "reason": f"Meshy API key is present via {source} (not echoed)"}


def detect_sketchfab() -> dict:
    token = os.environ.get("SKETCHFAB_TOKEN", "").strip()
    if not token:
        return {"state": "not-configured", "reason": "SKETCHFAB_TOKEN is not set"}
    return {"state": "configured", "reason": "SKETCHFAB_TOKEN is present (not echoed)"}


def detect_all(*, include_license_tools: bool = True) -> dict:
    cfg = config.load_config()
    system = inspect_system()
    tools = {
        "blender": detect_blender(cfg),
        "unity": detect_unity(cfg),
        "unreal": detect_unreal(cfg),
        "godot": detect_godot(cfg),
        "toolchains": detect_toolchains(),
        "meshy": detect_meshy(),
        "sketchfab": detect_sketchfab(),
    }
    summary = {
        "blender": tools["blender"]["state"],
        "unity": tools["unity"]["state"],
        "unreal": tools["unreal"]["state"],
        "godot": tools["godot"]["state"],
        "meshy": tools["meshy"]["state"],
    }
    return {
        "ok": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform_name(),
        "system": system,
        "tools": tools,
        "summary": summary,
        "notes": [
            "verified = executable found and version probed where safe",
            "detected = executable found but version could not be probed",
            "Engine installs do not prove a specific project is configured; use inspect_game_project.",
        ],
    }


# --------------------------------------------------------------------------
# project discovery
# --------------------------------------------------------------------------
def _looks_like_project(directory: str) -> str | None:
    if os.path.isfile(os.path.join(directory, "ProjectSettings", "ProjectVersion.txt")):
        return "unity"
    if os.path.isfile(os.path.join(directory, "project.godot")):
        return "godot"
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(".uproject"):
                    return "unreal"
    except OSError:
        pass
    return None


def discover_projects(roots: list[str] | None = None, *, max_depth: int = 4,
                      budget_seconds: float = 20.0) -> list[dict]:
    cfg = config.load_config()
    roots = [expand(r) for r in (roots or cfg.get("project_roots") or []) if expand(r)]
    roots = [r for r in roots if os.path.isdir(r)]
    deadline = time.time() + budget_seconds
    queue = [(root, 0) for root in roots]
    visited: set[str] = set()
    projects = []
    while queue and time.time() < deadline:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        kind = _looks_like_project(current)
        if kind:
            projects.append({"path": current, "engine": kind,
                             "name": os.path.basename(current)})
            continue  # do not descend into a project
        if depth >= max_depth:
            continue
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir() and entry.name.lower() not in SKIP_DIRS and \
                                not entry.name.startswith("."):
                            queue.append((entry.path, depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue
    projects.sort(key=lambda p: p["path"].lower())
    return projects


def detect_game_engines(*, discover: bool = True, roots: list[str] | None = None) -> dict:
    cfg = config.load_config()
    engines = {
        "unity": detect_unity(cfg),
        "unreal": detect_unreal(cfg),
        "godot": detect_godot(cfg),
    }
    projects = discover_projects(roots) if discover else []
    available = [name for name, data in engines.items() if data["state"] == "verified"]
    return {
        "ok": True,
        "engines": engines,
        "available_engines": available,
        "unavailable_engines": [name for name in engines if name not in available],
        "projects": projects,
        "selected": {
            "engine": cfg.get("selected_engine"),
            "path": cfg.get("selected_engine_path"),
        },
        "project_roots": cfg.get("project_roots"),
        "capability_note": "Adapters are exposed only for engines whose executable was found. "
                           "See inspect_engine_capabilities for what the adapter can actually do.",
    }
