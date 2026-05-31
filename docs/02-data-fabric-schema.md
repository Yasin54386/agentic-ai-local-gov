# 02 — Data Fabric Schema

The Data Fabric (Layer 3) is the single source of truth. Its design answers two
questions that are often confused:

1. **What is the one standard format?** → A canonical *schema* (governance layer).
2. **Should we store in multiple formats?** → Yes — by *category*, underneath the
   one canonical schema. Forcing all data into one physical format is an
   anti-pattern.

---

## The 3-layer model

```
  Open + operational sources
            │
            ▼
┌───────────────────────────────────────────────┐
│ 1. RAW / LANDING                                │
│    Store each source AS-IS, timestamped.        │  ← audit & replay
│    Original JSON / CSV / GeoJSON, untouched.    │
└───────────────────┬─────────────────────────────┘
                    │  normalize · clean · validate
┌───────────────────▼─────────────────────────────┐
│ 2. CANONICAL / STANDARDIZED                       │
│    THE one standard. Every record conforms to     │  ← the "single
│    the canonical record shape (below).            │     source of truth"
└───────────────────┬─────────────────────────────┘
                    │  shaped per use
   ┌────────────────┼─────────────────────────────┐
   ▼                ▼                             ▼
┌──────────┐  ┌──────────────┐          ┌──────────────────┐
│ 3a. SQL   │  │ 3b. PostGIS  │          │ 3c. Vector DB     │
│ tabular   │  │ spatial      │          │ embeddings (docs) │
└──────────┘  └──────────────┘          └──────────────────┘
 budgets,       roads, drains,            policies, DAs, FAQs
 counts         zones, assets             ← the LLM's doc-search format
```

- **Layer 1 (Raw)** exists for auditability and replay. We never throw away what
  a source gave us — important for ICAC and for reprocessing when the canonical
  schema evolves.
- **Layer 2 (Canonical)** is the governance contract: one shape, consistent
  fields, every agent reads from here.
- **Layer 3 (Serving)** splits by category because data *types* are physically
  different and the LLM consumes them differently.

---

## The canonical record (Layer 2)

Every ingested record is normalized to this envelope:

```jsonc
{
  "id": "string",                 // stable canonical id (namespaced by source)
  "type": "string",               // e.g. "flood_gauge_reading", "asset", "da_application"
  "domain": "string",             // one of the 6 operational domains
  "source": {
    "system": "string",           // e.g. "darwin-opendatasoft"
    "dataset": "string",          // source dataset id
    "retrieved_at": "ISO-8601",   // when we pulled it
    "source_updated_at": "ISO-8601" // when the source says it changed (if known)
  },
  "geo": {                        // null if non-spatial
    "lat": 0.0,
    "lng": 0.0,
    "geometry": null,             // GeoJSON geometry for shapes (roads, zones)
    "suburb": "string"
  },
  "valid_time": {                 // the real-world time the data is about
    "from": "ISO-8601",
    "to": "ISO-8601|null"
  },
  "classification": "open|internal|sensitive|cultural",  // governs storage placement
  "payload": { },                 // the actual, source-specific fields
  "provenance": {
    "raw_ref": "string",          // pointer back to the Layer-1 raw record
    "transform_version": "string" // which normalization rules produced this
  }
}
```

### Why each field earns its place
- `type` + `domain` → routing and filtering for agents.
- `source` + `provenance` → full audit trail (ICAC) and reprocessing.
- `geo` → drives the PostGIS serving layer.
- `valid_time` separate from `retrieved_at` → "when it's *about*" vs "when we *got* it" (critical for emergencies).
- `classification` → directly decides sovereignty placement (see below).

---

## Serving layer routing (Layer 3)

| Data category | Store | Why | LLM consumes as |
|---------------|-------|-----|-----------------|
| Tabular / numeric (budgets, counts, readings) | Relational (Postgres) | Aggregation, joins, exact queries | Structured JSON rows |
| Spatial (roads, drains, zones, assets) | PostGIS | "What's near here?" needs spatial indexing | GeoJSON + structured |
| Text / documents (policies, DAs, FAQs, legislation) | Vector DB | Semantic search / RAG | Retrieved passages |

> The LLM does **not** want "one format." It wants **structured data as JSON** to
> reason over, **plus a vector DB** for document search. Those are two different
> needs, both required.

---

## Cadence: do NOT pull everything hourly

A blanket hourly pull is wrong in both directions. Pull rate must match data
velocity. Full detail is in [03 — Source & cadence register](03-source-cadence-register.md).

| Data velocity | Strategy |
|---------------|----------|
| Emergency / real-time (flood gauge, cyclone track) | **Fetch live on-demand via MCP. Do NOT pre-cache** — stale data could be dangerous. |
| Time-series (traffic, pool usage) | Scheduled, 15 min – 1 hr |
| Slow-changing (property, assets, zones) | Scheduled, daily / weekly |
| Near-static (contracts, legislation) | On-change / weekly |

So the fabric is a **hybrid**: scheduled ingestion fills the historical/analytical
store; live operational data is fetched at query time and never cached.

---

## Classification → sovereignty placement

The `classification` field decides *where* a record may physically live, which is
our Essential Eight / data-sovereignty story made concrete.

| Classification | Examples | Placement |
|----------------|----------|-----------|
| `open` | BOM weather, open datasets | Public/standard cloud OK |
| `internal` | works orders, asset state | Sovereign Australian cloud |
| `sensitive` | finance, Land Titles, health | Sovereign cloud / on-prem; strict access |
| `cultural` | First Nations / Larrakia data | Indigenous data co-governance rules apply (see [05 — Governance](05-governance.md)) |
