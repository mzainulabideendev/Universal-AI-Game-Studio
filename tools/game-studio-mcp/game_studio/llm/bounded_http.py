"""Bounded HTTPS execution with a genuine total wall-clock deadline.

This module is used by the Gemini adapter only when a deadline is requested. It
does not replace the general-purpose ``util.http_request`` path used by other
providers. No dependencies beyond the Python standard library are used.

Design
------
* DNS resolution runs in a daemon worker so the caller can stop waiting.
* TCP connect, TLS handshake, response headers and response body each have a
  bounded budget, and a watchdog closes the socket when the total deadline
  expires.
* Every failure returns a structured ``error_detail`` with a kind and the stage
  where it occurred. No header or credential values are copied into errors.
* A truncated or partial body is never parsed into JSON. It is returned as an
  error with ``partial_response: true``.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time
import urllib.parse
from datetime import datetime, timezone

USER_AGENT = "UniversalAI-GameStudio-MCP/1.0 (+https://github.com/mzainulabideendev/Universal-AI-Game-Studio)"
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
CHUNK = 64 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


class _BoundedError(Exception):
    def __init__(self, kind: str, *, stage: str, message: str,
                 timed_out: bool = False, partial_response: bool = False,
                 partial_bytes: int = 0):
        super().__init__(message)
        self.kind = kind
        self.stage = stage
        self.timed_out = timed_out
        self.partial_response = partial_response
        self.partial_bytes = partial_bytes


class _Deadline:
    """Total wall-clock deadline with a watchdog that closes the socket."""

    def __init__(self, seconds: float):
        self.seconds = float(seconds)
        self.expires = time.monotonic() + max(0.0, self.seconds)
        self.expired = False
        self._lock = threading.Lock()
        self._sock = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="llm-deadline",
                                        daemon=True)

    def start(self) -> None:
        self._thread.start()

    def remaining(self) -> float:
        return max(0.0, self.expires - time.monotonic())

    def register(self, sock) -> None:
        with self._lock:
            self._sock = sock
            if self.expired or self.remaining() <= 0:
                self.expired = True
                self._close_locked()

    def unregister(self, sock) -> None:
        with self._lock:
            if self._sock is sock:
                self._sock = None

    def expire_now(self) -> None:
        with self._lock:
            self.expired = True
            self._close_locked()

    def _close_locked(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
        self._sock = None

    def _watch(self) -> None:
        self._stop.wait(self.remaining())
        if self._stop.is_set():
            return
        self.expire_now()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.2)


def _resolve(host: str, port: int, deadline: _Deadline) -> list[tuple[int, str]]:
    """Resolve host in a daemon worker so a hung resolver cannot block forever."""
    result: dict = {}

    def work() -> None:
        try:
            result["infos"] = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:  # noqa: BLE001 - reported below
            result["error"] = exc

    worker = threading.Thread(target=work, name="llm-dns", daemon=True)
    worker.start()
    worker.join(deadline.remaining())
    if worker.is_alive():
        raise _BoundedError("dns_timeout", stage="dns",
                            message=f"DNS resolution did not finish within the deadline",
                            timed_out=True)
    if "error" in result:
        raise _BoundedError("dns_failure", stage="dns",
                            message=f"DNS resolution failed: {result['error']}")
    infos = result.get("infos") or []
    addresses: list[tuple[int, str]] = []
    seen: set[str] = set()
    for family, _socktype, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        if ip in seen:
            continue
        seen.add(ip)
        addresses.append((family, ip))
    if not addresses:
        raise _BoundedError("dns_failure", stage="dns",
                            message="DNS resolution returned no addresses")
    return addresses


def _reject_private(addresses: list[tuple[int, str]]) -> None:
    for _family, ip in addresses:
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (parsed.is_private or parsed.is_loopback or parsed.is_link_local
                or parsed.is_reserved or parsed.is_multicast):
            raise _BoundedError("blocked_private_address", stage="dns",
                                message=f"refusing to contact private address {ip}")


def _connect(addresses: list[tuple[int, str]], port: int, deadline: _Deadline,
             connect_timeout: float) -> tuple[socket.socket, str]:
    last_error: Exception | None = None
    saw_timeout = False
    for family, ip in addresses:
        if deadline.expired or deadline.remaining() <= 0:
            raise _BoundedError("deadline_exceeded", stage="connect",
                                message="overall deadline expired before connecting",
                                timed_out=True)
        budget = min(deadline.remaining(), max(0.001, connect_timeout))
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(budget)
        try:
            sock.connect((ip, port))
            return sock, ip
        except socket.timeout as exc:
            last_error = exc
            saw_timeout = True
            try:
                sock.close()
            except OSError:
                pass
        except OSError as exc:
            last_error = exc
            try:
                sock.close()
            except OSError:
                pass
    if deadline.expired:
        raise _BoundedError("deadline_exceeded", stage="connect",
                            message="overall deadline expired while connecting",
                            timed_out=True)
    if saw_timeout:
        raise _BoundedError("connection_timeout", stage="connect",
                            message=(f"TCP connection did not complete within "
                                     f"{connect_timeout:g}s: {last_error}"),
                            timed_out=True)
    raise _BoundedError("connection_failure", stage="connect",
                        message=f"TCP connection failed: {last_error}")


def _tls(sock: socket.socket, host: str, deadline: _Deadline,
         tls_timeout: float) -> ssl.SSLSocket:
    if deadline.expired or deadline.remaining() <= 0:
        raise _BoundedError("deadline_exceeded", stage="tls",
                            message="overall deadline expired before TLS",
                            timed_out=True)
    sock.settimeout(min(deadline.remaining(), max(0.001, tls_timeout)))
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    try:
        tls = context.wrap_socket(sock, server_hostname=host)
        return tls
    except ssl.SSLError as exc:
        raise _BoundedError("tls_failure", stage="tls",
                            message=f"TLS handshake or certificate validation failed: {exc}")
    except socket.timeout as exc:
        if deadline.expired:
            raise _BoundedError("deadline_exceeded", stage="tls",
                                message="overall deadline expired during TLS",
                                timed_out=True)
        raise _BoundedError("tls_failure", stage="tls",
                            message=f"TLS handshake timed out: {exc}", timed_out=True)
    except OSError as exc:
        if deadline.expired:
            raise _BoundedError("deadline_exceeded", stage="tls",
                                message="overall deadline expired during TLS",
                                timed_out=True)
        raise _BoundedError("tls_failure", stage="tls",
                            message=f"TLS failure: {exc}")


def _build_request(url: str, method: str, headers: dict, body_bytes: bytes) -> tuple[str, bytes]:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host = parsed.hostname or ""
    host_header = host if parsed.port in (None, 443) else f"{host}:{parsed.port}"
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host_header}"]
    supplied = dict(headers)
    for key, value in supplied.items():
        if str(key).lower() in ("host", "content-length", "connection"):
            continue
        lines.append(f"{key}: {value}")
    lines.append(f"Content-Length: {len(body_bytes)}")
    lines.append("Connection: close")
    raw = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body_bytes
    return path, raw


def _exchange(tls: ssl.SSLSocket, *, method: str, deadline: _Deadline,
              header_timeout: float, body_timeout: float, max_bytes: int,
              timing: dict) -> dict:
    response = http.client.HTTPResponse(tls, method=method)
    try:
        header_budget = min(deadline.remaining(), max(0.001, header_timeout))
        tls.settimeout(header_budget)
        started = time.perf_counter()
        try:
            response.begin()
        except socket.timeout as exc:
            raise _BoundedError(
                "deadline_exceeded" if deadline.expired else "http_response_timeout",
                stage="headers",
                message=("overall deadline expired while waiting for response headers"
                         if deadline.expired else
                         f"response headers did not arrive within {header_budget:g}s: {exc}"),
                timed_out=True)
        except (OSError, ValueError) as exc:
            raise _BoundedError(
                "deadline_exceeded" if deadline.expired else "provider-error",
                stage="headers",
                message=("overall deadline expired while waiting for response headers"
                         if deadline.expired else f"response header read failed: {exc}"),
                timed_out=deadline.expired)
        timing["headers_ms"] = _ms(started)
        status = response.status
        response_headers = dict(response.getheaders())

        body_started = time.perf_counter()
        body_budget = min(deadline.remaining(), max(0.001, body_timeout))
        body_end = time.monotonic() + body_budget
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            if deadline.expired or deadline.remaining() <= 0:
                raise _BoundedError("deadline_exceeded", stage="body",
                                    message="overall deadline expired while reading the body",
                                    timed_out=True, partial_response=bool(chunks),
                                    partial_bytes=total)
            left = body_end - time.monotonic()
            if left <= 0:
                raise _BoundedError("response_body_timeout", stage="body",
                                    message=(f"response body did not complete within "
                                             f"{body_budget:g}s"),
                                    timed_out=True, partial_response=bool(chunks),
                                    partial_bytes=total)
            tls.settimeout(max(0.001, min(deadline.remaining(), left)))
            try:
                chunk = response.read(min(CHUNK, max_bytes + 1 - total))
            except socket.timeout as exc:
                kind = "deadline_exceeded" if deadline.expired else "response_body_timeout"
                raise _BoundedError(kind, stage="body",
                                    message=("overall deadline expired while reading the body"
                                             if deadline.expired else
                                             f"response body read timed out: {exc}"),
                                    timed_out=True, partial_response=bool(chunks),
                                    partial_bytes=total)
            except http.client.IncompleteRead as exc:
                raise _BoundedError("response_body_incomplete", stage="body",
                                    message=f"response body ended unexpectedly: {exc}",
                                    partial_response=True,
                                    partial_bytes=total + len(exc.partial or b""))
            except (OSError, ValueError) as exc:
                kind = "deadline_exceeded" if deadline.expired else "response_body_incomplete"
                raise _BoundedError(kind, stage="body",
                                    message=("overall deadline expired while reading the body"
                                             if deadline.expired else
                                             f"response body read failed: {exc}"),
                                    timed_out=deadline.expired,
                                    partial_response=bool(chunks), partial_bytes=total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        # A watchdog-triggered socket shutdown can surface as a clean EOF instead
        # of socket.timeout/OSError on some platforms. Never report that partial
        # body as a successful response.
        if deadline.expired:
            raise _BoundedError("deadline_exceeded", stage="body",
                                message="overall deadline expired before the body completed",
                                timed_out=True, partial_response=bool(chunks),
                                partial_bytes=total)
        timing["body_ms"] = _ms(body_started)
        return {
            "status": status,
            "headers": response_headers,
            "raw": b"".join(chunks),
            "truncated": total > max_bytes,
        }
    finally:
        try:
            response.close()
        except Exception:  # noqa: BLE001 - close must not mask the real error
            pass


def _decode_payload(raw: bytes, headers: dict, truncated: bool) -> tuple[object, bool]:
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        return text, False
    content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    if "json" in content_type.lower() or text.strip().startswith(("{", "[")):
        try:
            return json.loads(text), True
        except json.JSONDecodeError:
            return text, False
    return text, False


def request(url: str, *, method: str = "GET", headers: dict | None = None,
            body: dict | list | str | None = None, deadline_seconds: float,
            connect_timeout: float = 10.0, tls_timeout: float = 10.0,
            header_timeout: float = 30.0, body_timeout: float = 45.0,
            max_bytes: int = DEFAULT_MAX_BYTES,
            allowed_hosts: list[str] | None = None,
            allow_local: bool = False,
            user_agent: str = USER_AGENT) -> dict:
    """Perform one bounded HTTPS request. Returns a structured result."""
    started = time.perf_counter()
    timing: dict = {}
    deadline = _Deadline(deadline_seconds)
    deadline.start()
    tls_sock = None
    sock = None
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https":
            raise _BoundedError("invalid_url", stage="validate",
                                message="only https URLs are allowed")
        host = parsed.hostname
        if not host:
            raise _BoundedError("invalid_url", stage="validate",
                                message="URL has no host")
        if parsed.username or parsed.password:
            raise _BoundedError("invalid_url", stage="validate",
                                message="URL must not contain credentials")
        if allowed_hosts and not any(host == allowed or host.endswith("." + allowed)
                                     for allowed in allowed_hosts):
            raise _BoundedError("blocked_host", stage="validate",
                                message="host is not in the allow-list")
        if deadline.seconds <= 0:
            raise _BoundedError("deadline_exceeded", stage="start",
                                message="overall deadline expired before the request",
                                timed_out=True)

        dns_started = time.perf_counter()
        addresses = _resolve(host, parsed.port or 443, deadline)
        timing["dns_ms"] = _ms(dns_started)
        if not allow_local:
            _reject_private(addresses)

        connect_started = time.perf_counter()
        sock, _ip = _connect(addresses, parsed.port or 443, deadline,
                             connect_timeout)
        timing["connect_ms"] = _ms(connect_started)

        tls_started = time.perf_counter()
        tls_sock = _tls(sock, host, deadline, tls_timeout)
        sock = None
        timing["tls_ms"] = _ms(tls_started)
        deadline.register(tls_sock)

        request_headers = {"User-Agent": user_agent, "Accept": "application/json"}
        if headers:
            if hasattr(headers, "real_headers"):
                request_headers.update(headers.real_headers())
            else:
                request_headers.update(headers)
        body_bytes = b""
        if body is not None:
            if isinstance(body, (dict, list)):
                body_bytes = json.dumps(body).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/json")
            else:
                body_bytes = str(body).encode("utf-8")
        _path, raw_request = _build_request(url, method, request_headers, body_bytes)

        send_started = time.perf_counter()
        if deadline.remaining() <= 0:
            raise _BoundedError("deadline_exceeded", stage="send",
                                message="overall deadline expired before sending",
                                timed_out=True)
        tls_sock.settimeout(max(0.001, min(deadline.remaining(), header_timeout)))
        try:
            tls_sock.sendall(raw_request)
        except socket.timeout as exc:
            raise _BoundedError(
                "deadline_exceeded" if deadline.expired else "http_response_timeout",
                stage="send", message=f"request send timed out: {exc}", timed_out=True)
        except OSError as exc:
            raise _BoundedError(
                "deadline_exceeded" if deadline.expired else "connection_failure",
                stage="send", message=f"request send failed: {exc}",
                timed_out=deadline.expired)
        timing["send_ms"] = _ms(send_started)

        exchange = _exchange(tls_sock, method=method, deadline=deadline,
                             header_timeout=header_timeout,
                             body_timeout=body_timeout, max_bytes=max_bytes,
                             timing=timing)
        payload, parsed_json = _decode_payload(exchange["raw"],
                                               exchange["headers"],
                                               exchange["truncated"])
        timing["total_ms"] = _ms(started)
        return {
            "ok": 200 <= exchange["status"] < 300,
            "status": exchange["status"],
            "url": url,
            "headers": exchange["headers"],
            "payload": payload,
            "truncated": exchange["truncated"],
            "json_parse_skipped": exchange["truncated"] or not parsed_json,
            "timing": timing,
        }
    except _BoundedError as exc:
        timing["total_ms"] = _ms(started)
        return {
            "ok": False,
            "status": None,
            "url": url,
            "error": str(exc),
            "error_detail": {
                "kind": exc.kind,
                "stage": exc.stage,
                "timed_out": exc.timed_out,
                "partial_response": exc.partial_response,
                "partial_bytes": exc.partial_bytes,
                "elapsed_ms": timing["total_ms"],
                "deadline_seconds": deadline.seconds,
                "timing": timing,
            },
        }
    except Exception as exc:  # noqa: BLE001 - never leak a traceback or header value
        timing["total_ms"] = _ms(started)
        return {
            "ok": False,
            "status": None,
            "url": url,
            "error": f"bounded request failed: {type(exc).__name__}",
            "error_detail": {
                "kind": "internal_error",
                "stage": "unknown",
                "timed_out": False,
                "elapsed_ms": timing["total_ms"],
                "deadline_seconds": deadline.seconds,
                "timing": timing,
            },
        }
    finally:
        deadline.stop()
        for handle in (tls_sock, sock):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
