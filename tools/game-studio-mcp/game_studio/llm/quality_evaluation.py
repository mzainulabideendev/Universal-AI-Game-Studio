"""Deterministic quality rubric for a game design specification.

Structural validation answers "is this the required shape?". This module answers
"is this content complete, coherent and testable?" using fixed, reproducible
rules. It is deliberately conservative:

- No language model judges another language model.
- A single response proves nothing about general model intelligence.
- Subjective quality (fun, art direction) is only checked for specificity, not
  for taste.
- Every score exposes the rule that produced it.

Categories and methods
----------------------
1. completeness          Required-field coverage (0-10).
2. internal_consistency  10 minus 2 per contradiction (0-10).
3. gameplay_clarity      Loop steps + mechanics + objective cohesion (0-10).
4. technical_feasibility Engine, platforms and architecture concreteness (0-10).
5. engine_compatibility  Declared engine is supported and referenced (0-10).
6. performance_awareness FPS target, hardware and tier present and plausible (0-10).
7. asset_specificity     Individually named assets across required classes (0-10).
8. testability           Acceptance criteria that contain measurable checks (0-10).
9. requirement_traceability  Fraction of requirements with IDs and sources (0-10).
10. unsupported_claim_avoidance  10 minus 3 per unverified capability claim (0-10).
"""

from __future__ import annotations

from . import response_validation as rv

SCHEMA_VERSION = 1
MAX_SCORE = 100

MEASURABLE_MARKERS = (
    "at least", "at most", "within", "less than", "greater than", "equals",
    "returns", "passes", "reaches", "count", "fps", "ms", "seconds", "frames",
    "triangles", "bones", "materials", "bytes", "errors", "warnings",
    "checkpoint", "exit code",
)

ASSET_CLASSES = (
    ("character", ("character", "monkey", "player", "rig", "skeleton", "anim")),
    ("environment", ("terrain", "level", "jungle", "tree", "bush", "rock", "river")),
    ("prop", ("banana", "collectible", "prop", "crate", "log")),
    ("texture", ("texture", "material", "normal", "roughness", "base color", "pbr")),
    ("audio", ("audio", "sound", "music", "sfx")),
    ("ui", ("ui", "hud", "font", "icon", "menu")),
)


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return round(max(low, min(high, value)), 2)


def _ratio(count: int, total: int) -> float:
    return (count / total) if total else 0.0


def _items(payload: dict, key: str) -> list[str]:
    return rv._as_list(payload.get(key))


def _method_completeness(payload: dict) -> dict:
    required = rv.AI_GAME_SPEC_SCHEMA["required"]
    missing = rv.missing_fields(payload)
    present = len([key for key in required if key not in missing])
    score = _clamp(10.0 * _ratio(present, len(required)))
    return {
        "name": "completeness",
        "score": score,
        "max": 10,
        "method": "10 x (required fields present / required fields)",
        "evidence": {"present": present, "required": len(required), "missing": missing},
    }


def _method_consistency(payload: dict) -> dict:
    found = rv.contradictions(payload)
    score = _clamp(10.0 - 2.0 * len(found))
    return {
        "name": "internal_consistency",
        "score": score,
        "max": 10,
        "method": "10 - 2 per detected cross-field contradiction (floor 0)",
        "evidence": found,
    }


def _method_gameplay(payload: dict) -> dict:
    loop = _items(payload, "core_gameplay_loop")
    mechanics = _items(payload, "player_mechanics")
    objectives = [item for item in _items(payload, "progression") if item]
    points = 0.0
    points += 3.0 if len(loop) >= 3 else (2.0 if len(loop) == 2 else float(len(loop)))
    points += 3.0 if len(mechanics) >= 3 else float(len(mechanics))
    points += 2.0 if objectives else 0.0
    points += 2.0 if _items(payload, "collectibles") or _items(payload, "hazards") else 0.0
    return {
        "name": "gameplay_clarity",
        "score": _clamp(points),
        "max": 10,
        "method": ("3 for >=3 loop steps, 3 for >=3 mechanics, 2 for progression, "
                   "2 for a concrete collectible or hazard"),
        "evidence": {"loop_steps": len(loop), "mechanics": len(mechanics),
                     "progression": len(objectives)},
    }


def _method_technical(payload: dict) -> dict:
    architecture = _items(payload, "technical_architecture")
    platforms = _items(payload, "target_platforms")
    engine = str(payload.get("engine") or "").strip()
    points = 0.0
    points += 4.0 if len(architecture) >= 2 else 2.0 * min(len(architecture), 1)
    points += 3.0 if platforms else 0.0
    points += 3.0 if engine else 0.0
    return {
        "name": "technical_feasibility",
        "score": _clamp(points),
        "max": 10,
        "method": "4 for >=2 architecture items, 3 for platforms, 3 for an engine",
        "evidence": {"architecture_items": len(architecture),
                     "platforms": platforms, "engine": engine or None},
    }


def _method_engine(payload: dict) -> dict:
    engine = str(payload.get("engine") or "").strip().lower()
    architecture = " ".join(_items(payload, "technical_architecture")).lower()
    if engine not in rv.SUPPORTED_ENGINES:
        score = 0.0
    elif engine in architecture:
        score = 10.0
    else:
        score = 6.0
    return {
        "name": "engine_compatibility",
        "score": _clamp(score),
        "max": 10,
        "method": ("0 for an unsupported engine, 6 for a supported engine not "
                   "referenced in the architecture, 10 when both agree"),
        "evidence": {"engine": engine or None, "referenced_in_architecture": engine in architecture},
    }


