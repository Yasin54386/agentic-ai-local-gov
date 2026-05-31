"""Harvest orchestrator (CLI).

Pulls the catalog from every public source into the SQLite repository, then
(optionally) regenerates the catalog report.

Usage:
    python -m ingestion.harvest                 # harvest NT + Darwin (default)
    python -m ingestion.harvest --include-federal --federal-limit 500
    python -m ingestion.harvest --only smart.darwin.nt.gov.au
    python -m ingestion.harvest --db data/catalog.db --report
"""
from __future__ import annotations

import argparse
import sys
import time

from .report import write_report
from .sources import ArcGISHubSource, CKANSource, OpendatasoftSource
from .store import CatalogStore

DEFAULT_DB = "data/catalog.db"


def build_sources(args) -> list:
    sources = [
        CKANSource("https://data.nt.gov.au", system="data.nt.gov.au"),
        OpendatasoftSource(),
        ArcGISHubSource(),
    ]
    if args.include_federal:
        sources.append(CKANSource(
            "https://data.gov.au/data", system="data.gov.au",
            query="Northern Territory", max_datasets=args.federal_limit,
        ))
    if args.only:
        sources = [s for s in sources if s.system in args.only]
    return sources


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Harvest NT/Darwin public open data into the catalog.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--include-federal", action="store_true",
                   help="also harvest data.gov.au filtered to the NT (large, noisy)")
    p.add_argument("--federal-limit", type=int, default=500,
                   help="cap on federal datasets harvested (default 500)")
    p.add_argument("--only", nargs="*", help="harvest only these source systems")
    p.add_argument("--report", action="store_true", help="regenerate docs/CATALOG.md after harvest")
    args = p.parse_args(argv)

    store = CatalogStore(args.db)
    sources = build_sources(args)
    grand_total = 0
    started = time.time()

    for src in sources:
        t0 = time.time()
        print(f"[harvest] {src.system} ...", flush=True)
        try:
            n = store.upsert_many(src.harvest())
        except Exception as exc:  # one bad source shouldn't kill the run
            print(f"  !! {src.system} failed: {exc}", file=sys.stderr, flush=True)
            continue
        grand_total += n
        print(f"  +{n} datasets in {time.time()-t0:0.1f}s", flush=True)

    print(f"[harvest] catalog now holds {store.count()} datasets "
          f"(this run touched {grand_total}) in {time.time()-started:0.1f}s")

    if args.report:
        path = write_report(store)
        print(f"[harvest] wrote report -> {path}")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
