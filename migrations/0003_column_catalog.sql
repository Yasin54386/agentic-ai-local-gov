-- 0003 column catalog: the semantic dictionary (one row per column),
-- including which categorised table(s) each column belongs to.

CREATE TABLE IF NOT EXISTS column_catalog (
    column_name    TEXT,
    original_field TEXT,
    label          TEXT,
    semantic_class TEXT,
    data_type      TEXT,
    tables_json    TEXT,
    datasets_json  TEXT,
    examples_json  TEXT,
    null_rate      DOUBLE PRECISION,
    needs_review   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_catalog_class ON column_catalog(semantic_class);
