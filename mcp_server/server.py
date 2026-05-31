"""MCP server (stdio, JSON-RPC 2.0) — the real switchboard from docs/04.

Exposes the repository + live tools (defined once in agent/tools.py) over the
Model Context Protocol. Newline-delimited JSON-RPC messages on stdin/stdout, per
the MCP stdio transport. No third-party dependencies.

Run directly:           python -m mcp_server.server
Connect from a client:  configure command = ["python","-m","mcp_server.server"]

Supported methods: initialize, notifications/initialized, tools/list, tools/call.
All tools are READ-ONLY (the docs/05 human gate would wrap writes here).
"""
from __future__ import annotations

import json
import sys

from agent.repository import Repository
from agent.tools import TOOLS, dispatch

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "nt-darwin-data", "version": "0.1.0"}


def _mcp_tools() -> list[dict]:
    """MCP uses `inputSchema` (camelCase); our defs use `input_schema`."""
    return [{"name": t["name"], "description": t["description"],
             "inputSchema": t.get("input_schema", {"type": "object", "properties": {}})}
            for t in TOOLS]


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _result(req_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(req: dict, repo: Repository) -> None:
    method = req.get("method")
    req_id = req.get("id")

    # Notifications (no id) get no response.
    if method == "notifications/initialized":
        return
    if method == "initialize":
        _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
        return
    if method == "tools/list":
        _result(req_id, {"tools": _mcp_tools()})
        return
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        try:
            output = dispatch(repo, name, args)
            _result(req_id, {
                "content": [{"type": "text", "text": json.dumps(output, default=str)}],
                "isError": False,
            })
        except Exception as exc:  # surface tool errors as MCP tool errors
            _result(req_id, {
                "content": [{"type": "text", "text": f"tool error: {exc}"}],
                "isError": True,
            })
        return
    if req_id is not None:
        _error(req_id, -32601, f"method not found: {method}")


def main() -> int:
    repo = Repository()
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            handle(req, repo)
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
