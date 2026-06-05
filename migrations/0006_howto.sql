-- 0006 how-to guides: curated step-by-step NT government procedure guides.

CREATE TABLE IF NOT EXISTS howto_guides (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    summary     TEXT    NOT NULL DEFAULT '',   -- 2-3 sentence plain-English summary
    steps_json  TEXT    NOT NULL DEFAULT '[]', -- JSON array of step strings
    links_json  TEXT    NOT NULL DEFAULT '[]', -- JSON array of {label, url}
    category    TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '',   -- space-separated keywords for FTS boost
    updated_at  TEXT    NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS howto_fts USING fts5(
    title,
    summary,
    category,
    tags,
    content='howto_guides',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS howto_ai AFTER INSERT ON howto_guides BEGIN
    INSERT INTO howto_fts(rowid, title, summary, category, tags)
    VALUES (new.id, new.title, new.summary, new.category, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS howto_au AFTER UPDATE ON howto_guides BEGIN
    INSERT INTO howto_fts(howto_fts, rowid, title, summary, category, tags)
    VALUES ('delete', old.id, old.title, old.summary, old.category, old.tags);
    INSERT INTO howto_fts(rowid, title, summary, category, tags)
    VALUES (new.id, new.title, new.summary, new.category, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS howto_ad AFTER DELETE ON howto_guides BEGIN
    INSERT INTO howto_fts(howto_fts, rowid, title, summary, category, tags)
    VALUES ('delete', old.id, old.title, old.summary, old.category, old.tags);
END;
