"""Repository query layer — the functions the LLM's tools are wired to.

These read from the harvested catalog (SQLite) and the downloaded data
(data/raw/...). They are plain, testable functions with no LLM dependency, so
the data layer can be verified on its own. The LLM never touches the data
directly — it only calls these.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from ingestion.store import CatalogStore

DEFAULT_DB = "data/catalog.db"
UNIFIED_DB = "data/unified.db"
RAW_ROOT = Path("data/raw")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:80] or "resource"


class Repository:
    def __init__(self, db_path: str = DEFAULT_DB, unified_db: str = UNIFIED_DB):
        self.store = CatalogStore(db_path)
        # Connect to the unified records table if it has been built.
        self.uni = None
        if Path(unified_db).exists():
            # check_same_thread=False: the web server is threaded and serialises
            # access with a lock, so cross-thread use of this connection is safe.
            self.uni = sqlite3.connect(unified_db, check_same_thread=False)
            self.uni.row_factory = sqlite3.Row

    # ---- tool-backing functions -------------------------------------------

    def search_datasets(self, query: str = "", domain: str = "", limit: int = 15) -> list[dict]:
        """Find datasets by free text (matched against title/description/tags)
        and/or operational domain."""
        q = (query or "").lower()
        out = []
        for r in self.store.all_datasets():
            if domain and r["domain"] != domain:
                continue
            hay = f"{r['title']} {r['description']} {r['tags_json']}".lower()
            if q and q not in hay:
                # also allow any single word to match
                if not any(w in hay for w in q.split()):
                    continue
            out.append({
                "id": r["canonical_id"],
                "title": r["title"],
                "domain": r["domain"],
                "source": r["source_system"],
                "records": r["record_count"],
                "formats": json.loads(r["formats_json"]),
                "description": (r["description"] or "")[:240],
                "source_url": r["source_url"],
            })
            if len(out) >= limit:
                break
        return out

    def get_dataset_info(self, dataset_id: str) -> dict | None:
        for r in self.store.all_datasets():
            if r["canonical_id"] == dataset_id:
                res = self.store.resources_for(dataset_id)
                return {
                    "id": r["canonical_id"],
                    "title": r["title"],
                    "description": r["description"],
                    "domain": r["domain"],
                    "publisher": r["publisher"],
                    "source": r["source_system"],
                    "records": r["record_count"],
                    "spatial": bool(r["spatial"]),
                    "license": r["license"],
                    "source_url": r["source_url"],
                    "resources": [{"name": x["name"], "format": x["fmt"],
                                   "downloaded": bool(x["downloaded_path"])} for x in res],
                }
        return None

    def _local_json_path(self, dataset_id: str) -> Path | None:
        try:
            source, ds_id = dataset_id.split(":", 1)
        except ValueError:
            return None
        p = RAW_ROOT / _safe(source) / _safe(ds_id) / "JSON_export_full_data.json"
        return p if p.exists() else None

    def get_dataset_records(self, dataset_id: str, limit: int = 50,
                            contains: str = "") -> dict:
        """Return actual records for a dataset from the downloaded data.
        Optionally filter to records whose text contains `contains`."""
        path = self._local_json_path(dataset_id)
        if not path:
            return {"error": f"No downloaded data for {dataset_id}. "
                             f"Run: python -m ingestion.fetch_data --dataset \"{dataset_id}\""}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = [data]
        if contains:
            c = contains.lower()
            data = [row for row in data if c in json.dumps(row).lower()]
        total = len(data)
        return {"dataset_id": dataset_id, "total_matching": total,
                "returned": min(limit, total), "records": data[:limit]}

    def aggregate(self, dataset_id: str, group_by: str, value: str = "",
                  op: str = "count") -> dict:
        """Group records by a field and count, or sum/avg a numeric field."""
        path = self._local_json_path(dataset_id)
        if not path:
            return {"error": f"No downloaded data for {dataset_id}."}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return {"error": "Dataset is not a list of records."}
        buckets: dict[str, float] = {}
        counts: dict[str, int] = {}
        for row in data:
            key = str(row.get(group_by, "(missing)"))
            counts[key] = counts.get(key, 0) + 1
            if op in ("sum", "avg") and value:
                try:
                    buckets[key] = buckets.get(key, 0.0) + float(row.get(value) or 0)
                except (TypeError, ValueError):
                    pass
        if op == "count":
            result = dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))
        elif op == "sum":
            result = dict(sorted(buckets.items(), key=lambda kv: kv[1], reverse=True))
        else:  # avg
            result = {k: round(buckets.get(k, 0) / counts[k], 2) for k in counts}
        return {"dataset_id": dataset_id, "group_by": group_by, "op": op,
                "value": value, "groups": result}

    def stats(self) -> dict:
        """Repository-wide stats."""
        return {
            "total_datasets": self.store.count(),
            "by_source": dict(self.store.counts_by("source_system")),
            "by_domain": dict(self.store.counts_by("domain")),
        }

    # ---- unified-table tools (neighbourhood profiles, transparency) --------

    def _require_unified(self) -> dict | None:
        if self.uni is None:
            return {"error": "Unified table not built. Run: python -m ingestion.unify"}
        return None

    def list_suburbs(self, limit: int = 80) -> list[str]:
        if self._require_unified():
            return []
        rows = self.uni.execute(
            "SELECT area_name, COUNT(*) n FROM records "
            "WHERE area_name IS NOT NULL GROUP BY area_name ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["area_name"] for r in rows]

    def neighbourhood_profile(self, suburb: str) -> dict:
        """Combine every dataset that mentions a suburb/ward into one profile."""
        err = self._require_unified()
        if err:
            return err
        like = f"%{suburb.strip().upper()}%"
        rows = self.uni.execute(
            "SELECT dataset_title, dataset_id, domain, category, metric_name, "
            "metric_value, period_year, payload FROM records "
            "WHERE UPPER(area_name) LIKE ?", (like,),
        ).fetchall()
        if not rows:
            return {"suburb": suburb, "found": False,
                    "hint": "No records. Try a known suburb (see list_suburbs)."}
        by_dataset: dict[str, dict] = {}
        for r in rows:
            d = by_dataset.setdefault(r["dataset_title"], {
                "dataset_id": r["dataset_id"], "domain": r["domain"],
                "record_count": 0, "sample_categories": set()})
            d["record_count"] += 1
            if r["category"]:
                d["sample_categories"].add(r["category"])
        summary = []
        for title, d in sorted(by_dataset.items(), key=lambda kv: -kv[1]["record_count"]):
            summary.append({
                "dataset": title, "dataset_id": d["dataset_id"], "domain": d["domain"],
                "records_for_suburb": d["record_count"],
                "categories": sorted(list(d["sample_categories"]))[:8],
            })
        return {"suburb": suburb, "found": True,
                "total_records": len(rows), "datasets": summary}

    def list_tables(self) -> dict:
        """List the categorised tables (finance, demographics, …) with row counts."""
        path = Path("data/table_registry.json")
        if not path.exists():
            return {"error": "Tables not built. Run: python -m ingestion.tables"}
        return json.loads(path.read_text(encoding="utf-8"))

    def query_unified(self, domain: str = "", area: str = "", year: int | None = None,
                      category: str = "", group_by: str = "", op: str = "count",
                      value_field: str = "metric_value", limit: int = 25,
                      table: str = "records") -> dict:
        """Flexible query over a categorised table (default: all records)."""
        err = self._require_unified()
        if err:
            return err
        # whitelist the table name (it goes into SQL) against the built tables
        valid = {"records"}
        reg = self.list_tables()
        if "tables" in reg:
            valid |= {t["table"] for t in reg["tables"]}
        if table not in valid:
            return {"error": f"unknown table '{table}'. Valid: {sorted(valid)}"}
        where, params = [], []
        if domain:
            where.append("domain = ?"); params.append(domain)
        if area:
            where.append("UPPER(area_name) LIKE ?"); params.append(f"%{area.upper()}%")
        if year:
            where.append("period_year = ?"); params.append(year)
        if category:
            where.append("UPPER(category) LIKE ?"); params.append(f"%{category.upper()}%")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        if group_by in {"domain", "area_name", "category", "period_year", "dataset_title"}:
            agg = {"count": "COUNT(*)", "sum": f"SUM({value_field})",
                   "avg": f"AVG({value_field})"}.get(op, "COUNT(*)")
            sql = (f"SELECT {group_by} k, {agg} v FROM {table}{clause} "
                   f"GROUP BY {group_by} ORDER BY v DESC LIMIT ?")
            rows = self.uni.execute(sql, (*params, limit)).fetchall()
            return {"table": table, "op": op, "group_by": group_by,
                    "groups": {str(r["k"]): r["v"] for r in rows}}
        sql = (f"SELECT dataset_title, area_name, period_year, category, metric_value, "
               f"payload FROM {table}{clause} LIMIT ?")
        rows = self.uni.execute(sql, (*params, limit)).fetchall()
        return {"matched": len(rows),
                "records": [{"dataset": r["dataset_title"], "area": r["area_name"],
                             "year": r["period_year"], "category": r["category"],
                             "value": r["metric_value"],
                             "detail": json.loads(r["payload"])} for r in rows]}

    # ---- column catalog (the semantic dictionary the LLM picks columns from) ----

    _catalog_cache = None

    def find_columns(self, query: str = "", semantic_class: str = "", limit: int = 20) -> dict:
        """Search the unified column catalog so the model can pick which column
        (and dataset) answers a question, then fetch just that."""
        if Repository._catalog_cache is None:
            path = Path("data/column_catalog.json")
            if not path.exists():
                return {"error": "Column catalog not built. Run: python -m ingestion.columns"}
            Repository._catalog_cache = json.loads(path.read_text(encoding="utf-8"))
        cat = Repository._catalog_cache
        q = (query or "").lower()
        cls = (semantic_class or "").upper()
        hits = []
        for col in cat["columns"]:
            if cls and col["semantic_class"] != cls:
                continue
            hay = f"{col['column']} {col['original_field']} {col['label']} {col['examples']}".lower()
            # word-boundary match so "rain" doesn't hit "training"
            if q and not any(re.search(r"\b" + re.escape(w), hay) for w in q.split()):
                continue
            hits.append({
                "column": col["column"], "label": col["label"],
                "semantic_class": col["semantic_class"], "data_type": col["data_type"],
                "tables": col.get("tables", []),
                "datasets": [d["dataset_id"] for d in col["appears_in"]],
                "examples": col["examples"][:3],
            })
            if len(hits) >= limit:
                break
        return {"query": query, "matches": len(hits), "columns": hits}

    def close(self) -> None:
        self.store.close()
        if self.uni is not None:
            self.uni.close()
