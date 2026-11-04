"""Game-engine adapters.

Only operations that can be executed by a real, installed tool are exposed as
automation. Everything else is reported as unimplemented or staged-only instead
of pretending to succeed.

State vocabulary used in this module
------------------------------------
``verified``     The tool was found and its version/status was probed.
``implemented``  The command is wired to documented CLI arguments but has not
                 been executed in this environment.
``staged``       Files were copied into the project, but the engine has not
                 imported them yet.
``unverified``   Requires an engine that is not installed here.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import time
import xml.etree.ElementTree as ET

from . import config
from .detect import detect_all, detect_engine_cli, detect_godot, detect_unity
from .projects import detect_project_engine, inspect_game_project
from .util import (
    ToolError,
    expand,
    now_iso,
    read_json,
    require_path,
    run_command,
    safe_join,
    sha256_file,
    write_json,
)

ENGINES = ("unity", "unreal", "godot")
DEFAULT_TIMEOUT = int(os.environ.get("GAME_STUDIO_ENGINE_TIMEOUT", "1800"))
STAGING_DIR = ".game-studio"


# --------------------------------------------------------------------------
# selection / availability
# --------------------------------------------------------------------------
def engine_state(engine: str) -> dict:
    engine = (engine or "").lower()
    if engine == "unity":
        return detect_unity()
    if engine == "unreal":
        from .detect import detect_unreal
        return detect_unreal()
    if engine == "godot":
        return detect_godot()
    raise ToolError(f"engine must be one of {list(ENGINES)}")


def list_available_engines() -> dict:
    detected = detect_all()
    engines = {}
    for engine in ENGINES:
        data = detected["tools"][engine]
        engines[engine] = {
            "state": data.get("state"),
            "installed": data.get("state") == "verified",
            "adapter": _adapter_summary(engine),
            "detection": data,
        }
    return {
        "ok": True,
        "engines": engines,
        "available": [e for e in ENGINES if engines[e]["installed"]],
        "unavailable": [e for e in ENGINES if not engines[e]["installed"]],
        "selected": {
            "engine": config.load_config().get("selected_engine"),
            "path": config.load_config().get("selected_engine_path"),
        },
        "note": "Installed means an executable was found. It does not prove a project "
                "builds or that the adapter has been exercised against that version.",
    }


def _adapter_summary(engine: str) -> dict:
    if engine == "unity":
        return {
            "project_inspection": "implemented",
            "asset_staging": "implemented",
            "import_verification": "meta-and-log",
            "batch_refresh": "implemented-unverified",
            "tests": "implemented-unverified",
            "build": "implemented-unverified",
            "editor_commands": "available-when-pipeline-package-present",
        }
    if engine == "godot":
        return {
            "project_inspection": "implemented",
            "asset_staging": "implemented",
            "import_verification": "import-cache",
            "batch_refresh": "implemented-unverified",
            "tests": "not-implemented (use GUT/gdUnit4 and your own runner)",
            "build": "implemented-unverified",
            "editor_commands": "not-implemented",
        }
    return {
        "project_inspection": "implemented",
        "asset_staging": "implemented",
        "import_verification": "not-possible-without-editor-automation",
        "batch_refresh": "not-implemented",
        "tests": "not-implemented",
        "build": "not-implemented",
        "editor_commands": "not-implemented",
        "limitation": "Unreal import/build automation is not wired. Assets are staged only; "
                      "use the Unreal Editor to import and verify them.",
    }


def select_engine(engine: str, *, engine_path: str | None = None,
                  persist: bool = True) -> dict:
    engine = (engine or "").lower()
    if engine not in ENGINES:
        raise ToolError(f"engine must be one of {list(ENGINES)}")
    state = engine_state(engine)
    if state.get("state") != "verified":
        raise ToolError(
            f"{engine} is not installed or could not be verified: {state.get('state')}"
        )
    selected_path = expand(engine_path) if engine_path else None
    if selected_path:
        if engine == "unity":
            if not os.path.isfile(selected_path):
                raise ToolError(f"Unity editor executable not found: {selected_path}")
        elif engine == "godot":
            if not os.path.isfile(selected_path):
                raise ToolError(f"Godot executable not found: {selected_path}")
        elif not os.path.isfile(selected_path):
            raise ToolError(f"UnrealEditor-Cmd executable not found: {selected_path}")
    updates = {"selected_engine": engine, "selected_engine_path": selected_path}
    key = {"unity": "unity_exe", "unreal": "unreal_editor_cmd", "godot": "godot_exe"}[engine]
    if selected_path:
        updates[key] = selected_path
    if persist:
        config.save_config(updates)
    return {"ok": True, "selected_engine": engine, "selected_engine_path": selected_path,
            "persisted": persist, "state": state}


# --------------------------------------------------------------------------
# capabilities
# --------------------------------------------------------------------------
def inspect_engine_capabilities(engine: str | None = None) -> dict:
    cfg = config.load_config()
    engine = (engine or cfg.get("selected_engine") or "unity").lower()
    if engine not in ENGINES:
        raise ToolError(f"engine must be one of {list(ENGINES)}")
    state = engine_state(engine)
    result: dict = {
        "ok": True,
        "engine": engine,
        "state": state.get("state"),
        "installed": state.get("state") == "verified",
        "adapter": _adapter_summary(engine),
        "notes": [],
    }
    if engine == "unity":
        cli = detect_engine_cli("unity")
        pipeline = _unity_pipeline_list() if cli else None
        result.update({
            "cli": cli,
            "pipeline": pipeline,
            "operations": {
                "inspect_project": True,
                "stage_asset": True,
                "verify_import": "checks for .meta files; a missing .meta means not imported",
                "batch_refresh": bool(cli),
                "run_tests": bool(cli),
                "build_player": bool(cli),
                "editor_commands": bool(pipeline and pipeline.get("pipeline_available")),
            },
        })
        if not pipeline or not pipeline.get("pipeline_available"):
            result["notes"].append(
                "Unity Pipeline package is not reported as available; editor command "
                "automation needs an open editor with the package installed."
            )
    elif engine == "godot":
        godot = detect_godot()
        exe = (godot.get("executables") or [{}])[0].get("path")
        result.update({
            "executable": exe,
            "operations": {
                "inspect_project": True,
                "stage_asset": True,
                "verify_import": "checks for .import file and .godot/imported cache",
                "batch_refresh": bool(exe),
                "run_tests": False,
                "build_player": bool(exe),
                "editor_commands": False,
            },
        })
        result["notes"].append(
            "Godot has no built-in test runner. Use GUT or gdUnit4 with your own CI command; "
            "this server does not simulate a test result."
        )
    else:
        result.update({
            "operations": {
                "inspect_project": True,
                "stage_asset": True,
                "verify_import": False,
                "batch_refresh": False,
                "run_tests": False,
                "build_player": False,
                "editor_commands": False,
            },
        })
        result["notes"].append(
            "Unreal automation is staged-only. Import and build must be performed and "
            "verified in the Unreal Editor until a tested automation path exists."
        )
    return result


def _unity_pipeline_list() -> dict:
    cli = detect_engine_cli("unity")
    if not cli:
        return {"available": False, "reason": "unity CLI not found"}
    result = run_command([cli, "pipeline", "list"], timeout=30)
    text = (result.get("stdout") or "").strip()
    available = False
    rows = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        rows.append(line)
        lowered = line.lower()
        if "\t" in line:
            columns = [c.strip() for c in line.split("\t")]
            if len(columns) > 4 and columns[4].lower() in ("true", "yes", "1"):
                available = True
    return {
        "available": result.get("ok", False),
        "pipeline_available": available,
        "raw": text[:4000],
        "rows": rows[:20],
    }


# --------------------------------------------------------------------------
# staging
# --------------------------------------------------------------------------
def stage_asset(source: str, project_path: str, *, engine: str | None = None,
                relative_path: str | None = None, confirm: bool = False,
                confirm_overwrite: bool = False) -> dict:
    """Copy an asset into an engine project and record provenance.

    This only stages files. It never claims the engine imported them.
    """
    if not confirm:
        raise ToolError("staging writes into a game project; pass confirm=true")
    source_path = require_path(source, label="source")
    project = require_path(project_path, kind="dir", label="project_path")
    detected = detect_project_engine(project)
    engine = (engine or detected or "").lower()
    if engine not in ENGINES:
        raise ToolError("could not determine the project engine; pass engine explicitly")
    if detected and detected != engine:
        raise ToolError(f"project looks like {detected}, not {engine}")
    if detected is None:
        raise ToolError(f"not a recognised {engine} project: {project}")

    name = os.path.basename(source_path.rstrip("\\/"))
    if engine == "unity":
        root = os.path.join(project, "Assets")
        default_relative = os.path.join("Imported", name)
    elif engine == "godot":
        root = project
        default_relative = os.path.join("imported", name)
    else:
        root = os.path.join(project, "Content")
        default_relative = os.path.join("Imported", name)
    if not os.path.isdir(root):
        raise ToolError(f"expected {engine} content folder does not exist: {root}")

    relative_path = relative_path or default_relative
    destination = safe_join(root, relative_path)
    if os.path.exists(destination):
        if not confirm_overwrite:
            raise ToolError(f"destination already exists (pass confirm_overwrite=true): {destination}")
        if os.path.isdir(destination):
            shutil.rmtree(destination)
        else:
            os.remove(destination)

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.isdir(source_path):
        shutil.copytree(source_path, destination)
        files = []
        for dirpath, _dirnames, filenames in os.walk(destination):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                files.append({
                    "path": os.path.relpath(full, project).replace("\\", "/"),
                    "bytes": os.path.getsize(full),
                })
        main_hash = None
    else:
        shutil.copy2(source_path, destination)
        files = [{
            "path": os.path.relpath(destination, project).replace("\\", "/"),
            "bytes": os.path.getsize(destination),
        }]
        main_hash = sha256_file(destination)

    record = {
        "schema_version": 1,
        "engine": engine,
        "project": project,
        "source": source_path,
        "destination": destination,
        "relative_path": os.path.relpath(destination, project).replace("\\", "/"),
        "staged_at": now_iso(),
        "source_sha256": main_hash,
        "files": files,
        "import_state": "staged-not-imported",
        "note": "Staged only. The engine must import the file; verify with "
                "verify_staged_import or by opening the project.",
    }
    manifest_path = _manifest_path(project, destination)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    write_json(manifest_path, record)
    config.audit("engine.stage_asset", tool="stage_asset",
                 details={"engine": engine, "destination": record["relative_path"]})
    record["manifest"] = manifest_path
    record["ok"] = True
    return record


def _manifest_path(project: str, destination: str) -> str:
    rel = os.path.relpath(destination, project).replace("\\", "/")
    safe = rel.replace("/", "__").replace(":", "_")
    return os.path.join(project, STAGING_DIR, "staging", safe + ".json")


def _find_manifest(project: str, relative_path: str) -> str | None:
    target = os.path.join(project, STAGING_DIR, "staging")
    if not os.path.isdir(target):
        return None
    wanted = relative_path.replace("\\", "/")
    for path in glob.glob(os.path.join(target, "*.json")):
        try:
            record = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("relative_path") == wanted:
            return path
    return None


def verify_staged_import(project_path: str, relative_path: str) -> dict:
    """Check real on-disk import evidence for a staged file."""
    project = require_path(project_path, kind="dir", label="project_path")
    engine = detect_project_engine(project)
    if engine is None:
        raise ToolError(f"not a recognised game project: {project}")
    if os.path.isabs(relative_path):
        raise ToolError("relative_path must be relative to the project")
    destination = safe_join(project, relative_path)
    if not os.path.exists(destination):
        return {"ok": False, "state": "missing", "path": destination,
                "error": "staged path no longer exists"}

    manifest_path = _find_manifest(project, relative_path)
    manifest = None
    if manifest_path:
        try:
            manifest = read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            manifest = None

    evidence: dict = {"engine": engine, "path": destination,
                      "relative_path": relative_path,
                      "manifest": manifest_path}
    state = "staged-not-imported"
    if engine == "unity":
        meta = destination + ".meta"
        evidence["meta_exists"] = os.path.isfile(meta)
        evidence["meta_modified"] = (time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(meta))
        ) if os.path.isfile(meta) else None)
        library = os.path.join(project, "Library")
        evidence["library_exists"] = os.path.isdir(library)
        if os.path.isfile(meta):
            state = "imported"
        elif not os.path.isdir(library):
            state = "project-not-imported"
    elif engine == "godot":
        import_file = destination + ".import"
        evidence["import_file_exists"] = os.path.isfile(import_file)
        evidence["import_cache_exists"] = os.path.isdir(os.path.join(project, ".godot", "imported"))
        if os.path.isfile(import_file) and evidence["import_cache_exists"]:
            state = "imported"
        elif not evidence["import_cache_exists"]:
            state = "project-not-imported"
    else:
        evidence["note"] = ("Unreal does not expose a filesystem import marker that can be "
                            "verified without the editor.")
        state = "staged-only"

    exists = os.path.isfile(destination)
    if exists and manifest and manifest.get("source_sha256"):
        current = sha256_file(destination)
        evidence["sha256"] = current
        evidence["source_sha256"] = manifest["source_sha256"]
        evidence["hash_matches_staged_source"] = current == manifest["source_sha256"]
    return {
        "ok": state in ("imported", "staged-only"),
        "state": state,
        "evidence": evidence,
        "note": "imported means the engine wrote its import marker; it does not prove the "
                "asset looks correct or works at runtime.",
    }


# --------------------------------------------------------------------------
# Unity
# --------------------------------------------------------------------------
def _unity_cli() -> str:
    cli = detect_engine_cli("unity")
    if not cli:
        raise ToolError("Unity CLI ('unity') was not found. Install Unity CLI or add it to PATH.")
    return cli


def unity_editor_status() -> dict:
    cli = _unity_cli()
    result = run_command([cli, "status", "--format", "json"], timeout=30)
    payload = None
    text = (result.get("stdout") or "").strip()
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    connected = bool(isinstance(payload, dict) and payload.get("success") is True
                     and (payload.get("data") or {}).get("count"))
    return {
        "ok": bool(result.get("ok")) and connected,
        "connected": connected,
        "editors": payload,
        "exit_code": result.get("exit_code"),
        "stderr": (result.get("stderr") or "").strip()[:2000],
        "note": "No connected editor means Editor Pipeline commands and import verification "
                "through the editor are unavailable; batch mode may still be usable.",
    }


def unity_list_commands(project_path: str) -> dict:
    cli = _unity_cli()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "unity":
        raise ToolError(f"not a Unity project: {project}")
    result = run_command([cli, "command", "--project-path", project, "--format", "json"],
                         timeout=45)
    payload = None
    text = (result.get("stdout") or "").strip()
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    return {
        "ok": bool(result.get("ok")),
        "connected": bool(isinstance(payload, dict) and payload.get("success") is True),
        "commands": payload,
        "raw": (text or result.get("stderr") or "")[:8000],
        "note": "Listing requires an open editor on this project with the Pipeline package.",
    }


def unity_run_command(project_path: str, command: str, arguments: list[str] | None = None,
                      *, confirm: bool = False, timeout: int = 300) -> dict:
    if not confirm:
        raise ToolError("Editor commands can modify the project; pass confirm=true")
    if not command:
        raise ToolError("command is required")
    cli = _unity_cli()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "unity":
        raise ToolError(f"not a Unity project: {project}")
    argv = [cli, "command", command, "--project-path", project, "--format", "json",
            "--timeout", str(max(5, min(timeout, 3600))), "--"]
    argv.extend(str(a) for a in (arguments or []))
    result = run_command(argv, timeout=timeout + 30)
    config.audit("unity.command", tool="unity_run_command",
                 details={"project": project, "command": command,
                          "arguments": list(arguments or [])})
    return {
        "ok": bool(result.get("ok")),
        "command": command,
        "exit_code": result.get("exit_code"),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "note": "Editor command output is reported verbatim; this server does not infer success "
                "beyond the CLI exit code.",
    }


def unity_batch_refresh(project_path: str, *, confirm: bool = False,
                        timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Trigger Unity's documented batch import with -quit."""
    if not confirm:
        raise ToolError("Batch refresh opens the project and may reimport assets; pass confirm=true")
    cli = _unity_cli()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "unity":
        raise ToolError(f"not a Unity project: {project}")
    log_path = os.path.join(project, "Logs", "game-studio-refresh.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    argv = [cli, "run", project, "--timeout", str(timeout), "--",
            "-quit", "-batchmode", "-nographics", "-logFile", log_path]
    started = time.time()
    result = run_command(argv, timeout=timeout + 60)
    config.audit("unity.batch_refresh", tool="unity_batch_refresh",
                 details={"project": project, "ok": bool(result.get("ok")),
                          "duration_ms": result.get("duration_ms")})
    return {
        "ok": bool(result.get("ok")),
        "exit_code": result.get("exit_code"),
        "timed_out": result.get("timed_out"),
        "duration_ms": int((time.time() - started) * 1000),
        "log_file": log_path if os.path.isfile(log_path) else None,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "note": "Unity import success is inferred from a zero exit code and a log without "
                "compilation errors. Read the log before treating assets as imported.",
    }


