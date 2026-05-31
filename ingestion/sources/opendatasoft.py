"""Opendatasoft source adapter — the City of Darwin Smart Data Portal.

smart.darwin.nt.gov.au exposes the Explore API v2.1. These are the highest-value
public datasets: proper queryable APIs (not just file downloads), some real-time.
Each dataset gets canonical 'API' resources pointing at its live JSON/CSV exports.
"""
from __future__ import annotations

from typing import Iterator

from ..canonical import CanonicalDataset, Resource
from ..domains import classify
from ..http import get_json
from .base import Source

PAGE_SIZE = 100  # Opendatasoft Explore API max page size


class OpendatasoftSource(Source):
    def __init__(self, base_url: str = "https://smart.darwin.nt.gov.au",
                 system: str = "smart.darwin.nt.gov.au"):
        self.base_url = base_url.rstrip("/")
        self.system = system
        self.api = f"{self.base_url}/api/explore/v2.1"

    def harvest(self) -> Iterator[CanonicalDataset]:
        offset = 0
        while True:
            resp = get_json(f"{self.api}/catalog/datasets",
                            params={"limit": PAGE_SIZE, "offset": offset})
            results = resp.get("results", [])
            if not results:
                break
            for d in results:
                yield self._to_canonical(d)
            offset += PAGE_SIZE
            if offset >= resp.get("total_count", 0):
                break

    def _to_canonical(self, d: dict) -> CanonicalDataset:
        ds_id = d.get("dataset_id")
        metas = (d.get("metas") or {}).get("default", {}) or {}
        title = metas.get("title") or ds_id
        description = (metas.get("description") or "").strip()
        publisher = metas.get("publisher") or "City of Darwin"
        themes = metas.get("theme") or []
        if isinstance(themes, str):
            themes = [themes]
        keywords = metas.get("keyword") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        tags = [*themes, *keywords]
        record_count = metas.get("records_count")
        spatial = bool(metas.get("geographic_area") or "geo" in str(d.get("features", "")).lower())

        # Live export endpoints — these are real queryable APIs, the crown jewels.
        exports = f"{self.api}/catalog/datasets/{ds_id}/exports"
        records_api = f"{self.api}/catalog/datasets/{ds_id}/records"
        resources = [
            Resource(name="JSON export (full data)", fmt="JSON", url=f"{exports}/json"),
            Resource(name="CSV export (full data)", fmt="CSV", url=f"{exports}/csv"),
            Resource(name="Records API (queryable/live)", fmt="API", url=records_api),
            Resource(name="GeoJSON export", fmt="GEOJSON", url=f"{exports}/geojson") if spatial else
            Resource(name="Records API (queryable/live)", fmt="API", url=records_api),
        ]
        # de-dup
        seen, uniq = set(), []
        for r in resources:
            if r.url not in seen:
                seen.add(r.url)
                uniq.append(r)

        text = " ".join([title, description, " ".join(tags)])
        return CanonicalDataset(
            canonical_id=f"{self.system}:{ds_id}",
            source_system=self.system,
            source_dataset_id=ds_id,
            title=title,
            description=description,
            domain=classify(text),
            publisher=publisher,
            classification="open",
            spatial=spatial,
            record_count=int(record_count) if isinstance(record_count, int) else None,
            license=metas.get("license") or "",
            source_url=f"{self.base_url}/explore/dataset/{ds_id}/",
            source_modified=metas.get("modified") or "",
            retrieved_at=CanonicalDataset.now_iso(),
            tags=[t for t in tags if t],
            formats=sorted({r.fmt for r in uniq}),
            resources=uniq,
        )
