"""Ask Territory web server — stdlib only.

Panels (Live, Neighbourhood, Transparency, Stats, Form Finder, How-To Hub,
Guide Assistant, Admin) work without or with the local LLM.

    python -m webapp.server            # http://localhost:8000
    PORT=9000 python -m webapp.server

Concurrency-safe via _lock for the shared repository connection.
Search uses read-only SQLite connections (WAL mode — no contention with writes).
"""
from __future__ import annotations

import collections
import hashlib
import json
import logging
import logging.handlers
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
PORT   = int(os.environ.get("PORT", "8000"))

SCRAPE_KEY = os.environ.get("SCRAPE_KEY", "")
ADMIN_KEY  = os.environ.get("ADMIN_KEY", "")   # protect /admin and /api/admin/*

# ── structured request logging ────────────────────────────────────────────────
_log_dir = Path("logs")
_log_dir.mkdir(exist_ok=True)
_req_logger = logging.getLogger("requests")
_req_logger.setLevel(logging.INFO)
_req_logger.propagate = False
_rh = logging.handlers.RotatingFileHandler(
    _log_dir / "requests.log", maxBytes=10_000_000, backupCount=5, encoding="utf-8"
)
_rh.setFormatter(logging.Formatter("%(message)s"))
_req_logger.addHandler(_rh)

repo  = Repository()
_lock = threading.Lock()

# ── per-IP rate limiting ──────────────────────────────────────────────────────
RATE_LIMIT  = int(os.environ.get("RATE_LIMIT",  "60"))
RATE_WINDOW = int(os.environ.get("RATE_WINDOW", "60"))
_rate_lock    = threading.Lock()
_rate_buckets: dict[str, collections.deque] = collections.defaultdict(collections.deque)
RATE_LIMITED_PATHS = {"/api/forms/search", "/api/howto/search", "/api/ask", "/api/guide"}

def _check_rate(ip: str, path: str) -> bool:
    if path not in RATE_LIMITED_PATHS:
        return True
    now = time.monotonic()
    with _rate_lock:
        dq = _rate_buckets[ip]
        while dq and now - dq[0] > RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            return False
        dq.append(now)
    return True

