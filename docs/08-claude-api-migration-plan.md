# 08 — Migration Plan: Hosted AI Backend + Cost Controls + Feature Roadmap

Status: **PLAN** (no code changes yet). Scope: replace the Ollama/local-model
backend with the Anthropic (Claude) Messages API, rebrand as plain
"AI Powered", scope answers to the Northern Territory, add hard cost
controls (rate limiting + AUD 50/month budget cap with monthly reset),
and a roadmap of resident-facing features.

---

## 1. What exists today (relevant parts)

| Piece | File(s) | Notes |
|---|---|---|
| Pluggable LLM client | `agent/llm.py` | `local` (Ollama) default, `openai` opt-in; stdlib `urllib` only |
| Agent tool loop | `agent/agent.py` | system prompt + up to 8 tool rounds over read-only data tools |
| Data tools | `agent/tools.py` | already declared in Anthropic `input_schema` shape (converted to OpenAI shape at call time) |
| Web server | `webapp/server.py` | stdlib `ThreadingHTTPServer`; `/api/ask` is stateless, no rate limiting |
| UI | `webapp/static/index.html`, `concept.html` | "Self-hosted · No data leaves the Territory" branding |
| Infra | `docker-compose.yml` (ollama service), `Dockerfile`, `scripts/setup_local_model.sh`, `RUNBOOK.md` | all assume local model |

Useful fact: `agent/tools.py` TOOLS already use Anthropic's `input_schema`
format, so the Claude migration is mostly an `llm.py` rewrite — the tool
definitions pass through unchanged.

---

## 2. Phase 1 — Replace Ollama with the Claude API

### 2.1 New `agent/llm.py`

- Use the official `anthropic` Python SDK (`pip install anthropic`) — adds
  `requirements.txt` to a previously stdlib-only repo, but buys automatic
  retries (429/5xx), typed errors, streaming helpers, and `usage` accounting
  we need for the budget ledger.
- Single backend. Delete `LLM_BACKEND`, `OLLAMA_HOST`, `LLM_BASE_URL`,
  `LLM_FALLBACK`, the egress warning, and the OpenAI shape conversion.
- Env:
  - `ANTHROPIC_API_KEY` (required)
  - `MODEL` (default per §2.3)
  - `MAX_OUTPUT_TOKENS` (default ~700 — supports the ≤10-sentence rule)
- Messages API specifics:
  - tools passed as-is (`name`/`description`/`input_schema`)
  - agent loop: `stop_reason == "tool_use"` → execute tools → append
    `tool_result` blocks in a `user` turn → repeat; keep `MAX_STEPS = 8` cap
  - **prompt caching**: `cache_control: {"type": "ephemeral"}` on the last
    system block so tools + system prompt are cached across the multi-step
    loop and across questions (major cost reduction)
  - record `response.usage` (input/output/cache tokens) after every call →
    feeds the budget ledger (§4)

### 2.2 Remove local-model machinery

- Delete `scripts/setup_local_model.sh`
- `docker-compose.yml`: drop the `ollama` service + `ollama_models` volume;
  pass `ANTHROPIC_API_KEY` via env
- `Dockerfile`: drop `OLLAMA_HOST` / `MODEL=qwen…` env
- `.env.example`: replace the backend block with `ANTHROPIC_API_KEY=`,
  `MODEL=`, budget/rate-limit knobs (§4)
- `webapp/server.py`: `server_up()` becomes "is the API key configured";
  the "start your local model" hint becomes "AI assistant is not configured"
- `/api/health`: stop exposing the model name (currently would leak
  `claude-…` to anyone); report `"ai": true/false` plus budget status only

### 2.3 Model choice (decision needed)

AUD 50/month ≈ **US$32** (assume 0.64, configurable). Rough per-question
cost for this workload (≈2.7K system+tools prefix, ~3 tool rounds,
~15–25K input tokens largely cache-served, ~0.8K output):

| Model | $/MTok in/out | Est. cost/question | Questions per AUD 50 |
|---|---|---|---|
| `claude-haiku-4-5` | 1 / 5 | ~US$0.02–0.03 | ~1,100–1,600 |
| `claude-sonnet-4-6` | 3 / 15 | ~US$0.06–0.09 | ~350–500 |
| `claude-opus-4-8` | 5 / 25 | ~US$0.10–0.15 | ~210–320 |

**Recommendation:** `claude-sonnet-4-6` as default (good tool-use quality at
~400 questions/month within budget), with `MODEL` env override. Anthropic's
general default is `claude-opus-4-8` (highest quality) — viable if monthly
volume stays low. For maximum headroom on a public site, `claude-haiku-4-5`.
The task (pick a tool, filter, summarise aggregates) is well within
Sonnet/Haiku capability.

### 2.4 System-prompt changes (NT-only + concise)

Append to the existing prompt in `agent/agent.py`:

