"""The agent loop — Layer 4 orchestration over the local model + data tools.

This is the loop from docs/01: send the conversation + tools to the SELF-HOSTED
model, run whatever tool it asks for against the real repository, feed results
back, repeat until the model produces a final answer. No external services.
"""
from __future__ import annotations

import json
from typing import Any

from . import llm
from .repository import Repository
from .tools import TOOLS, dispatch

SYSTEM_PROMPT = """You are "Ask Territory", a data assistant for Northern \
Territory & City of Darwin local-government open data. Answer questions ONLY from \
the data, which you reach through the tools. Think about WHICH tool fits before calling.

Choosing the right tool:
- About a SUBURB or WARD (e.g. "tell me about Karama", "dogs in Malak", \
"Karama")? -> call neighbourhood_profile(suburb) FIRST to see what data exists \
for that place, then dig in with query_unified(area=...).
- "How much / how many / total / by ward / by category / by year"? -> use \
query_unified(table=..., group_by=..., op="sum" or "count") or \
aggregate(dataset_id, group_by, value, op).
- A SUBURB's council spending/cost (e.g. "how much for Karama")? Council money is \
by WARD, not suburb. So FIRST call suburb_lookup(suburb) to get its ward, THEN \
query_unified(table="finance", area=<that ward>, group_by="category", op="sum").
- A place AND a concept together (e.g. "Karama and expenses", "trees in Malak")? \
-> call find_records(area=..., keyword=...) to get exactly the records where both \
co-occur. If it returns 0, say so honestly and read its "note".
- Not sure which field or dataset has the answer? -> call find_columns(query) to \
locate the column, its table and dataset; then fetch from there.
- Exploring what exists? -> list_tables() and search_datasets(query).
- Weather, rain, flood, wet season? -> live_weather() / flood_risk().
- HOW to do something, step-by-step, apply for / register / pay / get a licence? \
-> search_howto(query) — searches NT government how-to guides with steps and links.
- Need a FORM, application, or document? -> search_forms(query) — finds official NT \
government forms and downloadable documents.

Hard rules:
- Filter by what the question names (suburb, ward, year, category). NEVER answer a \
question about one place with data about a different place.
- NEVER summarise the first few rows of a dataset as if they answer the question.
- If the data does NOT contain what was asked (e.g. there is no "cost" or "price" \
for a suburb), say so plainly in one sentence, then offer what IS available for it \
(e.g. its neighbourhood_profile). Do NOT substitute unrelated data.
- Prefer aggregated numbers (sum/count) over raw rows. Be concise and factual, and \
name the table or dataset you used.
- When a question spans more than one source (e.g. a suburb AND the weather, or \
spending AND population), consult each relevant tool and SYNTHESISE one combined \
answer rather than answering from a single source.

Response style:
- Keep answers short and conversational — 3 to 6 sentences max for simple questions.
- NEVER use markdown tables. Use plain sentences or a short bullet list (3-5 items).
- For step-by-step questions, use a numbered list with one line per step, no sub-bullets.
- Do not add unnecessary headers, footers, or "good luck" sign-offs.
- Link to official pages by name only (e.g. "nt.gov.au/driving"), not full URLs.
"""

MAX_STEPS = 8  # safety cap on tool-use rounds


def _rag_answer(question: str, repo: Repository, model: str | None) -> str:
    """Fallback: search DB directly, inject context, ask model without tools."""
    from .tools import dispatch
    # Pull relevant context using the most useful tools directly
    context_parts = []
    try:
        context_parts.append(dispatch(repo, "search_datasets", {"query": question}))
    except Exception:
        pass
    try:
        context_parts.append(dispatch(repo, "find_records", {"keyword": question}))
    except Exception:
        pass
    try:
        context_parts.append(dispatch(repo, "search_howto", {"query": question}))
    except Exception:
        pass
    try:
        context_parts.append(dispatch(repo, "search_forms", {"query": question}))
    except Exception:
        pass

    context = "\n\n".join(str(c) for c in context_parts if c)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context from NT government database:\n{context}\n\nQuestion: {question}"},
    ]
    kw = {"model": model} if model else {}
    msg = llm.chat(messages, tools=None, **kw)
    return (msg.get("content") or "").strip() or "(no answer produced)"


def run(question: str, *, repo: Repository | None = None, model: str | None = None,
        history: list[dict] | None = None, verbose: bool = True) -> str:
    """Answer a question by letting the local model reason over the data tools.

    `history` is an optional list of prior turns ({"role": "user"|"assistant",
    "content": str}) so follow-up questions keep context. Only the most recent
    few turns are kept, and each is length-capped, to keep the prompt lean.
    """
    own_repo = repo is None
    repo = repo or Repository()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)[:4000]})
    messages.append({"role": "user", "content": question})
    kw = {"model": model} if model else {}
    try:
        for step in range(MAX_STEPS):
            try:
                msg = llm.chat(messages, tools=TOOLS, **kw)
            except llm.LocalModelError as exc:
                if "tool" in str(exc).lower() or "404" in str(exc):
                    # Model doesn't support tool use — fall back to RAG
                    if verbose:
                        print("  [fallback] tool use unsupported, switching to RAG mode", flush=True)
                    return _rag_answer(question, repo, model)
                raise
            calls = llm.extract_tool_calls(msg)
            messages.append(llm.assistant_message(msg))
            if not calls:
                return (msg.get("content") or "").strip() or "(no answer produced)"

            for call in calls:
                if verbose:
                    print(f"  [tool] {call['name']}({json.dumps(call['args'])})", flush=True)
                result = dispatch(repo, call["name"], call["args"])
                messages.append(llm.tool_result(call["id"], call["name"], result))
        return "(reached step limit without a final answer)"
    finally:
        if own_repo:
            repo.close()