def unity_run_tests(project_path: str, *, mode: str = "EditMode",
                    test_filter: str | None = None, output: str | None = None,
                    confirm: bool = False, timeout: int = DEFAULT_TIMEOUT) -> dict:
    if not confirm:
        raise ToolError("Running tests launches the editor in batch mode; pass confirm=true")
    if mode not in ("EditMode", "PlayMode"):
        raise ToolError("mode must be EditMode or PlayMode")
    cli = _unity_cli()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "unity":
        raise ToolError(f"not a Unity project: {project}")
    report = os.path.abspath(expand(output)) if output else os.path.join(
        project, "Logs", f"game-studio-{mode}-results.xml")
    argv = [cli, "test", project, "--mode", mode, "--output", report,
            "--report-format", "nunit", "--timeout", str(timeout)]
    if test_filter:
        argv += ["--filter", test_filter]
    result = run_command(argv, timeout=timeout + 120)
    summary = _parse_nunit(report) if os.path.isfile(report) else None
    config.audit("unity.run_tests", tool="unity_run_tests",
                 details={"project": project, "mode": mode,
                          "ok": bool(result.get("ok")), "summary": summary})
    return {
        "ok": bool(result.get("ok")) and bool(summary and summary["failed"] == 0),
        "exit_code": result.get("exit_code"),
        "report": report if os.path.isfile(report) else None,
        "summary": summary,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "note": "A missing report means the run did not complete. Only report tests as passing "
                "when the report exists and failed == 0.",
    }


