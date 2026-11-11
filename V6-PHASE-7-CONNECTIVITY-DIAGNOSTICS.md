# V6 Phase 7 - Gemini Connectivity Diagnostics

**Host:** `generativelanguage.googleapis.com:443`  
**Generated:** `2026-11-11T06:59:00Z`  
**Outcome:** **CONNECTION_SUCCESS**  
**Evidence:** `reports/v6-phase7-connectivity-diagnostics.json`  
**Script:** `scripts/v6-phase7-connectivity-diagnostics.py`

---

## 1. Scope and safety

This diagnostic performed DNS, TCP and TLS checks only.

| Action | Performed |
| --- | --- |
| HTTP request sent | no |
| Gemini API called | no |
| API credential read | no |
| Quota consumed | no |
| Game-spec request retried | no |
| Protected files modified | no |

TLS was used only to complete a handshake and validate the certificate. No application data was written to the socket.

---

## 2. Results

### 2.1 DNS

| Metric | Value |
| --- | --- |
| Resolution | success |
| Duration | 42.4 ms |
| Addresses returned | 16 |
| Families | IPv4 and IPv6 |

Sample addresses tested: `172.217.119.4`, `172.217.115.4`, `2001:4860:4842:400::`, `2001:4860:4844:400::`.

### 2.2 TCP port 443

| Address | Result | Time |
| --- | --- | --- |
| `172.217.119.4` | connected | 38.3 ms |
| `172.217.115.4` | connected | 68.2 ms |
| `2001:4860:4842:400::` | connected | 61.3 ms |
| `2001:4860:4844:400::` | connected | 46.0 ms |

All four connections succeeded. No TCP refusal, reset or timeout.

### 2.3 TLS

| Metric | Value |
| --- | --- |
| Handshakes succeeded | 4 of 4 |
| Protocol | TLS 1.3 |
| Certificate validation | passed on all connections |
| Hostname validation | passed (`*.googleapis.com` SAN covers the host) |
| Issuer | Google Trust Services, `WE2` |
| Validity | 2026-10-07 to 2026-12-30 |
| Handshake time | 218.7 - 236.9 ms |

### 2.4 Proxy configuration

| Source | Result |
| --- | --- |
| `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` | not set |
| `NO_PROXY` | `127.0.0.1,localhost,::1` only |
| WinHTTP (`netsh winhttp show proxy`) | Direct access, no proxy server |
| `urllib.request.getproxies()` | only `no = 127.0.0.1,localhost,::1` |

No proxy is configured, so no proxy-related timeout or authentication path applies.

### 2.5 Windows Firewall

| Profile | Enabled | Default inbound | Default outbound |
| --- | --- | --- | --- |
| Domain | yes | Block | Allow |
| Private | yes | Block | Allow |
| Public | yes | Block | Allow |

Default outbound traffic is allowed on every profile. Per-rule enumeration was unavailable without administrator rights, but no profile-level policy blocks outbound HTTPS.

---

## 3. Adapter timeout handling

Path: `GeminiProvider.complete` -> `providers._request` -> `util.http_request` -> `urllib.request.urlopen`.

| Finding | Detail |
| --- | --- |
| Timeout passed | `GeminiProvider.complete(timeout=60)` passes one timeout value to `http_request` |
| Socket timeout location | `urllib.request.urlopen(request, timeout=timeout)` (`util.py` line 345) |
| Body read | `response.read(max_bytes + 1)` (`util.py` line 346) |
| Timeout meaning | per blocking socket operation, not total wall-clock time |
| Total request deadline | none |
| Separate connect timeout | not enforced; `connect_timeout_seconds = 10` is advertised in readiness but never passed to `http_request` |
| DNS timeout | none: `socket.getaddrinfo(host, None)` at `util.py` line 313 has no timeout argument |
| Retry loop in Gemini adapter | none |
| Phase 7 retries | 0 |

Implication: the 60-second value bounds each connect/read operation. A server that accepts the connection and then sends headers or body slowly can exceed 60 seconds of total request time without triggering the socket timeout until an individual read stalls. Conversely, a normal `read` timeout appears as `request failed: The read operation timed out`.

---

## 4. Previous live-attempt evidence

| Attempt | Finished (UTC) | Result | Error |
| --- | --- | --- | --- |
| 1 | 2026-11-11T05:59:08Z | failed | HTTP 503 `unavailable`, "high demand" |
| 2 | 2026-11-11T06:47:35Z | failed | `timeout`, read operation timed out |
| 3 | 2026-11-11T06:51:21Z | failed | `timeout`, read operation timed out |

Each attempt made exactly one network call with zero retries. Attempt 1 reached the provider and received an HTTP response; attempts 2 and 3 produced no response before the 60-second read timeout.

---

## 5. Classification

**Outcome: `CONNECTION_SUCCESS`**

- DNS resolved quickly and consistently.
- TCP 443 connected on both IPv4 and IPv6.
- TLS 1.3 negotiated with a valid certificate and matching hostname.
- No proxy is configured.
- Windows Firewall allows outbound traffic.

`DNS_FAILURE`, `TCP_FAILURE` and `TLS_FAILURE` are ruled out. The observed API failures occur after connection establishment, at the HTTP response stage or inside the provider. The timeout evidence is consistent with a slow or unavailable model endpoint, not with a broken network path.

No HTTP request was sent, so this diagnostic cannot determine whether the new key authenticates, whether the model would answer, or whether provider latency would exceed 60 seconds for a complete response.

---

## 6. Limitations

- A TLS handshake does not test the Gemini endpoint's application behaviour.
- DNS, TCP and TLS timings are single samples and may vary.
- Firewall per-rule inspection may require administrator rights.
- The 60-second timeout is not a total deadline; the diagnostic cannot measure full response time without an API request.

---

## 7. Follow-up: bounded deadline fix (offline)

The defect identified in §3 has been addressed in a separate offline change:

- `game_studio/llm/bounded_http.py` enforces a total wall-clock deadline with a
  socket-closing watchdog.
- `util.http_request` delegates to it when `deadline_seconds` is supplied.
- `GeminiProvider.complete` and `list_models` pass the total deadline plus
  connect, TLS, header and body budgets.
- Structured errors cover DNS, connection, TLS, headers, body and the overall
  deadline; partial bodies are never parsed as JSON.

This follow-up made no network request. See `reports/v6-phase7-timeout-fix.json`,
`reports/v6-phase7-timeout-validation.json` and
`V6-PHASE-7-REAL-AI-VALIDATION.md` §12.1.
