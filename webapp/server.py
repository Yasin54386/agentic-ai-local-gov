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

import collections
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

# Optional shared secret to protect the scrape-trigger endpoints.
SCRAPE_KEY = os.environ.get("SCRAPE_KEY", "")

repo = Repository()
_lock = threading.Lock()  # serialise access to the shared sqlite connection

# --- simple per-IP rate limiter -----------------------------------------------
# Limits search API calls to RATE_LIMIT requests per RATE_WINDOW seconds per IP.
# Protects against bots and runaway clients. Cloudflare does this too in
# production, but this layer works even on localhost / direct access.
RATE_LIMIT  = int(os.environ.get("RATE_LIMIT",  "60"))   # requests per window
RATE_WINDOW = int(os.environ.get("RATE_WINDOW", "60"))   # seconds

_rate_lock    = threading.Lock()
_rate_buckets: dict[str, collections.deque] = collections.defaultdict(collections.deque)

RATE_LIMITED_PATHS = {"/api/forms/search", "/api/howto/search", "/api/ask"}


def _check_rate(ip: str, path: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    if path not in RATE_LIMITED_PATHS:
        return True
    now = time.monotonic()
    with _rate_lock:
        dq = _rate_buckets[ip]
        # drop timestamps outside the window
        while dq and now - dq[0] > RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            return False
        dq.append(now)
    return True

# --- refresh-on-access: keep live data fresh without blocking requests --------
AUTOREFRESH = os.environ.get("AUTOREFRESH", "1") != "0"
LIVE_TTL = int(os.environ.get("REFRESH_TTL", "600"))
DATASETS_TTL = int(os.environ.get("DATASETS_TTL", "86400"))
_last_result = {"live": None, "datasets": None}

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
    with _lock:
        return fn(repo)


def _fdb():
    """Open a fresh DB connection for forms/howto queries (not the shared repo conn)."""
    from db.connection import Database
    return Database().connect()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        if not path.exists():
            return self._json({"error": "file not found"}, 404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _search(self, module_path: str, q_str: str, mode: str) -> dict:
        """Shared search helper for forms and howto — handles errors gracefully."""
        if module_path == "forms":
            from ingestion.forms_search import keyword_search, ai_search
        else:
            from ingestion.howto_search import keyword_search, ai_search
        db = _fdb()
        try:
            if mode == "ai" and llm.server_up():
                return ai_search(db, q_str, llm)
            return {"results": keyword_search(db, q_str), "expanded_terms": []}
        except Exception as exc:
            return {"results": [], "expanded_terms": [], "error": str(exc)}
        finally:
            db.close()

    def _client_ip(self) -> str:
        # Respect X-Forwarded-For set by Cloudflare/nginx; fall back to direct IP
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[0].strip() or self.client_address[0]

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith("/api/") and u.path != "/api/health":
            maybe_refresh()
            if not _check_rate(self._client_ip(), u.path):
                return self._json({"error": "rate limit exceeded — please slow down"}, 429)

        # --- static pages ---
        if u.path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if u.path in ("/concept", "/concept.html"):
            return self._file(STATIC / "concept.html", "text/html; charset=utf-8")
        if u.path in ("/forms", "/forms.html"):
            return self._file(STATIC / "forms.html", "text/html; charset=utf-8")
        if u.path in ("/howto", "/howto.html"):
            return self._file(STATIC / "howto.html", "text/html; charset=utf-8")
        if u.path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return

        # --- data APIs ---
        if u.path == "/api/stats":
            return self._json(tool("repository_stats"))
        if u.path == "/api/live":
            return self._json({"weather": tool("live_weather"), "flood": tool("flood_risk")})
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

        # --- Form Finder ---
        if u.path == "/api/forms/search":
            q_str = (q.get("q", [""])[0]).strip()
            mode  = (q.get("mode", ["keyword"])[0]).strip().lower()
            if not q_str:
                return self._json({"results": [], "expanded_terms": []})
            return self._json(self._search("forms", q_str, mode))

        if u.path == "/api/forms/stats":
            from ingestion.forms_search import stats as forms_stats
            db = _fdb()
            try:
                return self._json(forms_stats(db))
            finally:
                db.close()

        # --- How-To Hub ---
        if u.path == "/api/howto/search":
            q_str = (q.get("q", [""])[0]).strip()
            mode  = (q.get("mode", ["keyword"])[0]).strip().lower()
            if not q_str:
                return self._json({"results": [], "expanded_terms": []})
            return self._json(self._search("howto", q_str, mode))

        if u.path == "/api/howto/stats":
            from ingestion.howto_search import stats as howto_stats
            db = _fdb()
            try:
                return self._json(howto_stats(db))
            finally:
                db.close()

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if not _check_rate(self._client_ip(), u.path):
            return self._json({"error": "rate limit exceeded — please slow down"}, 429)
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or "{}")
        except (json.JSONDecodeError, ValueError):
            return self._json({"error": "invalid JSON body"}, 400)

        # --- AI chat ---
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

        # --- Scrape triggers (optional key protection) ---
        if u.path in ("/api/forms/scrape", "/api/howto/scrape"):
            if SCRAPE_KEY and body.get("key") != SCRAPE_KEY:
                return self._json({"error": "forbidden — set key in request body"}, 403)

        if u.path == "/api/forms/scrape":
            from ingestion.forms_scraper import run_scrape
            db = _fdb()
            try:
                result = run_scrape(db)
            except Exception as exc:
                return self._json({"error": str(exc)}, 500)
            finally:
                db.close()
            return self._json(result)

        if u.path == "/api/howto/scrape":
            from ingestion.howto_scraper import run_scrape as howto_run_scrape
            db = _fdb()
            try:
                result = howto_run_scrape(db)
            except Exception as exc:
                return self._json({"error": str(exc)}, 500)
            finally:
                db.close()
            return self._json(result)

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
