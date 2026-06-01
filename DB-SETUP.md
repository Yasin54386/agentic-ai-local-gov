# Database Setup — connection → migration → data

How to create your local database from scratch and load the data into it. Two
options, same commands. Assumes **no database exists yet**.

The flow is always:
```
1. configure connection   (DATABASE_URL)
2. run migrations          (python -m db.migrate)   → creates the schema
3. load the data           (python -m db.load)      → fills the tables
```

---

## Option A — SQLite (default, zero install)

Nothing to install. The database is a single file (`data/askterritory.db`).

```bash
# 1. connection — the default is already SQLite, but you can be explicit:
export DATABASE_URL="sqlite:///data/askterritory.db"

# 2. create the schema
python3 -m db.migrate

# 3. load the data
python3 -m db.load
```

Check it:
```bash
python3 -m db.migrate --status     # all migrations ✓ applied
```

That's it — one consolidated database with `datasets`, `records`, the categorised
tables (`finance`, `demographics`, …), and `column_catalog`.

---

## Option B — PostgreSQL (a real local server)

### 1. Install & start PostgreSQL

**macOS (Homebrew):**
```bash
brew install postgresql@16
brew services start postgresql@16
```

### 2. Create the database and a user

```bash
createdb askterritory
# (optional) a dedicated user:
psql askterritory -c "CREATE USER askterritory WITH PASSWORD 'askterritory';"
psql askterritory -c "GRANT ALL ON SCHEMA public TO askterritory;"
```

### 3. Install the Python driver

```bash
pip install "psycopg[binary]"
```

### 4. Point the connection at it, then migrate + load

```bash
export DATABASE_URL="postgresql://askterritory:askterritory@localhost:5432/askterritory"
# (or, using your own account:  postgresql://$USER@localhost:5432/askterritory )

python3 -m db.migrate     # creates schema in PostgreSQL
python3 -m db.load        # loads 1,104 datasets + 31,331 records + catalog
```

Verify:
```bash
psql askterritory -c "SELECT table_name, COUNT(*) FROM records GROUP BY table_name ORDER BY 2 DESC;"
```

---

## What gets created

| Object | Rows | Purpose |
|---|---:|---|
| `datasets` | 1,104 | dataset catalog (metadata) |
| `records` | 31,331 | all records (canonical envelope + JSON payload) |
| `finance`, `governance`, `demographics`, `economy`, `animals`, `environment`, `mobility`, `live`, `other` | 31,331 total | the same rows, split by category |
| `column_catalog` | 271 | semantic dictionary (column → table mapping) |
| `schema_migrations` | — | which migrations have been applied |

Because it's one database, `records` and `datasets` can be **joined** directly.

---

## Migrations

- Live in `migrations/` as numbered SQL files (`0001_*.sql`, …).
- Applied in order, once each; tracked in `schema_migrations`.
- **Add a change** → drop a new `0004_*.sql` file and run `python3 -m db.migrate`.
  Never edit an applied migration; add a new one.
- Portable SQL runs on both SQLite and PostgreSQL.

```bash
python3 -m db.migrate --status     # see applied / pending
python3 -m db.migrate              # apply pending
```

---

## Reset / rebuild

```bash
# SQLite: just delete the file and redo
rm -f data/askterritory.db && python3 -m db.migrate && python3 -m db.load

# PostgreSQL:
dropdb askterritory && createdb askterritory
python3 -m db.migrate && python3 -m db.load
```

---

## Notes

- The migrated DB is **not committed to git** (`data/askterritory.db` is gitignored).
  It's rebuilt in seconds from the committed raw data + migrations — no binary churn.
- `DATABASE_URL` is the single switch between engines. The app code doesn't change.
- The older `data/catalog.db` / `data/unified.db` are the *source* the loader reads
  from; once you're fully on the migrated DB they can be retired.
