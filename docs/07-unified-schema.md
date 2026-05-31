# 07 — Unified Record Schema

How 24 datasets with wildly different shapes become **one queryable SQL table**,
without losing any data. Built by `python -m ingestion.unify`
(`ingestion/unify.py`), output to `data/unified.db` (table `records`).

---

## The problem (from analyzing the real data)

The harvested datasets range from 5 columns (`councillor-expenses`: ward,
councillor_name, expense_type, fy_year, amount) to **130+** columns
(`economy-and-industry-by-lga-abs`). Forcing them into one rigid table would be
lossy; keeping 24 separate tables can't be queried together.

But analysis of all 24 datasets showed **recurring dimensions** hiding under
different field names:

| Dimension | Appears as (examples) | Datasets w/ it |
|---|---|---|
| **Time** | `census_year`, `year`, `fy_year`, `fy`, `financial_year`, `month`, `meeting_date` | most |
| **Place** | `suburb`, `suburb_name`, `ward`, `lga`, `lga_name`, `abs_lga` | most |
| **Coordinates** | `geo_point_2d` (and GeoJSON geometry) | several |
| **Category** | `category`, `sub_category`, `expense_type`, `grant_type`, `program`, `type` | most |
| **Measure** | `amount`, `total`, `count`, `population`, `expenditure`, `net_generation_mwh` | many |

## The solution: canonical envelope + JSON payload

This is the docs/02 canonical record, applied at **row** level:

> **Extract the common dimensions into typed columns** (so you can query across
> datasets) **+ keep the entire original row as a JSON `payload`** (so nothing is
> ever lost, no matter how unique a dataset's fields are).

### Table `records`

| Column | Type | Meaning |
|---|---|---|
| `record_id` | TEXT PK | `<dataset_id>#<rownum>` |
| `dataset_id` | TEXT | canonical id of the source dataset |
| `dataset_title` | TEXT | human title (from the catalog) |
| `source_system` | TEXT | e.g. `smart.darwin.nt.gov.au` |
| `domain` | TEXT | operational domain (from the catalog) |
| `period_raw` | TEXT | original time value, untouched |
| `period_year` | INTEGER | parsed 4-digit year, when detectable |
| `area_type` | TEXT | which field the area came from |
| `area_name` | TEXT | suburb / ward / lga / … |
| `geo_lat`, `geo_lng` | REAL | coordinates, when present |
| `category` | TEXT | primary categorical dimension |
| `metric_name` | TEXT | primary numeric field name, when obvious |
| `metric_value` | REAL | primary numeric value |
| `payload` | TEXT | **full original row as JSON (zero data loss)** |
| `ingested_at` | TEXT | when unified |

Indexes: `dataset_id`, `domain`, `area_name`, `period_year`, `category`.

### Extraction priority

For each row, the first matching field name (in priority order) populates each
dimension. Priorities live in `ingestion/unify.py`
(`PERIOD_FIELDS`, `AREA_FIELDS`, `GEO_FIELDS`, `CATEGORY_FIELDS`, `METRIC_FIELDS`)
and are easy to tune. Numbers are cleaned (`$`, commas stripped) before storage;
years are parsed with a `(19|20)\d{2}` regex.

---

## Verified result (live build)

```
31,330 records from 24 datasets -> data/unified.db
```

Common-dimension coverage across all 31,330 rows:

| Dimension | Populated |
|---|---:|
| `area_name` | 28,625 (91%) |
| `category` | 27,017 (86%) |
| `period_year` | 24,720 (79%) |
| `metric_value` | 15,472 (49%) |
| `geo_lat` | 9,454 (30%) |

Rows where a dimension is absent simply have `NULL` there — the full data still
lives in `payload`.

---

## What you can now do (cross-dataset queries)

```sql
-- records per operational domain, across ALL datasets
SELECT domain, COUNT(*) FROM records GROUP BY domain ORDER BY 2 DESC;

-- busiest Darwin suburbs across every dataset that records a place
SELECT area_name, COUNT(*) n FROM records
WHERE area_name IS NOT NULL GROUP BY area_name ORDER BY n DESC LIMIT 10;

-- anything from 2021, in one place, regardless of source dataset
SELECT dataset_title, area_name, category, metric_value
FROM records WHERE period_year = 2021;

-- pull the full original row when you need a dataset's unique fields
SELECT json_extract(payload, '$.expense_type'), metric_value
FROM records WHERE dataset_id = 'smart.darwin.nt.gov.au:councillor-expenses';
```

This is the single combined structure that lets agents (and analysts) reason
across the whole repository instead of dataset-by-dataset.

---

## Known limitations (honest)

- **ArcGIS Hub (9 datasets):** currently catalogued (metadata) only — their record
  data sits behind ArcGIS FeatureServer query endpoints the adapter doesn't yet
  download. A follow-up would add a FeatureServer fetch to bring their rows into
  `records` too.
- **`metric_value` is a single best-effort primary measure.** Datasets with many
  numeric columns (e.g. census age bands, the 130-column economy set) keep *all*
  their numbers in `payload`; only one representative measure is promoted to the
  typed column.
- **NT CKAN (1,071 datasets):** mostly file resources (Excel/PDF) — catalogued but
  not row-unified here (would require per-file parsing).