def _parse_nunit(path: str) -> dict:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return {"error": f"could not parse NUnit report: {exc}"}
    # Unity writes <test-run ... total=".." passed=".." failed="..">.
    if root.tag == "test-run":
        def number(name: str) -> int:
            try:
                return int(root.attrib.get(name, 0))
            except ValueError:
                return 0
        return {
            "total": number("total"),
            "passed": number("passed"),
            "failed": number("failed"),
            "skipped": number("skipped") or number("inconclusive"),
            "duration_seconds": root.attrib.get("duration"),
        }
    counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    for case in root.iter("test-case"):
        counts["total"] += 1
        result = (case.attrib.get("result") or "").lower()
        if result in ("passed", "success"):
            counts["passed"] += 1
        elif result in ("failed", "error"):
            counts["failed"] += 1
        else:
            counts["skipped"] += 1
    return counts


def unity_build(project_path: str, *, target: str, output_path: str,
                confirm: bool = False, timeout: int = DEFAULT_TIMEOUT,
                allow_dirty_build: bool = False) -> dict:
    if not confirm:
        raise ToolError("Building writes a player and opens the editor; pass confirm=true")
    if not target:
        raise ToolError("target is required, for example StandaloneWindows64")
    cli = _unity_cli()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "unity":
        raise ToolError(f"not a Unity project: {project}")
    destination = os.path.abspath(expand(output_path))
    log_path = os.path.join(project, "Logs", "game-studio-build.log")
    argv = [cli, "build", project, "--target", target, "--output-path", destination,
            "--log-file", log_path, "--no-tail", "--timeout", str(timeout)]
    if allow_dirty_build:
        argv.append("--allow-dirty-build")
    result = run_command(argv, timeout=timeout + 120)
    artifacts = []
    if os.path.isfile(destination):
        artifacts.append({"path": destination, "bytes": os.path.getsize(destination)})
    elif os.path.isdir(destination):
        for name in sorted(os.listdir(destination))[:200]:
            full = os.path.join(destination, name)
            if os.path.isfile(full):
                artifacts.append({"path": full, "bytes": os.path.getsize(full)})
    config.audit("unity.build", tool="unity_build",
                 details={"project": project, "target": target,
                          "ok": bool(result.get("ok")), "artifacts": len(artifacts)})
    return {
        "ok": bool(result.get("ok")) and bool(artifacts),
        "exit_code": result.get("exit_code"),
        "timed_out": result.get("timed_out"),
        "target": target,
        "output_path": destination,
        "artifacts": artifacts[:50],
        "log_file": log_path if os.path.isfile(log_path) else None,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "note": "A produced player is not evidence that the game runs correctly. Launch and "
                "test it, including the log for missing shaders or runtime exceptions.",
    }


