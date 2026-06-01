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
- A place AND a concept together (e.g. "Karama and expenses", "trees in Malak")? \
-> call find_records(area=..., keyword=...) to get exactly the records where both \
co-occur. If it returns 0, say so honestly and read its "note".
- Not sure which field or dataset has the answer? -> call find_columns(query) to \
locate the column, its table and dataset; then fetch from there.
- Exploring what exists? -> list_tables() and search_datasets(query).
- Weather, rain, flood, wet season? -> live_weather() / flood_risk().

Hard rules:
- Filter by what the question names (suburb, ward, year, category). NEVER answer a \
question about one place with data about a different place.
- NEVER summarise the first few rows of a dataset as if they answer the question.
- If the data does NOT contain what was asked (e.g. there is no "cost" or "price" \
for a suburb), say so plainly in one sentence, then offer what IS available for it \
(e.g. its neighbourhood_profile). Do NOT substitute unrelated data.
- Prefer aggregated numbers (sum/count) over raw rows. Be concise and factual, and \
name the table or dataset you used.
"""

MAX_STEPS = 8  # safety cap on tool-use rounds


def _tool_results_message(name: str, result: Any) -> dict:
    """Ollama expects tool outputs as role:'tool' messages."""
    return {"role": "tool", "content": json.dumps(result, default=str)[:12000]}


def run(question: str, *, repo: Repository | None = None, model: str | None = None,
        verbose: bool = True) -> str:
    """Answer a question by letting the local model reason over the data tools."""
    own_repo = repo is None
    repo = repo or Repository()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    kw = {"model": model} if model else {}
    try:
        for step in range(MAX_STEPS):
            msg = llm.chat(messages, tools=TOOLS, **kw)
            tool_calls = msg.get("tool_calls") or []
            messages.append({"role": "assistant",
                             "content": msg.get("content", ""),
                             "tool_calls": tool_calls})
            if not tool_calls:
                return msg.get("content", "").strip() or "(no answer produced)"

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if verbose:
                    print(f"  [tool] {name}({json.dumps(args)})", flush=True)
                # READ-ONLY tools — a high-stakes human gate (docs/05) would sit here.
                result = dispatch(repo, name, args)
                messages.append(_tool_results_message(name, result))
        return "(reached step limit without a final answer)"
    finally:
        if own_repo:
            repo.close()
