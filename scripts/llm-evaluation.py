#!/usr/bin/env python3
"""V5 multilingual LLM evaluation harness.

Modes
-----
deterministic  Call the offline vocabulary parser directly.
pipeline       Call the reasoning layer; with no provider it records a labelled
               deterministic fallback. This is the default.
live           Require a configured provider and send real requests. Refuses to
               run when no provider is configured; never falls back silently.

The harness scores intent, requirement extraction, exclusions, technical
reasoning, engine recommendation, clarification quality, structured output and
a heuristic hallucination rate. It never claims a live model was used unless
the reasoning layer reports source == "llm".
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(MCP))

from game_studio import understanding  # noqa: E402
from game_studio.llm import reasoning, schemas  # noqa: E402


COMPONENTS = (
    "genre_recall",
    "genre_precision",
    "dimension",
    "keyword_recall",
    "exclusion_recall",
    "technical",
    "engine",
    "clarification",
    "structure",
    "conflict",
    "non_hallucination",
)


def _lower(value: object) -> str:
    return str(value or "").lower()


def _flatten_requirements(analysis: dict) -> list[dict]:
    reqs = analysis.get("requirements")
    if isinstance(reqs, dict):
        out: list[dict] = []
        for key in ("explicit", "implied", "technical_dependencies", "optional_enhancements"):
            out.extend(reqs.get(key) or [])
        return out
    if isinstance(reqs, list):
        return reqs
    return []


def _extract(result: dict, mode: str) -> dict:
    if result.get("source") == "llm":
        data = result.get("understanding") or {}
        reqs = data.get("requirements") or []
        genres = data.get("genre") or []
        if isinstance(genres, str):
            genres = [genres]
        sub = data.get("subgenre")
        if sub and sub not in genres:
            genres = list(genres) + [sub]
        dimension = data.get("dimension")
        dimensions = [dimension] if isinstance(dimension, str) else list(dimension or [])
        exclusions = data.get("exclusions") or []
        questions = data.get("questions") or []
        conflicts = data.get("conflicts") or []
        engine = data.get("engine_recommendation")
        engine_names = []
        if isinstance(engine, str):
            engine_names = [engine]
        elif isinstance(engine, dict):
            engine_names = [engine.get("engine") or engine.get("selected") or ""]
        technical = [r for r in reqs if _lower(r.get("classification")) == "technical"]
        return {
            "data": data,
            "requirements": reqs,
            "genres": genres,
            "dimensions": dimensions,
            "exclusions": exclusions,
            "questions": questions,
            "conflicts": conflicts,
            "engines": [e for e in engine_names if e],
            "technical_count": len(technical),
        }

    data = result.get("analysis") or {}
    u = data.get("understanding") or {}
    reqs = _flatten_requirements(data)
    exclusions = data.get("exclusions") or []
    excl_values = []
    for item in exclusions:
        if isinstance(item, dict):
            excl_values.append(item.get("value"))
        else:
            excl_values.append(item)
    questions = data.get("questions") or []
    conflicts = data.get("conflicts") or []
    engines = u.get("engine_requested") or []
    return {
        "data": data,
        "requirements": reqs,
        "genres": list(u.get("game_genre") or []),
        "dimensions": list(u.get("dimension") or []),
        "exclusions": [e for e in excl_values if e],
        "questions": questions,
        "conflicts": conflicts,
        "engines": engines,
        "technical_count": len((data.get("requirements") or {}).get("technical_dependencies") or []),
    }


def _requirement_text(extracted: dict) -> str:
    parts = []
    for req in extracted["requirements"]:
        parts.append(_lower(req.get("statement")))
        parts.append(_lower(req.get("source_text")))
        parts.append(_lower(req.get("category")))
    return " ".join(parts)


def _hallucinated(extracted: dict, request: str) -> tuple[int, list[str]]:
    """Heuristic: a requirement is ungrounded when its source text is absent from
    the request and it is not explicitly marked implied/technical."""
    req_lower = _lower(request)
    ungrounded = []
    for req in extracted["requirements"]:
        source = _lower(req.get("source_text"))
        classification = _lower(req.get("classification"))
        if classification in ("implied", "technical", "optional"):
            continue
        if not source or source in req_lower:
            continue
        # Deterministic parser uses these exact placeholders for derived items.
        if source.startswith(("implied", "required by", "technical", "genre")):
            continue
        ungrounded.append(req.get("statement") or source)
    return len(ungrounded), ungrounded


def _structure_ok(result: dict, extracted: dict) -> bool:
    if not result.get("ok"):
        return False
    if not extracted["requirements"]:
        return False
    if result.get("source") == "llm":
        try:
            schemas.validate(extracted["data"], schemas.UNDERSTANDING_SCHEMA)
            return True
        except Exception:
            return False
    data = extracted["data"]
    return bool(data.get("understanding") and data.get("counts"))


def evaluate_case(case: dict, mode: str, live: bool) -> dict:
    request = case["request"]
    if mode == "deterministic":
        raw = understanding.analyze_request(
            request, installed_engines=None, known_platform=case.get("platform")
        )
        raw.pop("_concepts", None)
        raw.pop("_matched", None)
        result = {
            "ok": True,
            "source": "deterministic-fallback",
            "status": "degraded",
            "analysis": raw,
        }
    else:
        result = reasoning.understand_request(
            request,
            platform=case.get("platform"),
            confirm=live,
            allow_fallback=not live,
        )

    extracted = _extract(result, mode)
    detected_genres = [g for g in extracted["genres"] if g]
    expected_genres = list(case.get("expected_genres") or [])

    if case.get("capability_gap"):
        genre_recall = None
        genre_precision = None
    else:
        matched = set(detected_genres) & set(expected_genres)
        genre_recall = len(matched) / len(expected_genres) if expected_genres else 1.0
        genre_precision = len(matched) / len(detected_genres) if detected_genres else 1.0

    expected_dim = case.get("expected_dimension")
    dimension_score = (
        None if expected_dim is None else (1.0 if expected_dim in extracted["dimensions"] else 0.0)
    )

    req_text = _requirement_text(extracted)
    expected_keywords = list(case.get("expected_keywords") or [])
    found_keywords = [k for k in expected_keywords if k.lower().replace("-", " ") in req_text.replace("-", " ")]
    keyword_recall = (
        len(found_keywords) / len(expected_keywords) if expected_keywords else 1.0
    )

    expected_exclusions = list(case.get("expected_exclusions") or [])
    detected_exclusions = {_lower(e) for e in extracted["exclusions"]}
    found_exclusions = [e for e in expected_exclusions if _lower(e) in detected_exclusions]
    exclusion_recall = (
        len(found_exclusions) / len(expected_exclusions) if expected_exclusions else 1.0
    )
    # An excluded concept must not also become an active explicit requirement.
    exclusion_leaks = []
    for ex in expected_exclusions:
        for req in extracted["requirements"]:
            if _lower(req.get("classification")) != "excluded" and ex.lower() in _lower(req.get("statement")):
                exclusion_leaks.append(ex)
                break

    technical_score = None
    if case.get("expects_technical"):
        technical_score = 1.0 if extracted["technical_count"] > 0 else 0.0

    engine_score = None
    if case.get("expect_engine"):
        engine_score = 1.0 if case["expect_engine"] in [e.lower() for e in extracted["engines"]] else 0.0

    question_count = len(extracted["questions"])
    if case.get("expects_questions"):
        clarification = 1.0 if 1 <= question_count <= 5 else 0.0
    elif case.get("fully_specified"):
        # Engine and platform are legitimately material even for a fully
        # specified genre/mechanics request; two questions is acceptable.
        clarification = 1.0 if question_count <= 2 else (0.5 if question_count <= 4 else 0.0)
    else:
        clarification = None

    conflict_score = None
    if case.get("expects_conflict"):
        conflict_score = 1.0 if extracted["conflicts"] else 0.0

    structure = 1.0 if _structure_ok(result, extracted) else 0.0
    hallucinated_count, hallucinated_items = _hallucinated(extracted, request)
    total_reqs = max(1, len(extracted["requirements"]))
    hallucination_rate = hallucinated_count / total_reqs
    non_hallucination = 1.0 - hallucination_rate

    components = {
        "genre_recall": genre_recall,
        "genre_precision": genre_precision,
        "dimension": dimension_score,
        "keyword_recall": keyword_recall,
        "exclusion_recall": exclusion_recall,
        "technical": technical_score,
        "engine": engine_score,
        "clarification": clarification,
        "structure": structure,
        "conflict": conflict_score,
        "non_hallucination": non_hallucination,
    }
    used = [v for v in components.values() if v is not None]
    overall = statistics.mean(used) if used else 0.0

    return {
        "id": case["id"],
        "category": case["category"],
        "request": request,
        "expected": {
            "genres": expected_genres,
            "dimension": expected_dim,
            "keywords": expected_keywords,
            "exclusions": expected_exclusions,
            "engine": case.get("expect_engine"),
        },
        "detected": {
            "genres": detected_genres,
            "dimensions": extracted["dimensions"],
            "keywords": found_keywords,
            "exclusions": sorted(detected_exclusions),
            "engines": extracted["engines"],
            "requirements": len(extracted["requirements"]),
            "technical_requirements": extracted["technical_count"],
            "questions": question_count,
            "conflicts": len(extracted["conflicts"]),
        },
        "scores": components,
        "overall": round(overall, 3),
        "capability_gap": bool(case.get("capability_gap")),
        "gap_note": case.get("gap_note"),
        "exclusion_leaks": exclusion_leaks,
        "hallucinated": {
            "count": hallucinated_count,
            "rate": round(hallucination_rate, 3),
            "items": hallucinated_items[:8],
        },
        "source": result.get("source"),
        "degraded": result.get("degraded", False),
        "fallback_reason": result.get("fallback_reason"),
        "status": result.get("status"),
    }


def summarise(cases: list[dict], meta: dict) -> dict:
    component_means = {}
    for component in COMPONENTS:
        values = [c["scores"][component] for c in cases if c["scores"][component] is not None]
        component_means[component] = round(statistics.mean(values), 3) if values else None
    overall = [c["overall"] for c in cases]
    gaps = [c for c in cases if c["capability_gap"]]
    failures = [c for c in cases if c["overall"] < 0.75]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **meta,
        "case_count": len(cases),
        "capability_gap_count": len(gaps),
        "mean_overall": round(statistics.mean(overall), 3) if overall else None,
        "median_overall": round(statistics.median(overall), 3) if overall else None,
        "min_overall": round(min(overall), 3) if overall else None,
        "max_overall": round(max(overall), 3) if overall else None,
        "component_means": component_means,
        "failures": [{"id": c["id"], "category": c["category"], "overall": c["overall"]} for c in failures],
        "capability_gaps": [
            {"id": c["id"], "category": c["category"], "note": c["gap_note"]} for c in gaps
        ],
        "exclusion_leaks": [
            {"id": c["id"], "leaks": c["exclusion_leaks"]} for c in cases if c["exclusion_leaks"]
        ],
    }


def to_markdown(summary: dict, cases: list[dict]) -> str:
    lines = [
        "# V5 LLM evaluation results",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        f"- Mode: `{summary['mode']}`",
        f"- Source: `{summary['source']}`",
        f"- Live provider: `{summary['live']}`",
        f"- Provider/model: `{summary.get('provider')}` / `{summary.get('model')}`",
        f"- Cases: {summary['case_count']}",
        f"- Mean score: {summary['mean_overall']}",
        "",
        "## Component means",
        "",
        "| Component | Mean |",
        "| --- | --- |",
    ]
    for component, value in summary["component_means"].items():
        lines.append(f"| {component} | {value if value is not None else 'n/a'} |")
    lines += ["", "## Per-case results", "", "| ID | Category | Overall | Genres | Requirements | Questions | Gap |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for case in cases:
        lines.append(
            f"| {case['id']} | {case['category']} | {case['overall']} | "
            f"{', '.join(case['detected']['genres']) or '-'} | {case['detected']['requirements']} | "
            f"{case['detected']['questions']} | {'yes' if case['capability_gap'] else ''} |"
        )
    lines += ["", "## Capability gaps", ""]
    if summary["capability_gaps"]:
        for gap in summary["capability_gaps"]:
            lines.append(f"- **{gap['id']}** ({gap['category']}): {gap['note']}")
    else:
        lines.append("- None recorded.")
    lines += ["", "## Cases below 0.75", ""]
    if summary["failures"]:
        for failure in summary["failures"]:
            lines.append(f"- **{failure['id']}** ({failure['category']}): {failure['overall']}")
    else:
        lines.append("- None.")
    lines += ["", "## Exclusion leaks", ""]
    if summary["exclusion_leaks"]:
        for leak in summary["exclusion_leaks"]:
            lines.append(f"- **{leak['id']}**: {', '.join(leak['leaks'])}")
    else:
        lines.append("- None.")
    lines += [
        "",
        "## Interpretation",
        "",
        "These scores measure the path that actually ran. When `live` is false and",
        "`source` is `deterministic-fallback`, they describe the offline vocabulary",
        "parser, not an LLM. They must not be cited as model-quality evidence.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(ROOT / "validation" / "llm-eval-requests.json"))
    parser.add_argument("--mode", choices=("deterministic", "pipeline", "live"), default="pipeline")
    parser.add_argument("--output", default=str(ROOT / "validation" / "llm-eval-results.json"))
    parser.add_argument("--markdown", default=str(ROOT / "reports" / "llm-eval-summary.md"))
    args = parser.parse_args()

    live = args.mode == "live"
    if live:
        status = reasoning.status()
        if not status.get("configured"):
            print(
                "Refusing --mode live: no provider is configured. "
                "Missing: " + "; ".join(status.get("missing") or ["unknown"]),
                file=sys.stderr,
            )
            return 2

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    cases = [evaluate_case(case, "deterministic" if args.mode == "deterministic" else "pipeline", live)
             for case in dataset["cases"]]

    sources = sorted({c["source"] for c in cases})
    provider = None
    model = None
    if sources == ["llm"]:
        # Re-run a single probe result is not stored; provider/model are in the raw result only.
        provider = "configured"
        model = "configured"
    meta = {
        "mode": args.mode,
        "source": ", ".join(sources),
        "live": bool(live and sources == ["llm"]),
        "provider": provider,
        "model": model,
        "dataset": str(Path(args.dataset).relative_to(ROOT)),
    }
    summary = summarise(cases, meta)
    output = {"summary": summary, "cases": cases}
    Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.markdown).write_text(to_markdown(summary, cases), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote {args.output} and {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
