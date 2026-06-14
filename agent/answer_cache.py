"""Repeat-answer cache — layer 2 of the routing pyramid.

Public services see the same questions over and over; serving a stored
answer costs zero tokens. Keys are normalised questions (case, punctuation
and whitespace insensitive). Answers about live topics (weather, floods,
tides) get a short TTL; everything else keeps for a week.

Shares the SQLite file with the budget ledger (AI_DB_PATH).
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
import unicodedata

from .budget import _db_path  # same runtime DB file as the usage ledger

LIVE_TTL_S = 600            # 10 minutes for weather/flood style questions
STATIC_TTL_S = 7 * 86400    # a week for everything else
MAX_ANSWER_CHARS = 8000
MAX_ROWS = 50_000

_LIVE_WORDS = re.compile(
    r"\b(weather|rain|rainfall|forecast|flood|cyclone|storm|tide|tides|"
    r"temperature|humidity|today|tonight|tomorrow|now|current|currently|"
    r"open|closed)\b"
)
_NORM_STRIP = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")

_init_lock = threading.Lock()
_initialised: set[str] = set()


def _connect() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    with _init_lock:
        key = f"cache:{path}"
        if key not in _initialised:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS answer_cache ("
                " key TEXT PRIMARY KEY,"
                " question TEXT NOT NULL,"
                " answer TEXT NOT NULL,"
                " created REAL NOT NULL,"
                " expires REAL NOT NULL,"
                " hits INTEGER NOT NULL DEFAULT 0)"
            )
            conn.commit()
            _initialised.add(key)
    return conn


def normalize(question: str) -> str:
    q = unicodedata.normalize("NFKC", question).lower()
    q = _NORM_STRIP.sub(" ", q)
    return _WS.sub(" ", q).strip()


def ttl_for(question: str) -> int:
    return LIVE_TTL_S if _LIVE_WORDS.search(normalize(question)) else STATIC_TTL_S


def get(question: str) -> str | None:
    key = normalize(question)
    if not key:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT answer, expires FROM answer_cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if row["expires"] < time.time():
            conn.execute("DELETE FROM answer_cache WHERE key = ?", (key,))
            conn.commit()
            return None
        conn.execute("UPDATE answer_cache SET hits = hits + 1 WHERE key = ?", (key,))
        conn.commit()
        return row["answer"]
    finally:
        conn.close()


def put(question: str, answer: str) -> None:
    key = normalize(question)
    answer = (answer or "").strip()
    if not key or not answer:
        return
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO answer_cache"
            " (key, question, answer, created, expires, hits) VALUES (?,?,?,?,?,0)",
            (key, question[:500], answer[:MAX_ANSWER_CHARS], now, now + ttl_for(question)),
        )
        # Opportunistic cleanup: drop expired rows, and oldest rows past the cap.
        conn.execute("DELETE FROM answer_cache WHERE expires < ?", (now,))
        n = conn.execute("SELECT COUNT(*) AS c FROM answer_cache").fetchone()["c"]
        if n > MAX_ROWS:
            conn.execute(
                "DELETE FROM answer_cache WHERE key IN (SELECT key FROM answer_cache"
                " ORDER BY created ASC LIMIT ?)", (n - MAX_ROWS,)
            )
        conn.commit()
    finally:
        conn.close()


def stats() -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS entries, COALESCE(SUM(hits),0) AS hits FROM answer_cache"
        ).fetchone()
        return {"entries": int(row["entries"]), "hits": int(row["hits"])}
    finally:
        conn.close()
