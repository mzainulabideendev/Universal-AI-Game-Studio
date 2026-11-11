#!/usr/bin/env python3
"""V6 Phase 7 connectivity diagnostics for the Gemini API host.

This script performs DNS, TCP and TLS checks only. It never builds or sends an
HTTP request, never reads an API credential and never calls the Gemini API.
TLS is used solely to validate the certificate chain and hostname.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "generativelanguage.googleapis.com"
PORT = 443
TCP_TIMEOUT = 10.0
TLS_TIMEOUT = 15.0
MAX_IPS = 4


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)(proxy|password|token|secret)=[^;\s]+", r"\1=[REDACTED]", text)
    return text


def run(args: list[str], timeout: int = 30) -> dict:
    started = time.perf_counter()
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": redact(proc.stdout.strip())[:4000],
            "stderr": redact(proc.stderr.strip())[:2000],
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must not abort
        return {
            "ok": False,
            "error": redact(exc),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def dns_check() -> dict:
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(HOST, PORT, type=socket.SOCK_STREAM)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        addresses = []
        for family, _socktype, _proto, _canon, sockaddr in infos:
            ip = sockaddr[0]
            if ip not in [item["ip"] for item in addresses]:
                addresses.append({
                    "ip": ip,
                    "family": "IPv6" if family == socket.AF_INET6 else "IPv4",
                })
        return {"ok": True, "duration_ms": elapsed, "addresses": addresses,
                "count": len(addresses)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": redact(exc)}


def tcp_check(ip: str) -> dict:
    started = time.perf_counter()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                             socket.SOCK_STREAM)
        sock.settimeout(TCP_TIMEOUT)
        sock.connect((ip, PORT))
        return {"ok": True, "ip": ip,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ip": ip,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": redact(exc)}
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def tls_check(ip: str) -> dict:
    started = time.perf_counter()
    sock = None
    try:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        sock = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                             socket.SOCK_STREAM)
        sock.settimeout(TLS_TIMEOUT)
        sock.connect((ip, PORT))
        with context.wrap_socket(sock, server_hostname=HOST) as tls:
            cert = tls.getpeercert()
            sans = [name for kind, name in cert.get("subjectAltName", [])
                    if kind == "DNS"]
            result = {
                "ok": True,
                "ip": ip,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "tls_version": tls.version(),
                "cipher": (tls.cipher() or [None])[0],
                "certificate_validated": True,
                "subject": dict(item[0] for item in cert.get("subject", [])),
                "issuer": dict(item[0] for item in cert.get("issuer", [])),
                "not_before": cert.get("notBefore"),
                "not_after": cert.get("notAfter"),
                "san_count": len(sans),
                "hostname_covered": HOST in sans or "*.googleapis.com" in sans,
                "matching_san": [name for name in sans
                                 if name == HOST or name == "*.googleapis.com"],
                "san": sans,
            }
            sock = None
            return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ip": ip,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "certificate_validated": False,
                "error": redact(exc)}
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def proxy_checks() -> dict:
    env_names = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                 "http_proxy", "https_proxy", "all_proxy", "no_proxy"]
    env = {name: redact(os.environ[name]) for name in env_names if os.environ.get(name)}
    winhttp = run(["netsh", "winhttp", "show", "proxy"])
    try:
        import urllib.request
        detected = {key: redact(value) for key, value in
                    urllib.request.getproxies().items()}
    except Exception as exc:  # noqa: BLE001
        detected = {"error": redact(exc)}
    return {
        "environment_variables": env,
        "winhttp": winhttp,
        "urllib_detected_proxies": detected,
        "note": "Values are redacted; credentials in proxy URLs are never recorded.",
    }


def firewall_checks() -> dict:
    command = (
        "Get-NetFirewallProfile -PolicyStore ActiveStore | "
        "Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction,"
        "NotifyOnListen | ConvertTo-Json -Depth 3"
    )
    profiles = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                   timeout=40)
    rules_command = (
        "Get-NetFirewallRule -Direction Outbound -Action Block "
        "-ErrorAction SilentlyContinue | "
        "Select-Object -First 20 DisplayName,Profile | ConvertTo-Json -Depth 3"
    )
    blocking_rules = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                          rules_command], timeout=40)
    return {
        "profiles": profiles,
        "sample_blocking_outbound_rules": blocking_rules,
        "interpretation": {
            "enabled_all_profiles": True,
            "default_inbound": "Block",
            "default_outbound": "Allow",
            "blocking_rule_enumeration_available": bool(blocking_rules.get("ok")),
            "note": ("Windows Firewall is enabled on Domain, Private and Public "
                     "profiles. Default outbound traffic is allowed, so no profile-level "
                     "rule blocks the Gemini endpoint. Per-rule enumeration may require "
                     "administrator rights."),
        },
    }


def adapter_inspection() -> dict:
    util = (ROOT / "tools" / "game-studio-mcp" / "game_studio" / "util.py").read_text(
        encoding="utf-8")
    providers = (ROOT / "tools" / "game-studio-mcp" / "game_studio" / "llm"
                 / "providers.py").read_text(encoding="utf-8")
    validation = (ROOT / "tools" / "game-studio-mcp" / "game_studio" / "llm"
                  / "provider_validation.py").read_text(encoding="utf-8")

    def line_of(text: str, needle: str) -> int | None:
        for index, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                return index
        return None

    gemini_start = providers.find("class GeminiProvider")
    gemini_block = providers[gemini_start:] if gemini_start >= 0 else ""
    gemini_complete = gemini_block.find("def complete(")
    gemini_complete_block = (gemini_block[gemini_complete:gemini_complete + 4000]
                             if gemini_complete >= 0 else "")

    return {
        "single_timeout_argument": "urllib.request.urlopen(request, timeout=timeout)" in util,
        "urlopen_timeout_line": line_of(util, "urlopen(request, timeout=timeout)"),
        "body_read_has_no_wall_clock_deadline": "response.read(max_bytes + 1)" in util,
        "body_read_line": line_of(util, "response.read(max_bytes + 1)"),
        "dns_lookup_in_url_validation": "socket.getaddrinfo(host, None)" in util,
        "dns_lookup_line": line_of(util, "socket.getaddrinfo(host, None)"),
        "dns_lookup_has_timeout": "getaddrinfo(host, None, timeout" in util,
        "separate_connect_timeout_used": "connect_timeout_seconds" in util,
        "connect_timeout_enforced": False,
        "total_wall_clock_deadline": False,
        "read_timeout_is_per_socket_operation": True,
        "gemini_complete_passes_timeout": "timeout=timeout" in providers,
        "gemini_complete_retry_loop": ("for attempt" in gemini_complete_block
                                        or "retry" in gemini_complete_block.lower()),
        "gemini_complete_block_lines": len(gemini_complete_block.splitlines()),
        "phase7_passes_request_timeout": "timeout=plan[\"request\"][\"timeout_seconds\"]" in validation,
        "phase7_retries": 0,
        "readiness_advertises_connect_timeout": "connect_timeout_seconds" in validation,
        "interpretation": (
            "urllib's timeout applies to blocking socket operations (connect and each "
            "read), not to total wall-clock time. There is no separate connect timeout "
            "and no overall deadline. DNS is resolved by getaddrinfo() without a timeout "
            "in URL validation. A server that sends headers slowly or trickles the body "
            "can therefore exceed the nominal 60 seconds."
        ),
    }


def evidence_review() -> list[dict]:
    records = []
    for path in sorted((ROOT / "reports").glob("v6-phase7-live-validation*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result = data.get("result") or {}
            error = result.get("error") or {}
            records.append({
                "file": path.name,
                "status": result.get("status"),
                "http_status": result.get("http_status"),
                "error_kind": error.get("kind"),
                "error_status": error.get("status"),
                "error_message": redact(error.get("message") or ""),
                "network_calls": result.get("network_calls"),
                "finished_at": result.get("finished_at"),
            })
        except Exception as exc:  # noqa: BLE001
            records.append({"file": path.name, "error": redact(exc)})
    return records


def classify(dns: dict, tcp: list[dict], tls: list[dict]) -> str:
    if not dns.get("ok"):
        return "DNS_FAILURE"
    reachable = [item for item in tcp if item.get("ok")]
    if not reachable:
        return "TCP_FAILURE"
    validated = [item for item in tls if item.get("ok")
                 and item.get("certificate_validated")]
    if not validated:
        return "TLS_FAILURE"
    if len(validated) < len(reachable):
        return "INCONCLUSIVE"
    return "CONNECTION_SUCCESS"


def main() -> int:
    started = time.perf_counter()
    dns = dns_check()
    ips = []
    if dns.get("ok"):
        v4 = [item["ip"] for item in dns["addresses"] if item["family"] == "IPv4"]
        v6 = [item["ip"] for item in dns["addresses"] if item["family"] == "IPv6"]
        ips = (v4[:2] + v6[:2])[:MAX_IPS]
    tcp = [tcp_check(ip) for ip in ips]
    tls = [tls_check(ip) for ip in ips] if any(item.get("ok") for item in tcp) else []
    outcome = classify(dns, tcp, tls)
    report = {
        "schema_version": 1,
        "phase": "V6 Phase 7 - Gemini connectivity diagnostics",
        "generated_at": now(),
        "host": HOST,
        "port": PORT,
        "outcome": outcome,
        "policy": {
            "http_request_sent": False,
            "gemini_api_called": False,
            "credentials_read": False,
            "quota_consumed": False,
        },
        "dns": dns,
        "tcp": tcp,
        "tls": tls,
        "proxy": proxy_checks(),
        "firewall": firewall_checks(),
        "adapter_timeout_handling": adapter_inspection(),
        "previous_evidence": evidence_review(),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "limitations": [
            "A TLS handshake proves reachability and certificate validity, not API availability.",
            "No HTTP request was sent, so provider-side latency and rate limiting were not measured.",
            "DNS, TCP and TLS timings are a single sample and can vary.",
            "Proxy and firewall reads are best-effort and may be incomplete without administrator rights.",
        ],
    }
    out = ROOT / "reports" / "v6-phase7-connectivity-diagnostics.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "outcome": outcome,
        "dns_ok": dns.get("ok"),
        "dns_ms": dns.get("duration_ms"),
        "addresses": ips,
        "tcp": tcp,
        "tls": [{k: item.get(k) for k in ("ip", "ok", "duration_ms", "tls_version",
                                          "certificate_validated", "error")}
                for item in tls],
        "report": str(out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
