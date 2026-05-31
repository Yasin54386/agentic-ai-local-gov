"""Ask Territory web server — stdlib only, runs on localhost or in production.

Serves a single-page UI and a small JSON API backed by the same tools the agent
uses. The data panels (Live, Neighbourhood, Transparency, Stats) work WITHOUT a
language model. The 'Ask' chat panel uses the self-hosted Qwen agent if a local
Ollama server is running; otherwise it returns a friendly hint.

    python -m webapp.server            # http://localhost:8000
    PORT=9000 python -m webapp.server

In production it sits behind nginx (TLS) — see DEPLOY.md. Concurrency-safe via a
lock around the shared repository connection (ThreadingHTTPServer).
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from agent import llm
from agent.repository import Repository
from agent.tools import dispatch

STATIC = Path(__file__).parent / "static"
PORT = int(os.environ.get("PORT", "8000"))

repo = Repository()
_lock = threading.Lock()  # serialise access to the shared sqlite connection


def tool(name, args=None):
    with _lock:
        return dispatch(repo, name, args or {})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        return

    def _json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if u.path == "/api/stats":
            return self._json(tool("repository_stats"))
        if u.path == "/api/live":
            return self._json({"weather": tool("live_weather"),
                               "flood": tool("flood_risk")})
        if u.path == "/api/suburbs":
            return self._json(tool("list_suburbs", {"limit": 60}))
        if u.path == "/api/profile":
            suburb = (q.get("suburb", [""])[0]).strip()
            if not suburb:
                return self._json({"error": "pass ?suburb="}, 400)
            return self._json(tool("neighbourhood_profile", {"suburb": suburb}))
        if u.path == "/api/transparency":
            # council capital expenditure by category (sum) — a transparency view
            return self._json(tool("query_unified", {
                "domain": "finance & procurement", "group_by": "category",
                "op": "sum", "limit": 15}))
        if u.path == "/api/health":
            return self._json({"ok": True, "model_server": llm.server_up(),
                               "model": llm.DEFAULT_MODEL})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or "{}")
        if u.path == "/api/ask":
            question = (body.get("question") or "").strip()
            if not question:
                return self._json({"error": "empty question"}, 400)
            if not llm.server_up():
                return self._json({"answer": None, "model_offline": True,
                    "hint": "Start your local model: run `bash scripts/setup_local_model.sh`, "
                            "then it serves on localhost:11434. The data panels work without it."})
            from agent.agent import run
            try:
                with _lock:
                    answer = run(question, repo=repo, verbose=False)
                return self._json({"answer": answer})
            except Exception as exc:
                return self._json({"error": str(exc)}, 500)
        return self._json({"error": "not found"}, 404)


def main() -> int:
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Ask Territory running →  http://localhost:{PORT}")
    print(f"  model server: {'UP' if llm.server_up() else 'offline (data panels still work)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
