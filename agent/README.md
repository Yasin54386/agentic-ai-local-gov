# Agent — AI-Powered Data Assistant

An agent (Layer 4) that answers plain-language questions about the NT/Darwin
public data repository (Layer 3), powered by a hosted AI model reached through
`llm.py` — the single, budget-gated choke point for every model call.

> **Privacy:** chat questions are processed by a third-party AI service. Don't
> include personal information. The data panels, forms and how-to search never
> call the model and work with no key set.

## How it works

```
your question
     │
     ▼
┌──────────────────────────────┐
│ agent loop (agent.py)        │   the loop from docs/01
│   ↕ tools (tools.py)          │   "the hands" — read-only data tools
│   ↕ llm.py                    │   hosted AI · budget-gated · prompt-cached
└──────────────────────────────┘
     │ reads
     ▼
data repository (ingestion/) — 1,104 datasets, real records
```

The model decides which tools to call; the tools read the real harvested data;
the model reasons over the results and answers — citing dataset ids. Tool
results are trimmed before they go back to the model (input is the cost driver).

## Cost controls (why this stays cheap)

Every call passes through `llm.py`, which:

- checks the budget ledger (`budget.py`) **before** each call and records real
  token usage **after** — so a fixed monthly AUD ceiling cannot be exceeded;
- caches the system prompt + tool definitions (prompt caching);
- keeps `max_tokens` small (≈500), shrinking further in "degraded" mode.

Most traffic never reaches the model at all: the data panels are token-free and
a normalized-question answer cache (`answer_cache.py`) serves repeats for $0.

## Setup

Set an API key in the environment, then ask:

```bash
export ANTHROPIC_API_KEY=sk-...

# one-shot question:
python -m agent.cli "How much did each ward spend? Which ward spent the most?"

# interactive:
python -m agent.cli
```

Example questions the agent can answer from the real data:
- "Total councillor expenses by ward."
- "How many animal registrations are there, and by suburb?"
- "What datasets do we have about trees or the environment?"

## Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | _(unset)_ | API key. No key → chat offline, panels work. |
| `MODEL` | `claude-haiku-4-5` | model id (provider-neutral in the UI) |
| `MAX_OUTPUT_TOKENS` | `500` | per-call output cap |
| `BUDGET_MONTHLY_AUD` | `100` | hard monthly spend ceiling |
| `USD_PER_AUD` | `0.60` | conservative fixed FX rate |
| `AI_DAILY_CALLS` | `450` | global daily call ceiling |

## The tools (the agent's hands)

All **read-only** — defined in `tools.py`, backed by `repository.py`:

| Tool | What it does |
|------|--------------|
| `search_datasets` | find datasets by text / domain |
| `get_dataset_info` | full metadata for one dataset |
| `get_dataset_records` | read actual rows (optionally filtered) |
| `aggregate` | group + count / sum / avg over a dataset |
| `repository_stats` | repo-wide totals |

> When write actions are added later (e.g. raise a works order), the high-stakes
> **human gate** from docs/05 wraps `dispatch()` in `tools.py` — one conditional.

## No key? The data layer still works.

`repository.py` and `tools.py` have **no model dependency** and can be tested
directly:

```bash
python -c "from agent.repository import Repository as R; \
print(R().aggregate('smart.darwin.nt.gov.au:councillor-expenses','ward','amount','sum'))"
```

This proves the data plumbing independently of the AI — which is how this was
built and verified.
