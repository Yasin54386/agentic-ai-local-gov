# 01 — Architecture Overview

The system is an 8-layer agentic operating model. Each layer is described below
with its purpose, and — crucially — the concrete technology that implements it.

---

## The 8 layers

```
┌─────────────────────────────────────────────────────────────┐
│ 8. GOVERNANCE & ETHICS    human gates · ICAC · Essential Eight │
├─────────────────────────────────────────────────────────────┤
│ 7. OPERATIONAL DOMAINS    6 core council functions             │
├─────────────────────────────────────────────────────────────┤
│ 6. IoT & SENSOR MESH      flood gauges · traffic · bins · BOM  │
├─────────────────────────────────────────────────────────────┤
│ 5. DIGITAL TWIN ENGINE    simulate before you act              │
├─────────────────────────────────────────────────────────────┤
│ 4. AGENTIC ORCHESTRATION  plan · execute · monitor · learn     │
├─────────────────────────────────────────────────────────────┤
│ 3. DATA FABRIC            one canonical truth                  │
├─────────────────────────────────────────────────────────────┤
│ 2. API GATEWAY            the authenticated switchboard (MCP)  │
├─────────────────────────────────────────────────────────────┤
│ 1. CITIZEN INTERFACE      24/7 plain-language front door       │
└─────────────────────────────────────────────────────────────┘
```

| # | Layer | Purpose | Implemented by |
|---|-------|---------|----------------|
| 1 | **Citizen Interface** | 24/7 front door across web, mobile, SMS, voice. Residents describe needs in plain language; the system categorises, routes, acknowledges. | LLM (intent + routing) |
| 2 | **API Gateway** | Secure, authenticated, audited switchboard connecting every council system. | **MCP servers** |
| 3 | **Data Fabric** | A single source of truth. One governed canonical dataset every agent works from. | Canonical schema + SQL / PostGIS / vector DB |
| 4 | **Agentic Orchestration Core** | The decision engine: planning, execution, monitoring, learning agents working in parallel. | **AI agents** (LLM + MCP + loop) |
| 5 | **Digital Twin Engine** | Real-time virtual replica of the city. Significant decisions are simulated here before execution. | Simulation + spatial model |
| 6 | **IoT & Sensor Mesh** | The city's live nervous system: flood gauges, traffic counters, smart bins, air quality, tides, BOM feeds. | Sensor feeds → MCP (mostly live) |
| 7 | **Operational Domains** | The 6 council functions where agents do routine coordination. | Domain agents over operational systems |
| 8 | **Governance & Ethics** | Accountability: NT legislation, ICAC, Australian AI ethics, human sign-off, bias audits, transparency. | Human gates + audit log + policy |

---

## The technology, precisely

### LLM — the reasoning brain
A frozen, pre-trained model (e.g. Claude). It reasons and generates language but
**cannot see the live city** — it only knows its training data (with a knowledge
cutoff) plus whatever is placed in front of it. This is *why* MCP exists.

### MCP — the connector (Layers 2 + 3)
The Model Context Protocol is a **specific API protocol**, in the same category
as REST or GraphQL, but designed for an LLM to discover and call tools itself.
Each integrated system is wrapped in a small **MCP server** that exposes named
tools (with plain-English descriptions the model reads at runtime).

> An MCP server is just a backend microservice. Its "routes" are tools with
> descriptions, instead of REST endpoints. Underneath, it calls the same APIs and
> databases you already have.

### AI Agent — the autonomous worker (Layer 4)
An agent = **LLM + MCP tools + a goal + a loop**. The loop is the engine:

```python
messages = [user_request]
while True:
    response = llm.create(system=prompt, messages=messages, tools=mcp_tools)
    if response.wants_to_call_a_tool:
        if is_high_stakes(response.tool_name):        # Layer 8 — human gate
            if not human_approves(...): result = "DENIED"
            else:                       result = run_tool(...)
        else:
            result = run_tool(response.tool_name, response.tool_args)
        messages += [response, result]
        continue
    else:
        return response.text            # final answer — no more tools needed
```

The "thinking" is the LLM's output, not hand-coded logic. You write the loop,
the system prompt, the tool set, and the gates.

The framework's four named agents are **the same loop with different prompts and
tool sets**:

| Agent | System prompt theme | Tools |
|-------|---------------------|-------|
| Planning | sequence the work | read-only |
| Execution | carry out the plan | write actions (gated) |
| Monitoring | watch SLAs / thresholds | IoT + SLA reads |
| Learning | improve from outcomes | memory read/write |

---

## Worked example: wet-season flood, 2am

1. **IoT mesh (L6):** a BOM gauge on Rapid Creek crosses threshold.
2. **Monitoring agent (L4):** perceives it via the flood MCP server.
3. **Planning agent (L4):** reasons *which roads/assets are at risk?* — pulls live
   answers from ArcGIS + Confirm **via MCP** (not from memory).
4. **Digital Twin (L5):** the plan is simulated before anything real happens.
5. **Execution agent (L4):** drafts closures, alerts the duty engineer, pre-positions a crew.
6. **Governance (L8):** road closure is high-stakes → **human gate**. Duty officer
   approves with one tap. Every step is logged for ICAC audit.
7. **Learning agent (L4):** records the outcome to refine tomorrow's prediction.

No human was woken to *discover* the problem — but a human still *owns the
decision*.

---

## Darwin-specific differentiators

- **Wet season intelligence** — cyclone track integration, flood modelling, pre-season risk scoring, post-storm triage.
- **First Nations cultural safety** — Larrakia Nation data co-governance, cultural site overlays in planning AI, Indigenous data sovereignty.
- **Remote connectivity** — edge computing, offline-capable field apps, satellite fallback.
- **Defence & growth** — RAAF/NORCOM coordination, rapid population demand forecasting, northern corridor planning.
- **Sovereign security** — ASD-certified Australian cloud, Essential Eight compliance, on-premises options for sensitive data.
