# 03 — Source & Cadence Register

This register lists data sources, how we access them, and **how often** we pull
each one. The governing principle (from [02](02-data-fabric-schema.md)):

> Match the pull cadence to the data's velocity. Fetch emergency/real-time data
> **live on-demand** (never cache). Ingest slow-changing data on a schedule.

**Cadence legend:**
- `LIVE` — fetched on-demand at query time via MCP, never pre-cached
- `≤15m` / `1h` / `daily` / `weekly` — scheduled ingestion into the Data Fabric
- `on-change` — pulled when the source signals an update

---

## Public open-data sources (buildable today, no access agreement)

| Source | Platform / API | Example data | Classification | Cadence |
|--------|----------------|--------------|----------------|---------|
| **City of Darwin Smart Data Portal** | Opendatasoft Explore API v2.1 (`smart.darwin.nt.gov.au`) | Live movement: pool activity, open-space & shared-path usage, cruise arrivals, IoT | open | `LIVE` for movement feeds; `1h` for the rest |
| **City of Darwin Open Data Hub** | ArcGIS REST + Search API (`open-darwin.opendata.arcgis.com`) | Spatial layers, IoT (O3), asset geometry | open | `daily` (geometry) / `LIVE` (IoT) |
| **NT Government Open Data Portal** | CKAN REST API (`data.nt.gov.au`, ~800 datasets) | Roads, parks, crime stats, mineral titles, awarded contracts, streams/drainage | open | `weekly` (mostly slow-changing) |
| **Bureau of Meteorology — observations** | BOM data feeds | Weather observations, rainfall | open | `1h` |
| **Bureau of Meteorology — flood gauges** | BOM flood warning feeds | River/creek gauge levels | open | `LIVE` (emergency) |
| **Bureau of Meteorology — cyclone tracks** | BOM tropical cyclone feeds | Active cyclone tracks/forecasts | open | `LIVE` (emergency) |
| **data.gov.au (federal)** | CKAN API | ABS demographics, federal datasets covering NT | open | `weekly` |

---

## Operational systems (require council access agreements)

These are **not** public APIs. Cadence is mostly `LIVE` because agents act on
current state, with writes gated (see [04 — MCP server register](04-mcp-server-register.md)).

| Source | Domain | Example data | Classification | Cadence |
|--------|--------|--------------|----------------|---------|
| TechnologyOne | Finance & procurement | Budgets, POs, rates | sensitive | `LIVE` |
| Confirm | Infrastructure & assets | Works orders, asset register | internal | `LIVE` |
| ArcGIS (council instance) | Cross-domain spatial | Authoritative asset/zone geometry | internal | `daily` + `LIVE` |
| HPE Content Manager | Records | Documents, correspondence | internal/sensitive | `on-change` |
| Salesforce | Community services | CRM, case management | internal | `LIVE` |
| Planning / permits system | Planning & permits | DA applications, permits | internal | `LIVE` |

---

## NT & Federal government APIs (authenticated)

| Source | Domain | Example data | Classification | Cadence |
|--------|--------|--------------|----------------|---------|
| NT DIPL | Infrastructure | Roads, transport infrastructure | internal | `daily` |
| NT Land Titles | Planning | Title/ownership | sensitive | `LIVE` |
| ATO | Finance | Tax integration | sensitive | `on-change` |
| AusTender / BuyNT | Procurement | Tenders, panels | open/internal | `daily` |
| Banking APIs | Finance | Payments, reconciliation | sensitive | `LIVE` |

---

## IoT & sensor mesh (Layer 6)

| Source | Example data | Classification | Cadence |
|--------|--------------|----------------|---------|
| BOM flood gauges | Water levels | open | `LIVE` |
| LoRaWAN network | Distributed sensors | open/internal | `≤15m` / `LIVE` |
| Traffic counters | Vehicle/pedestrian counts | open | `≤15m` |
| Smart bins | Fill levels | open | `1h` |
| Air quality monitors | Pollutant readings | open | `1h` |
| Harbour / tide sensors | Tide levels | open | `≤15m` |

---

## Emergency & safety (authenticated, mostly LIVE)

| Source | Example data | Classification | Cadence |
|--------|--------------|----------------|---------|
| NT Police CAD | Incidents (where authorised) | sensitive | `LIVE` |
| BOM cyclone feeds | Active tracks | open | `LIVE` |
| NT Fire & Rescue | Incidents / bans | internal | `LIVE` |
| ADF NORCOM | Coordination (where authorised) | sensitive | `on-change` |
| AIIMS feeds | Incident management | internal | `LIVE` |

---

## Utilities & community

| Source | Example data | Classification | Cadence |
|--------|--------------|----------------|---------|
| Power & Water Corp | Outages, network status | internal | `LIVE` |
| NT Health | Public health data (where authorised) | sensitive | `on-change` |
| Darwin Port | Vessel movements, port ops | internal | `1h` / `LIVE` |

---

## First Nations data

| Source | Example data | Classification | Cadence |
|--------|--------------|----------------|---------|
| Larrakia Nation (co-governed) | Cultural site overlays, co-governed datasets | cultural | per co-governance agreement |

> Cultural data is **not** ingested on a default schedule. Access, cadence, and
> placement follow the Indigenous data sovereignty rules in
> [05 — Governance](05-governance.md), set with Larrakia Nation — not by us.
