"""Download the actual data for harvested datasets (CLI).

The catalog (harvest.py) stores *metadata*. This downloads the real *payloads*
into data/raw/<source>/<dataset_id>/ and records the local path against each
resource. This is the Layer-1 'raw / landing' store from docs/02.

Usage:
    # download everything for the clean API sources (Darwin ODS + ArcGIS):
    python -m ingestion.fetch_data --api-sources

    # download data for one dataset:
    python -m ingestion.fetch_data --dataset "smart.darwin.nt.gov.au:councillor-expenses"

    # mirror EVERYTHING including NT CKAN file resources (large, slow):
    python -m ingestion.fetch_data --all

    # limit which formats get downloaded (e.g. skip giant PDFs):
    python -m ingestion.fetch_data --all --formats JSON CSV GEOJSON XLSX
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .http import get_bytes
from .store import CatalogStore

DEFAULT_DB = "data/catalog.db"
RAW_ROOT = "data/raw"
API_SOURCES = {"smart.darwin.nt.gov.au", "open-darwin.opendata.arcgis.com"}

EXT = {"JSON": ".json", "CSV": ".csv", "GEOJSON": ".geojson", "XLSX": ".xlsx",
       "XLS": ".xls", "PDF": ".pdf", "SHP": ".zip", "KML": ".kml", "API": ".json"}


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:80] or "resource"


def _ingest_and_delete(target: Path, canonical_id: str, unified_db: str) -> int:
    """Parse a downloaded file into unified DB then delete it. Returns row count."""
    import sqlite3, json, glob as _glob
    from datetime import datetime, timezone
    from .unify import iter_rows_for_dataset, canon_row, load_catalog_meta, SCHEMA

    source_dir = str(target.parent)
    meta_by_id = load_catalog_meta(DEFAULT_DB)
    meta = meta_by_id.get(canonical_id, {"title": canonical_id, "source": "", "domain": "other"})

    rows = []
    for i, row in enumerate(iter_rows_for_dataset(source_dir)):
        if isinstance(row, dict):
            rows.append(canon_row(i, canonical_id, meta, row))

    if rows:
        con = sqlite3.connect(unified_db)
        # Create table if not exists (first run)
        try:
            con.execute("SELECT 1 FROM records LIMIT 1")
        except sqlite3.OperationalError:
            con.executescript(SCHEMA)
        con.executemany(
            "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()

    # Delete raw file to free disk
    try:
        target.unlink()
    except Exception:
        pass

    return len(rows)


def download_dataset(store: CatalogStore, row, formats: set[str] | None,
                     stream: bool = False, unified_db: str = "data/unified.db") -> int:
    n = 0
    dest = Path(RAW_ROOT) / _safe(row["source_system"]) / _safe(row["source_dataset_id"])
    for res in store.resources_for(row["canonical_id"]):
        fmt = (res["fmt"] or "").upper()
        if formats and fmt not in formats:
            continue
        url = res["url"]
        if not url or not url.startswith("http"):
            continue
        dest.mkdir(parents=True, exist_ok=True)
        fname = _safe(res["name"] or fmt) + EXT.get(fmt, "")
        target = dest / fname
        try:
            data = get_bytes(url)
        except Exception as exc:
            print(f"  !! {row['canonical_id']} [{fmt}] failed: {exc}", file=sys.stderr)
            continue
        target.write_bytes(data)
        store.mark_downloaded(res["id"], str(target))
        print(f"  + {row['canonical_id']} [{fmt}] -> {target} ({len(data)} bytes)")
        if stream:
            ingested = _ingest_and_delete(target, row["canonical_id"], unified_db)
            print(f"    -> ingested {ingested} rows, raw file deleted")
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Download actual data for harvested datasets.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--dataset", help="canonical_id of a single dataset to download")
    p.add_argument("--api-sources", action="store_true",
                   help="download data for the clean API sources (Darwin ODS + ArcGIS)")
    p.add_argument("--all", action="store_true", help="download data for ALL datasets (large)")
    p.add_argument("--formats", nargs="*", help="restrict to these formats (e.g. JSON CSV GEOJSON)")
    p.add_argument("--stream", action="store_true",
                   help="ingest each file into unified DB then delete it immediately (saves disk)")
    p.add_argument("--unified-db", default="data/unified.db",
                   help="unified DB path (used with --stream)")
    args = p.parse_args(argv)

    store = CatalogStore(args.db)
    formats = {f.upper() for f in args.formats} if args.formats else None

    if args.dataset:
        rows = [r for r in store.all_datasets() if r["canonical_id"] == args.dataset]
    elif args.api_sources:
        rows = [r for r in store.all_datasets() if r["source_system"] in API_SOURCES]
    elif args.all:
        rows = store.all_datasets()
    else:
        print("Nothing to do. Pass --dataset, --api-sources, or --all.", file=sys.stderr)
        store.close()
        return 2

    total = 0
    for row in rows:
        total += download_dataset(store, row, formats,
                                  stream=args.stream, unified_db=args.unified_db)
    print(f"[fetch] downloaded {total} resource files across {len(rows)} datasets")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
