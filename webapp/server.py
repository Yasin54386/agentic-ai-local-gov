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
import time
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

# --- refresh-on-access: keep live data fresh without blocking requests --------
# When a data API is hit and the data is older than REFRESH_TTL seconds, kick off
# a single background sync. Set AUTOREFRESH=0 to disable; REFRESH_TTL=0 forces
# every request (not recommended — hammers the source). --datasets stays on the
# scheduled 6h job; on-access refresh is the light, live feed only.
AUTOREFRESH = os.environ.get("AUTOREFRESH", "1") != "0"
LIVE_TTL = int(os.environ.get("REFRESH_TTL", "600"))            # live feed: 10 min
DATASETS_TTL = int(os.environ.get("DATASETS_TTL", "86400"))     # datasets: 24h (0 disables)
_last_result = {"live": None, "datasets": None}

# Each tier: a monotonic timestamp + a single-flight lock.
_tiers = {
    "live": {"at": 0.0, "lock": threading.Lock(), "ttl": LIVE_TTL},
    "datasets": {"at": 0.0, "lock": threading.Lock(), "ttl": DATASETS_TTL},
}


def _run_tier(name: str):
    from db.connection import Database
    from ingestion.refresh import refresh_live, refresh_datasets
    db = Database().connect()
    try:
        if name == "live":
            _last_result["live"] = refresh_live(db)
        else:
            res = refresh_datasets(db)
            _last_result["datasets"] = {"datasets": len(res),
                                        "changed": sum(1 for r in res if r.get("added") or r.get("removed"))}
        _last_result[name + "_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    except Exception as exc:
        _last_result[name + "_error"] = str(exc)
    finally:
        db.close()
        _tiers[name]["lock"].release()


def maybe_refresh():
    """Non-blocking, throttled, single-flight — live (10 min) + datasets (24h)."""
    if not AUTOREFRESH:
        return
    now = time.monotonic()
    for name, t in _tiers.items():
        if t["ttl"] <= 0:
            continue
        if now - t["at"] < t["ttl"]:
            continue
        if not t["lock"].acquire(blocking=False):
            continue
        t["at"] = now
        threading.Thread(target=_run_tier, args=(name,), daemon=True).start()


def tool(name, args=None):
    with _lock:
        return dispatch(repo, name, args or {})


def _call(fn):
    """Run a repository method under the lock (for panel views not exposed as tools)."""
    with _lock:
        return fn(repo)


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
        # data loads opportunistically keep the live data fresh (throttled, async)
        if u.path.startswith("/api/") and u.path != "/api/health":
            maybe_refresh()
        if u.path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if u.path in ("/concept", "/concept.html"):
            return self._file(STATIC / "concept.html", "text/html; charset=utf-8")
        if u.path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
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
            return self._json(_call(lambda r: r.capital_by_category()))
        if u.path == "/api/suburb_lookup":
            return self._json(_call(lambda r: r.suburb_lookup(q.get("suburb", [""])[0])))
        if u.path == "/api/canopy":
            return self._json(_call(lambda r: r.canopy_change()))
        if u.path == "/api/mobility":
            return self._json(_call(lambda r: r.mobility_trend()))
        if u.path == "/api/decisions":
            return self._json(_call(lambda r: r.decisions(q.get("q", [""])[0])))
        if u.path == "/api/grants":
            return self._json(_call(lambda r: r.grants(q.get("q", [""])[0])))
        if u.path == "/api/equity":
            return self._json(_call(lambda r: r.ward_spend()))
        if u.path == "/api/tables":
            return self._json(tool("list_tables", {}))
        if u.path == "/api/columns":
            return self._json(tool("find_columns", {"query": q.get("q", [""])[0]}))
        if u.path == "/api/health":
            now = time.monotonic()
            ages = {n: (None if not t["at"] else round(now - t["at"])) for n, t in _tiers.items()}
            return self._json({"ok": True, "model_server": llm.server_up(),
                               "model": llm.DEFAULT_MODEL, "autorefresh": AUTOREFRESH,
                               "ttl_s": {n: t["ttl"] for n, t in _tiers.items()},
                               "age_s": ages, "last_refresh": _last_result})
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
