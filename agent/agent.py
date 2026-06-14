"""The agent loop — Layer 4 orchestration over the hosted model + data tools.

Send the conversation + tools to the model, run whatever read-only tool it
asks for against the real repository, feed trimmed results back, repeat until
it produces a final answer. Every model call goes through agent.llm, which
enforces the budget ceiling, so this loop stays small.
"""
from __future__ import annotations

import json
from typing import Any

from . import budget, llm
from .repository import Repository
from .tools import TOOLS, dispatch

SYSTEM_PROMPT = """You are "Ask Territory", an AI assistant for Northern \
Territory and City of Darwin residents, answering from NT/Darwin local-government \
open data which you reach through the tools.

Scope — NT only:
- Answer ONLY questions about the Northern Territory or the City of Darwin \
(services, suburbs, council data, weather, forms, how-to). If a question is \
about somewhere else or an unrelated topic, decline in ONE sentence and steer \
back: "I can only help with Northern Territory and Darwin questions."

Choosing the right tool:
- About a SUBURB or WARD ("tell me about Karama", "dogs in Malak")? -> \
neighbourhood_profile(suburb) first, then dig in with query_unified(area=...).
- "How much / how many / total / by ward / by category / by year"? -> \
query_unified(table=..., group_by=..., op="sum"|"count") or aggregate(...).
- A suburb's council spending? Council money is by WARD, not suburb: call \
suburb_lookup(suburb) for its ward, then query_unified(table="finance", area=<ward>).
- A place AND a concept together ("Karama and expenses")? -> \
find_records(area=..., keyword=...). If it returns 0, say so honestly.
- Not sure which field/dataset? -> find_columns(query). Exploring? -> \
list_tables() and search_datasets(query).
- Weather, rain, flood, wet season? -> live_weather() / flood_risk().
- HOW to do something (register/apply/pay/licence)? -> search_howto(query).
- Need a FORM or document? -> search_forms(query).

Hard rules:
- Filter by what the question names (suburb, ward, year, category). NEVER answer \
about one place with data about another.
- NEVER summarise the first few rows of a dataset as if they answer the question.
- If the data does NOT contain what was asked, say so plainly in one sentence, \
then offer what IS available. Do NOT substitute unrelated data.
- Prefer aggregated numbers (sum/count) over raw rows; name the table/dataset used.

Response style:
- A minimised summary: at most 10 sentences, numbers over prose. Be concise \
and factual. No markdown tables — plain sentences or a short bullet list.
- For step-by-step questions, a numbered list, one line per step.
- Link to official sources as plain URLs when helpful (smart.darwin.nt.gov.au, \
nt.gov.au, darwin.nt.gov.au, bom.gov.au). No sign-offs or filler.
"""

# Extra instruction appended when the budget is in the degraded band.
_DEGRADED_NUDGE = ("\n\nKeep this answer especially short — 3 sentences or fewer.")

MAX_STEPS = 6  # safety cap on tool-use rounds


def _final_text(resp: Any) -> str:
    if getattr(resp, "stop_reason", None) == "refusal":
        return "I can only help with Northern Territory and Darwin questions."
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    return text or "(no answer produced)"


def run(question: str, *, repo: Repository | None = None, model: str | None = None,
        history: list[dict] | None = None, max_tokens: int | None = None,
        degraded: bool = False, verbose: bool = True) -> str:
    """Answer a question by letting the hosted model reason over the data tools."""
    own_repo = repo is None
    repo = repo or Repository()
    system = SYSTEM_PROMPT + (_DEGRADED_NUDGE if degraded else "")

    messages: list[dict] = []
    if history:
        for turn in history:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    try:
        for _ in range(MAX_STEPS):
            try:
                resp = llm.messages_create(
                    system, messages, tools=TOOLS,
                    max_tokens=max_tokens, endpoint="ask",
                )
            except budget.BudgetExceededError as exc:
                # Mid-loop guard: budget tripped between steps. If the model
                # already produced some text, return it; else the pause line.
                partial = "".join(
                    m.get("content", "") for m in messages
                    if m.get("role") == "assistant" and isinstance(m.get("content"), str)
                ).strip()
                return partial or budget.pause_message(exc.reason)

            if getattr(resp, "stop_reason", None) != "tool_use":
                return _final_text(resp)

            # Round-trip: append the assistant turn (incl. tool_use blocks),
            # then a user turn carrying every tool_result.
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if verbose:
                    print(f"  [tool] {block.name}({json.dumps(block.input)})", flush=True)
                result = dispatch(repo, block.name, dict(block.input))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": llm.trim_tool_result(result),
                })
            messages.append({"role": "user", "content": results})
        return "(reached step limit without a final answer)"
    finally:
        if own_repo:
            repo.close()
