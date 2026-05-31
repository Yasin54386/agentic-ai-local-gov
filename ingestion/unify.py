"""Unify all harvested records into ONE canonical SQL table.

The harvested datasets have wildly different schemas (5 columns to 130+). Rather
than force them into a rigid shape (lossy) or keep 24 separate tables (not
combinable), this builds the canonical record from docs/02 at ROW level:

  extracted common dimensions  +  full original row as JSON payload

So every row of every dataset lands in one `records` table you can query across
datasets (by domain / area / period / category / metric), while the `payload`
column guarantees zero data loss for each dataset's unique fields.

Usage:
    python -m ingestion.unify                       # build data/unified.db
    python -m ingestion.unify --db data/unified.db --catalog data/catalog.db
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

CATALOG_DB = "data/catalog.db"
UNIFIED_DB = "data/unified.db"
RAW_ROOT = "data/raw"

SCHEMA = """
DROP TABLE IF EXISTS records;
CREATE TABLE records (
    record_id     TEXT PRIMARY KEY,   -- "<dataset_id>#<rownum>"
    dataset_id    TEXT NOT NULL,      -- canonical id of the source dataset
    dataset_title TEXT,
    source_system TEXT,
    domain        TEXT,               -- operational domain (from the catalog)
    period_raw    TEXT,               -- original time value, as-is
    period_year   INTEGER,            -- parsed 4-digit year, when detectable
    area_type     TEXT,               -- which field the area came from
    area_name     TEXT,               -- suburb / ward / lga / ...
    geo_lat       REAL,
    geo_lng       REAL,
    category      TEXT,               -- primary categorical dimension
    metric_name   TEXT,               -- primary numeric field name, when obvious
    metric_value  REAL,               -- primary numeric value
    payload       TEXT NOT NULL,      -- full original row as JSON (no data loss)
    ingested_at   TEXT
);
CREATE INDEX idx_rec_dataset  ON records(dataset_id);
CREATE INDEX idx_rec_domain   ON records(domain);
CREATE INDEX idx_rec_area     ON records(area_name);
CREATE INDEX idx_rec_year     ON records(period_year);
CREATE INDEX idx_rec_category ON records(category);
"""

# Field-name priorities for extracting each common dimension. First match wins.
PERIOD_FIELDS = ["census_year", "fy_year", "financial_year", "fy", "year",
                 "month", "meeting_date", "infringment_date", "infringement_date",
                 "year_text"]
AREA_FIELDS = ["suburb", "suburb_name", "ward", "lga_name", "lga_name_2020",
               "lga", "abs_lga", "name", "sector"]
GEO_FIELDS = ["geo_point_2d", "geo_point", "centroid"]
CATEGORY_FIELDS = ["category", "expense_type", "grant_type", "program",
                   "animal_type", "vehicle_type", "bird_species", "measure",
                   "offence", "meeting_type", "type", "sub_category"]
METRIC_FIELDS = ["amount", "expenditure", "total", "population", "count",
                 "net_generation_mwh", "count_amt", "total_trips",
                 "total_distance_in_km", "persons", "gardens", "cash", "pos_count"]

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def parse_year(value) -> int | None:
    if value is None:
        return None
    m = _YEAR_RE.search(str(value))
    return int(m.group(0)) if m else None


def to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def first_present(row: dict, fields: list[str]):
    for f in fields:
        if f in row and row[f] not in (None, ""):
            return f, row[f]
    return None, None


def extract_geo(row: dict):
    """Return (lat, lng) from common ODS/GeoJSON geo representations."""
    for f in GEO_FIELDS:
        v = row.get(f)
        if not v:
            continue
        if isinstance(v, dict):
            lat = v.get("lat") or v.get("latitude")
            lng = v.get("lon") or v.get("lng") or v.get("longitude")
            if lat is not None and lng is not None:
                return to_float(lat), to_float(lng)
        if isinstance(v, (list, tuple)) and len(v) == 2:
            # ODS geo_point_2d is [lat, lon]
            return to_float(v[0]), to_float(v[1])
        if isinstance(v, str) and "," in v:
            parts = v.split(",")
            if len(parts) == 2:
                return to_float(parts[0]), to_float(parts[1])
    return None, None


def load_catalog_meta(catalog_db: str) -> dict[str, dict]:
    con = sqlite3.connect(catalog_db)
    con.row_factory = sqlite3.Row
    meta = {}
    for r in con.execute("SELECT canonical_id, title, source_system, domain FROM datasets"):
        meta[r["canonical_id"]] = {"title": r["title"], "source": r["source_system"],
                                   "domain": r["domain"]}
    con.close()
    return meta


def iter_rows_for_dataset(source_dir: str):
    """Yield rows from a dataset's downloaded data (JSON export or GeoJSON)."""
    json_path = os.path.join(source_dir, "JSON_export_full_data.json")
    if os.path.exists(json_path):
        data = json.load(open(json_path, encoding="utf-8"))
        if isinstance(data, list):
            yield from data
            return
    # GeoJSON (ArcGIS hub) — flatten feature properties + geometry centroid
    for gj in glob.glob(os.path.join(source_dir, "*.geojson")):
        gjson = json.load(open(gj, encoding="utf-8"))
        for feat in gjson.get("features", []):
            props = dict(feat.get("properties") or {})
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates")
            # rough centroid: first coordinate pair found
            flat = coords
            while isinstance(flat, list) and flat and isinstance(flat[0], list):
                flat = flat[0]
            if isinstance(flat, list) and len(flat) == 2:
                props["geo_point_2d"] = [flat[1], flat[0]]  # [lat, lng]
            yield props
        return


