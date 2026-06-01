"""Scheduled refresh — incremental change-detection sync into the live database.

Each cycle:
  1. Fetches live weather + flood THROUGH the MCP server and syncs it (only
     writes when the reading actually changes).
  2. (--datasets) re-fetches each City of Darwin dataset's export and syncs it —
     inserting new rows, deleting removed ones, leaving unchanged rows alone.

All writes go to the migrated database (db/connection.py → DATABASE_URL) and are
routed to the correct categorised table by db.sync. No DROP/rebuild, no dupes.

    python -m ingestion.refresh             # loop, live sync every 6h
    python -m ingestion.refresh --once      # one cycle (use with cron/systemd)
    python -m ingestion.refresh --once --datasets   # also reconcile all datasets
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from db.connection import Database
from db.sync import sync_dataset
from ingestion.http import get_json
from mcp_server.client import MCPClient

SIX_HOURS = 6 * 60 * 60
LIVE_ID = "live:darwin-weather"
ODS_EXPORT = "https://smart.darwin.nt.gov.au/api/explore/v2.1/catalog/datasets/{ds}/exports/json"


def refresh_live(db: Database) -> dict:
    """Pull live weather + flood via MCP and sync (current + forecast rows)."""
    with MCPClient() as mcp:
        weather = mcp.call_tool("live_weather")
        flood = mcp.call_tool("flood_risk")
    obs = (weather or {}).get("observed_now", {})
    rows = [{
        "kind": "current", "lga": "City of Darwin",
        "temp_c": obs.get("temp_c"), "humidity_pct": obs.get("humidity_pct"),
        "rain_mm": obs.get("rain_mm"), "conditions": obs.get("conditions"),
        "flood_risk": (flood or {}).get("flood_risk_level"),
    }]
    for d in (weather or {}).get("forecast", []):
        rows.append({"kind": "forecast", "date": d.get("date"), "rain_mm": d.get("rain_mm"),
                     "rain_chance_pct": d.get("rain_chance_pct"), "conditions": d.get("conditions")})
    return sync_dataset(db, LIVE_ID, rows,
                        title="Live Darwin Weather (via MCP)", source="open-meteo")


def refresh_datasets(db: Database) -> list[dict]:
    """Reconcile every City of Darwin dataset against its fresh export."""
    ids = [r["canonical_id"] for r in db.fetchall(
        "SELECT canonical_id FROM datasets WHERE source_system = 'smart.darwin.nt.gov.au'")]
    out = []
    for cid in ids:
        ds = cid.split(":", 1)[1]
        try:
            rows = get_json(ODS_EXPORT.format(ds=ds))
        except Exception as exc:
            out.append({"dataset": cid, "error": str(exc)})
            continue
        if isinstance(rows, list):
            out.append(sync_dataset(db, cid, rows))
    return out


def run_once(do_datasets: bool) -> None:
    print(f"[refresh] {datetime.now(timezone.utc).isoformat(timespec='seconds')} cycle start")
    db = Database().connect()
    try:
        live = refresh_live(db)
        print(f"  live (MCP): +{live['added']} -{live['removed']} "
              f"={live['unchanged']} → {live['table']} table")
        if do_datasets:
            for r in refresh_datasets(db):
                if "error" in r:
                    print(f"  !! {r['dataset']}: {r['error']}")
                else:
                    name = r["dataset"].split(":", 1)[1][:30]
                    print(f"  {name:30s} +{r['added']} -{r['removed']} "
                          f"={r['unchanged']} → {r['table']}")
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Incremental refresh sync into the live DB.")
    p.add_argument("--once", action="store_true", help="run a single cycle and exit")
    p.add_argument("--interval", type=int, default=SIX_HOURS, help="seconds between cycles (default 6h)")
    p.add_argument("--datasets", action="store_true", help="also reconcile all Darwin datasets")
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
