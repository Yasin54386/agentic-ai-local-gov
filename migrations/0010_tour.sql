-- Tour Guide: destinations + reviews

CREATE TABLE IF NOT EXISTS destinations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    category     TEXT    NOT NULL DEFAULT 'other',
    summary      TEXT    NOT NULL DEFAULT '',
    description  TEXT    NOT NULL DEFAULT '',
    address      TEXT    NOT NULL DEFAULT '',
    region       TEXT    NOT NULL DEFAULT '',
    image_url    TEXT    NOT NULL DEFAULT '',
    website      TEXT    NOT NULL DEFAULT '',
    phone        TEXT    NOT NULL DEFAULT '',
    hours        TEXT    NOT NULL DEFAULT '',
    price        TEXT    NOT NULL DEFAULT '',
    lat          REAL,
    lng          REAL,
    tips         TEXT    NOT NULL DEFAULT '',
    source_url   TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (date('now')),
    UNIQUE(name, region)
);

CREATE VIRTUAL TABLE IF NOT EXISTS destinations_fts USING fts5(
    name, category, summary, description, region, address, tips,
    content=destinations, content_rowid=id,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS destinations_ai AFTER INSERT ON destinations BEGIN
    INSERT INTO destinations_fts(rowid, name, category, summary, description, region, address, tips)
    VALUES (new.id, new.name, new.category, new.summary, new.description, new.region, new.address, new.tips);
END;
CREATE TRIGGER IF NOT EXISTS destinations_au AFTER UPDATE ON destinations BEGIN
    DELETE FROM destinations_fts WHERE rowid = old.id;
    INSERT INTO destinations_fts(rowid, name, category, summary, description, region, address, tips)
    VALUES (new.id, new.name, new.category, new.summary, new.description, new.region, new.address, new.tips);
END;
CREATE TRIGGER IF NOT EXISTS destinations_ad AFTER DELETE ON destinations BEGIN
    DELETE FROM destinations_fts WHERE rowid = old.id;
END;

CREATE TABLE IF NOT EXISTS destination_reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id  INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    reviewer_name   TEXT    NOT NULL DEFAULT 'Anonymous',
    rating          INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    review_text     TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reviews_dest_date
    ON destination_reviews(destination_id, created_at DESC);
