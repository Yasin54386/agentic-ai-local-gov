"""AI budget ledger — the hard spend ceiling behind the chat tab.

Every model call in the app is gated and recorded here (see agent/llm.py,
the single choke point). The ledger stores real token usage per call in
SQLite, keyed by month and day in Australia/Darwin time, so the monthly
budget resets automatically on the 1st with no cron.

States:
    ok        spend below DEGRADE_AT of the monthly budget
    degraded  >= 80% of monthly budget used -> shorter answers
    paused    monthly budget, daily sub-cap, or daily call ceiling reached
              -> chat pauses politely; data panels keep working

Config (env):
    BUDGET_MONTHLY_AUD  monthly AI budget in AUD            (default 100)
    USD_PER_AUD         conservative fixed FX rate          (default 0.60)
                        LOW on purpose: a low rate shrinks the USD ceiling,
                        so a real rate above it lands UNDER the AUD budget.
    BUDGET_DAILY_AUD    daily sub-cap in AUD                (default monthly/30)
    AI_DAILY_CALLS      hard ceiling on AI calls per day    (default 450)
    AI_DB_PATH          ledger database file                (default data/ai_runtime.db)
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

# Darwin is UTC+9:30 year-round (no daylight saving), so a fixed offset is
# correct and avoids needing tzdata in slim containers.
DARWIN_TZ = timezone(timedelta(hours=9, minutes=30))

DEGRADE_AT = 0.80

# USD per million tokens: (input, output). Cache reads bill at 0.1x input,
# cache writes at 1.25x input (5-minute TTL).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}
# Unknown model -> assume the most expensive known price so the cap still holds.
_FALLBACK_PRICE = max(PRICES_PER_MTOK.values())
CACHE_READ_MULT = 0.10
CACHE_WRITE_MULT = 1.25

_init_lock = threading.Lock()
_initialised: set[str] = set()


class BudgetExceededError(RuntimeError):
    """Raised by the llm choke point when the AI allowance is used up."""

    def __init__(self, reason: str):
        super().__init__(f"AI budget exhausted ({reason})")
        self.reason = reason  # "monthly" | "daily" | "calls"


def _db_path() -> str:
    return os.environ.get("AI_DB_PATH", "data/ai_runtime.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    with _init_lock:
        if path not in _initialised:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS ai_usage ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts TEXT NOT NULL,"
                " month TEXT NOT NULL,"
                " day TEXT NOT NULL,"
                " model TEXT NOT NULL,"
                " endpoint TEXT NOT NULL DEFAULT '',"
                " input_tokens INTEGER NOT NULL DEFAULT 0,"
                " output_tokens INTEGER NOT NULL DEFAULT 0,"
                " cache_read_tokens INTEGER NOT NULL DEFAULT 0,"
                " cache_write_tokens INTEGER NOT NULL DEFAULT 0,"
                " cost_usd REAL NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_month ON ai_usage(month)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_day ON ai_usage(day)")
            conn.commit()
            _initialised.add(path)
    return conn


def _now_darwin() -> datetime:
    return datetime.now(tz=DARWIN_TZ)


def month_key(dt: datetime | None = None) -> str:
    return (dt or _now_darwin()).strftime("%Y-%m")


def day_key(dt: datetime | None = None) -> str:
    return (dt or _now_darwin()).strftime("%Y-%m-%d")


def monthly_cap_usd() -> float:
    aud = float(os.environ.get("BUDGET_MONTHLY_AUD", "100"))
    return aud * usd_per_aud()


def usd_per_aud() -> float:
    return float(os.environ.get("USD_PER_AUD", "0.60"))


def daily_cap_usd() -> float:
    aud = os.environ.get("BUDGET_DAILY_AUD")
    if aud is not None:
        return float(aud) * usd_per_aud()
    return monthly_cap_usd() / 30.0


def daily_call_ceiling() -> int:
    return int(os.environ.get("AI_DAILY_CALLS", "450"))


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    in_price, out_price = _FALLBACK_PRICE
    for prefix, prices in PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            in_price, out_price = prices
            break
    return (
        input_tokens * in_price
        + cache_read_tokens * in_price * CACHE_READ_MULT
        + cache_write_tokens * in_price * CACHE_WRITE_MULT
    ) / 1_000_000 + output_tokens * out_price / 1_000_000


def record(model: str, input_tokens: int, output_tokens: int,
           cache_read_tokens: int = 0, cache_write_tokens: int = 0,
           endpoint: str = "") -> float:
    """Log one API call's real usage. Returns the call's cost in USD."""
    usd = cost_usd(model, input_tokens, output_tokens,
                   cache_read_tokens, cache_write_tokens)
    now = _now_darwin()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO ai_usage (ts, month, day, model, endpoint, input_tokens,"
            " output_tokens, cache_read_tokens, cache_write_tokens, cost_usd)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             month_key(now), day_key(now), model, endpoint,
             input_tokens, output_tokens, cache_read_tokens,
             cache_write_tokens, usd),
        )
        conn.commit()
    finally:
        conn.close()
    return usd


def _spend(conn: sqlite3.Connection, column: str, key: str) -> tuple[float, int]:
    row = conn.execute(
        f"SELECT COALESCE(SUM(cost_usd),0) AS usd, COUNT(*) AS calls"
        f" FROM ai_usage WHERE {column} = ?", (key,)
    ).fetchone()
    return float(row["usd"]), int(row["calls"])


def status() -> dict:
    """Current budget state. Cheap enough to call on every request."""
    now = _now_darwin()
    conn = _connect()
    try:
        month_usd, _ = _spend(conn, "month", month_key(now))
        day_usd, day_calls = _spend(conn, "day", day_key(now))
    finally:
        conn.close()

    m_cap, d_cap = monthly_cap_usd(), daily_cap_usd()
    rate = usd_per_aud()
    state, reason = "ok", ""
    if month_usd >= m_cap:
        state, reason = "paused", "monthly"
    elif day_usd >= d_cap:
        state, reason = "paused", "daily"
    elif day_calls >= daily_call_ceiling():
        state, reason = "paused", "calls"
    elif month_usd >= m_cap * DEGRADE_AT:
        state = "degraded"

    return {
        "state": state,
        "reason": reason,
        "month_spend_aud": round(month_usd / rate, 2),
        "month_cap_aud": round(m_cap / rate, 2),
        "month_pct": round(100 * month_usd / m_cap, 1) if m_cap else 100.0,
        "day_spend_aud": round(day_usd / rate, 2),
        "day_cap_aud": round(d_cap / rate, 2),
        "day_calls": day_calls,
        "day_call_ceiling": daily_call_ceiling(),
    }


def check_allowed() -> dict:
    """Gate for the llm choke point: raise if paused, else return status()."""
    st = status()
    if st["state"] == "paused":
        raise BudgetExceededError(st["reason"])
    return st


def pause_message(reason: str) -> str:
    if reason == "monthly":
        return ("This month's AI allowance has been used up — the chat will be "
                "back on the 1st. The data panels, forms and how-to guides "
                "all still work.")
    return ("Today's AI allowance has been used up — the chat will be back "
            "tomorrow. The data panels, forms and how-to guides all still work.")
