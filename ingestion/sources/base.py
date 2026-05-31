"""Common base for source adapters."""
from __future__ import annotations

from typing import Iterator

from ..canonical import CanonicalDataset


class Source:
    """A harvestable open-data platform.

    Subclasses set `system` (the source_system identifier) and implement
    `harvest()` to yield CanonicalDataset records.
    """
    system: str = "unknown"

    def harvest(self) -> Iterator[CanonicalDataset]:  # pragma: no cover - interface
        raise NotImplementedError
