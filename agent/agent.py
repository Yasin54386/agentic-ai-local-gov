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

SYSTEM_PROMPT = """You are a data assistant for the City of Darwin / Northern \
Territory local government. You answer questions using ONLY the public data \
repository, which you reach through the provided tools.

Rules:
- Always ground answers in real data. Use `search_datasets` to find the right \
dataset, then `get_dataset_records` or `aggregate` to read the actual numbers.
- Never invent figures. If the data does not contain the answer, say so plainly.
- Cite the dataset id(s) you used (e.g. `smart.darwin.nt.gov.au:councillor-expenses`).
- Be concise and factual. Prefer numbers from `aggregate` for totals/counts.
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
