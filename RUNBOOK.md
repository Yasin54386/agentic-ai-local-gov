# RUNBOOK — Run "Ask Darwin" on localhost

A step-by-step guide to run the whole system on your own machine. The data and
web layers are pure Python 3.10+ (**zero** pip installs). The chat is "AI
Powered" by a hosted API: it needs `pip install -r requirements.txt` and an
`ANTHROPIC_API_KEY`. Chat questions are processed by a third-party AI service —
don't include personal information. Everything else works with no key.

---

## 0. Prerequisites

- **Python 3.10+** — check: `python3 --version`
- **git** (to clone) — the repo already contains the harvested data + SQL databases.
- For the chat ("Ask") feature only: `pip install -r requirements.txt` and an
  `ANTHROPIC_API_KEY`. The other features work without it.

```bash
git clone <your-repo-url> agentic-ai-local-gov
cd agentic-ai-local-gov
```

The repo ships with the source data (`data/catalog.db`, `data/unified.db`,
`data/column_catalog.json`). The app now reads from a single **migrated database**
(`data/askterritory.db`) that you build once — see step 1.5.

> Shortcut: `bash scripts/try.sh` does the database build + launch for you.

---

## 1. (Optional) Rebuild the data from scratch

Only needed if you want fresh data or the `data/` folder is missing.

```bash
python3 -m ingestion.harvest --report          # catalog all ~1,100 datasets
python3 -m ingestion.fetch_data --api-sources  # download the live-API datasets
python3 -m ingestion.unify                     # build the unified SQL table
```

Verify:
```bash
python3 -c "import sqlite3;print(sqlite3.connect('data/unified.db').execute('SELECT COUNT(*) FROM records').fetchone()[0],'records')"
# -> 31330 records
```

---

## 1.5. Build the local database (required, one-time)

The app reads from one migrated database. Create it from the shipped source data:

```bash
python3 -m db.migrate     # create the schema
python3 -m db.load        # load datasets + records + categorised tables + catalog
```

This builds `data/askterritory.db` (gitignored, rebuilt anytime). To use
PostgreSQL instead, set `DATABASE_URL` first — see **DB-SETUP.md**.

---

## 2. (Optional) Enable the AI chat

Needed only for the **Ask** chat tab. The Live / Neighbourhood / Transparency /
Repository tabs work without it.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
```

Check it's configured:
```bash
curl -s http://localhost:8000/api/health | grep -o '"ai_available":[a-z]*'
```

> **Privacy:** chat questions are sent to a third-party AI service — don't
> include personal information. **Cost:** spend is capped by a hard monthly
> budget (`BUDGET_MONTHLY_AUD`, default 100); at the cap the chat pauses and the
> data tabs keep working.

---

## 3. Start the web UI

```bash
python3 -m webapp.server
# Ask Darwin running →  http://localhost:8000
```

Open **http://localhost:8000** in your browser. Tabs:

| Tab | What it does | Needs model? |
|-----|--------------|:-----------:|
| **Ask** | Plain-language questions answered from the data | yes |
| **Neighbourhood** | Full profile of any suburb/ward across datasets | no |
| **Live & Flood** | Live Darwin weather + indicative flood signal | no |
| **Transparency** | Council capital spend by category | no |
| **Repository** | What's in the harvested data repo | no |

Change the port: `PORT=9000 python3 -m webapp.server`

---

## 4. (Optional) The MCP server

The same tools are exposed over the **Model Context Protocol**, so any MCP client
(Claude Desktop, IDEs) can use your Darwin data.

Run it directly:
```bash
python3 -m mcp_server.server      # speaks JSON-RPC over stdio
```

Quick self-test from Python:
```bash
python3 -c "from mcp_server.client import MCPClient;\
import json;\
c=MCPClient(); c.start();\
print('tools:',[t['name'] for t in c.list_tools()]);\
print('flood:',c.call_tool('flood_risk')['flood_risk_level']);\
c.close()"
```

To connect from an MCP client, register this command:
```json
{ "command": "python3", "args": ["-m", "mcp_server.server"],
  "cwd": "/absolute/path/to/agentic-ai-local-gov" }
```

---

## 5. Keep data fresh — refresh every 6 hours (through MCP)

> **Usually not needed.** The web app **self-refreshes on access** — the live
> feed every ~10 min and the datasets every ~24h (throttled, in the background).
> Run a scheduled job only as a backup for periods of **zero traffic**, or if
> other consumers read the DB directly without going through the web app.

Each cycle pulls live weather/flood **through the MCP server** and appends a
snapshot to the unified table (building a time series). Add `--datasets` to also
re-harvest the City of Darwin datasets each cycle.

**Option A — long-running loop:**
```bash
python3 -m ingestion.refresh             # every 6 hours
python3 -m ingestion.refresh --datasets  # also rebuild datasets each cycle
```

**Option B — cron (recommended for servers):** run one cycle every 6 hours.
```bash
crontab -e
# add this line (adjust the path):
0 */6 * * * cd /absolute/path/to/agentic-ai-local-gov && /usr/bin/python3 -m ingestion.refresh --once >> data/refresh.log 2>&1
```

Verify snapshots are accumulating:
```bash
python3 -c "import sqlite3;print(sqlite3.connect('data/unified.db').execute(\"SELECT COUNT(*) FROM records WHERE dataset_id='live:darwin-weather'\").fetchone()[0],'live snapshots')"
```

---

## Typical full startup (server)

```bash
# 1. model (for chat)
bash scripts/setup_local_model.sh

# 2. background the 6-hourly refresh
nohup python3 -m ingestion.refresh >> data/refresh.log 2>&1 &

# 3. the web UI
python3 -m webapp.server
# → open http://localhost:8000
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Ask tab says "AI offline" | Set `ANTHROPIC_API_KEY` and `pip install -r requirements.txt` (step 2). Other tabs still work. |
| Ask tab says allowance used up | The monthly/daily budget cap was reached — chat resumes on the 1st (or next day). Data tabs keep working. |
| `Unified table not built` | Run `python3 -m ingestion.unify` (step 1). |
| Port already in use | `PORT=9000 python3 -m webapp.server` |
| Live weather empty | Needs outbound internet to Open-Meteo; flood/weather are the only online calls. |

Everything except the live weather call and the one-time model download runs
fully offline on your machine.
