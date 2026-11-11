"""Small, dependency-free helpers shared by the Game Studio modules."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_TEXT = 60_000
DEFAULT_HTTP_TIMEOUT = 30
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
USER_AGENT = "UniversalAI-GameStudio-MCP/1.0 (+https://github.com/mzainulabideendev/Universal-AI-Game-Studio)"


class RedactedHeaders(dict):
    """Expose redacted values to callers while preserving actual values for HTTP requests."""

    REDACTED = "******"

    def __init__(self, payload: dict | None = None, **kwargs):
        super().__init__()
        self._real = {}
        for source in (payload or {}, kwargs):
            for key, value in dict(source).items():
                self._real[str(key)] = value
                super().__setitem__(str(key), self._redacted_value(key, value))

    def _redacted_value(self, key: str, value: object) -> str:
        if key.lower() == "authorization":
            return self.REDACTED
        if key.lower() in {"x-api-key", "x-goog-api-key", "api-key", "token", "secret"}:
            return self.REDACTED
        return str(value) if value is not None else value

    def real_headers(self) -> dict:
        return dict(self._real)

    def __getitem__(self, key):
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def items(self):
        return dict.items(self)

    def __iter__(self):
        return dict.__iter__(self)

    def keys(self):
        return dict.keys(self)

    def values(self):
        return dict.values(self)

    def copy(self):
        return RedactedHeaders(self._real)


class ToolError(Exception):
    """Raised for expected, user-actionable failures."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def truncate(text: str, limit: int = MAX_TEXT) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [{len(text) - limit} characters truncated]"


def expand(path: str | os.PathLike | None) -> str | None:
    """Expand ~ and environment variables and return an absolute path."""
    if path is None:
        return None
    value = os.path.expandvars(os.path.expanduser(str(path)))
    return os.path.abspath(value)


def require_path(path: str | os.PathLike | None, *, kind: str = "file",
                 label: str = "path") -> str:
    resolved = expand(path)
    if not resolved:
        raise ToolError(f"{label} is required")
    exists = os.path.isfile(resolved) if kind == "file" else os.path.isdir(resolved)
    if not exists:
        raise ToolError(f"{label} does not exist ({kind}): {resolved}")
    return resolved


def is_within(root: str, candidate: str) -> bool:
    try:
        root_real = os.path.realpath(root)
        cand_real = os.path.realpath(candidate)
        return os.path.commonpath([root_real, cand_real]) == root_real
    except (ValueError, OSError):
        return False


def safe_join(root: str, relative: str) -> str:
    """Join a relative path under root, rejecting traversal and absolute paths."""
    if not relative:
        raise ToolError("relative path is required")
    if os.path.isabs(relative) or re.match(r"^[a-zA-Z]:", relative):
        raise ToolError(f"absolute paths are not allowed: {relative}")
    target = os.path.abspath(os.path.join(root, relative))
    if not is_within(root, target):
        raise ToolError(f"path escapes the target root: {relative}")
    return target


def read_text(path: str, limit: int = 4 * 1024 * 1024) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)


def read_json(path: str) -> object:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


def write_json(path: str, payload: object) -> None:
    write_text(path, json.dumps(payload, indent=2, default=str) + "\n")


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _windows_hidden_flags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_command(command: list[str], *, cwd: str | None = None,
                timeout: int = 60, env: dict | None = None) -> dict:
    """Run a process without a shell and return a structured, truncated result."""
    started = time.time()
    merged_env = os.environ.copy()
    if env:
        merged_env.update({k: str(v) for k, v in env.items()})
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=merged_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_windows_hidden_flags(),
        )
        stdout, stderr = proc.stdout or "", proc.stderr or ""
        code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stderr = (stderr + f"\nTimed out after {timeout}s").strip()
        code = None
        timed_out = True
    except OSError as exc:
        return {
            "ok": False,
            "command": command,
            "error": str(exc),
            "duration_ms": int((time.time() - started) * 1000),
        }
    return {
        "ok": code == 0 and not timed_out,
        "command": command,
        "exit_code": code,
        "timed_out": timed_out,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout": truncate(stdout),
        "stderr": truncate(stderr),
    }


def which_first(names: list[str], extra: list[str] | None = None) -> str | None:
    for candidate in extra or []:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    for name in names:
        found = shutil.which(name)
        if found:
            return os.path.abspath(found)
    return None


def first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.exists(path):
            return os.path.abspath(path)
    return None


def sorted_subdirs(path: str) -> list[str]:
    try:
        return sorted(
            (entry.path for entry in os.scandir(path) if entry.is_dir()),
            key=lambda p: os.path.basename(p).lower(),
        )
    except OSError:
        return []


def file_stats(root: str, max_files: int = 250_000) -> dict:
    """Count files by extension without following symlinks or unbounded walking."""
    by_ext: dict[str, int] = {}
    total = 0
    total_bytes = 0
    too_many = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in ("Library", "Temp", "Obj", "Binaries", "Intermediate",
                         "Saved", "DerivedDataCache", "node_modules", ".git")
        ]
        for name in filenames:
            total += 1
            if total > max_files:
                too_many = True
                break
            ext = os.path.splitext(name)[1].lower() or "<none>"
            by_ext[ext] = by_ext.get(ext, 0) + 1
            try:
                total_bytes += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
        if too_many:
            break
    return {
        "files": total,
        "bytes": total_bytes,
        "by_extension": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])[:40]),
        "truncated": too_many,
    }


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
_ALLOWED_SCHEMES = ("https",)


LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def _is_private_ip(ip: str) -> bool:
    """Return True for addresses that must not be reached without allow_local.

    Uses the full address classification instead of string prefixes so that
    carrier-grade NAT (100.64.0.0/10), IPv6 unique-local (fc00::/7), IPv6
    link-local (fe80::/10) and other non-public ranges are also refused.
    """
    try:
        parsed = ipaddress.ip_address(str(ip).split("%", 1)[0])
    except ValueError:
        return True
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        parsed = parsed.ipv4_mapped
    if isinstance(parsed, ipaddress.IPv4Address) and parsed in ipaddress.ip_network(
            "100.64.0.0/10"):
        return True
    return bool(parsed.is_private or parsed.is_loopback or parsed.is_link_local
                or parsed.is_reserved or parsed.is_multicast
                or parsed.is_unspecified)


def _validate_url(url: str, allowed_hosts: list[str] | None = None,
                  allow_local: bool = False) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    scheme_allowed = parsed.scheme == "https" or (
        allow_local and parsed.scheme == "http" and
        (parsed.hostname or "").lower() in LOOPBACK_HOSTS)
    if not scheme_allowed:
        raise ToolError(f"only https URLs are allowed: {url}")
    if not parsed.hostname:
        raise ToolError(f"URL has no host: {url}")
    host = parsed.hostname.lower()
    if allowed_hosts and not any(host == allowed or host.endswith("." + allowed)
                                 for allowed in allowed_hosts):
        raise ToolError(
            f"host {host!r} is not in the allow-list {sorted(allowed_hosts)}"
        )
    if allow_local and host in LOOPBACK_HOSTS:
        return parsed
    # Reject obvious SSRF targets. DNS names are still resolved below.
    try:
        resolved = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ToolError(f"cannot resolve {host}: {exc}") from exc
    for info in resolved:
        ip = info[4][0]
        if _is_private_ip(ip):
            raise ToolError(f"refusing to contact private address {ip} for {host}")
    return parsed


def http_request(url: str, *, method: str = "GET", headers: dict | None = None,
                 body: dict | list | str | None = None, timeout: int = DEFAULT_HTTP_TIMEOUT,
                 max_bytes: int = DEFAULT_MAX_BYTES,
                 allowed_hosts: list[str] | None = None,
                 allow_local: bool = False,
                 deadline_seconds: float | None = None,
                 connect_timeout: float = 10.0,
                 tls_timeout: float = 10.0,
                 header_timeout: float = 30.0,
                 body_timeout: float = 45.0) -> dict:
    """Perform one HTTPS request. Non-2xx responses are returned, not raised.

    When ``deadline_seconds`` is supplied the request is executed by the bounded
    transport, which enforces a genuine total wall-clock deadline covering DNS,
    TCP connect, TLS, response headers and the response body. Without it the
    historical urllib path is preserved unchanged for other callers.
    """
    if deadline_seconds is not None:
        from .llm.bounded_http import request as bounded_request
        return bounded_request(
            url, method=method, headers=headers, body=body,
            deadline_seconds=deadline_seconds,
            connect_timeout=connect_timeout, tls_timeout=tls_timeout,
            header_timeout=header_timeout, body_timeout=body_timeout,
            max_bytes=max_bytes, allowed_hosts=allowed_hosts,
            allow_local=allow_local)
    _validate_url(url, allowed_hosts, allow_local=allow_local)
    data = None
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        if hasattr(headers, "real_headers"):
            request_headers.update(headers.real_headers())
        else:
            request_headers.update(headers)
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        else:
            data = str(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            status = response.status
            response_headers = dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read(max_bytes + 1)
        status = exc.code
        response_headers = dict(exc.headers or {})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "url": url, "error": f"request failed: {exc}"}
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    payload: object = text
    content_type = response_headers.get("Content-Type", "")
    if "json" in content_type or text.strip().startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text
    return {
        "ok": 200 <= status < 300,
        "status": status,
        "url": url,
        "headers": response_headers,
        "payload": payload,
        "truncated": truncated,
    }


def http_download(url: str, destination: str, *, headers: dict | None = None,
                  timeout: int = 120, max_bytes: int = 512 * 1024 * 1024,
                  allowed_hosts: list[str] | None = None,
                  expected_sha256: str | None = None) -> dict:
    """Download to a temporary file, verify, then move into place atomically."""
    _validate_url(url, allowed_hosts)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    tmp_path = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                return {"ok": False, "url": url,
                        "error": f"declared size {declared} exceeds limit {max_bytes}"}
            fd, tmp_path = tempfile.mkstemp(prefix="gs-download-", dir=os.path.dirname(os.path.abspath(destination)))
            written = 0
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ToolError(f"download exceeded {max_bytes} bytes")
                    digest.update(chunk)
                    handle.write(chunk)
        if written == 0:
            raise ToolError("downloaded file is empty")
        actual = digest.hexdigest()
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise ToolError(f"sha256 mismatch: expected {expected_sha256}, got {actual}")
        os.replace(tmp_path, destination)
        tmp_path = None
        return {
            "ok": True,
            "url": url,
            "path": os.path.abspath(destination),
            "bytes": written,
            "sha256": actual,
            "content_type": response.headers.get("Content-Type"),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "url": url, "error": f"download failed: {exc}"}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def platform_name() -> str:
    return {"win32": "windows", "darwin": "macos", "linux": "linux"}.get(sys.platform, sys.platform)


def command_version(command: list[str], *, timeout: int = 20,
                    first_line: bool = True) -> str | None:
    result = run_command(command, timeout=timeout)
    text = (result.get("stdout") or result.get("stderr") or "").strip()
    if not text:
        return None
    line = text.splitlines()[0].strip()
    return line if first_line else text
