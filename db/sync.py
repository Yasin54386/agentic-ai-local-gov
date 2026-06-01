"""Incremental change-detection sync (upsert) into the migrated database.

Each row's identity is a hash of its content, so the id is stable across
reordering. On every fetch we reconcile the fresh hash-set against what's stored
for that dataset:

    new hash            -> INSERT   (a new row)
    hash now missing    -> DELETE   (row changed or removed)
    hash already stored -> skip     (unchanged -> zero writes)

Rows are routed to BOTH `records` and their categorised theme table (via
ingestion.themes.classify), and reconciled in both, so the partitions stay
consistent. No DROP/rebuild, no duplicates, no wipes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ingestion import unify as U
from ingestion.themes import classify
from .connection import Database

# Column order of the migrated `records` table (and every themed table).
REC_COLS = ["record_id", "dataset_id", "dataset_title", "source_system", "domain",
            "table_name", "period_raw", "period_year", "area_type", "area_name",
            "geo_lat", "geo_lng", "category", "metric_name", "metric_value",
            "payload", "ingested_at"]


def row_hash(row: dict) -> str:
    """Stable 16-char content hash of a row (order-independent)."""
    return hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:16]


def record_id(dataset_id: str, row: dict) -> str:
    return f"{dataset_id}#{row_hash(row)}"


def _canon(key, dataset_id, title, source, domain, theme, row) -> tuple:
    """Build a row in REC_COLS order, reusing the unify extractors."""
    _pf, pv = U.first_present(row, U.PERIOD_FIELDS)
    af, av = U.first_present(row, U.AREA_FIELDS)
    _cf, cv = U.first_present(row, U.CATEGORY_FIELDS)
    mf, mv = U.first_present(row, U.METRIC_FIELDS)
    lat, lng = U.extract_geo(row)
    return (key, dataset_id, title, source, domain, theme,
            str(pv) if pv is not None else None, U.parse_year(pv),
            af, str(av) if av is not None else None, lat, lng,
            str(cv) if cv is not None else None, mf, U.to_float(mv),
            json.dumps(row, default=str),
            datetime.now(timezone.utc).isoformat(timespec="seconds"))


def sync_dataset(db: Database, dataset_id: str, rows: list,
                 *, title: str | None = None, source: str | None = None) -> dict:
    """Reconcile fresh `rows` for one dataset into records + its theme table."""
    theme = classify(dataset_id)                      # <- the correct categorised table
    meta = db.fetchone(
        "SELECT title, source_system, domain FROM datasets WHERE canonical_id = ?",
        (dataset_id,))
    title = title or (meta["title"] if meta else dataset_id)
    source = source or (meta["source_system"] if meta else dataset_id.split(":")[0])
    domain = meta["domain"] if meta else theme

    # fresh state, deduped by content hash
    current: dict[str, dict] = {}
    for r in rows:
        if isinstance(r, dict):
            current[record_id(dataset_id, r)] = r

    stored = {x["record_id"] for x in db.fetchall(
        "SELECT record_id FROM records WHERE dataset_id = ?", (dataset_id,))}

    new = current.keys() - stored
    gone = stored - current.keys()

    for k in gone:                                    # remove from both partitions
        db.execute("DELETE FROM records WHERE record_id = ?", (k,))
        db.execute(f"DELETE FROM {theme} WHERE record_id = ?", (k,))
    if new:
        ph = ",".join("?" * len(REC_COLS))
        cols = ", ".join(REC_COLS)
        batch = [_canon(k, dataset_id, title, source, domain, theme, current[k]) for k in new]
        db.executemany(f"INSERT INTO records ({cols}) VALUES ({ph})", batch)
        db.executemany(f"INSERT INTO {theme} ({cols}) VALUES ({ph})", batch)
    db.commit()
    return {"dataset": dataset_id, "table": theme, "added": len(new),
            "removed": len(gone), "unchanged": len(current) - len(new),
            "total_now": len(current)}
