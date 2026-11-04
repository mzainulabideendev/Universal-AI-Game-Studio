"""Versioned, project-local memory and requirement traceability.

The manifest lives at ``<project>/.game-studio/manifest.json``. It is separate
from machine configuration so a project can be moved, committed selectively or
recovered after the agent restarts. Writes are atomic, confirmed, and must stay
inside the project root.

Nothing here marks a requirement verified on its own: verification requires
evidence whose kind is test, build, playtest or inspection. File creation alone
is never accepted as proof that a feature works.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone

from .util import ToolError, is_within, read_json, require_path, write_json

MANIFEST_DIR = ".game-studio"
MANIFEST_FILE = "manifest.json"
SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 8 * 1024 * 1024

STATUSES = ("pending", "in_progress", "implemented", "tested", "verified",
            "blocked", "rejected")
VERIFIED_EVIDENCE = ("test", "build", "playtest", "inspection")
TESTED_EVIDENCE = ("test", "playtest")
EVIDENCE_KINDS = ("file", "test", "build", "playtest", "inspection", "manual")

FORBIDDEN_KEY = re.compile(r"(api[_-]?key|secret|password|access[_-]?token|"
                           r"private[_-]?key|credential)", re.IGNORECASE)
SECRET_VALUE = re.compile(
    r"(?i)(api[_-]?key|secret|password|access[_-]?token|bearer)\s*[:=]\s*\S{8,}"
    r"|\b(sk-[A-Za-z0-9]{16,}|msy_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,})\b"
    r"|\b[0-9a-fA-F]{40,}\b")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(manifest: dict, event: str, detail: dict | None = None) -> None:
    manifest.setdefault("history", []).append({
        "at": _now(),
        "event": event,
        "detail": detail or {},
    })
    # Keep the log bounded so the manifest cannot grow without limit.
    manifest["history"] = manifest["history"][-500:]


def _check_no_secrets(payload: object, path: str = "") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if FORBIDDEN_KEY.search(str(key)):
                raise ToolError(
                    f"refusing to write a credential-like field at {path or key!r}; "
                    "store secrets in the studio's private config, not the project manifest")
            _check_no_secrets(value, f"{path}.{key}" if path else str(key))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _check_no_secrets(value, f"{path}[{index}]")
    elif isinstance(payload, str) and SECRET_VALUE.search(payload):
        raise ToolError(
            f"refusing to write what looks like a credential at {path or 'value'!r}; "
            "store secrets in the studio's private config, never in project memory")


def manifest_path(project_path: str) -> str:
    return os.path.join(project_path, MANIFEST_DIR, MANIFEST_FILE)


def _project(project_path: str) -> str:
    project = require_path(project_path, kind="dir", label="project_path")
    return project


def _project_id(project: str, spec_id: str | None = None) -> str:
    if spec_id:
        return spec_id
    digest = hashlib.sha1(os.path.normcase(os.path.abspath(project)).encode("utf-8"))
    return digest.hexdigest()[:12]


def init_manifest(project_path: str, spec: dict, *, confirm: bool = False,
                  overwrite: bool = False) -> dict:
    project = _project(project_path)
    if not confirm:
        raise ToolError("initialising a project manifest writes a file; pass confirm=true")
    if not isinstance(spec, dict) or not spec.get("spec_id"):
        raise ToolError("a specification from create_game_specification is required")
    path = manifest_path(project)
    if os.path.exists(path) and not overwrite:
        raise ToolError(
            f"manifest already exists at {path}; pass overwrite=true to replace it")
    if overwrite and not os.path.exists(path):
        overwrite = False

    requirements = []
    seen = set()
    for item in spec.get("requirements") or []:
        req_id = item.get("id")
        if not req_id or req_id in seen:
            continue
        seen.add(req_id)
        requirements.append({
            "id": req_id,
            "category": item.get("category"),
            "statement": item.get("statement"),
            "source_text": item.get("source_text"),
            "classification": item.get("classification"),
            "priority": item.get("priority"),
            "acceptance_test": item.get("acceptance_test"),
            "implementation_tasks": item.get("implementation_tasks") or [],
            "status": "pending",
            "evidence": [],
            "notes": [],
            "history": [{"at": _now(), "status": "pending",
                         "note": "created from specification"}],
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "project_id": _project_id(project, spec.get("spec_id")),
        "project_name": spec.get("project_name"),
        "project_path": project,
        "created_at": _now(),
        "updated_at": _now(),
        "spec": spec,
        "requirements": requirements,
        "decisions": [],
        "known_errors": [],
        "pending_questions": spec.get("questions") or [],
        "milestones": spec.get("milestones") or [],
        "replaced": bool(overwrite),
        "history": [],
    }
    _emit(manifest, "manifest.created",
          {"spec_id": spec.get("spec_id"), "requirements": len(requirements),
           "replaced": bool(overwrite)})
    _check_no_secrets(manifest)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_json(path, manifest)
    return {
        "ok": True,
        "status": "completed",
        "manifest_path": path,
        "project_id": manifest["project_id"],
        "requirements": len(requirements),
        "revision": manifest["revision"],
        "note": "Manifest created. Requirement statuses start at pending; nothing is "
                "claimed as implemented or verified.",
    }


def load_manifest(project_path: str) -> dict:
    project = _project(project_path)
    path = manifest_path(project)
    if not os.path.isfile(path):
        return {
            "ok": False,
            "status": "not-configured",
            "project_path": project,
            "manifest_path": path,
            "error": "no project manifest found; call init_project_manifest first",
        }
    if os.path.getsize(path) > MAX_MANIFEST_BYTES:
        raise ToolError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        manifest = read_json(path)
    except (OSError, ValueError) as exc:
        raise ToolError(f"manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ToolError("unsupported manifest schema; recreate it with init_project_manifest")
    manifest["_path"] = path
    return {"ok": True, "status": "completed", "manifest": manifest,
            "manifest_path": path}


def _save(project: str, manifest: dict) -> None:
    manifest.pop("_path", None)
    manifest["updated_at"] = _now()
    manifest["revision"] = int(manifest.get("revision", 1)) + 1
    _check_no_secrets(manifest)
    write_json(manifest_path(project), manifest)


def _require_manifest(project_path: str) -> tuple[str, dict]:
    project = _project(project_path)
    loaded = load_manifest(project)
    if not loaded["ok"]:
        raise ToolError(loaded["error"])
    return project, loaded["manifest"]


def _find_requirement(manifest: dict, requirement_id: str) -> dict:
    for requirement in manifest.get("requirements", []):
        if requirement.get("id") == requirement_id:
            return requirement
    raise ToolError(f"unknown requirement id: {requirement_id}")


def _looks_like_path(reference: str) -> bool:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", reference):
        return False
    return bool(re.search(r"[\\/]", reference) or re.match(r"^[a-zA-Z]:", reference))


def _normalise_evidence(project: str, evidence: list | None) -> list[dict]:
    items = []
    for raw in evidence or []:
        if isinstance(raw, str):
            raw = {"kind": "file", "reference": raw}
        if not isinstance(raw, dict):
            raise ToolError("each evidence item must be an object or a file path string")
        kind = raw.get("kind", "file")
        if kind not in EVIDENCE_KINDS:
            raise ToolError(f"evidence kind must be one of {list(EVIDENCE_KINDS)}")
        reference = str(raw.get("reference") or "").strip()
        if not reference:
            raise ToolError("evidence reference is required")
        item = {
            "kind": kind,
            "reference": reference,
            "note": str(raw.get("note") or "")[:2000],
            "recorded_at": _now(),
            "exists": None,
        }
        check_path = kind == "file" or _looks_like_path(reference)
        if check_path:
            candidate = reference if os.path.isabs(reference) else os.path.join(
                project, reference)
            if not is_within(project, candidate):
                raise ToolError(f"evidence path escapes the project root: {reference}")
            item["exists"] = os.path.exists(candidate)
        items.append(item)
    return items


def update_requirement_status(project_path: str, requirement_id: str, status: str, *,
                              evidence: list | None = None, note: str | None = None,
                              confirm: bool = False) -> dict:
    project, manifest = _require_manifest(project_path)
    if not confirm:
        raise ToolError("updating requirement status writes the manifest; pass confirm=true")
    if status not in STATUSES:
        raise ToolError(f"status must be one of {list(STATUSES)}")
    requirement = _find_requirement(manifest, requirement_id)
    items = _normalise_evidence(project, evidence)

    attached = requirement.setdefault("evidence", [])
    attached.extend(items)
    kinds = {item["kind"] for item in attached}
    missing_files = [item["reference"] for item in attached
                     if item.get("exists") is False]

    if status in ("implemented", "tested", "verified") and not attached:
        raise ToolError(
            f"{status} requires evidence; add a file, test, build, playtest or inspection "
            "reference. Creating code or an asset is not proof that it works.")
    if status == "tested" and not (kinds & set(TESTED_EVIDENCE)):
        raise ToolError("tested requires test or playtest evidence")
    if status == "verified":
        qualifying = [item for item in attached
                      if item["kind"] in VERIFIED_EVIDENCE and item["reference"]]
        if not qualifying:
            raise ToolError(
                "verified requires test, build, playtest or inspection evidence with a "
                "reference; file creation alone is not verification")
        if missing_files:
            raise ToolError(
                "cannot verify while evidence files are missing: " + ", ".join(missing_files))

    previous = requirement.get("status", "pending")
    requirement["status"] = status
    if note:
        requirement.setdefault("notes", []).append({
            "at": _now(), "note": str(note)[:4000]})
    requirement.setdefault("history", []).append({
        "at": _now(),
        "status": status,
        "previous": previous,
        "note": (note or "")[:1000],
        "evidence_kinds": sorted(kinds),
    })
    _emit(manifest, "requirement.status",
          {"id": requirement_id, "from": previous, "to": status,
           "evidence": len(items)})
    _save(project, manifest)
    return {
        "ok": True,
        "status": "completed",
        "requirement_id": requirement_id,
        "previous": previous,
        "current": status,
        "evidence_count": len(attached),
        "missing_evidence_files": missing_files,
        "revision": manifest["revision"],
        "note": "Requirement status is a recorded claim plus evidence; run "
                "compare_project_against_requirements to re-check it.",
    }


def record_decision(project_path: str, *, topic: str, decision: str,
                    rationale: str | None = None, source: str = "user",
                    approved: bool = False, confirm: bool = False) -> dict:
    project, manifest = _require_manifest(project_path)
    if not confirm:
        raise ToolError("recording a decision writes the manifest; pass confirm=true")
    if not topic.strip() or not decision.strip():
        raise ToolError("topic and decision are required")
    if source not in ("user", "ai-default", "ai-recommendation", "external"):
        raise ToolError("source must be user, ai-default, ai-recommendation or external")
    entry = {
        "id": f"D-{len(manifest.get('decisions', [])) + 1:03d}",
        "topic": topic.strip()[:200],
        "decision": decision.strip()[:4000],
        "rationale": (rationale or "").strip()[:4000],
        "source": source,
        "approved": bool(approved),
        "at": _now(),
    }
    manifest.setdefault("decisions", []).append(entry)
    # A recorded decision answers any matching pending question.
    remaining = []
    for question in manifest.get("pending_questions", []):
        if topic.strip().lower() in question.get("question", "").lower():
            continue
        remaining.append(question)
    manifest["pending_questions"] = remaining
    _emit(manifest, "decision.recorded",
          {"id": entry["id"], "topic": entry["topic"], "source": source,
           "approved": approved})
    _save(project, manifest)
    return {"ok": True, "status": "completed", "decision": entry,
            "revision": manifest["revision"],
            "pending_questions": len(manifest["pending_questions"])}


def load_manifest_view(project_path: str) -> dict:
    loaded = load_manifest(project_path)
    if not loaded["ok"]:
        return loaded
    manifest = loaded["manifest"]
    return {
        "ok": True,
        "status": "completed",
        "manifest_path": loaded["manifest_path"],
        "schema_version": manifest.get("schema_version"),
        "revision": manifest.get("revision"),
        "project_id": manifest.get("project_id"),
        "project_name": manifest.get("project_name"),
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
        "engine": (manifest.get("spec", {}).get("engine") or {}).get("selected"),
        "overview": manifest.get("spec", {}).get("overview"),
        "requirements": [{
            "id": item.get("id"),
            "statement": item.get("statement"),
            "classification": item.get("classification"),
            "priority": item.get("priority"),
            "status": item.get("status"),
            "evidence_count": len(item.get("evidence") or []),
            "acceptance_test": item.get("acceptance_test"),
        } for item in manifest.get("requirements", [])],
        "decisions": manifest.get("decisions", []),
        "pending_questions": manifest.get("pending_questions", []),
        "known_errors": manifest.get("known_errors", []),
        "recent_history": (manifest.get("history") or [])[-20:],
        "note": "Full specification and per-requirement history remain in the manifest file.",
    }


def _coverage(requirements: list[dict]) -> dict:
    counts = {status: 0 for status in STATUSES}
    for requirement in requirements:
        status = requirement.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    total = len(requirements)
    resolved = counts["verified"]
    return {
        "total": total,
        **counts,
        "verified_ratio": round(resolved / total, 3) if total else 0.0,
        "verified_or_tested": counts["verified"] + counts["tested"],
        "open": counts["pending"] + counts["in_progress"] + counts["implemented"],
    }


def track_progress(project_path: str) -> dict:
    loaded = load_manifest(project_path)
    if not loaded["ok"]:
        return loaded
    manifest = loaded["manifest"]
    requirements = manifest.get("requirements", [])
    coverage = _coverage(requirements)
    milestones = []
    for milestone in manifest.get("milestones", []):
        tasks = [node for node in (manifest.get("spec", {}).get(
            "dependency_graph", {}).get("nodes") or [])
            if node.get("milestone") == milestone.get("id")]
        milestone_status = milestone.get("status", "not-started")
        if tasks and all(task.get("status") == "verified" for task in tasks):
            milestone_status = "verified"
        milestones.append({
            "id": milestone.get("id"),
            "name": milestone.get("name"),
            "gate": milestone.get("gate"),
            "status": milestone_status,
            "tasks": len(tasks),
            "tasks_verified": sum(1 for task in tasks
                                  if task.get("status") == "verified"),
        })
    next_actions = []
    for requirement in requirements:
        if requirement.get("priority") in ("P0", "P1") and \
                requirement.get("status") in ("pending", "blocked"):
            next_actions.append(
                f"{requirement['id']} [{requirement.get('priority')}] "
                f"{requirement.get('statement')}")
        if len(next_actions) >= 8:
            break
    return {
        "ok": True,
        "status": "completed",
        "project_name": manifest.get("project_name"),
        "project_id": manifest.get("project_id"),
        "revision": manifest.get("revision"),
        "updated_at": manifest.get("updated_at"),
        "coverage": coverage,
        "milestones": milestones,
        "pending_questions": manifest.get("pending_questions", []),
        "known_errors": manifest.get("known_errors", []),
        "next_actions": next_actions,
        "recency": "Loaded from the project manifest, not from conversation memory.",
    }


def compare_project_against_requirements(project_path: str, *,
                                         inspect_project: bool = True) -> dict:
    loaded = load_manifest(project_path)
    if not loaded["ok"]:
        return loaded
    project = os.path.abspath(project_path)
    manifest = loaded["manifest"]
    requirements = manifest.get("requirements", [])
    issues_by_requirement: dict[str, list[str]] = {}
    invalid_claims = []

    for requirement in requirements:
        issues = []
        status = requirement.get("status", "pending")
        evidence = requirement.get("evidence") or []
        kinds = {item.get("kind") for item in evidence}
        for item in evidence:
            if item.get("exists") is False:
                issues.append(f"evidence file no longer exists: {item.get('reference')}")
            elif item.get("kind") == "file":
                reference = item.get("reference") or ""
                candidate = reference if os.path.isabs(reference) else os.path.join(
                    project, reference)
                if not is_within(project, candidate):
                    issues.append(f"evidence escapes project root: {reference}")
                elif not os.path.exists(candidate):
                    issues.append(f"evidence file no longer exists: {reference}")
        if status == "verified" and not (kinds & set(VERIFIED_EVIDENCE)):
            issues.append("marked verified without test/build/playtest/inspection evidence")
        if status == "tested" and not (kinds & set(TESTED_EVIDENCE)):
            issues.append("marked tested without test/playtest evidence")
        if status in ("implemented", "tested", "verified") and not evidence:
            issues.append("marked done without any evidence")
        if issues:
            issues_by_requirement[requirement["id"]] = issues
            if status in ("implemented", "tested", "verified"):
                invalid_claims.append(requirement["id"])

    project_checks: dict = {"inspected": False}
    detected_engine = None
    if inspect_project:
        # Imported lazily so the understanding/manifest layer stays testable
        # without touching detection.
        from .projects import detect_project_engine, inspect_game_project
        detected_engine = detect_project_engine(project)
        project_checks["detected_engine"] = detected_engine
        if detected_engine:
            try:
                inspected = inspect_game_project(project)
                project_checks["inspected"] = True
                project_checks["engine_ok"] = bool(inspected.get("ok"))
                project_checks["warnings"] = inspected.get("warnings", [])
                project_checks["structure"] = inspected.get("structure")
            except ToolError as exc:
                project_checks["inspection_error"] = str(exc)
        else:
            project_checks["inspection_error"] = (
                "unrecognised game project; only the manifest was checked")

    spec_engine = (manifest.get("spec", {}).get("engine") or {}).get("selected")
    if detected_engine and spec_engine and detected_engine != spec_engine:
        project_checks["engine_mismatch"] = (
            f"spec says {spec_engine}, project is {detected_engine}")

    coverage = _coverage(requirements)
    if invalid_claims:
        overall = "blocked"
    elif coverage["total"] == 0:
        overall = "not-started"
    elif coverage["verified"] == coverage["total"]:
        overall = "verified"
    elif coverage["verified"] or coverage["tested"] or coverage["implemented"]:
        overall = "partial"
    else:
        overall = "not-started"

    recommendations = []
    if invalid_claims:
        recommendations.append(
            "Fix or downgrade invalid claims: " + ", ".join(invalid_claims))
    if coverage["pending"]:
        recommendations.append(f"{coverage['pending']} requirements are still pending.")
    if project_checks.get("engine_mismatch"):
        recommendations.append(project_checks["engine_mismatch"])
    if not detected_engine and inspect_project:
        recommendations.append(
            "No Unity/Godot/Unreal marker was found; implementation evidence cannot be "
            "cross-checked against a real project yet.")
    if overall == "verified":
        recommendations.append(
            "All recorded requirements have qualifying evidence. This still does not "
            "replace human playtesting or review of the build.")

    return {
        "ok": True,
        "status": "completed",
        "project_name": manifest.get("project_name"),
        "project_path": project,
        "manifest_revision": manifest.get("revision"),
        "overall": overall,
        "coverage": coverage,
        "spec_engine": spec_engine,
        "detected_engine": detected_engine,
        "project_checks": project_checks,
        "requirements": [{
            "id": item.get("id"),
            "statement": item.get("statement"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "evidence_count": len(item.get("evidence") or []),
            "issues": issues_by_requirement.get(item["id"], []),
        } for item in requirements],
        "invalid_claims": invalid_claims,
        "recommendations": recommendations,
        "limitations": [
            "Evidence references are checked for existence, not for semantic correctness.",
            "A verified status means the recorded evidence exists; it is not an "
            "independent re-run of the test or build.",
        ],
    }
