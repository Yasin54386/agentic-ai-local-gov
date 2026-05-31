# Agentic AI for Northern Territory Local Government

> A conceptual framework and reference architecture for applying agentic AI to
> the operations of Northern Territory local government — grounded in real,
> publicly available Darwin/NT data and named system integrations.

**Author:** Mohammad Yasin Arafat — Independent Digital Transformation Researcher, Darwin NT

**Status:** Design phase. This repository holds the architecture and planning
documents. Working code is built on top of these once the designs are agreed.

---

## What this is (and isn't)

This is **independent research**, not a product pitch or a job application. It is
a documented, technically grounded, publicly shareable demonstration that the
design thinking for an agentic local-government operating model has already been
done — end to end, with real Darwin data sources named.

It is deliberately **honest about the boundary** between what is buildable today
(public open-data APIs) and what requires council access agreements (internal
operational systems).

---

## The core idea

Traditional council operations are reactive: residents report problems, staff
process them manually, departments work in silos. This framework proposes a
network of autonomous AI agents that continuously **monitor, plan, act, and
learn** across council operations — while keeping humans in control of every
significant decision.

The intelligence is not invented. It is a pre-trained Large Language Model (LLM)
given a goal, a set of tools (via the Model Context Protocol, MCP), and a loop
that lets it reason and act. Humans sit on the gates for anything high-stakes.

---

## Document index

| # | Document | What it pins down |
|---|----------|-------------------|
| 1 | [Architecture overview](docs/01-architecture-overview.md) | The 8 layers, and how LLM + MCP + Agents map onto them |
| 2 | [Data Fabric schema](docs/02-data-fabric-schema.md) | The canonical record format + the 3-layer storage model |
| 3 | [Source & cadence register](docs/03-source-cadence-register.md) | Every data source, its pull cadence (live vs scheduled) |
| 4 | [MCP server register](docs/04-mcp-server-register.md) | The 40+ integrations: access bucket, read/write, human gate, phase |
| 5 | [Governance & ethics](docs/05-governance.md) | Human gates, ICAC, Essential Eight, Indigenous data sovereignty |
| 6 | [Roadmap](docs/06-roadmap.md) | The 4-phase, 24-month+ implementation plan |

---

## The technology stack in one table

| Concept | What it actually is | Where it lives |
|---------|---------------------|----------------|
| **LLM** | A frozen, pre-trained reasoning brain. Smart, but blind to the live state of the city. | Layers 1, 4, 7, 8 |
| **MCP** | A specific API protocol (like REST, but designed for AIs). You build thin **MCP servers** — backend wrappers — one per system. | Layers 2 + 3 |
| **AI Agent** | LLM + MCP tools + a goal + a loop. The loop calls the LLM, runs whatever tool it asks for, feeds the result back, repeats until done. | Layer 4 |
| **Human gate** | One conditional in the agent loop: high-stakes tool calls pause for human sign-off. | Layer 8 |
| **Data Fabric** | Hybrid: live/emergency data fetched on-demand via MCP; historical data ingested on a variable cadence into one canonical schema, stored by category. | Layers 3 + 6 |

---

## Grounding reality

NT public data is **not** hundreds of separate APIs. It is a small number of
clean, standardized open-data platforms:

- **NT Government Open Data Portal** (`data.nt.gov.au`) — CKAN, ~800 datasets
- **City of Darwin Smart Data Portal** (`smart.darwin.nt.gov.au`) — Opendatasoft, ~24 datasets including **live** real-time feeds
- **City of Darwin Open Data Hub** (`open-darwin.opendata.arcgis.com`) — ArcGIS Hub, spatial layers + IoT

The **open** sources are easy to integrate today. The **operational** systems
(TechnologyOne, Confirm, Land Titles, etc.) are authenticated, human-gated, and
require access agreements — that is access work, not a coding problem.