- **Scope guard:** "You only answer questions about the Northern Territory
  and City of Darwin local government — places, services, spending, weather,
  demographics from the connected data. For anything else, decline in one
  sentence and steer back to NT topics."
- **Brevity:** "Answer as a minimised summary: never more than 10 sentences.
  Prefer numbers and short sentences over prose."
- **Links:** "When helpful, include a link — the source dataset on
  smart.darwin.nt.gov.au, or official pages (nt.gov.au, darwin.nt.gov.au,
  bom.gov.au) — as plain URLs."
- Belt-and-braces: server-side `max_tokens` ≈ 700 on the final call.

### 2.5 Chat memory — last 10 messages

`/api/ask` becomes conversational:

- Server keeps an in-memory per-session ring buffer:
  `deque(maxlen=10)` of `{role, content}` (i.e. 5 exchanges), keyed by a
  random session id set as a cookie (or returned in JSON and echoed by the
  client). Entries expire after ~30 min idle; no persistence needed.
- On each ask: history (≤10 msgs) + new question → Claude; append the
  question and final answer back to the buffer. Tool-use intermediate
  messages are *not* stored (keeps the buffer meaningful and cheap).
- UI: render the thread in the Ask tab; add a "New chat" button that rotates
  the session id.

---

## 3. Phase 2 — Rebrand: plain "AI Powered"

Remove every claim that the assistant is local/self-hosted, and do not name
the provider. Inventory:

| File | Change |
|---|---|
| `webapp/static/index.html` (≈ lines 158, 206, 234, 244) | tagline → "AI Powered · NT Open Data"; "100% Self-hosted" stat → something true (e.g. datasets count); "AI Assistant · self-hosted model" → "AI Assistant"; remove "Needs the local model running" |
| `webapp/static/concept.html` (≈ 319, 396) | same |
| `agent/README.md`, `agent/__init__.py`, `agent/agent.py`, `agent/llm.py`, `agent/tools.py` docstrings | rewrite "self-hosted / sovereign / no data leaves" framing → "hosted AI API" |
| `RUNBOOK.md` | drop Ollama setup section + troubleshooting rows; add "set ANTHROPIC_API_KEY" step |
| `README.md`, `scripts/try.sh` | same cleanup |
| `docs/01-architecture-overview.md` etc. | keep the *data*-governance content, but anywhere the docs claim the **LLM** runs locally, update to "hosted AI provider (no training on our data; questions leave the network)" |

Add a short privacy note in the UI footer / README: questions typed into the
Ask tab are processed by a third-party AI service — don't include personal
information. (Honest replacement for the deleted sovereignty claim.)

---

## 4. Phase 3 — Rate limiting + AUD 50/month budget cap

Two independent layers: **rate limiting** (stops abuse) and a **budget
ledger** (hard spend ceiling even if rate limits are mis-tuned).

### 4.1 Budget ledger (hard cap, auto monthly reset)

New module `agent/budget.py`, persisted in the existing SQLite DB:

```sql
CREATE TABLE IF NOT EXISTS ai_usage (
  month TEXT NOT NULL,            -- 'YYYY-MM' in Australia/Darwin time
  ts    TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER, output_tokens INTEGER,
  cache_read_tokens INTEGER, cache_write_tokens INTEGER,
  cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_month ON ai_usage(month);
```

- After **every** API call (each step of the tool loop), insert a row with
  cost computed from a price table per model (input/output/cache-read at
  0.1×/cache-write at 1.25×).
- **Monthly reset is free:** the cap is `SUM(cost_usd) WHERE month = current
  month` — a new month means a new key, nothing to cron.
- Config: `BUDGET_MONTHLY_AUD=50`, `USD_PER_AUD=0.64` (conservative fixed
  rate, env-overridable). Effective cap = 50 × 0.64 = US$32.
