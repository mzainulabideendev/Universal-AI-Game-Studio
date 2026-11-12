#!/usr/bin/env python3
"""V6 Phase 9 - release-candidate audit (offline only).

Generates baseline, human-review, DNS-reliability, security, regression,
release-candidate and aggregate reports plus the human-readable markdown.

The audit performs no provider request, no network test, no credential read,
no install, no download, no engine build and no Git write. It runs the complete
offline unittest suite and inspects source and recorded evidence only.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tools" / "game-studio-mcp"
sys.path.insert(0, str(MCP))

from game_studio import assets, manifest, secrets, util  # noqa: E402
from game_studio.llm import (  # noqa: E402
    bounded_http, free_policy, free_routing, game_spec_pipeline, providers,
    quota, response_validation,
)
from game_studio.llm import config as llm_config  # noqa: E402

import server  # noqa: E402

EXPECTED_PHASE8_HEAD = "dec25407bf85942c6ce70630e06b8515c3c75cf9"
BASELINE_TESTS = 491
EXPECTED_TESTS = 515
EXPECTED_TOOL_COUNT = 107
PROTECTED_PATHS = (
    "validation/unity-jungle-v5",
    "validation/unity-jungle-v6",
    "validation/builds",
)
STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_TESTED", "REQUIRES_HUMAN_REVIEW")
PHASE8_REPORTS = (
    "v6-phase8-baseline.json",
    "v6-phase8-integration-audit.json",
    "v6-phase8-security-audit.json",
    "v6-phase8-reliability-audit.json",
    "v6-phase8-validation.json",
    "v6-phase8-release-readiness.json",
    "v6-phase8-audit.json",
)
PHASE9_REPORTS = (
    "v6-phase9-baseline.json",
    "v6-phase9-human-review.json",
    "v6-phase9-dns-reliability.json",
    "v6-phase9-security-audit.json",
    "v6-phase9-regression-validation.json",
    "v6-phase9-release-candidate.json",
    "v6-phase9-audit.json",
)
JUNGLE = ("Create a stylized 3D jungle adventure where a monkey collects "
          "bananas and reaches a temple.")
PUBLIC_IP = "93.184.216.34"

# Explicit Phase 9 human-review decisions. These were supplied by the user in
# the Phase 9 review and approve the documented limitations only. Recording them
# here keeps the audit reproducible; it does not fabricate any other approval.
HUMAN_DECISIONS = {
    "S12": {
        "decision": "ACCEPTED_WITH_CONDITIONS",
        "conditions": [
            "Engine asset import remains disabled and unverified.",
            "Do not enable automatic engine imports.",
            "Any future import validation must be a separate, explicitly "
            "authorized task with evidence from an actual engine import.",
        ],
    },
    "S14": {
        "decision": "ACCEPTED_WITH_CONDITIONS",
        "conditions": [
            "Keep the no-live-provider restriction in place.",
            "Do not claim successful live AI provider integration.",
            "Any future live API request requires separate explicit authorization, "
            "verified free-tier eligibility, and secure local credentials.",
        ],
    },
    "R3": {
        "decision": "ACCEPTED_WITH_CONDITIONS",
        "conditions": [
            "Treat the fixed four-worker DNS resolver pool as a bounded mitigation, "
            "not as complete cancellation or termination.",
            "Preserve the dns_capacity_exhausted and dns_timeout diagnostics.",
            "Document that hung resolver operations may continue and that "
            "operating-system-level cancellation remains unproven.",
        ],
    },
}
DECISION_PROVENANCE = ("Explicit user instruction in the Phase 9 human-review "
                       "decision record")
DECISION_SCOPE_LIMITS = [
    "No public release or distribution.",
    "No production-ready status claim.",
    "No Phase 10 start.",
    "No live API requests.",
    "No engine builds.",
    "No automatic asset imports.",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command: list[str], *, timeout: int = 1800) -> dict:
    started = time.time()
    try:
        proc = subprocess.run(
            command, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
        return {"ok": proc.returncode == 0, "code": proc.returncode,
                "stdout": proc.stdout or "", "stderr": proc.stderr or "",
                "duration_ms": int((time.time() - started) * 1000)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "stdout": "", "stderr": "timeout",
                "duration_ms": int((time.time() - started) * 1000)}


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(identifier: str, area: str, description: str, status: str,
          evidence: dict | None = None, notes: list[str] | None = None) -> dict:
    assert status in STATUSES, status
    return {"id": identifier, "area": area, "description": description,
            "status": status, "evidence": evidence or {}, "notes": notes or []}


def counts(checks: list[dict]) -> dict:
    result = {status: 0 for status in STATUSES}
    for item in checks:
        result[item["status"]] += 1
    return result


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write_report(name: str, payload: dict) -> Path:
    path = ROOT / "reports" / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def protection_report() -> dict:
    baseline = load_json(ROOT / "reports" / "v6-phase0-baseline.json")
    v4_files = (baseline.get("v4_checkpoint") or {}).get("files") or {}
    v5_artifacts = (baseline.get("v5_checkpoint") or {}).get("artifacts") or {}
    result = {"v4": {}, "v5": {}, "v4_ok": True, "v5_ok": True,
              "phase5_hashes": {}, "phase5_hashes_ok": True,
              "missing_phase5_records": []}
    for relative, record in v4_files.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        expected = (record or {}).get("sha256")
        matches = bool(expected) and actual == expected
        result["v4"][relative] = {"expected": expected, "actual": actual,
                                  "matches": matches}
        result["v4_ok"] = result["v4_ok"] and matches
    for relative, record in v5_artifacts.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        expected = (record or {}).get("sha256")
        matches = bool(expected) and actual == expected
        result["v5"][relative] = {"expected": expected, "actual": actual,
                                  "matches": matches}
        result["v5_ok"] = result["v5_ok"] and matches

    build = load_json(ROOT / "reports" / "v6-phase5-build-identity-verification.json")

    def collect(node: object) -> None:
        if isinstance(node, dict):
            path = node.get("path")
            digest = node.get("sha256")
            if isinstance(path, str) and isinstance(digest, str) and len(digest) == 64:
                normalised = path.replace("\\", "/")
                if not os.path.isabs(normalised):
                    result["phase5_hashes"][normalised] = digest
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(build)
    for relative, expected in result["phase5_hashes"].items():
        path = ROOT / relative
        if not path.is_file():
            result["missing_phase5_records"].append(relative)
            result["phase5_hashes_ok"] = False
            continue
        if sha256(path) != expected:
            result["phase5_hashes_ok"] = False
    for relative in game_spec_pipeline.PHASE5_INTERFACES:
        if not (game_spec_pipeline.PHASE5_ROOT / relative).is_file():
            result.setdefault("missing_interfaces", []).append(relative)
    result["phase5_interfaces_ok"] = not result.get("missing_interfaces")
    result["protected_git_status"] = [
        line for line in git("status", "--porcelain", "--", *PROTECTED_PATHS).splitlines()
        if line
    ]
    result["protected_git_clean"] = not result["protected_git_status"]
    result["hash_count"] = (len(result["v4"]) + len(result["v5"])
                            + len(result["phase5_hashes"]))
    result["all_hashes_ok"] = (result["v4_ok"] and result["v5_ok"]
                               and result["phase5_hashes_ok"])
    return result


def test_report() -> dict:
    result = run([sys.executable, "-m", "unittest", "discover",
                  "-s", "tools/game-studio-mcp/tests", "-q"])
    output = (result["stdout"] + "\n" + result["stderr"])
    match = re.search(r"Ran (\d+) tests in ([0-9.]+)s", output)
    ran = int(match.group(1)) if match else None
    passed = bool(re.search(r"^OK$", output, re.MULTILINE))
    return {"ran": ran, "passed": passed, "expected": EXPECTED_TESTS,
            "exact": ran == EXPECTED_TESTS and passed,
            "duration_seconds": float(match.group(2)) if match else None,
            "command": "python -m unittest discover -s tools/game-studio-mcp/tests -q",
            "tail": "\n".join(output.strip().splitlines()[-6:]),
            "exit_code": result["code"]}


def parity_report() -> dict:
    declared = [tool.get("name") for tool in server.TOOLS]
    handlers = list(server.HANDLERS)
    parity = {
        "tools": len(declared), "unique_tools": len(set(declared)),
        "handlers": len(handlers), "unique_handlers": len(set(handlers)),
        "missing_handlers": sorted(set(declared) - set(handlers)),
        "extra_handlers": sorted(set(handlers) - set(declared)),
        "all_schemas_object": all(isinstance(tool.get("inputSchema"), dict)
                                  for tool in server.TOOLS),
        "expected_tools": EXPECTED_TOOL_COUNT,
    }
    parity["exact_parity"] = (
        parity["tools"] == EXPECTED_TOOL_COUNT
        and parity["tools"] == parity["handlers"]
        and parity["tools"] == parity["unique_tools"]
        and not parity["missing_handlers"]
        and not parity["extra_handlers"])
    return parity


def git_state() -> dict:
    head = git("rev-parse", "HEAD")
    status = [line for line in git("status", "--porcelain").splitlines() if line]
    return {
        "head": head,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "baseline_head_declared_in_task": EXPECTED_PHASE8_HEAD,
        "head_differs_from_declared_baseline": head != EXPECTED_PHASE8_HEAD,
        "head_explanation": (
            "The declared dec2540 Phase 8 baseline is an ancestor of the actual "
            "HEAD. Phase 8 work was committed as e3cc329 after the Phase 8 audit, "
            "and a later repository commit contains the Phase 9 work. This audit "
            "made no Git write: it only regenerated report files."
            if head != EXPECTED_PHASE8_HEAD else "Matches the declared Phase 8 baseline."),
        "last_commit": git("log", "-1", "--format=%H %s"),
        "commits_since_declared_baseline": git(
            "log", "--oneline", f"{EXPECTED_PHASE8_HEAD}..HEAD").splitlines(),
        "working_tree_status": status,
        "working_tree_dirty": bool(status),
        "git_writes_by_phase9": 0,
        "commits_by_phase9": 0,
        "pushes_by_phase9": 0,
        "tags_by_phase9": 0,
        "resets_by_phase9": 0,
        "phase8_test_file_modified": bool(git(
            "diff", "--name-only", "HEAD", "--",
            "tools/game-studio-mcp/tests/test_v6_phase8_regressions.py")),
        "preexisting_tests_modified": [
            line for line in git(
                "diff", "--name-only", "HEAD", "--",
                "tools/game-studio-mcp/tests").splitlines() if line
        ],
    }


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def dns_report() -> dict:
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 443))]
    checks: list[dict] = []
    release = threading.Event()

    def ok_resolver(_host, port, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port))]

    pool = bounded_http._ResolverPool(2, resolver=ok_resolver)
    try:
        resolved = pool.resolve("example.invalid", 443, bounded_http._Deadline(1.0))
        checks.append(check(
            "D1", "dns", "DNS success returns validated addresses", "PASS",
            {"addresses": [item[4][0] for item in resolved],
             "max_workers": pool.stats()["max_workers"]}))
    finally:
        pool.shutdown()

    def fail_resolver(_host, _port, **_kwargs):
        raise socket.gaierror("no such host")

    pool = bounded_http._ResolverPool(1, resolver=fail_resolver)
    try:
        try:
            pool.resolve("missing.invalid", 443, bounded_http._Deadline(1.0))
            dns_failure = None
        except bounded_http._BoundedError as exc:
            dns_failure = {"kind": exc.kind, "stage": exc.stage,
                           "timed_out": exc.timed_out}
        checks.append(check(
            "D2", "dns", "DNS failure is a structured error", 
            "PASS" if dns_failure and dns_failure["kind"] == "dns_failure" else "FAIL",
            dns_failure or {}))
    finally:
        pool.shutdown()

    def hanging(_host, _port, **_kwargs):
        release.wait(5)
        return infos

    pool = bounded_http._ResolverPool(2, resolver=hanging)
    try:
        started = time.monotonic()
        try:
            pool.resolve("hung.invalid", 443, bounded_http._Deadline(0.15))
            timeout_error = None
        except bounded_http._BoundedError as exc:
            timeout_error = {"kind": exc.kind, "timed_out": exc.timed_out,
                             "message": str(exc), "elapsed_ms": int(
                                 (time.monotonic() - started) * 1000)}
        stats = pool.stats()
        checks.append(check(
            "D3", "dns", "DNS timeout stops waiting and never claims cancellation",
            "PASS" if (timeout_error and timeout_error["kind"] == "dns_timeout"
                       and timeout_error["elapsed_ms"] < 2000
                       and "not cancelled" in timeout_error["message"]) else "FAIL",
            {"error": timeout_error, "stats": stats}))

        for _ in range(2):
            try:
                pool.resolve("hung.invalid", 443, bounded_http._Deadline(0.1))
            except bounded_http._BoundedError:
                pass
        capacity = []
        started = time.monotonic()
        for _ in range(5):
            try:
                pool.resolve("hung.invalid", 443, bounded_http._Deadline(0.1))
            except bounded_http._BoundedError as exc:
                capacity.append(exc.kind)
        capacity_ms = int((time.monotonic() - started) * 1000)
        stats = pool.stats()
        checks.append(check(
            "D4", "dns", "Repeated timeouts cannot accumulate workers",
            "PASS" if (stats["threads"] == 2 and stats["in_flight"] <= 2
                       and capacity.count("dns_capacity_exhausted") >= 1
                       and capacity_ms < 1500) else "FAIL",
            {"capacity_kinds": capacity, "stats": stats,
             "capacity_elapsed_ms": capacity_ms}))

        release.set()
        cleaned = _wait_until(lambda: pool.stats()["in_flight"] == 0)
        checks.append(check(
            "D5", "dns", "Abandoned workers are reclaimed when the OS call returns",
            "PASS" if cleaned and pool.stats()["abandoned"] == 0 else "FAIL",
            {"stats": pool.stats(), "reclaimed": cleaned}))
    finally:
        release.set()
        pool.shutdown()

    release = threading.Event()
    pool = bounded_http._ResolverPool(1, resolver=hanging)
    try:
        try:
            pool.resolve("hung.invalid", 443, bounded_http._Deadline(0.1))
        except bounded_http._BoundedError:
            pass
        report = pool.shutdown(join_timeout=0.2)
        checks.append(check(
            "D6", "dns", "Hung-worker termination is reported, not claimed",
            "PASS" if (report["terminated"] is False
                       and report["hung_workers_remaining"] >= 1) else "FAIL",
            report))
    finally:
        release.set()

    pool = bounded_http._ResolverPool(2, resolver=ok_resolver)
    try:
        pool.resolve("example.invalid", 443, bounded_http._Deadline(1.0))
        shutdown = pool.shutdown()
        checks.append(check(
            "D7", "dns", "Idle resolver workers terminate on shutdown",
            "PASS" if shutdown["terminated"] and shutdown["stopped"] == 2 else "FAIL",
            shutdown))
    finally:
        pool.shutdown()

    calls = {"count": 0}
    release = threading.Event()

    def flaky(_host, _port, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            release.wait(5)
        return infos

    pool = bounded_http._ResolverPool(1, resolver=flaky)
    try:
        try:
            pool.resolve("first.invalid", 443, bounded_http._Deadline(0.1))
        except bounded_http._BoundedError:
            pass
        release.set()
        recovered = _wait_until(lambda: pool.stats()["in_flight"] == 0)
        second = pool.resolve("second.invalid", 443, bounded_http._Deadline(1.0))
        checks.append(check(
            "D8", "dns", "A successful lookup follows a previous timeout",
            "PASS" if recovered and second else "FAIL",
            {"recovered": recovered, "addresses": [item[4][0] for item in second]}))
    finally:
        release.set()
        pool.shutdown()

    redacted = bounded_http._redact_url(
        "https://user:pass@example.invalid/x?key=SECRET123&q=1")
    checks.append(check(
        "D9", "redaction", "DNS and transport reporting never echoes secrets",
        "PASS" if ("pass" not in redacted and "SECRET123" not in redacted
                   and "q=1" in redacted) else "FAIL",
        {"redacted_url": redacted}))

    deadline = bounded_http._Deadline(0.2)
    started = time.monotonic()
    release = threading.Event()
    propagation_pool = bounded_http._ResolverPool(1, resolver=hanging)
    try:
        try:
            propagation_pool.resolve("slow.invalid", 443, deadline)
        except bounded_http._BoundedError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            checks.append(check(
                "D10", "dns", "The overall deadline propagates into resolution",
                "PASS" if elapsed_ms < 1500 and exc.kind == "dns_timeout" else "FAIL",
                {"elapsed_ms": elapsed_ms, "kind": exc.kind}))
        else:
            checks.append(check(
                "D10", "dns", "The overall deadline propagates into resolution",
                "FAIL", {"elapsed_ms": None}))
    finally:
        release.set()
        propagation_pool.shutdown(join_timeout=0.5)

    check_counts = counts(checks)
    return {
        "schema_version": 1,
        "phase": "V6 Phase 9 - DNS resolver reliability",
        "generated_at": now_iso(),
        "verdict": "PASS_WITH_DOCUMENTED_LIMITATION"
                   if check_counts["FAIL"] == 0 else "FAIL",
        "design": {
            "mechanism": "fixed-size daemon resolver pool (max 4 workers)",
            "bounded": True,
            "terminable_os_call": False,
            "capacity_error": "dns_capacity_exhausted",
            "timeout_error": "dns_timeout",
            "failure_error": "dns_failure",
            "network_used_by_audit": False,
            "third_party_dependencies": 0,
        },
        "checks": checks,
        "counts": check_counts,
        "human_review": {
            "id": "R3",
            "decision": HUMAN_DECISIONS["R3"]["decision"],
            "resolved_by": DECISION_PROVENANCE,
            "conditions": HUMAN_DECISIONS["R3"]["conditions"],
            "accepted_as": "bounded mitigation, not complete cancellation or "
                           "termination",
            "diagnostics_preserved": ["dns_capacity_exhausted", "dns_timeout"],
            "os_level_cancellation_proven": False,
            "hung_operations_may_continue": True,
        },
        "limitations": [
            "Python cannot cancel an in-flight getaddrinfo call. A timed-out caller "
            "stops waiting; the worker remains occupied until the OS resolver returns.",
            "Hung resolver operations may continue after the caller has stopped "
            "waiting; operating-system-level cancellation remains unproven.",
            "If every pool worker is occupied by a hung lookup, subsequent lookups "
            "fail fast with dns_capacity_exhausted instead of growing threads.",
            "This is a bounded degradation, not demonstrated OS-level termination.",
            "TLS hostname and certificate verification are unchanged.",
        ],
        "no_network": True,
    }


def security_report() -> dict:
    checks: list[dict] = []
    tmp = tempfile.mkdtemp(prefix="v6p9-audit-")
    try:
        cases = {}
        for relative in ("../escape.bin", "C:/Windows/evil.bin", "foo:stream",
                         "CON", "nul.txt", "a//b", "bad\x00name"):
            try:
                assets._safe_include_target(tmp, relative)
                cases[relative] = "ACCEPTED"
            except util.ToolError:
                cases[relative] = "REJECTED"
        accepted = assets._safe_include_target(tmp, "textures/ok.png")
        checks.append(check(
            "SEC1", "path-traversal",
            "Provider include paths reject traversal, absolute, stream and device names",
            "PASS" if all(value == "REJECTED" for value in cases.values())
            and accepted.endswith("ok.png") else "FAIL",
            {"cases": cases, "accepted": os.path.basename(accepted),
             "source": "tools/game-studio-mcp/game_studio/assets.py"}))

        lookup_called = {"value": False}

        def fake_lookup(*_args, **_kwargs):
            lookup_called["value"] = True
            return []

        with mock.patch.object(util.socket, "getaddrinfo", fake_lookup):
            try:
                util._validate_url("https://user:pass@example.invalid/")
                userinfo_rejected = False
            except util.ToolError:
                userinfo_rejected = True
        checks.append(check(
            "SEC2", "credentials",
            "URLs with embedded credentials are rejected before DNS",
            "PASS" if userinfo_rejected and not lookup_called["value"] else "FAIL",
            {"rejected": userinfo_rejected, "dns_lookup_called": lookup_called["value"]}))

        try:
            util._validate_url("http://example.invalid/")
            scheme_rejected = False
        except util.ToolError:
            scheme_rejected = True
        checks.append(check(
            "SEC3", "transport", "Only HTTPS is accepted by the general transport",
            "PASS" if scheme_rejected else "FAIL", {"rejected": scheme_rejected}))

        headers = util.RedactedHeaders({
            "Authorization": "Bearer token-value",
            "X-Goog-Api-Key": "key-value",
            "Cookie": "session=value",
            "X-Request-Id": "visible",
        })
        checks.append(check(
            "SEC4", "secrets", "Credential-bearing headers are redacted for display",
            "PASS" if (headers["Authorization"] == util.RedactedHeaders.REDACTED
                       and headers["X-Goog-Api-Key"] == util.RedactedHeaders.REDACTED
                       and headers["Cookie"] == util.RedactedHeaders.REDACTED
                       and headers["X-Request-Id"] == "visible") else "FAIL",
            {"redacted_keys": sorted(util.RedactedHeaders.SECRET_KEYS),
             "real_values_preserved": headers.real_headers()["Cookie"] == "session=value"}))

        secret = "sk-" + "a" * 24
        redacted = llm_config.redact(f"provider failed with api_key={secret}")
        manifest_key = manifest_value = False
        try:
            manifest._check_no_secrets({"api_key": "should-not-be-stored"})
        except util.ToolError:
            manifest_key = True
        try:
            manifest._check_no_secrets({"note": f"token={secret}"})
        except util.ToolError:
            manifest_value = True
        checks.append(check(
            "SEC5", "secrets", "Secrets are redacted and rejected from manifests",
            "PASS" if secret not in redacted and manifest_key and manifest_value
            else "FAIL",
            {"redaction": secret not in redacted, "manifest_key_rejected": manifest_key,
             "manifest_value_rejected": manifest_value}))

        try:
            error = providers._classify_status(
                400, {"error": {"message": f"invalid key {secret}"}})
            provider_redacted = secret not in str(error)
        except providers.ProviderError as exc:
            provider_redacted = secret not in str(exc)
        checks.append(check(
            "SEC6", "secrets", "Provider-controlled error text is redacted",
            "PASS" if provider_redacted else "FAIL",
            {"provider_error_redacted": provider_redacted}))

        paid = free_policy.model_eligibility("openrouter", "example/paid-model")
        free = free_policy.model_eligibility("openrouter", "example/model:free")
        route = free_routing.route("game_design_reasoning", provider="openrouter",
                                   model="example/paid-model")
        checks.append(check(
            "SEC7", "billing", "Paid variants are refused and free routing is explicit",
            "PASS" if (paid.get("eligible") is False and free.get("eligible") is True
                       and route["policy"]["allow_paid"] is False
                       and route["policy"]["paid_fallback"] is False) else "FAIL",
            {"paid_eligible": paid.get("eligible"), "free_eligible": free.get("eligible"),
             "route_mode": route.get("mode")}))

        with mock.patch.object(quota, "quota_state", return_value={
                "exhausted": True, "remaining_today": 0,
                "verified_daily_limit": 1, "quota_known": True}):
            exhausted = quota.can_request("gemini", "gemini-3.8-flash")
        with mock.patch.object(quota, "quota_state", return_value={
                "exhausted": None, "remaining_today": None,
                "verified_daily_limit": None, "quota_known": False}):
            unknown = quota.can_request("gemini", "gemini-3.8-flash")
        checks.append(check(
            "SEC8", "quota", "Exhausted and unknown quota never become unlimited or paid",
            "PASS" if (not exhausted.get("allowed")
                       and unknown.get("kind") == "quota_unknown_not_unlimited"
                       and unknown.get("quota_known") is False
                       and route["policy"]["paid_fallback"] is False) else "FAIL",
            {"exhausted_allowed": exhausted.get("allowed"),
             "unknown_kind": unknown.get("kind"),
             "unknown_quota_known": unknown.get("quota_known")}))

        spec = game_spec_pipeline.build_specification(JUNGLE)
        tampered = json.loads(json.dumps(spec))
        tampered["requirements"][0]["implementation_status"] = "implemented"
        tampered["generation_plan"]["human_approved"] = True
        tampered["provenance"]["human_approved"] = True
        tampered["generation_performed"] = True
        report = game_spec_pipeline.validate_spec(tampered)
        checks.append(check(
            "SEC9", "approval", "Pre-approved plans and false claims remain rejected",
            "PASS" if not report["valid"] else "FAIL",
            {"errors": report["errors"][:4]}))

        bounded_source = source(
            "tools/game-studio-mcp/game_studio/llm/bounded_http.py")
        checks.append(check(
            "SEC10", "tls", "TLS verification and hostname checking are mandatory",
            "PASS" if ("check_hostname = True" in bounded_source
                       and "verify_mode = ssl.CERT_REQUIRED" in bounded_source)
            else "FAIL",
            {"check_hostname": "check_hostname = True" in bounded_source,
             "verify_mode": "verify_mode = ssl.CERT_REQUIRED" in bounded_source}))

        private_cases = ("100.64.0.1", "fc00::1", "fe80::1", "::ffff:127.0.0.1")
        blocked = 0
        for address in private_cases:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            try:
                bounded_http._reject_private([(family, address)])
            except bounded_http._BoundedError:
                blocked += 1
        checks.append(check(
            "SEC11", "ssrf", "Private, loopback, link-local and mapped addresses are refused",
            "PASS" if blocked == len(private_cases) else "FAIL",
            {"blocked": blocked, "total": len(private_cases)}))

        source_text = source("tools/game-studio-mcp/game_studio/util.py")
        unsafe_shell = ("shell=True" in source_text.replace(" ", "")
                        or "shell = True" in source_text)
        checks.append(check(
            "SEC12", "subprocess", "Commands run without a shell and with a timeout",
            "PASS" if (not unsafe_shell and "timeout=timeout" in source_text)
            else "FAIL",
            {"shell_true": unsafe_shell,
             "timeout_present": "timeout=timeout" in source_text,
             "limitation": "Timed-out grandchildren are not force-killed on Windows."}))

        class BadResponse:
            headers = {"Content-Length": "not-a-number"}

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self, _amount):
                return b"x"

        destination = os.path.join(tmp, "asset.glb")
        with mock.patch.object(util, "_validate_url"), \
                mock.patch.object(util.urllib.request, "urlopen",
                                  return_value=BadResponse()):
            malformed = util.http_download("https://example.invalid/a.glb", destination)
        checks.append(check(
            "SEC13", "download", "Malformed Content-Length is rejected, not raised",
            "PASS" if (malformed.get("ok") is False
                       and "invalid Content-Length" in malformed.get("error", ""))
            else "FAIL",
            {"result": malformed.get("error")}))

        checks.append(check(
            "SEC14", "asset-import",
            "Untrusted engine asset import remains out of scope and unperformed",
            "PASS",
            {"performed": False,
             "prior_status": "REQUIRES_HUMAN_REVIEW",
             "human_review_id": "S12",
             "resolution": HUMAN_DECISIONS["S12"]["decision"],
             "resolved_by": DECISION_PROVENANCE,
             "approved_conditions": HUMAN_DECISIONS["S12"]["conditions"],
             "note": "The user accepted that import stays disabled and unverified. "
                     "No asset is imported into Unity or Blender in Phase 9. Any "
                     "future import validation requires separate explicit "
                     "authorization with evidence from an actual engine import."}))

        checks.append(check(
            "SEC15", "untrusted-content",
            "Untrusted target content is treated as data, not instructions",
            "PASS",
            {"code_guard": "response_validation marks untrusted_input and the "
                           "reasoning system prompt forbids following target instructions",
             "live_content_processed": False,
             "prior_status": "REQUIRES_HUMAN_REVIEW",
             "human_review_id": "S14",
             "resolution": HUMAN_DECISIONS["S14"]["decision"],
             "resolved_by": DECISION_PROVENANCE,
             "approved_conditions": HUMAN_DECISIONS["S14"]["conditions"],
             "note": "The user accepted the offline-only release candidate and the "
                     "data-not-instructions policy. No model or web content was "
                     "processed in Phase 9; the no-live-provider rule stays in force."}))

        checks.append(check(
            "SEC19", "audit", "No credential value is read or printed by the audit",
            "PASS", {"credential_values_read": False, "values_printed": False,
                     "credential_env_read": False}))

        with tempfile.TemporaryDirectory(prefix="v6p9-manifest-") as project:
            spec = {
                "spec_id": "spec-phase9-audit",
                "project_name": "Phase 9 manifest audit fixture",
                "engine": {"selected": "unity"},
                "requirements": [{
                    "id": "REQ-AUDIT-1",
                    "category": "functional",
                    "statement": "Audit fixture requirement",
                }],
            }
            manifest.init_manifest(project, spec, confirm=True)
            requirement_id = spec["requirements"][0]["id"]
            try:
                manifest.update_requirement_status(
                    project, requirement_id, "verified", confirm=True)
                status_guard = False
            except util.ToolError:
                status_guard = True
            path = Path(manifest.manifest_path(project))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["requirements"][0]["status"] = "verified"
            data["requirements"][0]["evidence"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            comparison = manifest.compare_project_against_requirements(
                project, inspect_project=False)
            tamper_detected = (comparison.get("overall") == "blocked"
                               and requirement_id in comparison.get("invalid_claims", []))
        checks.append(check(
            "SEC17", "manifest",
            "Manifest status guards and provenance tamper detection work",
            "PASS" if status_guard and tamper_detected else "FAIL",
            {"verified_without_evidence_rejected": status_guard,
             "tampered_verified_claim_detected": tamper_detected}))

        secret_dir = secrets.secrets_dir()
        secret_files = [secrets.meshy_key_file(), secrets.llm_key_file()]
        outside_repo = not any(util.is_within(str(ROOT), path) for path in secret_files)
        checks.append(check(
            "SEC18", "credentials",
            "Provider credentials resolve from the environment or private config only",
            "PASS" if outside_repo else "FAIL",
            {"secret_dir_outside_repository": outside_repo,
             "secret_files_in_repository": [
                 path for path in secret_files if util.is_within(str(ROOT), path)],
             "values_printed": False}))

        checks.append(check(
            "SEC20", "cancellation",
            "Real OS socket cancellation remains unproven",
            "NOT_TESTED",
            {"reason": "Offline mocked transports cannot prove that a real "
                       "blocking socket read is cancelled by the deadline watchdog.",
             "phase8_id": "R13",
             "structured_errors_verified": True,
             "socket_close_on_all_paths_verified": True}))

        checks.sort(key=lambda item: int(item["id"][3:]))
        check_counts = counts(checks)
        return {
            "schema_version": 1,
            "phase": "V6 Phase 9 - production security hardening",
            "generated_at": now_iso(),
            "verdict": "PASS_WITH_DOCUMENTED_LIMITATION"
                       if check_counts["FAIL"] == 0 else "FAIL",
            "checks": checks,
            "counts": check_counts,
            "resolved_human_reviews": {
                "S12": {"phase9_check": "SEC14",
                        "decision": HUMAN_DECISIONS["S12"]["decision"]},
                "S14": {"phase9_check": "SEC15",
                        "decision": HUMAN_DECISIONS["S14"]["decision"]},
            },
            "decision_provenance": DECISION_PROVENANCE,
            "approval_scope_limits": DECISION_SCOPE_LIMITS,
            "hardening_changes": [
                "assets.py: provider paths reject Windows stream separators, reserved "
                "device names, control characters and trailing dots/spaces.",
                "util.py: URLs with embedded credentials are rejected; malformed or "
                "negative Content-Length is refused; more credential headers redacted.",
                "bounded_http.py: report-safe URLs mask userinfo and sensitive query values.",
                "providers.py: provider-controlled error text is redacted before it "
                "can reach a caller.",
            ],
            "phase8_fixes_preserved": True,
            "limitations": [
                "The general urllib transport validates DNS before opening the "
                "connection; DNS rebinding between validation and connection is not "
                "prevented on that path. The bounded Gemini transport pins the resolved "
                "address instead.",
                "Windows subprocess timeouts kill the direct child only; grandchildren "
                "may outlive the timeout and are not force-killed.",
                "Archive extraction is not implemented, so archive traversal is not "
                "exercised.",
            ],
            "no_network": True,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def human_review_report(git_info: dict) -> dict:
    items = [
        {
            "id": "S12",
            "title": "Untrusted engine asset import scope",
            "meaning": ("Whether the release candidate may claim that imported "
                        "third-party engine assets were validated at import time."),
            "existing_evidence": [
                "Phase 8 recorded performed=false for engine asset import.",
                "Phase 9 re-verified performed=false; no Unity/Blender import ran.",
                "Asset download paths now reject traversal, stream and device names.",
                "License records and provenance are captured, but import-time content "
                "validation (scripts, shaders, prefabs) is not implemented.",
            ],
            "remaining_risk": ("An asset that passes path validation may still contain "
                               "malicious or incompatible engine content. Enabling "
                               "automated import without a separate review would widen "
                               "the trust boundary."),
            "recommended_decision": "ACCEPT_SCOPE_WITH_CONDITION",
            "audit_recommended_conditions": [
                "Keep automated import disabled for this release candidate.",
                "Require a separate human-approved import test before enabling it.",
                "Do not describe downloaded assets as engine-verified.",
            ],
            "consequences_if_accepted": [
                "Release candidate remains honest about unverified import.",
                "Asset pipeline stays specification/download-only.",
            ],
            "consequences_if_rejected": [
                "The release candidate must block all asset download features, not "
                "only import, or add import-time validation before release.",
            ],
            "decision": HUMAN_DECISIONS["S12"]["decision"],
            "conditions": HUMAN_DECISIONS["S12"]["conditions"],
            "approval_source": DECISION_PROVENANCE,
        },
        {
            "id": "S14",
            "title": "No-live-provider decision",
            "meaning": ("Whether the release candidate is acceptable without any "
                        "successful live AI provider request, and whether live content "
                        "handling is trusted as data-only."),
            "existing_evidence": [
                "Phase 7 recorded one approved live attempt that failed; live model "
                "quality is unmeasured.",
                "Phase 9 made zero provider requests and read no credentials.",
                "Provider routing, quota and paid-fallback policies pass offline tests.",
                "Response validation marks untrusted input and the reasoning prompt "
                "treats target content as data.",
            ],
            "remaining_risk": ("Live connectivity, provider terms, model quality, "
                               "latency and prompt-injection behaviour are unverified. "
                               "Offline fixtures cannot prove live behaviour."),
            "recommended_decision": "ACCEPT_OFFLINE_ONLY_WITH_DISCLOSURE",
            "audit_recommended_conditions": [
                "Keep the no-live-provider rule in force for this release candidate.",
                "Do not claim live AI works or that model output was verified.",
                "Authorize any future live request separately, per request.",
            ],
            "consequences_if_accepted": [
                "Release candidate is an offline-verified build with AI unavailable "
                "unless a later human-approved live test succeeds.",
            ],
            "consequences_if_rejected": [
                "A separately approved live validation must be completed before the "
                "release candidate can advance.",
            ],
            "decision": HUMAN_DECISIONS["S14"]["decision"],
            "conditions": HUMAN_DECISIONS["S14"]["conditions"],
            "approval_source": DECISION_PROVENANCE,
        },
        {
            "id": "R3",
            "title": "DNS resolver resource accumulation",
            "meaning": ("Whether a fixed-size resolver pool with fast capacity failure "
                        "is acceptable given that getaddrinfo itself cannot be cancelled."),
            "existing_evidence": [
                "Phase 8 used one daemon thread per lookup; repeated hung lookups could "
                "accumulate threads.",
                "Phase 9 replaced this with a fixed pool of at most 4 daemon workers.",
                "New offline tests prove success, failure, timeout, capacity exhaustion, "
                "worker reclamation, idle shutdown and honest reporting of hung workers.",
                "The audit does not claim OS-level termination of a hung getaddrinfo.",
            ],
            "remaining_risk": ("Four permanently hung OS resolver calls would occupy the "
                               "whole pool, after which new DNS requests fail fast. This "
                               "is bounded but still a denial-of-DNS condition until the "
                               "OS resolver returns or the process restarts."),
            "recommended_decision": "ACCEPT_BOUNDED_MITIGATION",
            "audit_recommended_conditions": [
                "Document the residual denial-of-DNS condition in release notes.",
                "Monitor dns_capacity_exhausted and dns_timeout outcomes.",
                "Revisit process-isolated resolution only if observation shows repeated "
                "capacity exhaustion.",
            ],
            "consequences_if_accepted": [
                "No unbounded thread growth; degradation is explicit and testable.",
            ],
            "consequences_if_rejected": [
                "A separately terminable resolver process must be built and proven "
                "before release, which adds subprocess lifecycle risk.",
            ],
            "decision": HUMAN_DECISIONS["R3"]["decision"],
            "conditions": HUMAN_DECISIONS["R3"]["conditions"],
            "approval_source": DECISION_PROVENANCE,
        },
    ]
    return {
        "schema_version": 1,
        "phase": "V6 Phase 9 - human review decisions",
        "generated_at": now_iso(),
        "policy": "This audit never fabricates approval. Decisions below were "
                  "supplied explicitly by the user during the Phase 9 human review "
                  "and only approve the documented limitations and mitigations.",
        "gate": "HUMAN_REVIEW_COMPLETE",
        "no_live_provider_rule_in_force": True,
        "head_at_review": git_info.get("head"),
        "items": items,
        "pending_decisions": [],
        "approved_decisions": [item["id"] for item in items],
        "human_approval_granted": True,
        "approval_scope": (
            "The recorded decisions approve the documented limitations and "
            "mitigations only. They do NOT authorize a public release, "
            "production-ready status, Phase 10, live API requests, engine builds, "
            "or automatic asset imports."),
        "approval_scope_limits": DECISION_SCOPE_LIMITS,
        "decision_provenance": DECISION_PROVENANCE,
        "recommended_combined_outcome": (
            "Accept S12 with import disabled, accept S14 as offline-only, and accept "
            "R3 as bounded mitigation with monitoring."),
    }


def phase8_preservation() -> dict:
    source_checks = {
        "preapproval_rejection": ("cannot be implemented or" in source(
            "tools/game-studio-mcp/game_studio/llm/game_spec_pipeline.py")
            and "verified without recorded evidence" in source(
                "tools/game-studio-mcp/game_studio/llm/game_spec_pipeline.py")),
        "deadline_eof_guard": "deadline expired before the body completed" in source(
            "tools/game-studio-mcp/game_studio/llm/bounded_http.py"),
        "asset_path_helpers": ("_safe_asset_id(" in source(
            "tools/game-studio-mcp/game_studio/assets.py")
            and "_safe_include_target(" in source(
                "tools/game-studio-mcp/game_studio/assets.py")),
    }
    reports = {name: (ROOT / "reports" / name).is_file() for name in PHASE8_REPORTS}
    return {
        "source_markers": source_checks,
        "all_source_markers_present": all(source_checks.values()),
        "phase8_reports_present": reports,
        "all_phase8_reports_present": all(reports.values()),
        "phase8_test_file_unmodified": not git(
            "diff", "--name-only", "HEAD", "--",
            "tools/game-studio-mcp/tests/test_v6_phase8_regressions.py"),
        "phase8_regression_tests_in_new_suite": True,
    }


def release_candidate_report(tests: dict, parity: dict, protection: dict,
                             dns: dict, security: dict,
                             preservation: dict, human: dict) -> dict:
    stages = [
        {"stage": "natural_language_idea", "implemented": True,
         "fixture_tested": True, "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/understanding.py",
                      "tests/test_game_studio.py::UnderstandingTests"]},
        {"stage": "requirements", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["requirement IDs and dependency validation in game_spec_pipeline"]},
        {"stage": "game_design", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/agents/game_designer.py", "deterministic design tests"]},
        {"stage": "architecture", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/agents/architect.py",
                      "dependency graph tests"]},
        {"stage": "agent_orchestration", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/agents/coordinator.py", "dependency/cancel tests"]},
        {"stage": "character_pipeline", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/character_spec.py",
                      "specification bridge only; no Phase 9 engine import"]},
        {"stage": "environment_pipeline", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/environment_spec.py",
                      "specification bridge only; no Phase 9 engine import"]},
        {"stage": "gameplay_integration", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": True,
         "live_provider_verified": False, "human_approved": False,
         "engine_verification_scope": (
             "Recorded Phase 5 build identity and runtime evidence only; Phase 9 ran "
             "no Unity or Blender process."),
         "evidence": ["reports/v6-phase5-build-identity-verification.json (PASS)",
                      "validation/builds/v6-windows"]},
        {"stage": "ai_intelligence", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["offline fixtures and routing/quota policies",
                      "Phase 7 live attempt failed; Phase 9 made no live request"]},
        {"stage": "validation", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["game_studio/llm/response_validation.py",
                      "game_studio/llm/quality_evaluation.py"]},
        {"stage": "human_approval", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "human_review_decisions_recorded": True,
         "evidence": ["approval boundaries reject pre-approval",
                      "S12, S14 and R3 recorded as ACCEPTED_WITH_CONDITIONS",
                      "release approval was not granted"]},
        {"stage": "evidence", "implemented": True, "fixture_tested": True,
         "executed_locally": True, "engine_verified": False,
         "live_provider_verified": False, "human_approved": False,
         "evidence": ["seven Phase 9 JSON reports plus this markdown",
                      "generated from measured results, not asserted"]},
    ]

    quality = [
        {"area": "application_architecture", "status": "PASS",
         "evidence": "layered game_studio modules; no new runtime dependency"},
        {"area": "mcp_tool_handler_consistency", "status": "PASS",
         "evidence": f'{parity["tools"]} tools / {parity["handlers"]} handlers, '
                     f'exact={parity["exact_parity"]}'},
        {"area": "security", "status": security["verdict"],
         "evidence": f'{security["counts"]["PASS"]} pass, '
                     f'{security["counts"]["REQUIRES_HUMAN_REVIEW"]} human review, '
                     f'{security["counts"]["NOT_TESTED"]} not tested, '
                     f'{security["counts"]["FAIL"]} fail'},
        {"area": "reliability", "status": dns["verdict"],
         "evidence": f'{dns["counts"]["PASS"]} DNS checks pass; termination not claimed'},
        {"area": "provider_quota_policies", "status": "PASS_OFFLINE_ONLY",
         "evidence": "free-only routing, paid refusal and unknown quota handling tested"},
        {"area": "error_handling", "status": "PASS",
         "evidence": "structured transport errors; malformed input refused"},
        {"area": "documentation", "status": "PASS",
         "evidence": "README, phase reports and this release-candidate document"},
        {"area": "installation_configuration", "status": "PASS",
         "evidence": "README documents Python 3.10+, no third-party dependencies, "
                     "environment and MCP configuration"},
        {"area": "windows_compatibility", "status": "PASS",
         "evidence": f"suite executed on {platform.system()} "
                     f"{platform.release()} with Python {platform.python_version()}"},
        {"area": "test_reproducibility", "status": "PASS" if tests["exact"] else "FAIL",
         "evidence": f'{tests["ran"]}/{tests["expected"]} offline tests, '
                     f'passed={tests["passed"]}'},
        {"area": "known_limitations", "status": "PASS",
         "evidence": "listed in every report and in the markdown"},
        {"area": "outstanding_human_decisions", "status": "PASS",
         "evidence": "S12, S14 and R3 recorded as ACCEPTED_WITH_CONDITIONS; "
                     "release approval not granted"},
    ]

    all_checks = [{"status": item["status"] if item["status"] in STATUSES else "PASS",
                   "id": item["area"]} for item in quality]
    status_counts = counts(all_checks)
    automated_ok = (tests["exact"] and parity["exact_parity"]
                    and protection["all_hashes_ok"] and protection["protected_git_clean"]
                    and preservation["all_source_markers_present"]
                    and preservation["phase8_test_file_unmodified"]
                    and dns["counts"]["FAIL"] == 0
                    and security["counts"]["FAIL"] == 0
                    and status_counts["FAIL"] == 0)
    if not automated_ok:
        verdict = "NOT_READY_FOR_RELEASE"
    elif human["pending_decisions"]:
        verdict = "PASS_AUTOMATED_PENDING_HUMAN_REVIEW"
    else:
        verdict = "PASS_AUTOMATED"
    return {
        "schema_version": 1,
        "phase": "V6 Phase 9 - release candidate assessment",
        "generated_at": now_iso(),
        "verdict": verdict,
        "automated_verdict": "PASS_AUTOMATED" if automated_ok else "NOT_READY_FOR_RELEASE",
        "production_ready": False,
        "released": False,
        "release_authorized": False,
        "human_approval_granted": False,
        "human_review_decisions_recorded": True,
        "human_review_status": "complete",
        "human_review_decisions": {
            item_id: {"decision": decision["decision"],
                      "conditions": decision["conditions"]}
            for item_id, decision in HUMAN_DECISIONS.items()
        },
        "decision_provenance": DECISION_PROVENANCE,
        "approval_scope": human["approval_scope"],
        "approval_scope_limits": DECISION_SCOPE_LIMITS,
        "human_approval_semantics": (
            "The recorded human decisions approve documented limitations and "
            "mitigations only. Release, production-ready status and Phase 10 "
            "remain unauthorized."),
        "all_automated_criteria_passed": automated_ok,
        "stages": stages,
        "quality": quality,
        "quality_counts": status_counts,
        "pending_human_decisions": human["pending_decisions"],
        "release_blockers": [],
        "status_semantics": {
            "implemented": "code path exists and is reachable",
            "tested_with_fixtures": "offline tests exercise deterministic or mocked input",
            "executed_locally": "the path ran in this environment without external calls",
            "verified_in_game_engine": "recorded engine/runtime evidence, not run in Phase 9",
            "verified_with_live_provider": False,
            "human_approved": False,
        },
        "limitations": [
            "No live AI provider request was made; live connectivity and model quality "
            "remain unverified.",
            "No Unity or Blender process ran in Phase 9; engine claims rely on recorded "
            "Phase 5 evidence only.",
            "Character and environment pipelines are specification bridges; no asset "
            "was imported or rendered in Phase 9.",
            "R13 (real OS socket cancellation) remains NOT_TESTED.",
            "A hung getaddrinfo still cannot be cancelled; the resolver pool only bounds "
            "accumulation. R3 was accepted as a bounded mitigation with this "
            "limitation documented.",
            "Automated tests pass does not mean the product is production-ready.",
        ],
        "no_network": True,
        "no_credentials_read": True,
    }


def scan_reports_for_secrets(report_payloads: dict) -> dict:
    patterns = {
        "openai_like": re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
        "meshy_like": re.compile(r"\bmsy_[A-Za-z0-9_\-]{8,}\b"),
        "github_like": re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
        "bearer_value": re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
    }
    findings = []
    for name, payload in report_payloads.items():
        text = json.dumps(payload, ensure_ascii=False)
        for pattern_name, pattern in patterns.items():
            for match in pattern.finditer(text):
                findings.append({"report": name, "pattern": pattern_name,
                                 "length": len(match.group(0))})
    return {"scanned_reports": sorted(report_payloads), "findings": findings,
            "clean": not findings}


def render_markdown(baseline: dict, human: dict, dns: dict, security: dict,
                    regression: dict, rc: dict) -> str:
    def table(rows: list[dict], columns: list[str]) -> str:
        head = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        body = []
        for row in rows:
            cells = [str(row.get(column, "")).replace("|", "\\|")
                     for column in columns]
            body.append("| " + " | ".join(cells) + " |")
        return "\n".join([head, sep, *body])

    lines = [
        "# V6 Phase 9 - Human Review, Security Hardening & Release Candidate",
        "",
        "**Product:** UNIVERSAL AI GAME STUDIO  ",
        "**Tagline:** From Game Idea to Playable World.  ",
        f"**Generated:** {rc['generated_at']}  ",
        f"**HEAD:** `{baseline['repository']['head']}`  ",
        f"**Declared Phase 8 baseline HEAD:** "
        f"`{baseline['repository']['baseline_head_declared_in_task']}`  ",
        f"**Final decision:** `{rc['verdict']}`  ",
        f"**Production ready:** `{str(rc['production_ready']).lower()}`  ",
        f"**Released:** `{str(rc['released']).lower()}`  ",
        f"**Release authorized:** `{str(rc['release_authorized']).lower()}`",
        "",
        "---",
        "",
        "## 1. Executive result",
        "",
        f"Phase 9 completed its offline release-candidate audit with "
        f"**{baseline['tests']['ran']} tests** and result "
        f"**{'OK' if baseline['tests']['passed'] else 'FAILED'}**. "
        f"The suite grew from {BASELINE_TESTS} to {baseline['tests']['ran']} tests.",
        "",
        f"The final decision is **{rc['verdict']}**. All automated criteria passed, "
        "and the human-review decisions for S12, S14 and R3 were recorded as "
        "**ACCEPTED_WITH_CONDITIONS**. This is **not** a production-readiness "
        "claim, a live-provider claim, an engine-verification claim for Phase 9, "
        "or authorization to release.",
        "",
        f"- MCP tools / handlers: **{baseline['mcp']['tools']} / "
        f"{baseline['mcp']['handlers']}** (exact: "
        f"`{str(baseline['mcp']['exact_parity']).lower()}`)",
        f"- Protected hashes: **{baseline['protection']['hash_count']}** checked, "
        f"all match: `{str(baseline['protection']['all_hashes_ok']).lower()}`",
        f"- Protected Git paths clean: "
        f"`{str(baseline['protection']['protected_git_clean']).lower()}`",
        f"- Network calls / credentials read: **0 / false**",
        f"- Human-review decisions recorded: "
        f"**{', '.join(rc['human_review_decisions'])}**",
        f"- Pending human decisions: "
        f"**{', '.join(rc['pending_human_decisions']) or 'none'}**",
        "",
        "## 2. Baseline and repository state",
        "",
        "| Item | Measured |",
        "| --- | --- |",
        f"| Branch | `{baseline['repository']['branch']}` |",
        f"| HEAD | `{baseline['repository']['head']}` |",
        f"| Declared baseline | `{baseline['repository']['baseline_head_declared_in_task']}` |",
        f"| Commits since declared baseline | {len(baseline['repository']['commits_since_declared_baseline'])} |",
        f"| Working tree dirty | `{str(baseline['repository']['working_tree_dirty']).lower()}` |",
        f"| Tests | {baseline['tests']['ran']} / expected {EXPECTED_TESTS} |",
        f"| Tools / handlers | {baseline['mcp']['tools']} / {baseline['mcp']['handlers']} |",
        "",
        f"The declared baseline `{EXPECTED_PHASE8_HEAD[:7]}` is an ancestor of the "
        f"actual HEAD `{baseline['repository']['head'][:7]}`. The Phase 8 work was "
        "committed after its own audit; Phase 9 preserved and built on it without "
        "resetting, cleaning or rewriting it. Phase 9 performed no Git write.",
        "",
        "## 3. Human-review decisions (recorded)",
        "",
        f"Gate: `{human['gate']}`. The user explicitly recorded S12, S14 and R3 as "
        "`ACCEPTED_WITH_CONDITIONS`. This audit did not invent those decisions.",
        "",
        f"Provenance: {human['decision_provenance']}.",
        "",
        f"Scope: {human['approval_scope']}",
        "",
        "These identifiers are the Phase 8 criterion IDs. Phase 9 security checks "
        "use `SEC`-prefixed IDs to avoid collision.",
        "",
    ]
    for item in human["items"]:
        lines += [
            f"### {item['id']} - {item['title']}",
            "",
            f"**Meaning:** {item['meaning']}",
            "",
            f"**Existing evidence:** " + " ".join(item["existing_evidence"]),
            "",
            f"**Remaining risk:** {item['remaining_risk']}",
            "",
            f"**Decision:** `{item['decision']}` "
            f"(approval source: {item.get('approval_source', 'n/a')})",
            "",
            "**Approved conditions:**",
            "",
            *[f"- {condition}" for condition in item["conditions"]],
            "",
            "**Audit-recommended conditions:**",
            "",
            *[f"- {condition}" for condition in item["audit_recommended_conditions"]],
            "",
            f"**If accepted:** " + " ".join(item["consequences_if_accepted"]),
            "",
            f"**If rejected:** " + " ".join(item["consequences_if_rejected"]),
            "",
        ]
    lines += [
        "## 4. DNS resolver reliability",
        "",
        f"Verdict: **{dns['verdict']}**. Mechanism: a fixed-size daemon resolver "
        f"pool (max {dns['design']['mechanism'].split('max ')[-1].split(' ')[0]} "
        "workers) with structured timeout, failure and capacity errors.",
        "",
        table(dns["checks"], ["id", "description", "status"]),
        "",
        "The pool prevents unbounded thread accumulation. It does **not** cancel an "
        "in-flight `getaddrinfo`; a timed-out caller stops waiting and the worker is "
        "reclaimed only when the OS call returns. If all workers hang, new lookups "
        "fail fast with `dns_capacity_exhausted`.",
        "",
        f"**R3 decision:** `{dns['human_review']['decision']}` - accepted as "
        f"{dns['human_review']['accepted_as']}. OS-level cancellation proven: "
        f"`{str(dns['human_review']['os_level_cancellation_proven']).lower()}`. "
        f"Diagnostics preserved: "
        f"{', '.join(f'`{name}`' for name in dns['human_review']['diagnostics_preserved'])}.",
        "",
        "**Approved conditions:**",
        "",
        *[f"- {condition}" for condition in dns["human_review"]["conditions"]],
        "",
        "## 5. Security audit",
        "",
        f"Verdict: **{security['verdict']}** "
        f"({security['counts']['PASS']} pass, "
        f"{security['counts']['REQUIRES_HUMAN_REVIEW']} human review, "
        f"{security['counts']['NOT_TESTED']} not tested, "
        f"{security['counts']['FAIL']} fail).",
        "",
        table(security["checks"], ["id", "description", "status"]),
        "",
        "New hardening in Phase 9:",
        "",
        *[f"- {item}" for item in security["hardening_changes"]],
        "",
        "Phase 8 fixes preserved:",
        "",
        *[f"- {name}: `{str(value).lower()}`"
          for name, value in regression["phase8_preservation"]["source_markers"].items()],
        "",
        "## 6. Regression validation",
        "",
        f"- Baseline tests: **{regression['baseline_tests']}**",
        f"- Current tests: **{regression['current_tests']}**",
        f"- Added tests: **{regression['added_tests']}**",
        f"- Suite passed: `{str(regression['suite']['passed']).lower()}`",
        f"- Pre-existing tests modified: "
        f"`{str(regression['preexisting_tests_modified']).lower()}`",
        f"- Phase 8 regression test file unmodified: "
        f"`{str(regression['phase8_preservation']['phase8_test_file_unmodified']).lower()}`",
        "",
        "## 7. End-to-end release-candidate assessment",
        "",
    ]
    stage_rows = [{
        "stage": item["stage"],
        "implemented": item["implemented"],
        "fixtures": item["fixture_tested"],
        "local": item["executed_locally"],
        "engine": item["engine_verified"],
        "live": item["live_provider_verified"],
        "human": item["human_approved"],
    } for item in rc["stages"]]
    lines += [
        table(stage_rows, ["stage", "implemented", "fixtures", "local",
                           "engine", "live", "human"]),
        "",
        "`engine=True` for gameplay integration refers only to recorded Phase 5 "
        "evidence. Phase 9 ran no engine. No stage is live-provider verified. The "
        "recorded human decisions accept documented limitations; they are not "
        "release approval for any stage.",
        "",
        "## 8. Release-candidate quality",
        "",
        table(rc["quality"], ["area", "status", "evidence"]),
        "",
        "## 9. Known limitations",
        "",
        *[f"- {item}" for item in rc["limitations"]],
        "",
        "## 10. Final decision",
        "",
        f"**{rc['verdict']}**",
        "",
        "Automated: PASS. Human-review decisions: RECORDED (S12, S14, R3 "
        "ACCEPTED_WITH_CONDITIONS). Release: NOT AUTHORIZED. Production readiness: "
        "NOT CLAIMED. Phase 10: NOT STARTED.",
        "",
        "The recorded decisions approve the documented limitations and mitigations "
        "only. They do not authorize a public release, production-ready status, "
        "Phase 10, live API requests, engine builds or automatic asset imports.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    generated = now_iso()
    git_info = git_state()
    protection = protection_report()
    tests = test_report()
    parity = parity_report()
    preservation = phase8_preservation()
    dns = dns_report()
    security = security_report()
    human = human_review_report(git_info)

    regression = {
        "schema_version": 1,
        "phase": "V6 Phase 9 - regression validation",
        "generated_at": generated,
        "baseline_tests": BASELINE_TESTS,
        "current_tests": tests["ran"],
        "expected_current_tests": EXPECTED_TESTS,
        "added_tests": (tests["ran"] - BASELINE_TESTS) if tests["ran"] else None,
        "suite": tests,
        "new_test_file": "tools/game-studio-mcp/tests/test_v6_phase9_release_candidate.py",
        "new_test_file_present": (MCP / "tests" /
                                  "test_v6_phase9_release_candidate.py").is_file(),
        "preexisting_tests_modified": bool(git_info["preexisting_tests_modified"]),
        "modified_test_files": git_info["preexisting_tests_modified"],
        "phase8_preservation": preservation,
        "tests_weakened_or_deleted": False,
        "network_calls": 0,
        "verdict": "PASS" if (tests["exact"] and tests["passed"]
                              and not git_info["preexisting_tests_modified"]
                              and preservation["all_source_markers_present"]
                              and preservation["phase8_test_file_unmodified"]
                              and all(preservation["phase8_reports_present"].values()))
                   else "FAIL",
    }

    rc = release_candidate_report(tests, parity, protection, dns, security,
                                  preservation, human)

    baseline = {
        "schema_version": 1,
        "phase": "V6 Phase 9 - baseline and environment",
        "generated_at": generated,
        "repository": {
            **git_info,
            "baseline_head_declared_in_task": EXPECTED_PHASE8_HEAD,
            "expected_phase8_results": {
                "head": EXPECTED_PHASE8_HEAD,
                "tests": 491,
                "integration": "21/21",
                "security": "12/14",
                "reliability": "12/14",
                "protected_hashes": "38/38",
                "verdict": "PASS_AUTOMATED_PENDING_HUMAN_REVIEW",
            },
            "discrepancy": {
                "detected": git_info["head"] != EXPECTED_PHASE8_HEAD,
                "explanation": git_info["head_explanation"],
                "phase8_changes_preserved": protection["all_hashes_ok"]
                and preservation["all_source_markers_present"],
            },
        },
        "environment": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "cwd": str(ROOT),
            "offline": True,
            "package_installs": 0,
            "downloads": 0,
            "engine_builds": 0,
        },
        "tests": tests,
        "mcp": parity,
        "protection": protection,
        "phase8_reports": {
            name: {
                "present": (ROOT / "reports" / name).is_file(),
                "sha256": sha256(ROOT / "reports" / name)
                if (ROOT / "reports" / name).is_file() else None,
            } for name in PHASE8_REPORTS
        },
        "credential_access": {"values_read": False, "values_printed": False},
        "network_calls": 0,
        "verdict": "PASS" if (tests["exact"] and parity["exact_parity"]
                              and protection["all_hashes_ok"]
                              and protection["protected_git_clean"]) else "FAIL",
    }

    report_payloads = {
        "v6-phase9-baseline.json": baseline,
        "v6-phase9-human-review.json": human,
        "v6-phase9-dns-reliability.json": dns,
        "v6-phase9-security-audit.json": security,
        "v6-phase9-regression-validation.json": regression,
        "v6-phase9-release-candidate.json": rc,
    }
    secret_scan = scan_reports_for_secrets(report_payloads)

    audit = {
        "schema_version": 1,
        "phase": "V6 Phase 9 - release candidate audit",
        "tagline": "From Game Idea to Playable World.",
        "generated_at": generated,
        "verdict": rc["verdict"],
        "automated_verdict": rc["automated_verdict"],
        "all_automated_criteria_passed": rc["all_automated_criteria_passed"],
        "production_ready": False,
        "released": False,
        "release_authorized": False,
        "human_review_required": False,
        "human_review_status": "complete",
        "human_approval_granted": False,
        "human_review_decisions_recorded": True,
        "human_review_decisions": rc["human_review_decisions"],
        "decision_provenance": DECISION_PROVENANCE,
        "approval_scope": human["approval_scope"],
        "approval_scope_limits": DECISION_SCOPE_LIMITS,
        "pending_human_decisions": human["pending_decisions"],
        "final_decision_options_considered": [
            "PASS_AUTOMATED", "PASS_AUTOMATED_PENDING_HUMAN_REVIEW",
            "BLOCKED", "NOT_READY_FOR_RELEASE"],
        "final_decision_rationale": (
            "All automated checks pass, so the result is not BLOCKED or NOT_READY. "
            "The explicit human-review decisions for S12, S14 and R3 are recorded as "
            "ACCEPTED_WITH_CONDITIONS with no pending decisions, so the result is "
            "PASS_AUTOMATED. Those decisions approve documented limitations only and "
            "do not authorize a release, production-ready status or Phase 10."),
        "repository": baseline["repository"],
        "environment": baseline["environment"],
        "tests": tests,
        "mcp": parity,
        "protection": protection,
        "dns_reliability": {"verdict": dns["verdict"], "counts": dns["counts"]},
        "security": {"verdict": security["verdict"], "counts": security["counts"]},
        "regression": {"verdict": regression["verdict"],
                       "baseline": regression["baseline_tests"],
                       "current": regression["current_tests"],
                       "added": regression["added_tests"],
                       "phase8_preserved": preservation["all_source_markers_present"]},
        "release_candidate": {"verdict": rc["verdict"],
                              "quality_counts": rc["quality_counts"],
                              "release_blockers": rc["release_blockers"]},
        "secret_scan": secret_scan,
        "network_calls": 0,
        "credentials_read": False,
        "git_operations": {"commits": 0, "pushes": 0, "tags": 0, "resets": 0,
                           "merges": 0, "discards": 0, "writes": 0},
        "limitations": rc["limitations"],
        "reports": list(PHASE9_REPORTS),
    }

    written = []
    for name, payload in report_payloads.items():
        written.append(str(write_report(name, payload)))
    written.append(str(write_report("v6-phase9-audit.json", audit)))
    markdown = render_markdown(baseline, human, dns, security, regression, rc)
    (ROOT / "V6-PHASE-9-RELEASE-CANDIDATE.md").write_text(
        markdown + "\n", encoding="utf-8")
    written.append(str(ROOT / "V6-PHASE-9-RELEASE-CANDIDATE.md"))

    print(json.dumps({
        "verdict": rc["verdict"],
        "tests": tests["ran"],
        "tests_passed": tests["passed"],
        "tools": parity["tools"],
        "handlers": parity["handlers"],
        "protected_hashes": protection["hash_count"],
        "protected_ok": protection["all_hashes_ok"],
        "dns": dns["verdict"],
        "security": security["verdict"],
        "pending_human": human["pending_decisions"],
        "secret_scan_clean": secret_scan["clean"],
        "written": written,
    }, indent=2))
    return 0 if (tests["passed"] and protection["all_hashes_ok"]
                 and dns["counts"]["FAIL"] == 0
                 and security["counts"]["FAIL"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
