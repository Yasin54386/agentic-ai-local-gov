# 06 — Roadmap

A four-phase, 24-month+ implementation plan. Each phase has a focus, concrete
deliverables, and a decision gate before the next phase begins.

The sequencing principle: **start with what's public and buildable today, prove
the concept on real data, then earn access to operational systems.**

---

## Phase 1 — Foundation (Months 1–6)

**Focus:** the base everything hangs off, plus a real-data proof of concept.

- Stand up the **MCP gateway** pattern and the **Data Fabric** (canonical schema,
  raw + canonical layers, initial SQL/PostGIS/vector stores).
- Build the **7 public open-data MCP servers** (`darwin-smart`, `darwin-arcgis`,
  `nt-opendata`, `bom-weather`, `bom-flood`, and prep `bom-cyclone`, `data-gov-au`).
- Identity & access management; **Essential Eight** baseline.
- A first **agent loop** reasoning over genuine Darwin data (e.g. the wet-season
  flood scenario, using only public sources).

**Gate:** working agent answers a real question from live Darwin data, fully
logged. Architecture validated on the ground.

---

## Phase 2 — First agents live (Months 6–12)

**Focus:** first resident- and operations-facing agents, first operational
integrations.

- **Citizen Interface** (Layer 1) — plain-language intake, categorisation, routing.
- **Waste & fleet** agent (e.g. smart-bin-informed scheduling).
- **Permit pre-screening** agent (read-only DA checks against planning rules).
- First operational MCP servers behind **human gates**: `confirm`, `salesforce`,
  `permits`, `arcgis-council`.
- Bias-audit and audit-trail tooling operational.

**Gate:** at least one agent in supervised production use; human gates and audit
trail proven in a real workflow.

---

## Phase 3 — Digital Twin & IoT (Months 12–24)

**Focus:** the live city — sensing and simulation.

- **IoT & Sensor Mesh** (Layer 6): `iot-lorawan`, `traffic`, `smart-bins`,
  `air-quality`, `tides`.
- **Digital Twin Engine** (Layer 5): simulate significant decisions before
  execution — informed by CDU smart-grid Digital Twin research.
- **Flood modelling**, predictive maintenance, fleet optimisation.
- Heavier operational integrations: `technology-one`, `content-manager`,
  `nt-dipl`, `land-titles`, `power-water`, `darwin-port`.

**Gate:** a significant decision is simulated in the Digital Twin and executed
under human sign-off, end to end.

---

## Phase 4 — Full orchestration (Months 24+)

**Focus:** all 8 layers working together; full NT & Federal integration;
transparency to residents.

- All four orchestration agents (plan/execute/monitor/learn) coordinating across
  domains.
- NT & Federal servers: `ato`, `banking`, `nt-health`, `nt-police-cad`,
  `nt-fire`, `adf-norcom`, `aiims`.
- **Public transparency portal** — residents see what agents do and how.
- Continuous bias audits, learning-agent improvement loops.

**Gate:** ongoing. Independent review; measured outcomes against baseline.

---

## Cross-cutting throughout all phases

- **First Nations data co-governance** — engaged from Phase 1; cultural data only
  under agreement with Larrakia Nation, on their terms.
- **Human-in-the-loop** — every write action gated, in every phase.
- **Sovereignty placement** — per-server, by classification, from day one.
- **Audit trail** — uniform, complete, from the first MCP call.

---

## Phase summary

| Phase | Timeline | Focus | Key gate |
|-------|----------|-------|----------|
| 1 | Months 1–6 | Foundation + public-data PoC | Agent answers from live Darwin data |
| 2 | Months 6–12 | First agents + first operational integrations | Supervised agent in production |
| 3 | Months 12–24 | Digital Twin + IoT mesh | Simulated decision executed under sign-off |
| 4 | Months 24+ | Full orchestration + transparency | Independent review; measured outcomes |
