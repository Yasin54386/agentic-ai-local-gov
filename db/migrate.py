"""Migration runner — applies versioned SQL in migrations/ in order, once each.

Tracks applied versions in a schema_migrations table. Works on SQLite and
PostgreSQL. The `LIKE_RECORDS` macro in a migration is expanded to the canonical
record columns (so themed tables stay in sync with `records`).

    python -m db.migrate                 # apply all pending migrations
    python -m db.migrate --status        # show applied / pending
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .connection import Database, describe

MIGRATIONS_DIR = Path("migrations")

# Canonical columns shared by `records` and every themed table.
LIKE_RECORDS = """
    record_id      TEXT PRIMARY KEY,
    dataset_id     TEXT,
    dataset_title  TEXT,
    source_system  TEXT,
    domain         TEXT,
    table_name     TEXT,
    period_raw     TEXT,
    period_year    INTEGER,
    area_type      TEXT,
    area_name      TEXT,
    geo_lat        DOUBLE PRECISION,
    geo_lng        DOUBLE PRECISION,
    category       TEXT,
    metric_name    TEXT,
    metric_value   DOUBLE PRECISION,
    payload        TEXT,
    ingested_at    TEXT
""".strip()


def _ensure_tracking(db: Database) -> None:
    db.run_script(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT)")
    db.commit()


def _applied(db: Database) -> set[str]:
    try:
        return {r[0] for r in db.fetchall("SELECT version FROM schema_migrations")}
    except Exception:
        return set()


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def status() -> None:
    db = Database().connect()
    _ensure_tracking(db)
    done = _applied(db)
    print(f"Database: {describe()}")
    for f in _migration_files():
        mark = "✓ applied" if f.stem in done else "· pending"
        print(f"  {mark}  {f.name}")
    db.close()


def migrate() -> int:
    db = Database().connect()
    _ensure_tracking(db)
    done = _applied(db)
    pending = [f for f in _migration_files() if f.stem not in done]
    if not pending:
        print(f"Up to date ({describe()}). No pending migrations.")
        db.close()
        return 0
    print(f"Applying {len(pending)} migration(s) to {describe()}")
    for f in pending:
        sql = f.read_text(encoding="utf-8").replace("LIKE_RECORDS", LIKE_RECORDS)
        db.run_script(sql)
        db.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                   (f.stem, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        db.commit()
        print(f"  ✓ {f.name}")
    db.close()
    print("Done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run database migrations.")
    p.add_argument("--status", action="store_true", help="show applied/pending and exit")
    args = p.parse_args(argv)
    if args.status:
        status()
        return 0
    return migrate()


if __name__ == "__main__":
    raise SystemExit(main())
