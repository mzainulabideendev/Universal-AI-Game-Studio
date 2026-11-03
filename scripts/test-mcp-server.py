r"""Smoke-test any stdio MCP server: initialize, tools/list, optional read-only call.

Usage:
  python scripts/test-mcp-server.py -- <exe> [args...]
  python scripts/test-mcp-server.py --call <tool> --args "{}" -- <exe> [args...]
"""
import argparse
import json
import subprocess
import sys


def send(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def recv(proc):
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("server closed stdout")
    return json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", default=None)
    ap.add_argument("--args", default="{}")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("no command given; use -- <exe> [args...]")

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "smoke", "version": "1"}}})
        init = recv(proc)
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = recv(proc)
        names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
        report = {"initialize": init.get("result", {}).get("serverInfo"),
                  "tool_count": len(names), "tools": names[:80]}
        if a.call:
            send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": a.call, "arguments": json.loads(a.args)}})
            report["call"] = recv(proc)
        print(json.dumps(report, indent=2)[:9000])
        return 0 if names else 2
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