# --------------------------------------------------------------------------
# Godot
# --------------------------------------------------------------------------
def _godot_exe() -> str:
    detected = detect_godot()
    for item in detected.get("executables") or []:
        if item.get("path"):
            return item["path"]
    raise ToolError("Godot executable was not found. Install Godot 4 or set godot_exe.")


def godot_batch_import(project_path: str, *, confirm: bool = False,
                       timeout: int = DEFAULT_TIMEOUT) -> dict:
    if not confirm:
        raise ToolError("Batch import writes the .godot cache; pass confirm=true")
    exe = _godot_exe()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "godot":
        raise ToolError(f"not a Godot project: {project}")
    log_path = os.path.join(project, STAGING_DIR, "logs", "godot-import.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    argv = [exe, "--headless", "--path", project, "--editor", "--quit"]
    result = run_command(argv, timeout=timeout)
    cache = os.path.join(project, ".godot", "imported")
    imports = glob.glob(os.path.join(project, "**", "*.import"), recursive=True)
    config.audit("godot.batch_import", tool="godot_batch_import",
                 details={"project": project, "ok": bool(result.get("ok"))})
    return {
        "ok": bool(result.get("ok")) and os.path.isdir(cache),
        "exit_code": result.get("exit_code"),
        "timed_out": result.get("timed_out"),
        "import_cache": cache if os.path.isdir(cache) else None,
        "import_files": len(imports),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "note": "Godot wrote import metadata if the cache exists. Open the project and inspect "
                "the asset before using it in a scene.",
    }


def godot_build(project_path: str, *, preset: str, output_path: str,
                confirm: bool = False, timeout: int = DEFAULT_TIMEOUT) -> dict:
    if not confirm:
        raise ToolError("Exporting writes a build; pass confirm=true")
    if not preset:
        raise ToolError("preset is required (a name from export_presets.cfg)")
    exe = _godot_exe()
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "godot":
        raise ToolError(f"not a Godot project: {project}")
    if not os.path.isfile(os.path.join(project, "export_presets.cfg")):
        raise ToolError("export_presets.cfg is missing; configure an export preset in Godot first")
    destination = os.path.abspath(expand(output_path))
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    argv = [exe, "--headless", "--path", project, "--export-release", preset, destination]
    start = time.time()
    result = run_command(argv, timeout=timeout)
    exists = os.path.exists(destination)
    config.audit("godot.build", tool="godot_build",
                 details={"project": project, "preset": preset, "ok": bool(result.get("ok"))})
    return {
        "ok": bool(result.get("ok")) and exists,
        "exit_code": result.get("exit_code"),
        "preset": preset,
        "output_path": destination,
        "artifact": ({"path": destination, "bytes": os.path.getsize(destination)}
                     if exists and os.path.isfile(destination) else None),
        "duration_ms": int((time.time() - start) * 1000),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "note": "Export success does not prove the build runs. Launch it and check the log.",
    }


# --------------------------------------------------------------------------
# Unreal
# --------------------------------------------------------------------------
def unreal_stage_only(project_path: str) -> dict:
    project = require_path(project_path, kind="dir", label="project_path")
    if detect_project_engine(project) != "unreal":
        raise ToolError(f"not an Unreal project: {project}")
    return {
        "ok": True,
        "engine": "unreal",
        "automation": "staged-only",
        "supported": ["inspect_project", "stage_asset"],
        "not_supported": ["import", "batch_refresh", "tests", "build"],
        "reason": "No tested UnrealEditor-Cmd automation path is implemented. Staging copies "
                  "files and provenance, nothing more.",
        "inspection": inspect_game_project(project),
    }


# --------------------------------------------------------------------------
# dispatcher
# --------------------------------------------------------------------------
def engine_build(engine: str, project_path: str, *, target: str | None = None,
                 output_path: str | None = None, confirm: bool = False,
                 preset: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    engine = (engine or "").lower()
    if engine == "unity":
        if not target or not output_path:
            raise ToolError("Unity builds require target and output_path")
        return unity_build(project_path, target=target, output_path=output_path,
                           confirm=confirm, timeout=timeout)
    if engine == "godot":
        if not preset or not output_path:
            raise ToolError("Godot builds require preset and output_path")
        return godot_build(project_path, preset=preset, output_path=output_path,
                           confirm=confirm, timeout=timeout)
    if engine == "unreal":
        return {"ok": False, "engine": "unreal", "state": "not-implemented",
                "error": "Unreal builds are not automated by this server.",
                "remediation": "Build and verify in Unreal Editor or UnrealBuildTool."}
    raise ToolError(f"engine must be one of {list(ENGINES)}")
