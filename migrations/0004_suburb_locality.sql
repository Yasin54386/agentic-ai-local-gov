-- 0004 suburb locality: maps a suburb to its LGA (council) and, where it exists,
-- its City of Darwin ward. Lets suburb questions resolve to ward/LGA-level data
-- (e.g. a suburb's council spending, which is recorded by ward).

CREATE TABLE IF NOT EXISTS suburb_locality (
    suburb TEXT,
    lga    TEXT,
    ward   TEXT
);

CREATE INDEX IF NOT EXISTS idx_locality_suburb ON suburb_locality(suburb);