def _method_performance(payload: dict) -> dict:
    performance = payload.get("performance_targets")
    if not isinstance(performance, dict):
        return {"name": "performance_awareness", "score": 0.0, "max": 10,
                "method": "FPS/hardware/tier presence", "evidence": {}}
    fps = performance.get("target_fps")
    points = 0.0
    points += 5.0 if isinstance(fps, int) and 30 <= fps <= 120 else 0.0
    points += 3.0 if str(performance.get("hardware") or "").strip() else 0.0
    points += 2.0 if str(performance.get("quality_tier") or "").strip() else 0.0
    return {
        "name": "performance_awareness",
        "score": _clamp(points),
        "max": 10,
        "method": "5 for a plausible FPS target, 3 for hardware, 2 for a quality tier",
        "evidence": {"target_fps": fps, "hardware_present": bool(performance.get("hardware")),
                     "quality_tier": performance.get("quality_tier")},
    }


def _method_assets(payload: dict) -> dict:
    assets = " ".join(_items(payload, "asset_requirements")).lower()
    covered = [name for name, markers in ASSET_CLASSES
               if any(marker in assets for marker in markers)]
    score = _clamp(10.0 * _ratio(len(covered), len(ASSET_CLASSES)))
    return {
        "name": "asset_specificity",
        "score": score,
        "max": 10,
        "method": "10 x (asset classes named / 6)",
        "evidence": {"classes_covered": covered,
                     "classes_missing": [name for name, _ in ASSET_CLASSES
                                         if name not in covered]},
    }


def _method_testability(payload: dict) -> dict:
    criteria = _items(payload, "acceptance_criteria")
    measurable = [item for item in criteria
                  if any(marker in item.lower() for marker in MEASURABLE_MARKERS)]
    score = _clamp(10.0 * _ratio(len(measurable), max(len(criteria), 1))
                   if criteria else 0.0)
    return {
        "name": "testability",
        "score": score,
        "max": 10,
        "method": "10 x (measurable acceptance criteria / all criteria)",
        "evidence": {"criteria": len(criteria), "measurable": len(measurable),
                     "ambiguous": rv.ambiguous_requirements(payload)},
    }


def _method_traceability(payload: dict) -> dict:
    requirements = payload.get("requirements") or []
    if not isinstance(requirements, list) or not requirements:
        return {"name": "requirement_traceability", "score": 0.0, "max": 10,
                "method": "10 x (requirements with id + provenance / all requirements)",
                "evidence": {"requirements": 0}}
    traced = [
        item for item in requirements
        if isinstance(item, dict)
        and (item.get("id") or item.get("requirement_id"))
        and item.get("provenance")
        and item.get("acceptance_criteria")
    ]
    return {
        "name": "requirement_traceability",
        "score": _clamp(10.0 * _ratio(len(traced), len(requirements))),
        "max": 10,
        "method": "10 x (requirements with id + provenance + acceptance / all requirements)",
        "evidence": {"requirements": len(requirements), "traced": len(traced)},
    }


def _method_claims(payload: dict) -> dict:
    claims = rv.unsupported_claims(payload)
    return {
        "name": "unsupported_claim_avoidance",
        "score": _clamp(10.0 - 3.0 * len(claims)),
        "max": 10,
        "method": "10 - 3 per unverified capability claim (floor 0)",
        "evidence": claims,
    }


def evaluate(payload: object, *, source: str = "unknown",
             validation: dict | None = None) -> dict:
    """Score a game specification on ten fixed categories (0-100 total)."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    normalised = rv.normalise(payload)
    check = validation or rv.validate_game_spec(normalised, source=source)
    categories = [
        _method_completeness(normalised),
        _method_consistency(normalised),
        _method_gameplay(normalised),
        _method_technical(normalised),
        _method_engine(normalised),
        _method_performance(normalised),
        _method_assets(normalised),
        _method_testability(normalised),
        _method_traceability(normalised),
        _method_claims(normalised),
    ]
    total = round(sum(item["score"] for item in categories), 2)
    weakest = sorted(categories, key=lambda item: item["score"])[:3]
    recommendations = []
    for category in weakest:
        if category["score"] < 7.0:
            recommendations.append(
                f"Improve {category['name']}: {category['method']}.")
    if check.get("contradictions"):
        recommendations.append("Resolve contradictions before approval.")
    if check.get("unsupported_claims"):
        recommendations.append("Confirm or remove unverified capability claims.")
    if check.get("ambiguous_requirements"):
        recommendations.append("Rewrite subjective acceptance criteria as measurable checks.")

    grade = ("strong" if total >= 85 else "usable_with_review" if total >= 65
             else "weak" if total >= 40 else "not_usable")
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "scores": categories,
        "total_score": total,
        "max_score": MAX_SCORE,
        "grade": grade,
        "missing_requirements": check.get("missing_fields") or [],
        "contradictions": check.get("contradictions") or [],
        "unsupported_claims": check.get("unsupported_claims") or [],
        "ambiguous_requirements": check.get("ambiguous_requirements") or [],
        "schema_errors": check.get("errors") or [],
        "human_review_recommendations": recommendations,
        "requires_human_review": True,
        "human_approved": False,
        "single_response_evidence_only": True,
        "general_intelligence_claimed": False,
        "live_model_evaluated": source == "ai_provider",
        "note": ("A single response cannot demonstrate general AI intelligence. This "
                 "rubric measures completeness, coherence and testability only; it "
                 "does not prove fun, artistic quality or production readiness."),
    }