def canon_row(rownum: int, dataset_id: str, meta: dict, row: dict) -> tuple:
    p_field, p_val = first_present(row, PERIOD_FIELDS)
    a_field, a_val = first_present(row, AREA_FIELDS)
    c_field, c_val = first_present(row, CATEGORY_FIELDS)
    m_field, m_val = first_present(row, METRIC_FIELDS)
    lat, lng = extract_geo(row)
    return (
        f"{dataset_id}#{rownum}",
        dataset_id,
        meta.get("title"),
        meta.get("source"),
        meta.get("domain"),
        str(p_val) if p_val is not None else None,
        parse_year(p_val),
        a_field,
        str(a_val) if a_val is not None else None,
        lat, lng,
        str(c_val) if c_val is not None else None,
        m_field,
        to_float(m_val),
        json.dumps(row, default=str),
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def build(unified_db: str = UNIFIED_DB, catalog_db: str = CATALOG_DB) -> dict:
    meta_by_id = load_catalog_meta(catalog_db)
    con = sqlite3.connect(unified_db)
    con.executescript(SCHEMA)

    total = 0
    per_dataset = {}
    # Walk each downloaded dataset directory.
    for source_dir in sorted(glob.glob(os.path.join(RAW_ROOT, "*", "*"))):
        if not os.path.isdir(source_dir):
            continue
        source_system = os.path.basename(os.path.dirname(source_dir))
        ds_id = os.path.basename(source_dir)
        canonical_id = f"{source_system}:{ds_id}"
        meta = meta_by_id.get(canonical_id, {"title": ds_id, "source": source_system,
                                             "domain": "other"})
        rows = []
        for i, row in enumerate(iter_rows_for_dataset(source_dir)):
            if isinstance(row, dict):
                rows.append(canon_row(i, canonical_id, meta, row))
        if rows:
            con.executemany(
                "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            per_dataset[canonical_id] = len(rows)
            total += len(rows)
    con.commit()
    con.close()
    return {"total_records": total, "datasets": len(per_dataset), "per_dataset": per_dataset}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Unify all harvested records into one SQL table.")
    p.add_argument("--db", default=UNIFIED_DB)
    p.add_argument("--catalog", default=CATALOG_DB)
    args = p.parse_args(argv)
    result = build(args.db, args.catalog)
    print(f"[unify] {result['total_records']:,} records from {result['datasets']} "
          f"datasets -> {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
