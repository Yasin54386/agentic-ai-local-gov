-- 0001 core schema: dataset catalog + the unified records table.
-- Portable DDL (works on SQLite and PostgreSQL).

CREATE TABLE IF NOT EXISTS datasets (
    canonical_id      TEXT PRIMARY KEY,
    source_system     TEXT,
    source_dataset_id TEXT,
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

CREATE TABLE IF NOT EXISTS records (
    record_id      TEXT PRIMARY KEY,
    dataset_id     TEXT,
    dataset_title  TEXT,
    source_system  TEXT,
    domain         TEXT,
    table_name     TEXT,
    period_raw     TEXT,
    period_year    INTEGER,
    area_type      TEXT,
    area_name      TEXT,
    geo_lat        DOUBLE PRECISION,
    geo_lng        DOUBLE PRECISION,
    category       TEXT,
    metric_name    TEXT,
    metric_value   DOUBLE PRECISION,
    payload        TEXT,
    ingested_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_dataset ON records(dataset_id);
CREATE INDEX IF NOT EXISTS idx_records_table   ON records(table_name);
CREATE INDEX IF NOT EXISTS idx_records_area    ON records(area_name);
CREATE INDEX IF NOT EXISTS idx_records_year    ON records(period_year);
