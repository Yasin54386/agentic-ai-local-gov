"""Minimal MCP stdio client — dependency-free.

Spawns the MCP server as a subprocess, performs the initialize handshake, and
calls tools over JSON-RPC. Used by the refresh scheduler so data genuinely flows
'through MCP', and handy for testing the server from Python.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


class MCPClient:
    def __init__(self, command: list[str] | None = None):
        self.command = command or [sys.executable, "-m", "mcp_server.server"]
        self.proc: subprocess.Popen | None = None
        self._id = 0

    def __enter__(self) -> "MCPClient":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self._request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "refresh-scheduler", "version": "0.1.0"},
        })
        self._notify("notifications/initialized", {})

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _write(self, msg: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _request(self, method: str, params: dict) -> Any:
        req_id = self._next_id()
        self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        assert self.proc and self.proc.stdout
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed unexpectedly")
            msg = json.loads(line)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"MCP error: {msg['error']}")
                return msg.get("result")

    def _notify(self, method: str, params: dict) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def list_tools(self) -> list[dict]:
        return self._request("tools/list", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content", [])
        text = content[0]["text"] if content else "null"
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    def close(self) -> None:
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
            self.proc = None
