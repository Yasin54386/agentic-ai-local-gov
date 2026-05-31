# 05 — Governance & Ethics

Layer 8 is not a disclaimer bolted on at the end. It is an architectural layer
with concrete, implementable mechanisms. The principle:

> Agents do the routine coordination work. Humans own every significant decision.
> Everything is logged, explainable, and compliant.

---

## 1. Human-in-the-loop gates

The human gate is **literally a conditional in the agent loop** (see
[01 — Architecture](01-architecture-overview.md)):

```python
if response.wants_to_call_a_tool:
    if is_high_stakes(response.tool_name):     # any write/action tool
        if not human_approves(tool_name, tool_args):
            result = "DENIED by human reviewer"
        else:
            result = run_tool(tool_name, tool_args)
    else:
        result = run_tool(response.tool_name, response.tool_args)  # read-only, free
```

**What counts as high-stakes (always gated):**
- Any **write** to an operational system (create works order, raise PO, payment).
- Any action affecting the public (road closure, public notice).
- Any spend, contract, or financial commitment.
- Any action touching `sensitive` or `cultural` data.

**What is not gated:** read-only queries against `open` and `internal` data — the
agent reads freely to reason; it just cannot *act* unsupervised.

The gate maps directly to the `Gate` column in the
[MCP server register](04-mcp-server-register.md).

---

## 2. Audit trail (ICAC-ready)

Every MCP call — read or write — is logged with:
- who/what initiated it (which agent, which user request),
- the tool, arguments, and result,
- the timestamp and the provenance pointer into the Data Fabric raw layer,
- for gated actions: the human approver and their decision.

Because MCP standardizes every system call through one shape, this audit log is
*uniform and complete* by construction — not bolted on per integration. This is a
direct ICAC and accountability requirement, satisfied at the protocol level.

---

## 3. Compliance frameworks

| Framework | What it governs | How it's met |
|-----------|-----------------|--------------|
| **NT legislation** | Lawful basis for automated actions | Human gates on all statutory decisions; legal review of agent scopes |
| **ICAC (NT)** | Integrity, transparency, anti-corruption | Complete uniform audit trail; no unsupervised spend/contracting |
| **Australian AI Ethics Principles** | Fairness, accountability, transparency, contestability | Bias audits; plain-language explanations; human appeal path |
| **Essential Eight (ASD)** | Cyber security maturity | Per-server placement; sovereign cloud / on-prem for sensitive; authenticated MCP |

---

## 4. Indigenous data sovereignty (First Nations cultural safety)

This is a **first-class governance constraint**, not a feature.

- **Co-governance, not extraction.** Cultural data (`classification: cultural`) is
  governed *with* Larrakia Nation, under agreements they shape. We do not set the
  terms.
- **No default ingestion.** The `larrakia-cultural` MCP server's existence, tools,
  access, cadence, and placement are all decided by agreement — see
  [03](03-source-cadence-register.md) and [04](04-mcp-server-register.md).
- **Cultural site overlays** in planning AI respect access restrictions; sensitive
  locations are protected, not exposed.
- **CARE principles** (Collective benefit, Authority to control, Responsibility,
  Ethics) sit alongside FAIR data principles for all cultural data.

---

## 5. Bias, transparency & contestability

- **Bias audits** — regular review of agent decisions for disparate impact across
  communities and suburbs.
- **Plain-language explanation** — the LLM explains *why* a decision was reached,
  in language residents understand (Layer 1 + Layer 8). This is a deliberate use
  of the LLM's strength.
- **Contestability** — residents can challenge an automated outcome and reach a
  human. The audit trail makes every decision reviewable.
- **Transparency portal** (Phase 4) — public visibility into what the agents do
  and how.

---

## 6. Sovereignty placement summary

Placement is decided per-server by data classification (see
[02 — Data Fabric](02-data-fabric-schema.md)):

| Classification | Placement |
|----------------|-----------|
| `open` | Public/standard cloud acceptable |
| `internal` | Sovereign Australian cloud (ASD-certified) |
| `sensitive` | Sovereign cloud / on-premises; strict, logged access |
| `cultural` | Per Indigenous data co-governance agreement |
