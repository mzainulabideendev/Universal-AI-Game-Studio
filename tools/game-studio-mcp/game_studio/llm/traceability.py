"""Requirement traceability across understanding, specification and manifest.

Traceability is deterministic and evidence-aware:

* every requirement keeps the user's original wording (``source_text``);
* LLM requirement ids are matched to specification ids without rewriting either;
* optional recommendations are never re-labelled as explicit user requirements;
* a manifest status is copied only when the manifest actually contains it.

Nothing here changes a requirement status. Only ``verification.py`` may do that
after a real command or inspection produced qualifying evidence.
"""

from __future__ import annotations

import re

from ..util import ToolError

CLASSIFICATIONS = ("explicit", "implied", "technical", "optional", "unresolved",
                   "conflict", "excluded")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "to", "of", "in", "on", "is",
    "are", "be", "game", "player", "should", "must", "can", "able",
}


def _normalise_id(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _tokens(value: object) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return {word for word in words if len(word) > 2 and word not in _STOPWORDS}


def _similarity(a: dict, b: dict) -> float:
    left = _tokens(a.get("statement")) | _tokens(a.get("source_text"))
    right = _tokens(b.get("statement")) | _tokens(b.get("source_text"))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def normalise_requirements(understanding: dict | None) -> list[dict]:
    """Accept both LLM and deterministic understanding shapes."""
    if not isinstance(understanding, dict):
        return []
    raw = understanding.get("requirements")
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = []
        for key in ("explicit", "implied", "technical_dependencies",
                    "optional_enhancements"):
            value = raw.get(key)
            if isinstance(value, list):
                items.extend(value)
    else:
        return []
    result = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        classification = item.get("classification")
        if classification not in CLASSIFICATIONS:
            classification = "explicit"
        result.append({
            "id": str(item.get("id") or f"R{index:03d}"),
            "category": str(item.get("category") or "general"),
            "statement": str(item.get("statement") or "").strip(),
            "source_text": str(item.get("source_text") or "").strip(),
            "classification": classification,
            "priority": item.get("priority") or "P1",
            "acceptance_test": item.get("acceptance_test") or "",
            "confidence": item.get("confidence"),
            "depends_on": [str(value) for value in (item.get("depends_on") or [])],
        })
    # Deterministic understanding keeps exclusions in their own list. Surface them
    # as explicitly excluded requirements so they are traceable and never become
    # approved features.
    known = {item["statement"].lower() for item in result}
    existing_ids = {item["id"] for item in result}
    for exclusion in understanding.get("exclusions") or []:
        if not isinstance(exclusion, dict):
            continue
        value = str(exclusion.get("value") or "").strip()
        if not value or value.lower() in known:
            continue
        index = len(result) + 1
        while f"X{index:03d}" in existing_ids:
            index += 1
        result.append({
            "id": f"X{index:03d}",
            "category": str(exclusion.get("category") or "exclusion"),
            "statement": f"Excluded: {value}",
            "source_text": str(exclusion.get("matched_text") or value),
            "classification": "excluded",
            "priority": "P0",
            "acceptance_test": f"No {value} system or content is present",
            "confidence": "high",
            "depends_on": [],
        })
        known.add(value.lower())
    return [item for item in result if item["statement"]]


def _manifest_index(manifest: dict | None) -> dict[str, dict]:
    index: dict[str, dict] = {}
    payload = manifest
    if isinstance(manifest, dict) and isinstance(manifest.get("manifest"), dict):
        payload = manifest["manifest"]
    if not isinstance(payload, dict):
        return index
    for item in payload.get("requirements") or []:
        if isinstance(item, dict) and item.get("id"):
            index[_normalise_id(item["id"])] = item
    return index


def build_traceability(understanding: dict | None, specification: dict | None = None,
                       manifest: dict | None = None) -> dict:
    """Return a requirement trace map with honest coverage counts.

    ``specification`` and ``manifest`` are optional. When omitted, the result
    reports that the corresponding mapping was not evaluated instead of
    pretending the requirements are covered.
    """
    requirements = normalise_requirements(understanding)
    spec_requirements = []
    if isinstance(specification, dict):
        spec_requirements = [item for item in specification.get("requirements") or []
                             if isinstance(item, dict)]
    manifest_by_id = _manifest_index(manifest)

    used_spec: set[int] = set()
    traced = []
    for item in requirements:
        spec_match = None
        spec_match_id = None
        best = 0.0
        if spec_requirements:
            # Exact id first, then textual similarity above a conservative floor.
            for index, candidate in enumerate(spec_requirements):
                if index in used_spec:
                    continue
                if _normalise_id(candidate.get("id")) == _normalise_id(item["id"]):
                    score = 1.0
                else:
                    score = _similarity(item, candidate)
                if score > best:
                    best = score
                    spec_match = candidate
                    spec_match_id = index
            if spec_match is None or best < 0.34:
                spec_match = None
                spec_match_id = None
            elif spec_match_id is not None:
                used_spec.add(spec_match_id)

        status_item = manifest_by_id.get(_normalise_id(item["id"]))
        if status_item is None and spec_match is not None:
            status_item = manifest_by_id.get(_normalise_id(spec_match.get("id")))

        trace = {
            "id": item["id"],
            "category": item["category"],
            "statement": item["statement"],
            "source_text": item["source_text"],
            "classification": item["classification"],
            "priority": item["priority"],
            "acceptance_test": item["acceptance_test"],
            "confidence": item["confidence"],
            "depends_on": item["depends_on"],
            "spec_requirement_id": spec_match.get("id") if spec_match else None,
            "match_confidence": round(best, 3) if spec_match else 0.0,
            "status": (status_item.get("status") if status_item else None),
            "evidence_count": len(status_item.get("evidence") or [])
            if status_item else 0,
            "status_source": ("manifest" if status_item else None),
        }
        traced.append(trace)

    mapped_ids = {_normalise_id(item["spec_requirement_id"])
                  for item in traced if item.get("spec_requirement_id")}
    orphan_spec = [item for item in spec_requirements
                   if _normalise_id(item.get("id")) not in mapped_ids]
    untraced = [item["id"] for item in traced
                if specification is not None and not item["spec_requirement_id"]
                and item["classification"] != "excluded"]

    def _count(classification: str) -> int:
        return sum(1 for item in traced if item["classification"] == classification)

    return {
        "schema_version": "1.0",
        "original_request_preserved": bool(
            isinstance(understanding, dict)
            and understanding.get("original_request")),
        "requirements": traced,
        "counts": {
            "total": len(traced),
            "explicit": _count("explicit"),
            "implied": _count("implied"),
            "technical": _count("technical"),
            "optional": _count("optional"),
            "unresolved": _count("unresolved"),
            "conflict": _count("conflict"),
            "excluded": _count("excluded"),
        },
        "specification": {
            "evaluated": specification is not None,
            "mapped": len(traced) - len(untraced),
            "unmapped_requirements": untraced,
            "spec_only_requirements": [item.get("id") for item in orphan_spec],
        },
        "manifest": {
            "evaluated": manifest is not None,
            "matched": sum(1 for item in traced if item["status_source"] == "manifest"),
            "statuses": {
                status: sum(1 for item in traced if item["status"] == status)
                for status in ("pending", "implemented", "tested", "verified",
                               "blocked", "failed")
            },
        },
        "rules": [
            "source_text is copied from the user's wording and never rewritten",
            "optional recommendations are never treated as approved requirements",
            "status is only non-null when a manifest actually records it",
            "a plan does not prove implementation",
        ],
    }


def assert_traceable(trace: dict, *, require_all_mapped: bool = False) -> None:
    """Raise ``ToolError`` when a trace is structurally unusable."""
    if not isinstance(trace, dict) or not isinstance(trace.get("requirements"), list):
        raise ToolError("traceability report is missing a requirements array")
    if require_all_mapped and trace["specification"].get("unmapped_requirements"):
        raise ToolError("some requirements have no specification mapping; review them "
                        "before claiming traceability")
