# Ingestion Engine — the Public Data Repository

The real, working harvester for the Data Fabric (Layer 3), scoped to **public**
open-data sources. It connects to live NT and City of Darwin open-data APIs,
normalizes every dataset into the [canonical record](../docs/02-data-fabric-schema.md),
and stores them in a SQLite catalog — your own unified public data repository.

**Standard library only.** No `pip install` required. Runs anywhere Python 3.10+ runs.

## Sources harvested

| Source | API | Adapter | Notes |
|---|---|---|---|
| NT Government Open Data (`data.nt.gov.au`) | CKAN | `sources/ckan.py` | ~1,071 datasets |
| City of Darwin Smart Portal (`smart.darwin.nt.gov.au`) | Opendatasoft Explore v2.1 | `sources/opendatasoft.py` | 24 live/queryable APIs |
| City of Darwin ArcGIS Hub (`open-darwin…`) | OGC API Features | `sources/arcgis_hub.py` | spatial + IoT |
| Federal (`data.gov.au`) | CKAN | `sources/ckan.py` | opt-in, NT-filtered, capped |

## Quick start

```bash
# 1. Harvest the catalog (metadata) from NT + Darwin sources, write the report:
python -m ingestion.harvest --report

# 2. Add the federal portal (NT-filtered, capped at 500):
python -m ingestion.harvest --include-federal --federal-limit 500 --report

# 3. Download the actual data for the clean API sources:
python -m ingestion.fetch_data --api-sources

# 4. Download one dataset's data:
python -m ingestion.fetch_data --dataset "smart.darwin.nt.gov.au:councillor-expenses"

# 5. Mirror everything (large — Excel/PDF/etc.), restricted to sane formats:
python -m ingestion.fetch_data --all --formats JSON CSV GEOJSON XLSX
```

## Layout

```
ingestion/
  http.py           # dependency-free GET with retry/backoff
  canonical.py      # CanonicalDataset — the one standard record
  domains.py        # transparent keyword -> operational-domain classifier
  store.py          # SQLite catalog (the repository index)
  report.py         # generates docs/CATALOG.md
  harvest.py        # CLI: harvest catalogs from all sources
  fetch_data.py     # CLI: download actual data (Layer-1 raw store)
  sources/
    ckan.py  opendatasoft.py  arcgis_hub.py
```

## What is and isn't committed

- **Committed:** all code + `docs/CATALOG.md` (the human-readable snapshot).
- **Not committed** (`.gitignore`): `data/catalog.db` and `data/raw/*` — regenerable
  by re-running the harvester. This keeps the repo light and the data always fresh.

## Migrating to production (docs/02 serving layer)

The SQLite schema in `store.py` maps cleanly onto Postgres + PostGIS (spatial) +
a vector DB (descriptions → embeddings for semantic search). The canonical record
is storage-agnostic by design, so the adapters never change.