- Enforcement in `/api/ask` *before* calling the API:
  - ≥ 100% → HTTP 200 with `{"budget_exhausted": true}` and a friendly
    message ("the monthly AI allowance is used up — back on the 1st; the
    data panels still work"). Data panels are unaffected.
  - ≥ 80% → degrade gracefully: lower `max_tokens`, optionally switch
    `MODEL` to `claude-haiku-4-5` for the remainder of the month.
- Also a **daily sub-cap** (monthly/30, configurable) so one bad day can't
  burn the month.
- Mid-loop guard: if the budget trips between tool steps, finish with a
  "partial answer" rather than starting another round.
- `/api/health` (and later an admin view) reports
  `{month_spend_aud, budget_aud, pct_used}`.

### 4.2 Request rate limiting

`/api/ask` only (data endpoints stay open but are cheap):

- **nginx first line** (deploy/nginx.conf): `limit_req_zone` on
  `/api/ask` — e.g. 5 r/m per IP, burst 3 — plus `client_max_body_size 2k`.
- **App-level second line** (stdlib, works in dev too): token-bucket per IP
  (`X-Forwarded-For` trusted only from nginx): defaults
  `RATE_PER_MIN=5`, `RATE_PER_HOUR=30`, `RATE_PER_DAY=100`; one in-flight
  request per session; question length cap (500 chars → HTTP 400).
- **Global circuit breaker:** max questions/day across all users
  (`GLOBAL_DAILY_QUESTIONS`, default sized to the daily budget sub-cap) —
  scripts hitting from many IPs still can't exceed spend.
- 429 responses include `retry-after`; UI shows "easy — try again in a
  minute".

### 4.3 Token hygiene (cost per question down)

- Prompt caching on system+tools (≈90% off the repeated prefix).
- Tool results already truncated at 12K chars — keep; trim `limit` defaults
  in tools so the model gets aggregates, not row dumps.
- `MAX_STEPS` stays at 8; consider 6.
- History capped at 10 messages (§2.5) bounds input growth.

---

## 5. Phase 4 — Feature roadmap ("extraordinary help guide for Territory residents")

Ordered by value ÷ effort; A-items first.

### A. High value, low effort
1. **Streaming answers (SSE)** — `client.messages.stream()` piped through
   the stdlib server; chat feels instant even on multi-tool questions.
2. **Cited answers** — every answer ends with "Source: <dataset>" linking to
   the smart.darwin.nt.gov.au dataset page (we already know which table each
   tool hit). Builds trust; pairs with the new link rule.
3. **Suggested question chips** — per-tab starters ("How much did Council
   spend in my ward?", "Dog registrations in Karama", "Is it going to
   flood this week?"). Guides residents and reduces vague (expensive)
   queries.
4. **"New chat" + visible 10-message memory** — surfaces the memory rule as
   a feature.
5. **Budget transparency widget** — small footer note when in degraded
   (80%+) mode; honest and deflects complaints.

### B. High value, medium effort
6. **My Suburb page** — one shareable URL per suburb
   (`/suburb/karama`): ward + councillors, council spend for its ward,
   demographics, trees/canopy, animal stats, current weather/flood risk.
   Pre-rendered from existing tools — zero AI cost.
7. **Suburb comparison** — pick two suburbs, side-by-side stats (again no
   AI tokens; pure data panels).
8. **Multilingual answers** — language picker (the Census language data in
   this very repo shows the need: Greek, Tagalog, Kriol, Indonesian…).
   Claude answers in the selected language at no extra integration cost;
   also translate the UI chrome statically.
9. **Council decisions & grants plain-English digest** — pre-summarise new
   councillor decisions and grants monthly with the **Batches API (50%
   price)**, store summaries in SQLite, serve them token-free thereafter.
10. **Live alerts strip** — BOM warnings (cyclone/flood watches), fire
    danger, tide times for the Top End wet season; extends the existing
    live_weather/flood_risk ingestion, no AI cost.

### C. Differentiators (later)
11. **Weekly "Territory Brief"** — auto-generated digest page (what Council
    decided, spend movements, canopy/mobility trends), generated once a week
    via the Batches API; shareable, costs cents.
12. **Feedback loop** — 👍/👎 per answer stored with the (anonymised)
    question; monthly review tunes the system prompt and chips.
13. **More sources** — data.nt.gov.au (Territory-wide, not just Darwin),
    NTG road report, Power & Water outages; the ingestion layer
    (ckan/opendatasoft/arcgis adapters) already supports this.
14. **PWA / mobile install** — manifest + service-worker caching of data
    panels; the site already works offline-ish for panels.
15. **Admin mini-dashboard** — `/admin` (basic auth): month spend, top
    questions, rate-limit hits, dataset freshness.

### Explicitly out (cost/abuse risk)
- Voice input, image upload, open-ended web search from the chat, and
  per-user accounts — all reopen the cost-control surface for little
  resident value right now.

---

## 6. Suggested implementation order

| Step | Contents | Risk |
|---|---|---|
| 1 | `llm.py` rewrite + SDK + prompt caching + usage capture | core |
| 2 | Budget ledger + enforcement + `/api/health` budget status | must land **with or before** going live on the API key |
| 3 | Rate limiting (nginx + app) | must land before public exposure |
| 4 | NT-only + ≤10 sentences + links in system prompt; `max_tokens` cap | quick |
| 5 | 10-message session memory + UI thread | quick |
| 6 | Rebrand sweep (UI, READMEs, docs, compose/Dockerfile, delete setup script) | mechanical |
| 7 | Roadmap items A1–A5, then B | iterative |

Definition of done for the migration: no `ollama`/`qwen`/"self-hosted"
references outside git history; `/api/ask` answers from Claude with caching
on; pulling the API key or exhausting the budget degrades the chat tab only;
a load test against `/api/ask` cannot push estimated monthly spend past
AUD 50.
