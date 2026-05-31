# Agent — Self-Hosted Data Assistant

A backend-agnostic agent (Layer 4) that answers plain-language questions about
the NT/Darwin public data repository (Layer 3), driven by a **self-hosted**
open-weight model running on **your own server**. No external API. No data
leaves your machine. This is the sovereign architecture your governance layer
(docs/05) requires.

## How it works

```
your question
     │
     ▼
┌──────────────────────────────┐
│ agent loop (agent.py)        │   the ~loop from docs/01
│   ↕ tools (tools.py)          │   "the hands" — read-only data tools
│   ↕ local model (llm.py)      │   Qwen2.5-7B via Ollama on localhost
└──────────────────────────────┘
     │ reads
     ▼
data repository (ingestion/) — 1,104 datasets, real records
```

The model decides which tools to call; the tools read the real harvested data;
the model reasons over the results and answers — citing dataset ids. The model
never sees the internet and the data never leaves your server.

## Model: Qwen2.5-7B-Instruct

- **Apache-2.0** — free, permissive, fine for government/commercial use.
- Runs on a decent CPU (~6–8 GB RAM) or a small GPU. No GPU? Still works, slower.
- Strong at tool-use + retrieval-grounded answering (our exact use case).
- Want it sharper? `MODEL=qwen2.5:32b-instruct` (needs a real GPU).

## Setup (one time)

```bash
# installs Ollama + pulls the model (everything local):
bash scripts/setup_local_model.sh
```

## Use

```bash
# one-shot question:
python -m agent.cli "How much did each ward spend? Which ward spent the most?"

# interactive:
python -m agent.cli
```

Example questions the agent can answer from the real data:
- "Total councillor expenses by ward."
- "How many animal registrations are there, and by suburb?"
- "What datasets do we have about trees or the environment?"
- "Show me the landfill gas generation figures."

## Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `MODEL` | `qwen2.5:7b-instruct` | which local model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | local model server URL |

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

## No model? The data layer still works.

`repository.py` and `tools.py` have **no model dependency** and can be tested
directly:

```bash
python -c "from agent.repository import Repository as R; \
print(R().aggregate('smart.darwin.nt.gov.au:councillor-expenses','ward','amount','sum'))"
```

This proves the data plumbing before you attach the local model — which is how
this was built and verified.
