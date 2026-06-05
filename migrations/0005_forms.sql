-- 0005 form finder: scraped government forms with full-text search.

CREATE TABLE IF NOT EXISTS forms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    description   TEXT    DEFAULT '',
    url           TEXT    NOT NULL UNIQUE,
    department    TEXT    DEFAULT '',
    category      TEXT    DEFAULT '',
    source_domain TEXT    DEFAULT '',
    keywords      TEXT    DEFAULT '',   -- space-separated extras fed into FTS
    last_scraped  TEXT    DEFAULT ''
);

-- FTS5 virtual table indexes title + description + department + category + keywords
CREATE VIRTUAL TABLE IF NOT EXISTS forms_fts USING fts5(
    title,
    description,
    department,
    category,
    keywords,
    content='forms',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Keep FTS in sync with the base table
CREATE TRIGGER IF NOT EXISTS forms_ai AFTER INSERT ON forms BEGIN
    INSERT INTO forms_fts(rowid, title, description, department, category, keywords)
    VALUES (new.id, new.title, new.description, new.department, new.category, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS forms_au AFTER UPDATE ON forms BEGIN
    INSERT INTO forms_fts(forms_fts, rowid, title, description, department, category, keywords)
    VALUES ('delete', old.id, old.title, old.description, old.department, old.category, old.keywords);
    INSERT INTO forms_fts(rowid, title, description, department, category, keywords)
    VALUES (new.id, new.title, new.description, new.department, new.category, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS forms_ad AFTER DELETE ON forms BEGIN
    INSERT INTO forms_fts(forms_fts, rowid, title, description, department, category, keywords)
    VALUES ('delete', old.id, old.title, old.description, old.department, old.category, old.keywords);
END;
