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
from pathlib import Path
from typing import Any

from ingestion.store import CatalogStore

DEFAULT_DB = "data/catalog.db"
RAW_ROOT = Path("data/raw")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:80] or "resource"


class Repository:
    def __init__(self, db_path: str = DEFAULT_DB):
        self.store = CatalogStore(db_path)

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

    def close(self) -> None:
        self.store.close()
