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

# Dataset ids used by the panel-specific views.
DS_CANOPY = "smart.darwin.nt.gov.au:tree-canopy-cover"
DS_MOBILITY = "smart.darwin.nt.gov.au:micromobility-data-neuron-beam"
DS_DECISIONS = "smart.darwin.nt.gov.au:councillor-decisions"
DS_GRANTS = "smart.darwin.nt.gov.au:sponsorships-and-grants-data"
DS_CAPITAL = "smart.darwin.nt.gov.au:year_by_year_capital_expenditure0"
DS_EXPENSES = "smart.darwin.nt.gov.au:councillor-expenses"


def _f(v):
    """Best-effort float from messy values."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


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

    def suburb_lookup(self, suburb: str) -> dict:
        """Resolve a suburb to its LGA (council) and — for City of Darwin — its ward,
        so suburb questions can reach ward/LGA-level data (e.g. council spending)."""
        if not self.ready:
            return self._not_ready()
        s = suburb.strip().upper()
        rows = self.db.fetchall(
            "SELECT suburb, lga, ward FROM suburb_locality WHERE UPPER(suburb) = ?", (s,))
        if not rows:
            rows = self.db.fetchall(
                "SELECT suburb, lga, ward FROM suburb_locality WHERE UPPER(suburb) LIKE ?",
                (f"%{s}%",))
        if not rows:
            return {"suburb": suburb, "found": False,
                    "hint": "Unknown suburb. Try list_suburbs."}
        r = rows[0]
        out = {"suburb": r["suburb"], "lga": r["lga"], "ward": r["ward"], "found": True}
        if r["ward"]:
            out["hint"] = (f"{r['suburb']} is in {r['ward']} (City of Darwin). For its "
                           f"council spending, query the finance table with area='{r['ward']}'.")
        else:
            out["hint"] = (f"{r['suburb']} is in {r['lga']}. Ward-level data exists only "
                           "for City of Darwin suburbs.")
        return out

    def find_records(self, area: str = "", keyword: str = "", limit: int = 50) -> dict:
        """Cross-dataset co-occurrence search: every record matching BOTH a place
        (area) AND a term (keyword, matched against the payload, category,
        metric and dataset title). Either filter is optional."""
        if not self.ready:
            return self._not_ready()
        where, params = [], []
        if area:
            where.append("UPPER(area_name) LIKE ?"); params.append(f"%{area.upper()}%")
        if keyword:
            kw = f"%{keyword.lower()}%"
            where.append("(LOWER(payload) LIKE ? OR LOWER(COALESCE(category,'')) LIKE ? "
                         "OR LOWER(COALESCE(metric_name,'')) LIKE ? "
                         "OR LOWER(COALESCE(dataset_title,'')) LIKE ?)")
            params += [kw, kw, kw, kw]
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.db.fetchone(
            f"SELECT COUNT(*) AS c FROM records{clause}", tuple(params))["c"]
        # accurate per-dataset counts (not capped by the sample limit)
        counts = self.db.fetchall(
            f"SELECT dataset_title, table_name, COUNT(*) AS c FROM records{clause} "
            f"GROUP BY dataset_title, table_name ORDER BY c DESC", tuple(params))
        # a few real example rows
        samples = [json.loads(r["payload"]) for r in self.db.fetchall(
            f"SELECT payload FROM records{clause} LIMIT ?", (*params, min(limit, 5)))]
        result = {
            "area": area, "keyword": keyword, "total_matching": total,
            "by_dataset": [{"dataset": r["dataset_title"], "table": r["table_name"],
                            "records": r["c"]} for r in counts],
            "examples": samples,
        }
        if total == 0 and area and keyword:
            result["note"] = (
                f"No records combine '{area}' with '{keyword}'. Money (expenses, "
                "capital, grants) is recorded by WARD, but suburbs are not wards — "
                "so a suburb + cost search has no matches by design.")
        return result

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

    # ---- panel views (real data for the web UI) --------------------------

    def canopy_change(self, limit: int = 14) -> dict:
        """Tree-canopy % change 2011→2021 by area (most loss first)."""
        if not self.ready:
            return self._not_ready()
        out = []
        for p in self._records_for(DS_CANOPY):
            name = p.get("name") or p.get("name_1")
            a, b = _f(p.get("tcc2011")), _f(p.get("tcc2021"))
            if name and a is not None and b is not None:
                out.append({"area": str(name), "y2011": round(a, 1), "y2021": round(b, 1),
                            "change": round(b - a, 1)})
        out.sort(key=lambda x: x["change"])
        return {"areas": out[:limit]}

    def mobility_trend(self) -> dict:
        """Micromobility trips/distance/CO2 aggregated by month."""
        if not self.ready:
            return self._not_ready()
        from collections import defaultdict
        bym = defaultdict(lambda: {"trips": 0.0, "km": 0.0, "co2": 0.0})
        for p in self._records_for(DS_MOBILITY):
            m = p.get("month")
            if not m:
                continue
            bym[m]["trips"] += _f(p.get("total_trips")) or 0
            bym[m]["km"] += _f(p.get("total_distance_in_km")) or 0
            bym[m]["co2"] += _f(p.get("co2_offset")) or 0
        months = sorted(bym)
        series = [{"month": m, "trips": round(bym[m]["trips"]),
                   "km": round(bym[m]["km"]), "co2": round(bym[m]["co2"], 1)} for m in months]
        last = series[-1] if series else {}
        return {"series": series, "latest": last,
                "total_trips": round(sum(s["trips"] for s in series)),
                "total_km": round(sum(s["km"] for s in series)),
                "total_co2": round(sum(s["co2"] for s in series), 1)}

    def capital_by_category(self, limit: int = 12) -> dict:
        """Capital expenditure summed by category (the real capital dataset)."""
        if not self.ready:
            return self._not_ready()
        from collections import defaultdict
        agg = defaultdict(float)
        for p in self._records_for(DS_CAPITAL):
            agg[str(p.get("category", "?"))] += _f(p.get("expenditure")) or 0
        items = sorted(agg.items(), key=lambda x: -x[1])[:limit]
        return {"total": round(sum(agg.values())),
                "categories": [{"category": k, "amount": round(v)} for k, v in items]}

    def decisions(self, query: str = "", limit: int = 20) -> dict:
        """Council decisions, newest first, optional text filter."""
        if not self.ready:
            return self._not_ready()
        data = self._records_for(DS_DECISIONS)
        if query:
            ql = query.lower()
            data = [p for p in data if ql in json.dumps(p, default=str).lower()]
        data.sort(key=lambda p: str(p.get("meeting_date", "")), reverse=True)
        return {"total": len(data),
                "decisions": [{"date": p.get("meeting_date"), "title": p.get("title"),
                               "department": p.get("department"),
                               "type": p.get("meeting_type")} for p in data[:limit]]}

    def grants(self, query: str = "", limit: int = 20) -> dict:
        """Grants & sponsorships, largest first, optional text filter."""
        if not self.ready:
            return self._not_ready()
        data = self._records_for(DS_GRANTS)
        if query:
            ql = query.lower()
            data = [p for p in data if ql in json.dumps(p, default=str).lower()]
        data.sort(key=lambda p: _f(p.get("total")) or 0, reverse=True)
        return {"total": len(data),
                "total_value": round(sum(_f(p.get("total")) or 0 for p in data)),
                "grants": [{"recipient": p.get("organisation_event"),
                            "type": p.get("grant_type"), "fy": p.get("financial_year"),
                            "total": _f(p.get("total"))} for p in data[:limit]]}

    def ward_spend(self) -> dict:
        """Real councillor-expense spend by ward (basis for the equity view)."""
        if not self.ready:
            return self._not_ready()
        from collections import defaultdict
        agg = defaultdict(float)
        for p in self._records_for(DS_EXPENSES):
            agg[str(p.get("ward", "?"))] += _f(p.get("amount")) or 0
        wards = [{"ward": k, "spend": round(v)} for k, v in sorted(agg.items(), key=lambda x: -x[1])]
        return {"wards": wards, "total": round(sum(w["spend"] for w in wards))}

    def close(self) -> None:
        self.db.close()
