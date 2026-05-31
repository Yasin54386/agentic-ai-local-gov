"""Scheduled refresh — feeds the unified table THROUGH MCP every 6 hours.

Each cycle:
  1. Calls the live tools VIA THE MCP SERVER (real JSON-RPC round-trip) and
     appends a live weather/flood snapshot into the unified `records` table,
     building a time series over time.
  2. (Optional, --datasets) re-harvests the City of Darwin live datasets and
     rebuilds the unified table so stored data stays fresh.

Run as a long-lived loop:   python -m ingestion.refresh            # every 6h
One cycle then exit:        python -m ingestion.refresh --once
Custom interval (seconds):  python -m ingestion.refresh --interval 3600

Prefer cron? See RUNBOOK.md — point cron at `--once`.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from mcp_server.client import MCPClient

UNIFIED_DB = "data/unified.db"
SIX_HOURS = 6 * 60 * 60


def _ensure_table(con: sqlite3.Connection) -> None:
    # Reuse the unified schema; create if a fresh DB.
    con.execute("""
        CREATE TABLE IF NOT EXISTS records (
            record_id TEXT PRIMARY KEY, dataset_id TEXT, dataset_title TEXT,
            source_system TEXT, domain TEXT, period_raw TEXT, period_year INTEGER,
            area_type TEXT, area_name TEXT, geo_lat REAL, geo_lng REAL,
            category TEXT, metric_name TEXT, metric_value REAL, payload TEXT,
            ingested_at TEXT)
    """)


def snapshot_live_via_mcp(unified_db: str = UNIFIED_DB) -> dict:
    """Pull live weather + flood risk THROUGH the MCP server and store a snapshot."""
    now = datetime.now(timezone.utc)
    ts = now.isoformat(timespec="seconds")
    with MCPClient() as mcp:
        weather = mcp.call_tool("live_weather")
        flood = mcp.call_tool("flood_risk")

    obs = (weather or {}).get("observed_now", {})
    payload = {"weather": weather, "flood_risk": flood, "captured_at": ts}
    row = (
        f"live:darwin-weather#{ts}", "live:darwin-weather", "Live Darwin Weather (via MCP)",
        "open-meteo", "parks & environment", ts, now.year, "city", "Darwin",
        -12.4634, 130.8456, (flood or {}).get("flood_risk_level"),
        "temp_c", obs.get("temp_c"), json.dumps(payload, default=str), ts,
    )
    con = sqlite3.connect(unified_db)
    _ensure_table(con)
    con.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
    con.commit()
    total = con.execute(
        "SELECT COUNT(*) FROM records WHERE dataset_id='live:darwin-weather'").fetchone()[0]
    con.close()
    return {"captured_at": ts, "temp_c": obs.get("temp_c"),
            "flood_risk": (flood or {}).get("flood_risk_level"),
            "live_snapshots_in_table": total}


def refresh_datasets() -> dict:
    """Re-harvest the City of Darwin live datasets and rebuild the unified table."""
    from ingestion import unify
    from ingestion.fetch_data import API_SOURCES, download_dataset
    from ingestion.sources import OpendatasoftSource
    from ingestion.store import CatalogStore

    store = CatalogStore("data/catalog.db")
    n = store.upsert_many(OpendatasoftSource().harvest())
    count = 0
    for row in store.all_datasets():
        if row["source_system"] in API_SOURCES:
            count += download_dataset(store, row, {"JSON", "CSV", "GEOJSON"})
    store.close()
    result = unify.build()
    return {"datasets_refreshed": n, "files_downloaded": count,
            "unified_records": result["total_records"]}


def run_once(do_datasets: bool) -> None:
    print(f"[refresh] {datetime.now(timezone.utc).isoformat(timespec='seconds')} cycle start")
    live = snapshot_live_via_mcp()
    print(f"  live (via MCP): {live['temp_c']}C, flood={live['flood_risk']}, "
          f"snapshots={live['live_snapshots_in_table']}")
    if do_datasets:
        ds = refresh_datasets()
        print(f"  datasets: refreshed {ds['datasets_refreshed']}, "
              f"unified now {ds['unified_records']} records")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Feed the unified table through MCP on a schedule.")
    p.add_argument("--once", action="store_true", help="run a single cycle and exit (use with cron)")
    p.add_argument("--interval", type=int, default=SIX_HOURS, help="seconds between cycles (default 6h)")
    p.add_argument("--datasets", action="store_true",
                   help="also re-harvest + rebuild the Darwin datasets each cycle")
    args = p.parse_args(argv)

    if args.once:
        run_once(args.datasets)
        return 0
    print(f"[refresh] loop every {args.interval}s. Ctrl-C to stop.")
    while True:
        try:
            run_once(args.datasets)
        except Exception as exc:
            print(f"  !! cycle failed: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
