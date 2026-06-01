"""Load data into the migrated database.

Reads the already-harvested artifacts (data/catalog.db, data/unified.db,
data/column_catalog.json) and inserts them into the migrated schema — datasets,
records (+ the themed table for each row), and the column catalog. Works against
whatever DATABASE_URL points at (SQLite by default, or PostgreSQL).

Run migrations first, then this:
    python -m db.migrate
    python -m db.load
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ingestion.themes import THEMES, classify
from .connection import Database

CATALOG_DB = "data/catalog.db"
UNIFIED_DB = "data/unified.db"
COLUMN_CATALOG = "data/column_catalog.json"
BATCH = 2000

RECORD_COLS = ["record_id", "dataset_id", "dataset_title", "source_system", "domain",
               "table_name", "period_raw", "period_year", "area_type", "area_name",
               "geo_lat", "geo_lng", "category", "metric_name", "metric_value",
               "payload", "ingested_at"]
SRC_RECORD_COLS = [c for c in RECORD_COLS if c != "table_name"]


def _src(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def _insert_batches(db: Database, table: str, cols: list[str], rows: list[tuple]) -> int:
    ph = ",".join("?" * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph})"
    n = 0
    for i in range(0, len(rows), BATCH):
        db.executemany(sql, rows[i:i + BATCH])
        n += len(rows[i:i + BATCH])
    db.commit()
    return n


def load_datasets(db: Database) -> int:
    if not Path(CATALOG_DB).exists():
        return 0
    src = _src(CATALOG_DB)
    cols = ["canonical_id", "source_system", "source_dataset_id", "title", "description",
            "domain", "publisher", "classification", "spatial", "record_count", "license",
            "source_url", "source_modified", "retrieved_at", "tags_json", "formats_json"]
    rows = [tuple(r[c] for c in cols) for r in src.execute(f"SELECT {','.join(cols)} FROM datasets")]
    src.close()
    db.execute("DELETE FROM datasets")
    return _insert_batches(db, "datasets", cols, rows)


def load_resources(db: Database) -> int:
    if not Path(CATALOG_DB).exists():
        return 0
    src = _src(CATALOG_DB)
    cols = ["dataset_id", "name", "fmt", "url", "downloaded_path"]
    rows = [tuple(r[c] for c in cols)
            for r in src.execute(f"SELECT {','.join(cols)} FROM resources")]
    src.close()
    db.execute("DELETE FROM resources")
    return _insert_batches(db, "resources", cols, rows)


def load_records(db: Database) -> dict:
    if not Path(UNIFIED_DB).exists():
        return {"records": 0}
    src = _src(UNIFIED_DB)
    # clear target tables
    for t in ["records", *THEMES, "other"]:
        try:
            db.execute(f"DELETE FROM {t}")
        except Exception:
            pass
    db.commit()

    all_rows, by_theme = [], {t: [] for t in [*THEMES, "other"]}
    for r in src.execute(f"SELECT {','.join(SRC_RECORD_COLS)} FROM records"):
        theme = classify(r["dataset_id"])
        # build a full record row in RECORD_COLS order, injecting table_name
        d = {c: r[c] for c in SRC_RECORD_COLS}
        d["table_name"] = theme
        row = tuple(d[c] for c in RECORD_COLS)
        all_rows.append(row)
        by_theme.setdefault(theme, []).append(row)
    src.close()

    total = _insert_batches(db, "records", RECORD_COLS, all_rows)
    counts = {"records": total}
    for theme, rows in by_theme.items():
        if rows:
            counts[theme] = _insert_batches(db, theme, RECORD_COLS, rows)
    return counts


def load_column_catalog(db: Database) -> int:
    if not Path(COLUMN_CATALOG).exists():
        return 0
    cat = json.loads(Path(COLUMN_CATALOG).read_text(encoding="utf-8"))
    cols = ["column_name", "original_field", "label", "semantic_class", "data_type",
            "tables_json", "datasets_json", "examples_json", "null_rate", "needs_review"]
    rows = []
    for c in cat["columns"]:
        rows.append((
            c["column"], c["original_field"], c["label"], c["semantic_class"], c["data_type"],
            json.dumps(c.get("tables", [])),
            json.dumps([d["dataset_id"] for d in c["appears_in"]]),
            json.dumps(c["examples"], default=str),
            c["null_rate"], 1 if c["needs_review"] else 0,
        ))
    db.execute("DELETE FROM column_catalog")
    return _insert_batches(db, "column_catalog", cols, rows)


def main() -> int:
    db = Database().connect()
    try:
        nd = load_datasets(db)
        nr = load_resources(db)
        rc = load_records(db)
        ncat = load_column_catalog(db)
    finally:
        db.close()
    print(f"[load] datasets: {nd}  resources: {nr}")
    print(f"[load] records: {rc.get('records', 0)} (themed: "
          + ", ".join(f"{k} {v}" for k, v in rc.items() if k != 'records') + ")")
    print(f"[load] column_catalog: {ncat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
