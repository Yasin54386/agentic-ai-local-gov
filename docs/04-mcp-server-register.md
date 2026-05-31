# 04 — MCP Server Register

Every integrated system is wrapped in a small **MCP server** that exposes named
tools to the agents (Layer 2). This register sizes that work honestly and tags
each system by the four things that matter for the build.

## How to read this register

**Access bucket** — how much work the MCP server is:
- **B1** — an MCP server already exists or is trivial; just connect/authenticate.
- **B2** — the system has a REST/SOAP API; we write a thin MCP wrapper over it. *(Most systems.)*
- **B3** — no API; we build the connector *and* the access path. *(Hardest — but this cost exists with any integration approach, not just MCP.)*

**R/W** — does the agent only read, or also write/act?
- Read-only tools are safe to expose freely.
- **Write tools always sit behind a human gate** (Layer 8) — see [05](05-governance.md).

**Gate** — `none` (read-only) or `HUMAN` (high-stakes write requires sign-off).

**Placement** — sovereignty/Essential Eight placement, driven by `classification`.

**Phase** — when in the [roadmap](06-roadmap.md) this server is built.

---

## Public open-data servers (build first — Phase 1, no access agreement)

| MCP server | Wraps | Bucket | R/W | Gate | Placement | Phase |
|------------|-------|--------|-----|------|-----------|-------|
| `darwin-smart` | City of Darwin Opendatasoft API (24 datasets, live movement/IoT) | B2 | R | none | public cloud | 1 |
| `darwin-arcgis` | City of Darwin ArcGIS Hub (spatial + IoT) | B2 | R | none | public cloud | 1 |
| `nt-opendata` | NT Gov CKAN API (~800 datasets) | B2 | R | none | public cloud | 1 |
| `bom-weather` | BOM observations & rainfall | B2 | R | none | public cloud | 1 |
| `bom-flood` | BOM flood gauge feeds (LIVE) | B2 | R | none | public cloud | 1 |
| `bom-cyclone` | BOM cyclone tracks (LIVE) | B2 | R | none | public cloud | 2 |
| `data-gov-au` | Federal CKAN (ABS, etc.) | B2 | R | none | public cloud | 2 |

> These seven are buildable **today** and return genuine Darwin/NT data. They are
> the proof-of-concept and the foundation of Layer 6 (IoT mesh) — much of which is
> already public.

---

## Core council operational servers (Phase 2–3, require access agreements)

| MCP server | Wraps | Bucket | R/W | Gate | Placement | Phase |
|------------|-------|--------|-----|------|-----------|-------|
| `technology-one` | TechnologyOne (finance/procurement) | B2 | R/W | HUMAN | sovereign/on-prem | 3 |
| `confirm` | Confirm (assets, works orders) | B2 | R/W | HUMAN | sovereign | 2 |
| `arcgis-council` | Council ArcGIS (authoritative geometry) | B2 | R | none | sovereign | 2 |
| `content-manager` | HPE Content Manager (records) | B2/B3 | R/W | HUMAN | sovereign | 3 |
| `salesforce` | Salesforce (community CRM/cases) | B1/B2 | R/W | HUMAN | sovereign | 2 |
| `permits` | Planning/permit system | B2 | R/W | HUMAN | sovereign | 2 |

---

## NT & Federal government servers (Phase 3–4, authenticated)

| MCP server | Wraps | Bucket | R/W | Gate | Placement | Phase |
|------------|-------|--------|-----|------|-----------|-------|
| `nt-dipl` | NT DIPL infrastructure | B2 | R | none | sovereign | 3 |
| `land-titles` | NT Land Titles | B2 | R | none* | sovereign/on-prem | 3 |
| `ato` | ATO integration | B2 | R/W | HUMAN | sovereign/on-prem | 4 |
| `austender-buynt` | AusTender / BuyNT | B2 | R | none | sovereign | 3 |
| `banking` | Banking / payments | B2 | R/W | HUMAN | sovereign/on-prem | 4 |

\* Land Titles is read-only here, but classified `sensitive` — access is logged and restricted even for reads.

---

## IoT & sensor mesh servers (Phase 3, Layer 6)

| MCP server | Wraps | Bucket | R/W | Gate | Placement | Phase |
|------------|-------|--------|-----|------|-----------|-------|
| `iot-lorawan` | LoRaWAN sensor network | B2/B3 | R | none | sovereign | 3 |
| `traffic` | Traffic counters | B2 | R | none | public/sovereign | 3 |
| `smart-bins` | Smart bin fill levels | B2 | R | none | sovereign | 3 |
| `air-quality` | Air quality monitors | B2 | R | none | public | 3 |
| `tides` | Harbour / tide sensors | B2 | R | none | public | 3 |

---

## Emergency, utilities & community servers (Phase 3–4)

| MCP server | Wraps | Bucket | R/W | Gate | Placement | Phase |
|------------|-------|--------|-----|------|-----------|-------|
| `power-water` | Power & Water Corp (outages) | B2 | R | none | sovereign | 3 |
| `nt-health` | NT Health (authorised data) | B2 | R | none* | sovereign/on-prem | 4 |
| `darwin-port` | Darwin Port operations | B2 | R | none | sovereign | 3 |
| `nt-police-cad` | NT Police CAD (authorised) | B2/B3 | R | none* | on-prem | 4 |
| `nt-fire` | NT Fire & Rescue | B2 | R | none | sovereign | 4 |
| `adf-norcom` | ADF NORCOM coordination | B3 | R | none* | on-prem | 4 |
| `aiims` | AIIMS incident management | B2 | R/W | HUMAN | sovereign | 4 |

\* Sensitive-classified reads are access-controlled and fully logged.

---

## First Nations data server (special governance)

| MCP server | Wraps | Bucket | R/W | Gate | Placement | Phase |
|------------|-------|--------|-----|------|-----------|-------|
| `larrakia-cultural` | Co-governed cultural overlays | per agreement | R | per agreement | per agreement | per agreement |

> This server is **not** built on our timeline or terms. Its existence, tools,
> access, and placement are decided *with* Larrakia Nation under the Indigenous
> data sovereignty principles in [05 — Governance](05-governance.md).

---

## Summary

- **~30 named MCP servers** across all domains (40+ underlying systems/datasets).
- **7 are public and buildable today** with zero access agreements.
- The rest are **mostly B2 (thin wrappers)** — the real cost is *access*, not protocol.
- **Every write action is HUMAN-gated.** Reads of sensitive data are logged.
- **Placement is per-server**, driven by data classification — this *is* the
  sovereignty/Essential Eight architecture.
