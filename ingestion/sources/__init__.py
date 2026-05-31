"""Source adapters. Each knows how to harvest one open-data platform's catalog
and normalize it into CanonicalDataset records.
"""
from .ckan import CKANSource
from .opendatasoft import OpendatasoftSource
from .arcgis_hub import ArcGISHubSource

__all__ = ["CKANSource", "OpendatasoftSource", "ArcGISHubSource"]
