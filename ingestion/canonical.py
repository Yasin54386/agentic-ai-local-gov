"""The canonical dataset record — the 'one standard' from docs/02-data-fabric-schema.md.

Every source-specific dataset is normalized into a CanonicalDataset before it
enters the catalog, so every downstream consumer (and every MCP server) sees one
consistent shape regardless of whether it came from CKAN, Opendatasoft or ArcGIS.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class Resource:
    """A downloadable/queryable artifact attached to a dataset."""
    name: str
    fmt: str            # normalized format: CSV, XLSX, PDF, GEOJSON, API, ...
    url: str


@dataclass
class CanonicalDataset:
    """One dataset, normalized. This is the catalog row + the basis for ingestion."""
    canonical_id: str           # "<source_system>:<source_dataset_id>"
    source_system: str          # e.g. "data.nt.gov.au"
    source_dataset_id: str
    title: str
    description: str
    domain: str                 # one of the 6 operational domains (or "other")
    publisher: str
    classification: str         # always "open" for these public sources
    spatial: bool
    record_count: int | None
    license: str
    source_url: str
    source_modified: str        # ISO-8601, as reported by the source ("" if unknown)
    retrieved_at: str           # ISO-8601, when we harvested it
    tags: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
