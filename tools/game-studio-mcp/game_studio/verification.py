"""Requirement evidence inspection and re-run verification.

This module closes the gap between "a file exists" and "the requirement was
actually tested". It:

1. ties every requirement back to the original user wording (``source_text``);
2. lists implementation files, tests and the acceptance test;
3. re-runs a caller-supplied validation command through the tracked operation
   runner (never a shell);
4. captures stdout/stderr, exit code, timestamps and hashes as evidence;
5. compares the new run with the previous evidence;
6. upgrades the requirement status only on a real exit code 0.

A command is never executed without the ``execute_process`` permission and an
explicit ``confirm=true``. No command is invented for the user.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone

from . import governance, manifest, operations
from .util import ToolError, is_within, read_json, require_path, write_json

EVIDENCE_DIR = os.path.join(".game-studio", "evidence")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evidence_dir(project: str) -> str:
    path = os.path.join(project, EVIDENCE_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _load(project_path: str) -> tuple[str, dict]:
    project = require_path(project_path, kind="dir", label="project_path")
    loaded = manifest.load_manifest(project)
    if not loaded["ok"]:
        raise ToolError(loaded.get("error", "no project manifest"))
    return project, loaded["manifest"]


def _requirement(manifest_data: dict, requirement_id: str) -> dict:
    for item in manifest_data.get("requirements", []):
        if item.get("id") == requirement_id:
            return item
    raise ToolError(f"unknown requirement id: {requirement_id}")


def _resolve(project: str, reference: str) -> str | None:
    if not reference:
        return None
    candidate = reference if os.path.isabs(reference) else os.path.join(project, reference)
    if not is_within(project, candidate):
        return None
    return candidate


def _classify_evidence(project: str, evidence: list[dict]) -> dict:
    files, tests, builds, notes = [], [], [], []
    missing = []
    for item in evidence or []:
        kind = item.get("kind")
        reference = str(item.get("reference") or "")
        exists = None
        path = _resolve(project, reference)
        if path and (kind == "file" or os.sep in reference or "/" in reference):
            exists = os.path.exists(path)
        if exists is False:
            missing.append(reference)
        entry = {
            "kind": kind,
            "reference": reference,
            "recorded_at": item.get("recorded_at"),
            "exists": exists,
            "note": item.get("note"),
        }
        if kind == "file":
            files.append(entry)
        elif kind in ("test", "playtest"):
            tests.append(entry)
        elif kind == "build":
            builds.append(entry)
        else:
            notes.append(entry)
    return {"files": files, "tests": tests, "builds": builds,
            "other": notes, "missing": missing}


def inspect_requirement_evidence(project_path: str,
                                 requirement_id: str | None = None) -> dict:
    """Read-only inspection. Never upgrades a status."""
    project, manifest_data = _load(project_path)
    requirements = manifest_data.get("requirements", [])
    selected = requirements
    if requirement_id:
        selected = [_requirement(manifest_data, requirement_id)]

    evidence_root = os.path.join(project, EVIDENCE_DIR)
    runs_by_requirement: dict[str, list[dict]] = {}
    if os.path.isdir(evidence_root):
        for name in sorted(os.listdir(evidence_root)):
            if not name.endswith(".json"):
                continue
            try:
                record = read_json(os.path.join(evidence_root, name))
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and record.get("requirement_id"):
                runs_by_requirement.setdefault(record["requirement_id"], []).append({
                    "file": os.path.join(EVIDENCE_DIR, name),
                    "run_at": record.get("run_at"),
                    "exit_code": record.get("exit_code"),
                    "cancelled": record.get("cancelled"),
                    "timed_out": record.get("timed_out"),
                    "ok": record.get("ok"),
                })

    report = []
    for requirement in selected:
        req_id = requirement.get("id")
        evidence = requirement.get("evidence") or []
        classified = _classify_evidence(project, evidence)
        runs = runs_by_requirement.get(req_id, [])
        code_files = [entry for entry in classified["files"]]
        report.append({
            "id": req_id,
            "statement": requirement.get("statement"),
            "source_text": requirement.get("source_text"),
            "classification": requirement.get("classification"),
            "priority": requirement.get("priority"),
            "status": requirement.get("status"),
            "acceptance_test": requirement.get("acceptance_test"),
            "implementation_tasks": requirement.get("implementation_tasks") or [],
            "implementation_files": code_files,
            "tests": classified["tests"],
            "builds": classified["builds"],
            "other_evidence": classified["other"],
            "missing_evidence_files": classified["missing"],
            "verification_runs": runs,
            "last_run": runs[-1] if runs else None,
            "gaps": _gaps(requirement, classified, runs),
            "ready_to_verify": bool(runs and runs[-1].get("ok") and
                                    not classified["missing"]),
        })

    total = len(report)
    ready = sum(1 for item in report if item["ready_to_verify"])
    return {
        "ok": True,
        "status": "completed",
        "project_path": project,
        "manifest_revision": manifest_data.get("revision"),
        "requirement_count": total,
        "ready_to_verify": ready,
        "requirements": report,
        "limitations": [
            "This inspection checks evidence existence and recorded runs; it does not "
            "re-run anything by itself.",
            "A file listed as implementation evidence is not proof the behaviour works.",
            "Use run_requirement_verification with a concrete command to create new "
            "executable evidence.",
        ],
    }


def _gaps(requirement: dict, classified: dict, runs: list[dict]) -> list[str]:
    gaps = []
    if not requirement.get("source_text"):
        gaps.append("no original user wording is recorded for this requirement")
    if not requirement.get("acceptance_test"):
        gaps.append("no acceptance test is defined")
    if classified["missing"]:
        gaps.append("missing evidence files: " + ", ".join(classified["missing"]))
    if not classified["tests"] and not runs:
        gaps.append("no test or playtest evidence has been recorded")
    if not runs:
        gaps.append("no verification command has been executed")
    if requirement.get("status") in ("tested", "verified") and not runs:
        gaps.append("status claims testing but no executed verification run exists")
    return gaps


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def run_requirement_verification(project_path: str, requirement_id: str, *,
                                 command: list[str] | None = None,
                                 confirm: bool = False,
                                 timeout: int = 900,
                                 apply_status: bool = True) -> dict:
    """Execute one validation command and record verifiable evidence.

    ``command`` must be a list of argv strings. It runs without a shell inside
    the project directory. Without a command nothing is executed and the tool
    explains what evidence is missing.
    """
    project, manifest_data = _load(project_path)
    requirement = _requirement(manifest_data, requirement_id)

    decision = governance.authorize("execute_process", project_path=project,
                                    confirm=confirm,
                                    action=f"verification for {requirement_id}")
    if not command:
        inspection = inspect_requirement_evidence(project, requirement_id)
        return {
            "ok": False,
            "status": "blocked",
            "error": "no verification command supplied; refusing to guess one",
            "requirement": inspection["requirements"][0],
            "suggestions": [
                "Pass a concrete argv command such as "
                '["python", "-m", "unittest", "tests.test_player"]',
                "A command must be approved by the user and covered by the "
                "execute_process permission.",
            ],
            "governance": decision,
        }
    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        raise ToolError("command must be an array of strings (argv), never a shell string")
    if any(not part.strip() for part in command):
        raise ToolError("command contains an empty argument")

    before = _classify_evidence(project, requirement.get("evidence") or [])
    started = time.time()
    result = operations.run_tracked(
        command,
        kind="requirement-verification",
        label=f"verify {requirement_id}",
        cwd=project,
        timeout=timeout,
        metadata={"requirement_id": requirement_id, "project_path": project},
    )
    duration = int((time.time() - started) * 1000)

    run_at = _now()
    record = {
        "schema_version": 1,
        "requirement_id": requirement_id,
        "statement": requirement.get("statement"),
        "source_text": requirement.get("source_text"),
        "acceptance_test": requirement.get("acceptance_test"),
        "command": command,
        "cwd": project,
        "run_at": run_at,
        "exit_code": result.get("exit_code"),
        "cancelled": bool(result.get("cancelled")),
        "timed_out": bool(result.get("timed_out")),
        "duration_ms": duration,
        "ok": bool(result.get("ok")),
        "operation_id": result.get("operation_id"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "stdout_sha256": _hash(result.get("stdout") or ""),
        "stderr_sha256": _hash(result.get("stderr") or ""),
        "governance_decision": decision,
        "previous_evidence": {
            "tests": len(before["tests"]),
            "files": len(before["files"]),
            "missing": before["missing"],
        },
    }
    directory = _evidence_dir(project)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    filename = f"{requirement_id}-{stamp}-{result.get('operation_id', 'run')}.json"
    path = os.path.join(directory, filename)
    write_json(path, record)
    reference = os.path.relpath(path, project).replace(os.sep, "/")

    comparison = _compare_previous(directory, requirement_id, record)
    record["comparison"] = comparison
    write_json(path, record)

    status_update = None
    if apply_status and result.get("ok"):
        # An exit code 0 is real test evidence. It upgrades to "tested", not
        # "verified": automated tests do not prove a human playtest.
        status_update = manifest.update_requirement_status(
            project, requirement_id, "tested",
            evidence=[{"kind": "test", "reference": reference,
                       "note": f"verification command exit={result.get('exit_code')} "
                               f"at {run_at}"}],
            note="Evidence re-run: command returned exit code 0",
            confirm=True,
        )
    elif apply_status and result.get("cancelled"):
        status_update = {"ok": True, "status": "skipped",
                         "reason": "cancelled runs are not accepted as evidence"}
    elif apply_status:
        status_update = {"ok": True, "status": "skipped",
                         "reason": "non-zero exit codes do not upgrade requirement status"}

    return {
        "ok": bool(result.get("ok")),
        "status": "completed" if result.get("ok") else "failed",
        "requirement_id": requirement_id,
        "evidence_path": path,
        "evidence_reference": reference,
        "run": {key: record[key] for key in (
            "command", "run_at", "exit_code", "cancelled", "timed_out",
            "duration_ms", "ok", "operation_id", "stdout_sha256", "stderr_sha256")},
        "stdout_tail": (record["stdout"] or "")[-4000:],
        "stderr_tail": (record["stderr"] or "")[-4000:],
        "comparison": comparison,
        "status_update": status_update,
        "caveats": [
            "Exit code 0 shows this command passed; it is not proof of visual quality, "
            "fun or platform performance.",
            "A cancelled or timed-out run is never accepted as evidence.",
            "The command ran without a shell; shell syntax is not interpreted.",
        ],
    }


def _compare_previous(directory: str, requirement_id: str, current: dict) -> dict:
    previous = None
    for name in sorted(os.listdir(directory), reverse=True):
        if not name.endswith(".json") or not name.startswith(requirement_id + "-"):
            continue
        path = os.path.join(directory, name)
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("operation_id") != current.get(
                "operation_id"):
            previous = payload
            break
    if not previous:
        return {"previous_run": None, "changed": None,
                "note": "first recorded verification run for this requirement"}
    changed = {
        "command": previous.get("command") != current.get("command"),
        "exit_code": previous.get("exit_code") != current.get("exit_code"),
        "stdout": previous.get("stdout_sha256") != current.get("stdout_sha256"),
        "stderr": previous.get("stderr_sha256") != current.get("stderr_sha256"),
    }
    return {
        "previous_run": {
            "run_at": previous.get("run_at"),
            "exit_code": previous.get("exit_code"),
            "ok": previous.get("ok"),
        },
        "changed": changed,
        "changed_any": any(changed.values()),
        "note": "Output changes are expected when timings or hashes are printed; compare "
                "the exit code and the asserted behaviour, not raw text alone.",
    }
