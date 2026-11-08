"""Tracked, cancellable long-running operations.

Every operation gets a persisted record under
``GAME_STUDIO_HOME/operations/<id>.json`` so cancellation survives an agent
restart. Subprocesses are launched with ``Popen`` (never a shell), their PID is
recorded, and cancellation kills the whole process tree.

Honest limitations that are always reported instead of hidden:

* A killed local process is confirmed by the operating system.
* A timed-out local process is not proof that remote work stopped.
* Remote providers (Meshy, LLM APIs) are only reported cancelled when the
  provider itself confirms it; this module never invents that confirmation.
* Blender is a local process, so killing it does stop the local job, but files
  it was writing may be left partial. The caller is told that cleanup is needed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone

from . import config
from .util import ToolError, now_iso, read_json, truncate, write_json

OPERATIONS_DIRNAME = "operations"
MAX_RECORDS = 400
TERMINAL = ("completed", "failed", "cancelled", "timed-out", "interrupted")
ACTIVE = ("starting", "running", "cancelling")

_lock = threading.RLock()
_processes: dict[str, subprocess.Popen] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def operations_dir() -> str:
    path = os.path.join(config.config_dir(), OPERATIONS_DIRNAME)
    os.makedirs(path, exist_ok=True)
    return path


def _path(operation_id: str) -> str:
    if not operation_id or not all(ch.isalnum() or ch in "-_" for ch in operation_id):
        raise ToolError("invalid operation id")
    return os.path.join(operations_dir(), f"{operation_id}.json")


def _read(operation_id: str) -> dict:
    path = _path(operation_id)
    if not os.path.isfile(path):
        raise ToolError(f"unknown operation: {operation_id}")
    try:
        payload = read_json(path)
    except (OSError, ValueError) as exc:
        raise ToolError(f"operation record is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ToolError("operation record is malformed")
    return payload


def _write(payload: dict) -> dict:
    payload["schema_version"] = 1
    payload["updated_at"] = _now()
    write_json(_path(payload["id"]), payload)
    return payload


def start_operation(kind: str, label: str, *, metadata: dict | None = None,
                    timeout_seconds: float | None = None) -> dict:
    """Create a persisted operation record before doing any real work."""
    with _lock:
        operation_id = f"op-{uuid.uuid4().hex[:16]}"
        record = {
            "id": operation_id,
            "kind": str(kind)[:80],
            "label": str(label)[:400],
            "state": "starting",
            "pid": None,
            "command": None,
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "finished_at": None,
            "timeout_seconds": timeout_seconds,
            "cancel_requested_at": None,
            "cancel_confirmed": False,
            "remote_cancel": {
                "supported": False,
                "confirmed": False,
                "note": "remote cancellation is never claimed without provider confirmation",
            },
            "metadata": metadata or {},
            "result": None,
        }
        _write(record)
        _prune()
        return record


def get_operation(operation_id: str) -> dict:
    with _lock:
        return _read(operation_id)


def list_operations(*, limit: int = 50, include_terminal: bool = True) -> dict:
    directory = operations_dir()
    records = []
    for name in os.listdir(directory):
        if not name.endswith(".json"):
            continue
        try:
            payload = read_json(os.path.join(directory, name))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if not include_terminal and payload.get("state") in TERMINAL:
            continue
        records.append(payload)
    records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {
        "ok": True,
        "count": len(records[:limit]),
        "total": len(records),
        "operations": records[:limit],
        "directory": directory,
    }


def _prune() -> None:
    """Bound the registry; never delete active records."""
    directory = operations_dir()
    names = [name for name in os.listdir(directory) if name.endswith(".json")]
    if len(names) <= MAX_RECORDS:
        return
    entries = []
    for name in names:
        path = os.path.join(directory, name)
        try:
            entries.append((os.path.getmtime(path), path))
        except OSError:
            continue
    entries.sort()
    for _, path in entries[:max(0, len(entries) - MAX_RECORDS)]:
        try:
            payload = read_json(path)
            if isinstance(payload, dict) and payload.get("state") in ACTIVE:
                continue
            os.remove(path)
        except (OSError, ValueError):
            pass


def _update(operation_id: str, **changes) -> dict:
    with _lock:
        record = _read(operation_id)
        record.update(changes)
        return _write(record)


def finish_operation(operation_id: str, result: dict, *, state: str | None = None) -> dict:
    """Attach a caller-produced result to a cooperative operation."""
    if state is None:
        if result.get("cancelled"):
            state = "cancelled"
        elif result.get("ok"):
            state = "completed"
        else:
            state = "failed"
    with _lock:
        record = _read(operation_id)
        if record.get("state") == "cancelled":
            state = "cancelled"
        return _update(operation_id, state=state, finished_at=_now(), result=result)


def request_cancel(operation_id: str, *, confirm: bool = False,
                   reason: str | None = None) -> dict:
    """Persist a cancellation request and, for local processes, enforce it."""
    if not confirm:
        raise ToolError("cancelling an operation requires explicit confirm=true")
    with _lock:
        record = _read(operation_id)
        if record.get("state") in TERMINAL:
            return {
                "ok": True,
                "status": "already-finished",
                "operation_id": operation_id,
                "state": record.get("state"),
                "note": "the operation already reached a terminal state; nothing to cancel",
            }
        record["cancel_requested_at"] = _now()
        record["cancel_reason"] = (reason or "")[:1000]
        record["state"] = "cancelling"
        _write(record)
        proc = _processes.get(operation_id)
    killed = _terminate_tree(proc) if proc is not None else False
    confirmed = bool(killed)
    with _lock:
        record = _read(operation_id)
        record["cancel_confirmed"] = confirmed
        record["cancel_target"] = "local-process" if proc is not None else "cooperative"
        if killed:
            record["state"] = "cancelled"
            record["finished_at"] = _now()
            record["result"] = {
                "ok": False,
                "cancelled": True,
                "error": "operation cancelled by user",
            }
        _write(record)
    return {
        "ok": True,
        "status": "cancelled" if confirmed else "cancel-requested",
        "operation_id": operation_id,
        "local_process_killed": confirmed,
        "cancel_target": "local-process" if proc is not None else "cooperative",
        "remote_cancel": record.get("remote_cancel"),
        "note": ("local process tree was terminated" if confirmed else
                 "no local process was running; the operation will stop at its next "
                 "cancellation checkpoint"),
        "caveat": ("Remote/provider-side work is not cancelled unless the provider "
                   "confirms it. Partial files may remain and are listed in cleanup."),
    }


def is_cancel_requested(operation_id: str) -> bool:
    try:
        return bool(_read(operation_id).get("cancel_requested_at"))
    except ToolError:
        return False


def _terminate_tree(proc: subprocess.Popen) -> bool:
    if proc is None or proc.poll() is not None:
        return proc is not None
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    proc.kill()
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
            return True
        except OSError:
            return False


def run_tracked(command: list[str], *, kind: str, label: str | None = None,
                cwd: str | None = None, timeout: int = 900,
                env: dict | None = None, operation_id: str | None = None,
                metadata: dict | None = None) -> dict:
    """Run a local process with persisted tracking and cancellation.

    Returns the same shape as :func:`game_studio.util.run_command` plus
    ``operation_id``, ``cancelled`` and ``state``. It never raises for a
    non-zero exit code: the caller decides what the exit code means.
    """
    if not command:
        raise ToolError("command is required")
    record = start_operation(kind, label or " ".join(command[:3]),
                             metadata=metadata, timeout_seconds=timeout)
    return _run_recorded(record, command, cwd=cwd, timeout=timeout, env=env)


def _run_recorded(record: dict, command: list[str], *, cwd: str | None,
                  timeout: int, env: dict | None) -> dict:
    operation_id = record["id"]
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(key): str(value) for key, value in env.items()})
    started = time.time()
    _update(operation_id, state="running", started_at=now_iso(),
            command=[str(part) for part in command])
    try:
        proc = subprocess.Popen(
            command, cwd=cwd, env=merged_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        result = {
            "ok": False, "command": command, "error": str(exc),
            "operation_id": operation_id, "state": "failed",
            "duration_ms": int((time.time() - started) * 1000),
        }
        _update(operation_id, state="failed", finished_at=now_iso(), result=result)
        return result

    with _lock:
        _processes[operation_id] = proc
    cancelled = False
    timed_out = False
    try:
        # Drain stdout/stderr while the process runs. Waiting for exit before
        # reading deadlocks when a child (e.g. the Blender FBX exporter) emits
        # more output than the OS pipe buffer can hold.
        while True:
            if is_cancel_requested(operation_id):
                cancelled = True
                _terminate_tree(proc)
                break
            if time.time() - started > timeout:
                timed_out = True
                _terminate_tree(proc)
                break
            try:
                proc.communicate(timeout=0.2)
                # The process may have exited because request_cancel killed it
                # between our last flag check and communicate() returning.
                if is_cancel_requested(operation_id):
                    cancelled = True
                break
            except subprocess.TimeoutExpired:
                continue
        # Covers any remaining race where the cancel flag was persisted just
        # after the process exited on its own.
        if not cancelled and is_cancel_requested(operation_id):
            cancelled = True
        try:
            stdout, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            _terminate_tree(proc)
            stdout, stderr = proc.communicate(timeout=30)
    finally:
        with _lock:
            _processes.pop(operation_id, None)

    duration = int((time.time() - started) * 1000)
    code = proc.returncode
    result = {
        "ok": code == 0 and not timed_out and not cancelled,
        "command": [str(part) for part in command],
        "exit_code": code,
        "timed_out": timed_out,
        "cancelled": cancelled,
        "duration_ms": duration,
        "stdout": truncate(stdout or ""),
        "stderr": truncate(stderr or ""),
        "operation_id": operation_id,
    }
    if cancelled:
        result["error"] = "operation cancelled by user"
        state = "cancelled"
    elif timed_out:
        result["error"] = f"timed out after {timeout}s"
        state = "timed-out"
    elif code == 0:
        state = "completed"
    else:
        state = "failed"
    result["state"] = state
    with _lock:
        latest = _read(operation_id)
        # request_cancel may already have written a terminal state.
        state = latest.get("state") if latest.get("state") == "cancelled" else state
    _update(operation_id, state=state, finished_at=now_iso(),
            pid=proc.pid, result=result)
    return result


def recover_interrupted() -> dict:
    """Mark operations that were running when the server stopped as interrupted.

    This does not resurrect them and does not claim they succeeded.
    """
    interrupted = []
    for name in os.listdir(operations_dir()):
        if not name.endswith(".json"):
            continue
        path = os.path.join(operations_dir(), name)
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("state") not in ACTIVE:
            continue
        payload["state"] = "interrupted"
        payload["finished_at"] = _now()
        payload["result"] = {
            "ok": False,
            "error": "server restarted before the operation reported a result",
            "cancelled": False,
        }
        payload["recovered_at"] = _now()
        write_json(path, payload)
        interrupted.append(payload["id"])
    return {"ok": True, "interrupted": interrupted,
            "count": len(interrupted),
            "note": "Interrupted operations are not retried automatically. Inspect the "
                    "project for partial output before re-running."}


def cleanup_operation(operation_id: str, *, confirm: bool = False,
                      temp_dir: str | None = None) -> dict:
    """Remove a finished operation record and optionally its temp directory."""
    if not confirm:
        raise ToolError("cleanup requires explicit confirm=true")
    record = _read(operation_id)
    if record.get("state") in ACTIVE:
        raise ToolError("cannot clean up an operation that is still active; cancel it first")
    removed = []
    if temp_dir and os.path.isdir(temp_dir):
        # Guard: only delete inside the studio temp root or the operation's own temp.
        allowed_root = os.path.abspath(os.path.join(config.config_dir(), "temp"))
        target = os.path.abspath(temp_dir)
        if not (target == allowed_root or target.startswith(allowed_root + os.sep)):
            raise ToolError("refusing to delete a temp directory outside the studio temp root")
        import shutil
        shutil.rmtree(target, ignore_errors=True)
        removed.append(target)
    path = _path(operation_id)
    if os.path.isfile(path):
        os.remove(path)
        removed.append(path)
    return {"ok": True, "status": "completed", "operation_id": operation_id,
            "removed": removed}


def studio_temp_dir(prefix: str = "job") -> str:
    """Return a temp directory owned by the studio, safe for cleanup."""
    root = os.path.join(config.config_dir(), "temp")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{prefix}-{uuid.uuid4().hex[:12]}")
    os.makedirs(path, exist_ok=True)
    return path


def status() -> dict:
    listing = list_operations(limit=20, include_terminal=True)
    active = [item for item in listing["operations"]
              if item.get("state") in ACTIVE]
    return {
        "ok": True,
        "directory": listing["directory"],
        "total": listing["total"],
        "active": len(active),
        "operations": listing["operations"],
        "capabilities": {
            "local_process_cancel": True,
            "process_tree_kill": True,
            "persisted_cancellation": True,
            "temp_cleanup": True,
            "remote_cancel": "only when the provider confirms it; Meshy cancellation "
                             "is reported unsupported unless a documented endpoint is used",
        },
    }
