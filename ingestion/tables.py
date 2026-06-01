"""Split the unified records into a handful of CATEGORISED tables.

Instead of one big `records` table (or 24 tiny ones), partition rows into ~7
themed tables (finance, governance, demographics, economy, animals, environment,
mobility, live) by dataset theme. Each themed table keeps the canonical envelope
(extracted dims + JSON payload) so it's queryable and lossless.

Reads from data/unified.db (the `records` table) and writes the themed tables
back into the same DB, plus a data/table_registry.json describing them.

    python -m ingestion.tables
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict

from .themes import THEME_DESCRIPTIONS, classify

UNIFIED_DB = "data/unified.db"
REGISTRY = "data/table_registry.json"

CANON_COLS = ["record_id", "dataset_id", "dataset_title", "source_system", "domain",
              "period_raw", "period_year", "area_type", "area_name", "geo_lat",
              "geo_lng", "category", "metric_name", "metric_value", "payload",
              "ingested_at"]


def _create(con: sqlite3.Connection, table: str) -> None:
    cols = ",\n  ".join(f"{c} {'INTEGER' if c=='period_year' else ('REAL' if c in ('geo_lat','geo_lng','metric_value') else 'TEXT')}"
                        + (" PRIMARY KEY" if c == "record_id" else "")
                        for c in CANON_COLS)
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CREATE TABLE {table} (\n  {cols}\n)")
    con.execute(f"CREATE INDEX idx_{table}_area ON {table}(area_name)")
    con.execute(f"CREATE INDEX idx_{table}_year ON {table}(period_year)")
    con.execute(f"CREATE INDEX idx_{table}_dataset ON {table}(dataset_id)")


def build(unified_db: str = UNIFIED_DB) -> dict:
    con = sqlite3.connect(unified_db)
    con.row_factory = sqlite3.Row
    rows = con.execute(f"SELECT {', '.join(CANON_COLS)} FROM records").fetchall()

    # Route each record to its theme.
    by_theme: dict[str, list] = defaultdict(list)
    datasets_by_theme: dict[str, set] = defaultdict(set)
    for r in rows:
        theme = classify(r["dataset_id"])
        by_theme[theme].append(tuple(r[c] for c in CANON_COLS))
        datasets_by_theme[theme].add(r["dataset_id"])

    placeholders = ",".join("?" * len(CANON_COLS))
    registry = {"tables": []}
    for theme in sorted(by_theme):
        _create(con, theme)
        con.executemany(f"INSERT OR REPLACE INTO {theme} VALUES ({placeholders})", by_theme[theme])
        registry["tables"].append({
            "table": theme,
            "description": THEME_DESCRIPTIONS.get(theme, "uncategorised"),
            "rows": len(by_theme[theme]),
            "datasets": sorted(datasets_by_theme[theme]),
        })
    con.commit()
    con.close()

    json.dump(registry, open(REGISTRY, "w", encoding="utf-8"), indent=2)
    return registry


def main() -> int:
    reg = build()
    print(f"[tables] built {len(reg['tables'])} categorised tables in {UNIFIED_DB}:")
    for t in reg["tables"]:
        print(f"  {t['table']:14s} {t['rows']:6d} rows  ({len(t['datasets'])} datasets)  — {t['description']}")
    print(f"[tables] registry -> {REGISTRY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
