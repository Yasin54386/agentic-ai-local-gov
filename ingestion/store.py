"""SQLite-backed catalog store — the public data repository index.

One file, zero setup, fully committable. The schema mirrors docs/02 and is
designed to migrate cleanly to Postgres/PostGIS later (the canonical layer).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .canonical import CanonicalDataset

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    canonical_id      TEXT PRIMARY KEY,
    source_system     TEXT NOT NULL,
    source_dataset_id TEXT NOT NULL,
    title             TEXT,
    description       TEXT,
    domain            TEXT,
    publisher         TEXT,
    classification    TEXT,
    spatial           INTEGER,
    record_count      INTEGER,
    license           TEXT,
    source_url        TEXT,
    source_modified   TEXT,
    retrieved_at      TEXT,
    tags_json         TEXT,
    formats_json      TEXT
);

CREATE TABLE IF NOT EXISTS resources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id      TEXT NOT NULL REFERENCES datasets(canonical_id) ON DELETE CASCADE,
    name            TEXT,
    fmt             TEXT,
    url             TEXT,
    downloaded_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_datasets_source ON datasets(source_system);
CREATE INDEX IF NOT EXISTS idx_datasets_domain ON datasets(domain);
CREATE INDEX IF NOT EXISTS idx_resources_dataset ON resources(dataset_id);
"""


class CatalogStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the threaded web server can share this
        # connection (access is serialised by a lock in webapp/server.py).
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def upsert(self, ds: CanonicalDataset) -> None:
        """Insert or replace a dataset and its resources (idempotent re-harvest)."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO datasets (
                canonical_id, source_system, source_dataset_id, title, description,
                domain, publisher, classification, spatial, record_count, license,
                source_url, source_modified, retrieved_at, tags_json, formats_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ds.canonical_id, ds.source_system, ds.source_dataset_id, ds.title,
                ds.description, ds.domain, ds.publisher, ds.classification,
                int(ds.spatial), ds.record_count, ds.license, ds.source_url,
                ds.source_modified, ds.retrieved_at,
                json.dumps(ds.tags), json.dumps(ds.formats),
            ),
        )
        self.conn.execute("DELETE FROM resources WHERE dataset_id = ?", (ds.canonical_id,))
        self.conn.executemany(
            "INSERT INTO resources (dataset_id, name, fmt, url) VALUES (?,?,?,?)",
            [(ds.canonical_id, r.name, r.fmt, r.url) for r in ds.resources],
        )
        self.conn.commit()

    def upsert_many(self, datasets: Iterable[CanonicalDataset]) -> int:
        n = 0
        for ds in datasets:
            self.upsert(ds)
            n += 1
        return n

    # --- queries used by reporting and by fetch_data ---

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]

    def counts_by(self, column: str) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            f"SELECT {column}, COUNT(*) c FROM datasets GROUP BY {column} ORDER BY c DESC"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def format_counts(self) -> list[tuple[str, int]]:
        rows = self.conn.execute("SELECT fmt, COUNT(*) c FROM resources GROUP BY fmt ORDER BY c DESC").fetchall()
        return [(r[0], r[1]) for r in rows]

    def resources_for(self, canonical_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM resources WHERE dataset_id = ?", (canonical_id,)
        ).fetchall()

    def datasets_for_source(self, source_system: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM datasets WHERE source_system = ?", (source_system,)
        ).fetchall()

    def all_datasets(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM datasets ORDER BY source_system, title").fetchall()

    def mark_downloaded(self, resource_id: int, path: str) -> None:
        self.conn.execute("UPDATE resources SET downloaded_path = ? WHERE id = ?", (path, resource_id))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
