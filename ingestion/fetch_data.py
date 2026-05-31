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


def download_dataset(store: CatalogStore, row, formats: set[str] | None) -> int:
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
        total += download_dataset(store, row, formats)
    print(f"[fetch] downloaded {total} resource files across {len(rows)} datasets")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
