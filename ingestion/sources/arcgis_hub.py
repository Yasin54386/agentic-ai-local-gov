"""ArcGIS Hub source adapter — the City of Darwin Open Data Hub.

open-darwin.opendata.arcgis.com exposes an OGC API Features endpoint listing the
hub's catalog items (spatial layers and IoT feeds). Each item links back to its
ArcGIS REST service for live querying / GeoJSON download.
"""
from __future__ import annotations

from typing import Iterator

from ..canonical import CanonicalDataset, Resource
from ..domains import classify
from ..http import get_json
from .base import Source

PAGE_SIZE = 100


class ArcGISHubSource(Source):
    def __init__(self, base_url: str = "https://open-darwin.opendata.arcgis.com",
                 system: str = "open-darwin.opendata.arcgis.com"):
        self.base_url = base_url.rstrip("/")
        self.system = system
        self.items_url = f"{self.base_url}/api/search/v1/collections/all/items"

    def harvest(self) -> Iterator[CanonicalDataset]:
        # OGC API Features paginates with `startindex` (1-based offset), not `offset`.
        startindex = 1
        while True:
            resp = get_json(self.items_url,
                            params={"limit": PAGE_SIZE, "startindex": startindex})
            features = resp.get("features", [])
            if not features:
                break
            for f in features:
                yield self._to_canonical(f)
            matched = resp.get("numberMatched", 0)
            startindex += len(features)
            if startindex > matched or not resp.get("numberReturned"):
                break

    def _to_canonical(self, feature: dict) -> CanonicalDataset:
        props = feature.get("properties", {}) or {}
        ds_id = str(feature.get("id") or props.get("id") or props.get("slug") or "")
        title = props.get("title") or ds_id
        description = (props.get("description") or props.get("snippet") or "").strip()
        tags = props.get("tags") or props.get("categories") or []
        if isinstance(tags, str):
            tags = [tags]
        source_url = props.get("landingPage") or props.get("url") or \
            f"{self.base_url}/datasets/{ds_id}"

        resources = []
        for link in feature.get("links", []) or []:
            href = link.get("href")
            rel = (link.get("type") or link.get("rel") or "").upper()
            if href and ("GEOJSON" in rel or href.lower().endswith(".geojson")):
                resources.append(Resource(name="GeoJSON", fmt="GEOJSON", url=href))
        if not resources:
            resources.append(Resource(name="Hub landing page", fmt="API", url=source_url))

        text = " ".join([title, description, " ".join(map(str, tags))])
        return CanonicalDataset(
            canonical_id=f"{self.system}:{ds_id}",
            source_system=self.system,
            source_dataset_id=ds_id,
            title=title,
            description=description,
            domain=classify(text),
            publisher=props.get("source") or "City of Darwin",
            classification="open",
            spatial=True,  # ArcGIS Hub items are spatial by nature
            record_count=props.get("recordCount"),
            license=props.get("license") or "",
            source_url=source_url,
            source_modified=props.get("modified") or "",
            retrieved_at=CanonicalDataset.now_iso(),
            tags=[str(t) for t in tags],
            formats=sorted({r.fmt for r in resources}),
            resources=resources,
        )