# ── auto-refresh tiers ────────────────────────────────────────────────────────
AUTOREFRESH  = os.environ.get("AUTOREFRESH", "1") != "0"
LIVE_TTL     = int(os.environ.get("REFRESH_TTL",   "600"))
DATASETS_TTL = int(os.environ.get("DATASETS_TTL", "86400"))
_last_result = {"live": None, "datasets": None}
_tiers = {
    "live":     {"at": 0.0, "lock": threading.Lock(), "ttl": LIVE_TTL},
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
    if not AUTOREFRESH:
        return
    now = time.monotonic()
    for name, t in _tiers.items():
        if t["ttl"] <= 0 or now - t["at"] < t["ttl"]:
            continue
        if not t["lock"].acquire(blocking=False):
            continue
        t["at"] = now
        threading.Thread(target=_run_tier, args=(name,), daemon=True).start()

# ── helpers ───────────────────────────────────────────────────────────────────

def tool(name, args=None):
    with _lock:
        return dispatch(repo, name, args or {})

def _call(fn):
    with _lock:
        return fn(repo)

def _fdb():
    """Read-only DB connection for search queries (WAL mode: no lock contention)."""
    import sqlite3
    from db.config import load_config
    cfg = load_config()
    if cfg.engine == "sqlite":
        conn = sqlite3.connect(f"file:{cfg.sqlite_path}?mode=ro", uri=True,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    # PostgreSQL — fall back to normal connection
    from db.connection import Database
    return Database().connect()

def _fdb_rw():
    """Read-write DB connection (for writes: feedback, search logs)."""
    from db.connection import Database
    return Database().connect()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass   # silence default stderr output; we do structured JSON logging

    def _log_req(self, status: int, start: float):
        ip = self.headers.get("X-Forwarded-For", self.client_address[0] or "").split(",")[0].strip()
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:8]
        _req_logger.info(json.dumps({
            "ts":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": self.command,
            "path":   urlparse(self.path).path,
            "status": status,
            "ms":     round((time.monotonic() - start) * 1000),
            "ip":     ip_hash,
        }))

    def _json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        if not path.exists():
            return self._json({"error": "not found"}, 404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _client_ip(self) -> str:
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[0].strip() or self.client_address[0]

    def _check_admin(self) -> bool:
        if not ADMIN_KEY:
            return True   # no key set → allow (localhost dev mode)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        return q.get("key", [""])[0] == ADMIN_KEY

    def _search(self, source: str, q_str: str, mode: str, log_db=None) -> dict:
        if source == "forms":
            from ingestion.forms_search import keyword_search, fuzzy_search, did_you_mean, ai_search, log_search
        else:
            from ingestion.howto_search import keyword_search, fuzzy_search, did_you_mean, ai_search, log_search
        db = _fdb()
        try:
            if mode == "ai" and llm.server_up():
                result = ai_search(db, q_str, llm)
                used_mode = "ai"
            else:
                result = {"results": keyword_search(db, q_str), "expanded_terms": []}
                used_mode = "keyword"

            # Fuzzy fallback if FTS5 found nothing
            if not result["results"]:
                fuzzy = fuzzy_search(db, q_str)
                if fuzzy:
                    result["results"] = fuzzy
                    result["fuzzy"] = True
                    used_mode = "fuzzy"
                else:
                    result["did_you_mean"] = did_you_mean(db, q_str)
        except Exception as exc:
            result = {"results": [], "expanded_terms": [], "error": str(exc)}
            used_mode = "keyword"
        finally:
            if hasattr(db, "close"):
                db.close()

        # Log the search anonymously (write DB)
        try:
            wdb = _fdb_rw()
            log_search(wdb, q_str, len(result["results"]), used_mode)
            wdb.close()
        except Exception:
            pass

        return result

    def do_GET(self):
        t0 = time.monotonic()
        u  = urlparse(self.path)
        q  = parse_qs(u.query)
        status = 200

        try:
            status = self._handle_get(u, q)
        except Exception:
            self._json({"error": "internal server error"}, 500)
            status = 500
        finally:
            self._log_req(status, t0)

    def _handle_get(self, u, q) -> int:
        if u.path.startswith("/api/") and u.path != "/api/health":
            maybe_refresh()
            if not _check_rate(self._client_ip(), u.path):
                self._json({"error": "rate limit exceeded"}, 429); return 429

        # ── static pages ──
        pages = {
            "/": "index.html", "/index.html": "index.html",
            "/concept": "concept.html", "/concept.html": "concept.html",
            "/forms":   "forms.html",   "/forms.html":   "forms.html",
            "/howto":   "howto.html",   "/howto.html":   "howto.html",
            "/guide":   "guide.html",   "/guide.html":   "guide.html",
            "/tour":    "tour.html",    "/tour.html":    "tour.html",
        }
        if u.path in pages:
            self._file(STATIC / pages[u.path], "text/html; charset=utf-8"); return 200
        if u.path == "/manifest.json":
            self._file(STATIC / "manifest.json", "application/manifest+json"); return 200
        if u.path == "/sw.js":
            self._file(STATIC / "sw.js", "application/javascript"); return 200
        if u.path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return 204

        # ── admin pages ──
        if u.path in ("/admin", "/admin.html"):
            if not self._check_admin():
                self._json({"error": "forbidden"}, 403); return 403
            self._file(STATIC / "admin.html", "text/html; charset=utf-8"); return 200

        # ── core data APIs ──
        if u.path == "/api/stats":
            self._json(tool("repository_stats")); return 200
        if u.path == "/api/live":
            self._json({"weather": tool("live_weather"), "flood": tool("flood_risk")}); return 200
        if u.path == "/api/suburbs":
            self._json(tool("list_suburbs", {"limit": 60})); return 200
        if u.path == "/api/profile":
            suburb = (q.get("suburb", [""])[0]).strip()
            if not suburb:
                self._json({"error": "pass ?suburb="}, 400); return 400
            self._json(tool("neighbourhood_profile", {"suburb": suburb})); return 200
        if u.path == "/api/transparency":
            self._json(_call(lambda r: r.capital_by_category())); return 200
        if u.path == "/api/suburb_lookup":
            self._json(_call(lambda r: r.suburb_lookup(q.get("suburb", [""])[0]))); return 200
        if u.path == "/api/canopy":
            self._json(_call(lambda r: r.canopy_change())); return 200
        if u.path == "/api/mobility":
            self._json(_call(lambda r: r.mobility_trend())); return 200
        if u.path == "/api/decisions":
            self._json(_call(lambda r: r.decisions(q.get("q", [""])[0]))); return 200
        if u.path == "/api/grants":
            self._json(_call(lambda r: r.grants(q.get("q", [""])[0]))); return 200
        if u.path == "/api/equity":
            self._json(_call(lambda r: r.ward_spend())); return 200
        if u.path == "/api/tables":
            self._json(tool("list_tables", {})); return 200
        if u.path == "/api/columns":
            self._json(tool("find_columns", {"query": q.get("q", [""])[0]})); return 200
        if u.path == "/api/health":
            now = time.monotonic()
            ages = {n: (None if not t["at"] else round(now - t["at"])) for n, t in _tiers.items()}
            self._json({"ok": True, "model_server": llm.server_up(),
                        "model": llm.DEFAULT_MODEL, "autorefresh": AUTOREFRESH,
                        "ttl_s": {n: t["ttl"] for n, t in _tiers.items()},
                        "age_s": ages, "last_refresh": _last_result}); return 200

        # ── Form Finder ──
        if u.path == "/api/forms/search":
            q_str = (q.get("q", [""])[0]).strip()
            mode  = (q.get("mode", ["keyword"])[0]).strip().lower()
            if not q_str:
                self._json({"results": [], "expanded_terms": []}); return 200
            self._json(self._search("forms", q_str, mode)); return 200

        if u.path == "/api/forms/stats":
            from ingestion.forms_search import stats as fstats
            db = _fdb()
            try:
                self._json(fstats(db))
            finally:
                db.close()
            return 200

        if u.path == "/api/forms/popular":
            from ingestion.forms_search import popular_searches
            days  = int(q.get("days",  ["7"])[0])
            limit = int(q.get("limit", ["10"])[0])
            db = _fdb()
            try:
                self._json(popular_searches(db, days, limit))
            finally:
                db.close()
            return 200

        if u.path == "/api/forms/related":
            from ingestion.forms_search import related_howto
            category = (q.get("category", [""])[0]).strip()
            fid      = int(q.get("id", ["0"])[0])
            db = _fdb()
            try:
                self._json(related_howto(db, category, fid))
            finally:
                db.close()
            return 200

        # ── How-To Hub ──
        if u.path == "/api/howto/search":
            q_str = (q.get("q", [""])[0]).strip()
            mode  = (q.get("mode", ["keyword"])[0]).strip().lower()
            if not q_str:
                self._json({"results": [], "expanded_terms": []}); return 200
            self._json(self._search("howto", q_str, mode)); return 200

        if u.path == "/api/howto/stats":
            from ingestion.howto_search import stats as hstats
            db = _fdb()
            try:
                self._json(hstats(db))
            finally:
                db.close()
            return 200

        if u.path == "/api/howto/popular":
            from ingestion.howto_search import popular_searches
            days  = int(q.get("days",  ["7"])[0])
            limit = int(q.get("limit", ["10"])[0])
            db = _fdb()
            try:
                self._json(popular_searches(db, days, limit))
            finally:
                db.close()
            return 200

        if u.path == "/api/howto/related":
            from ingestion.howto_search import related_forms
            category = (q.get("category", [""])[0]).strip()
            gid      = int(q.get("id", ["0"])[0])
            db = _fdb()
            try:
                self._json(related_forms(db, category, gid))
            finally:
                db.close()
            return 200

        # ── Tour Guide ──
        if u.path == "/api/tour/search":
            from ingestion.tour_search import search as tsearch
            q_str    = (q.get("q",        [""])[0]).strip()
            category = (q.get("category", [""])[0]).strip()
            page     = max(1, int(q.get("page",  ["1"])[0]))
            limit    = min(24, max(1, int(q.get("limit", ["12"])[0])))
            db = _fdb()
            try:
                self._json(tsearch(db, q_str, category, page, limit))
            finally:
                db.close()
            return 200

        if u.path == "/api/tour/stats":
            from ingestion.tour_search import stats as tstats
            db = _fdb()
            try:
                self._json(tstats(db))
            finally:
                db.close()
            return 200

        if u.path.startswith("/api/tour/destination/"):
            from ingestion.tour_search import destination_detail
            try:
                dest_id = int(u.path.split("/")[-1])
            except ValueError:
                self._json({"error": "invalid id"}, 400); return 400
            db = _fdb()
            try:
                d = destination_detail(db, dest_id)
            finally:
                db.close()
            if d is None:
                self._json({"error": "not found"}, 404); return 404
            self._json(d); return 200

        if u.path.startswith("/api/tour/reviews/"):
            from ingestion.tour_search import reviews as treviews
            try:
                dest_id = int(u.path.split("/")[-1])
            except ValueError:
                self._json({"error": "invalid id"}, 400); return 400
            page  = max(1, int(q.get("page",  ["1"])[0]))
            limit = min(20, max(1, int(q.get("limit", ["3"])[0])))
            db = _fdb()
            try:
                self._json(treviews(db, dest_id, page, limit))
            finally:
                db.close()
            return 200

        # ── Admin API ──
        if u.path.startswith("/api/admin/"):
            if not self._check_admin():
                self._json({"error": "forbidden"}, 403); return 403
            return self._handle_admin(u, q)

        self._json({"error": "not found"}, 404); return 404

    def _handle_admin(self, u, q) -> int:
        import os as _os
        from db.config import load_config
        if u.path == "/api/admin/stats":
            db = _fdb()
            rw = _fdb_rw()
            try:
                from ingestion.forms_search import stats as fstats, popular_searches as fp
                from ingestion.howto_search  import stats as hstats, popular_searches as hp
                fs = fstats(db); hs = hstats(db)
                cfg = load_config()
                db_size = _os.path.getsize(cfg.sqlite_path) if cfg.engine == "sqlite" else 0
                feedback_count = rw.fetchone("SELECT COUNT(*) AS c FROM feedback")["c"]
                dead_forms     = rw.fetchone("SELECT COUNT(*) AS c FROM forms WHERE status='dead'")["c"]
                self._json({
                    "forms":         fs["total_forms"],
                    "howto_guides":  hs["total_guides"],
                    "db_size_mb":    round(db_size / 1_048_576, 1),
                    "feedback":      feedback_count,
                    "dead_forms":    dead_forms,
                    "forms_popular": fp(db, days=7),
                    "howto_popular": hp(db, days=7),
                    "model_up":      llm.server_up(),
                })
            finally:
                db.close(); rw.close()
            return 200

        if u.path == "/api/admin/feedback":
            rw = _fdb_rw()
            try:
                rows = rw.fetchall(
                    "SELECT id, url, title, source, issue, created_at "
                    "FROM feedback ORDER BY id DESC LIMIT 50"
                )
                self._json([dict(r) for r in rows])
            finally:
                rw.close()
            return 200

        self._json({"error": "not found"}, 404); return 404

    def do_POST(self):
        t0 = time.monotonic()
        u  = urlparse(self.path)
        status = 200

        if not _check_rate(self._client_ip(), u.path):
            self._json({"error": "rate limit exceeded"}, 429)
            self._log_req(429, t0); return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or "{}")
        except (json.JSONDecodeError, ValueError):
            self._json({"error": "invalid JSON body"}, 400)
            self._log_req(400, t0); return

        try:
            status = self._handle_post(u, body)
        except Exception:
            self._json({"error": "internal server error"}, 500)
            status = 500
        finally:
            self._log_req(status, t0)

    def _handle_post(self, u, body) -> int:
        # ── AI chat ──
        if u.path == "/api/ask":
            question = (body.get("question") or "").strip()
            if not question:
                self._json({"error": "empty question"}, 400); return 400
            if not llm.server_up():
                self._json({"answer": None, "model_offline": True,
                    "hint": "Start your local model: `bash scripts/setup_local_model.sh`"})
                return 200
            from agent.agent import run
            try:
                with _lock:
                    answer = run(question, repo=repo, verbose=False)
                self._json({"answer": answer}); return 200
            except Exception as exc:
                self._json({"error": str(exc)}, 500); return 500

        # ── Guide assistant (citizen-facing, NT-context prompt) ──
        if u.path == "/api/guide":
            question = (body.get("question") or "").strip()
            if not question:
                self._json({"error": "empty question"}, 400); return 400
            if not llm.server_up():
                self._json({"answer": None, "model_offline": True,
                    "hint": "AI guide offline — try searching Forms or How-To guides instead."})
                return 200
            ctx_prompt = (
                "You are a helpful Northern Territory (NT) local government services "
                "guide for citizens of Darwin and the NT. You help citizens understand "
                "what government services they need, what steps to take, and where to go. "
                "Be concise, friendly, and practical. Focus on NT-specific information. "
                "If you don't know the exact current fee or processing time, say so and "
                "direct them to the official NT Government website (nt.gov.au).\n\n"
                f"Citizen's question: {question}"
            )
            from agent.agent import run
            try:
                with _lock:
                    answer = run(ctx_prompt, repo=repo, verbose=False)
                self._json({"answer": answer}); return 200
            except Exception as exc:
                self._json({"error": str(exc)}, 500); return 500

        # ── Feedback submission ──
        if u.path == "/api/feedback":
            url   = (body.get("url")   or "").strip()[:500]
            title = (body.get("title") or "").strip()[:200]
            src   = (body.get("source") or "unknown")[:20]
            issue = (body.get("issue") or "").strip()[:1000]
            if not issue or not url:
                self._json({"error": "url and issue required"}, 400); return 400
            db = _fdb_rw()
            try:
                db.execute(
                    "INSERT INTO feedback (url, title, source, issue, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (url, title, src, issue,
                     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                )
                db.commit()
            finally:
                db.close()
            self._json({"ok": True}); return 200

        # ── Scrape triggers (optional key protection) ──
        if u.path in ("/api/forms/scrape", "/api/howto/scrape"):
            if SCRAPE_KEY and body.get("key") != SCRAPE_KEY:
                self._json({"error": "forbidden"}, 403); return 403

        if u.path == "/api/forms/scrape":
            from ingestion.forms_scraper import run_scrape
            db = _fdb_rw()
            try:
                result = run_scrape(db)
            except Exception as exc:
                self._json({"error": str(exc)}, 500); return 500
            finally:
                db.close()
            self._json(result); return 200

        if u.path == "/api/howto/scrape":
            from ingestion.howto_scraper import run_scrape as howto_run_scrape
            db = _fdb_rw()
            try:
                result = howto_run_scrape(db)
            except Exception as exc:
                self._json({"error": str(exc)}, 500); return 500
            finally:
                db.close()
            self._json(result); return 200

        # ── Tour Guide POST ──
        if u.path == "/api/tour/review":
            from ingestion.tour_search import add_review
            try:
                dest_id = int(body.get("destination_id", 0))
                name    = str(body.get("name", "")).strip()[:80] or "Anonymous"
                rating  = int(body.get("rating", 0))
                text    = str(body.get("text", "")).strip()[:2000]
            except (ValueError, TypeError):
                self._json({"error": "invalid fields"}, 400); return 400
            if not dest_id or not (1 <= rating <= 5) or not text:
                self._json({"error": "destination_id, rating (1-5) and text are required"}, 400)
                return 400
            db = _fdb_rw()
            try:
                result = add_review(db, dest_id, name, rating, text)
            except Exception as exc:
                self._json({"error": str(exc)}, 500); return 500
            finally:
                db.close()
            self._json(result); return 200

        self._json({"error": "not found"}, 404); return 404


def main() -> int:
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Ask Territory  →  http://localhost:{PORT}")
    print(f"  model: {'UP — ' + llm.DEFAULT_MODEL if llm.server_up() else 'offline (data panels still work)'}")
    print(f"  admin: http://localhost:{PORT}/admin" + (f"?key={ADMIN_KEY}" if ADMIN_KEY else " (no key set)"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
