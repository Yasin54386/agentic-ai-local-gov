"""Repository query layer — the functions the LLM's tools are wired to.

Reads everything from the ONE migrated database (db/connection.py, selected by
DATABASE_URL — SQLite by default, PostgreSQL when configured). The LLM, the MCP
server, the agent loop and the tool definitions are unchanged: they only call
these methods, which keep the same signatures and return shapes as before.

Build the database first:  python -m db.migrate && python -m db.load
"""
from __future__ import annotations

import json
import re
from typing import Any

from db.connection import Database
from ingestion.themes import THEMES, THEME_DESCRIPTIONS

THEMED_TABLES = [*THEMES, "other"]
RECORD_TABLES = {"records", *THEMED_TABLES}


class Repository:
    def __init__(self, url: str | None = None):
        self.db = Database(url).connect()
        self._catalog_cache: list[dict] | None = None
        try:
            self.ready = self.db.fetchone("SELECT COUNT(*) AS c FROM datasets")["c"] > 0
        except Exception:
            self.ready = False

    def _not_ready(self) -> dict:
        return {"error": "Database not built. Run: python -m db.migrate && python -m db.load"}

    # ---- dataset catalog tools -------------------------------------------

    def search_datasets(self, query: str = "", domain: str = "", limit: int = 15) -> list[dict]:
        """Find datasets by free text (title/description/tags) and/or domain."""
        if not self.ready:
            return []
        q = (query or "").lower()
        rows = self.db.fetchall(
            "SELECT canonical_id, title, description, domain, source_system, "
            "record_count, formats_json, source_url, tags_json FROM datasets")
        out = []
        for r in rows:
            if domain and r["domain"] != domain:
                continue
            hay = f"{r['title']} {r['description']} {r['tags_json']}".lower()
            if q and q not in hay and not any(w in hay for w in q.split()):
                continue
            out.append({
                "id": r["canonical_id"], "title": r["title"], "domain": r["domain"],
                "source": r["source_system"], "records": r["record_count"],
                "formats": json.loads(r["formats_json"] or "[]"),
                "description": (r["description"] or "")[:240], "source_url": r["source_url"],
            })
            if len(out) >= limit:
                break
        return out

    def get_dataset_info(self, dataset_id: str) -> dict | None:
        if not self.ready:
            return None
        r = self.db.fetchone(
            "SELECT canonical_id, title, description, domain, publisher, source_system, "
            "record_count, spatial, license, source_url FROM datasets WHERE canonical_id = ?",
            (dataset_id,))
        if not r:
            return None
        res = self.db.fetchall(
            "SELECT name, fmt, downloaded_path FROM resources WHERE dataset_id = ?",
            (dataset_id,))
        return {
            "id": r["canonical_id"], "title": r["title"], "description": r["description"],
            "domain": r["domain"], "publisher": r["publisher"], "source": r["source_system"],
            "records": r["record_count"], "spatial": bool(r["spatial"]),
            "license": r["license"], "source_url": r["source_url"],
            "resources": [{"name": x["name"], "format": x["fmt"],
                           "downloaded": bool(x["downloaded_path"])} for x in res],
        }

    def _records_for(self, dataset_id: str) -> list[dict]:
        rows = self.db.fetchall(
            "SELECT payload FROM records WHERE dataset_id = ?", (dataset_id,))
        return [json.loads(r["payload"]) for r in rows]

    def get_dataset_records(self, dataset_id: str, limit: int = 50, contains: str = "") -> dict:
        """Return actual records for a dataset (from the records table payload)."""
        if not self.ready:
            return self._not_ready()
        data = self._records_for(dataset_id)
        if not data:
            return {"dataset_id": dataset_id, "total_matching": 0, "returned": 0,
                    "records": [], "note": "No records stored for this dataset id."}
        if contains:
            c = contains.lower()
            data = [row for row in data if c in json.dumps(row, default=str).lower()]
        return {"dataset_id": dataset_id, "total_matching": len(data),
                "returned": min(limit, len(data)), "records": data[:limit]}

    def aggregate(self, dataset_id: str, group_by: str, value: str = "", op: str = "count") -> dict:
        """Group a dataset's records by a payload field; count or sum/avg a number."""
        if not self.ready:
            return self._not_ready()
        data = self._records_for(dataset_id)
        if not data:
            return {"error": f"No records stored for {dataset_id}."}
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
        else:
            result = {k: round(buckets.get(k, 0) / counts[k], 2) for k in counts}
        return {"dataset_id": dataset_id, "group_by": group_by, "op": op,
                "value": value, "groups": result}

    def stats(self) -> dict:
        if not self.ready:
            return self._not_ready()
        total = self.db.fetchone("SELECT COUNT(*) AS c FROM datasets")["c"]
        by_source = {r["source_system"]: r["c"] for r in self.db.fetchall(
            "SELECT source_system, COUNT(*) AS c FROM datasets GROUP BY source_system ORDER BY c DESC")}
        by_domain = {r["domain"]: r["c"] for r in self.db.fetchall(
            "SELECT domain, COUNT(*) AS c FROM datasets GROUP BY domain ORDER BY c DESC")}
        return {"total_datasets": total, "by_source": by_source, "by_domain": by_domain}

    # ---- records / categorised-table tools -------------------------------

    def list_suburbs(self, limit: int = 80) -> list[str]:
        if not self.ready:
            return []
        rows = self.db.fetchall(
            "SELECT area_name, COUNT(*) AS n FROM records "
            "WHERE area_name IS NOT NULL GROUP BY area_name ORDER BY n DESC LIMIT ?", (limit,))
        return [r["area_name"] for r in rows]

    def neighbourhood_profile(self, suburb: str) -> dict:
        if not self.ready:
            return self._not_ready()
        like = f"%{suburb.strip().upper()}%"
        rows = self.db.fetchall(
            "SELECT dataset_title, dataset_id, domain, category FROM records "
            "WHERE UPPER(area_name) LIKE ?", (like,))
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
        summary = [{
            "dataset": title, "dataset_id": d["dataset_id"], "domain": d["domain"],
            "records_for_suburb": d["record_count"],
            "categories": sorted(d["sample_categories"])[:8],
        } for title, d in sorted(by_dataset.items(), key=lambda kv: -kv[1]["record_count"])]
        return {"suburb": suburb, "found": True, "total_records": len(rows), "datasets": summary}

    def list_tables(self) -> dict:
        """List the categorised tables with row counts and datasets."""
        if not self.ready:
            return self._not_ready()
        tables = []
        for t in THEMED_TABLES:
            n = self.db.fetchone(f"SELECT COUNT(*) AS c FROM {t}")["c"]
            if not n:
                continue
            ds = [r["dataset_id"] for r in self.db.fetchall(
                f"SELECT DISTINCT dataset_id FROM {t} ORDER BY dataset_id")]
            tables.append({"table": t, "description": THEME_DESCRIPTIONS.get(t, "uncategorised"),
                           "rows": n, "datasets": ds})
        return {"tables": tables}

    def query_unified(self, domain: str = "", area: str = "", year: int | None = None,
                      category: str = "", group_by: str = "", op: str = "count",
                      value_field: str = "metric_value", limit: int = 25,
                      table: str = "records") -> dict:
        """Flexible query over a categorised table (default: all records)."""
        if not self.ready:
            return self._not_ready()
        if table not in RECORD_TABLES:
            return {"error": f"unknown table '{table}'. Valid: {sorted(RECORD_TABLES)}"}
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
            rows = self.db.fetchall(
                f"SELECT {group_by} AS k, {agg} AS v FROM {table}{clause} "
                f"GROUP BY {group_by} ORDER BY v DESC LIMIT ?", (*params, limit))
            return {"table": table, "op": op, "group_by": group_by,
                    "groups": {str(r["k"]): r["v"] for r in rows}}
        rows = self.db.fetchall(
            f"SELECT dataset_title, area_name, period_year, category, metric_value, "
            f"payload FROM {table}{clause} LIMIT ?", (*params, limit))
        return {"table": table, "matched": len(rows),
                "records": [{"dataset": r["dataset_title"], "area": r["area_name"],
                             "year": r["period_year"], "category": r["category"],
                             "value": r["metric_value"],
                             "detail": json.loads(r["payload"])} for r in rows]}

    # ---- column catalog --------------------------------------------------

    def _catalog(self) -> list[dict]:
        if self._catalog_cache is None:
            rows = self.db.fetchall(
                "SELECT column_name, original_field, label, semantic_class, data_type, "
                "tables_json, datasets_json, examples_json FROM column_catalog")
            self._catalog_cache = [{
                "column": r["column_name"], "original_field": r["original_field"],
                "label": r["label"], "semantic_class": r["semantic_class"],
                "data_type": r["data_type"], "tables": json.loads(r["tables_json"] or "[]"),
                "datasets": json.loads(r["datasets_json"] or "[]"),
                "examples": json.loads(r["examples_json"] or "[]"),
            } for r in rows]
        return self._catalog_cache

    def find_columns(self, query: str = "", semantic_class: str = "", limit: int = 20) -> dict:
        """Search the column catalog to locate which column (and table/dataset)
        answers a question."""
        if not self.ready:
            return self._not_ready()
        cols = self._catalog()
        q = (query or "").lower()
        cls = (semantic_class or "").upper()
        hits = []
        for col in cols:
            if cls and col["semantic_class"] != cls:
                continue
            hay = f"{col['column']} {col['original_field']} {col['label']} {col['examples']}".lower()
            if q and not any(re.search(r"\b" + re.escape(w), hay) for w in q.split()):
                continue
            hits.append({
                "column": col["column"], "label": col["label"],
                "semantic_class": col["semantic_class"], "data_type": col["data_type"],
                "tables": col["tables"], "datasets": col["datasets"],
                "examples": col["examples"][:3],
            })
            if len(hits) >= limit:
                break
        return {"query": query, "matches": len(hits), "columns": hits}

    def close(self) -> None:
        self.db.close()
