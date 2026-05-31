"""CKAN source adapter.

Handles any CKAN portal via the standard /api/3/action/package_search endpoint.
Used for both the NT Government Open Data Portal (data.nt.gov.au, ~1,071 datasets)
and, optionally, the federal portal (data.gov.au) filtered to the NT.
"""
from __future__ import annotations

from typing import Iterator
from urllib.parse import urljoin

from ..canonical import CanonicalDataset, Resource
from ..domains import classify
from ..http import get_json
from .base import Source

PAGE_SIZE = 200  # conservative; most CKAN portals cap rows per request


class CKANSource(Source):
    def __init__(self, base_url: str, system: str, *, query: str | None = None,
                 max_datasets: int | None = None):
        self.base_url = base_url.rstrip("/") + "/"
        self.system = system
        self.query = query          # full-text filter (used to scope data.gov.au to NT)
        self.max_datasets = max_datasets
        self.web_base = self.base_url.split("/api/")[0]

    def _action(self, action: str, params: dict) -> dict:
        url = urljoin(self.base_url, f"api/3/action/{action}")
        resp = get_json(url, params=params)
        if not resp.get("success"):
            raise RuntimeError(f"CKAN {action} failed: {resp}")
        return resp["result"]

    def harvest(self) -> Iterator[CanonicalDataset]:
        start = 0
        seen = 0
        while True:
            params = {"rows": PAGE_SIZE, "start": start}
            if self.query:
                params["q"] = self.query
            result = self._action("package_search", params)
            total = result["count"]
            packages = result["results"]
            if not packages:
                break
            for pkg in packages:
                yield self._to_canonical(pkg)
                seen += 1
                if self.max_datasets and seen >= self.max_datasets:
                    return
            start += PAGE_SIZE
            if start >= total:
                break

    def _to_canonical(self, pkg: dict) -> CanonicalDataset:
        resources = []
        formats: set[str] = set()
        spatial = False
        for r in pkg.get("resources", []):
            fmt = (r.get("format") or "").upper().strip() or "UNKNOWN"
            formats.add(fmt)
            if fmt in {"SHP", "GEOJSON", "KML", "KMZ", "MAPINFO TAB", "ESRI GDB", "WMS", "WFS"}:
                spatial = True
            resources.append(Resource(name=r.get("name") or r.get("id") or "", fmt=fmt,
                                      url=r.get("url") or ""))
        org = (pkg.get("organization") or {}).get("title") or ""
        tags = [t.get("name", "") for t in pkg.get("tags", []) if t.get("name")]
        # NB: classify on title/description/tags only — NOT the org name, since
        # publisher names like "Lands, Planning and Environment" pollute the domain.
        text = " ".join([pkg.get("title", ""), pkg.get("notes", ""), " ".join(tags)])
        ds_id = pkg.get("name") or pkg.get("id")
        return CanonicalDataset(
            canonical_id=f"{self.system}:{ds_id}",
            source_system=self.system,
            source_dataset_id=ds_id,
            title=pkg.get("title") or ds_id,
            description=(pkg.get("notes") or "").strip(),
            domain=classify(text),
            publisher=org,
            classification="open",
            spatial=spatial,
            record_count=None,
            license=pkg.get("license_title") or pkg.get("license_id") or "",
            source_url=urljoin(self.web_base + "/", f"dataset/{ds_id}"),
            source_modified=pkg.get("metadata_modified") or "",
            retrieved_at=CanonicalDataset.now_iso(),
            tags=tags,
            formats=sorted(formats),
            resources=resources,
        )
