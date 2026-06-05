-- 0008 enhancements: search logs, feedback, form status/fees/requirements,
--   howto processing time / fees / indigenous notes / verification.

-- Anonymous search analytics (no IP, no time-of-day — just query + day)
CREATE TABLE IF NOT EXISTS search_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query        TEXT    NOT NULL,
    source       TEXT    NOT NULL DEFAULT 'unknown',  -- 'forms' | 'howto'
    result_count INTEGER NOT NULL DEFAULT 0,
    mode         TEXT    NOT NULL DEFAULT 'keyword',  -- 'keyword' | 'ai' | 'fuzzy'
    day          TEXT    NOT NULL                     -- YYYY-MM-DD only
);
CREATE INDEX IF NOT EXISTS idx_search_logs_day    ON search_logs(day);
CREATE INDEX IF NOT EXISTS idx_search_logs_source ON search_logs(source, day);

-- Citizen feedback on broken/outdated links
CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT 'unknown',  -- 'forms' | 'howto'
    issue      TEXT NOT NULL,                    -- citizen's description
    created_at TEXT NOT NULL
);

-- Extend forms
ALTER TABLE forms ADD COLUMN status           TEXT NOT NULL DEFAULT 'active';
ALTER TABLE forms ADD COLUMN fee              TEXT          DEFAULT '';
ALTER TABLE forms ADD COLUMN requirements_json TEXT         DEFAULT '[]';

-- Extend howto_guides
ALTER TABLE howto_guides ADD COLUMN fee             TEXT DEFAULT '';
ALTER TABLE howto_guides ADD COLUMN processing_time TEXT DEFAULT '';
ALTER TABLE howto_guides ADD COLUMN indigenous_note TEXT DEFAULT '';
ALTER TABLE howto_guides ADD COLUMN verified_by     TEXT DEFAULT '';
