"""Hosted AI backend — the single choke point for every model call.

The chat is "AI Powered" by a hosted API (the provider is deliberately not
named in user-facing surfaces). This module is the ONE place every call
passes through, so the budget ledger can guarantee the monthly spend
ceiling: each call checks the budget before and records real token usage
after. Nothing else in the app talks to the API directly.

Cost controls live here:
  - prompt caching (cache_control ephemeral) on the system prompt, which —
    because tools render before system — caches the tool definitions too;
  - tool results are trimmed before they go back to the model (input is the
    cost driver);
  - max output tokens is small and shrinks further in "degraded" mode.

Config (env):
    ANTHROPIC_API_KEY   the API key. No key -> chat shows offline, panels work.
    MODEL               model id              (default: claude-haiku-4-5)
    MAX_OUTPUT_TOKENS   per-call output cap   (default: 500)
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import budget

MODEL = os.environ.get("MODEL", "claude-haiku-4-5")
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "500"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Back-compat alias kept so existing callers (server/cli/health) keep working.
DEFAULT_MODEL = MODEL

# Tool results are trimmed to roughly this many characters (~1.5K tokens)
# before being sent back — the model only needs the aggregates, not raw rows.
TOOL_RESULT_CHARS = 6000

_client = None


class AIError(RuntimeError):
    """Any failure talking to the hosted model."""


# Back-compat alias: older code caught llm.LocalModelError.
LocalModelError = AIError


def describe() -> str:
    """Generic, provider-neutral description for logs/status."""
    return "AI Powered (hosted)"


def server_up() -> bool:
    """True when the chat is usable: a key is set and the SDK is importable.

    Budget exhaustion is a SEPARATE, softer state (see agent.budget.status);
    this only reports whether the hosted AI is configured at all, so that
    pulling the key degrades the chat tab only.
    """
    if not ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def _system_blocks(system: str) -> list[dict]:
    """System prompt as a single cached block. Tools render before system,
    so this one breakpoint caches the tool definitions + system together."""
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def trim_tool_result(result: Any) -> str:
    """Serialise a tool result and cap its size to control input cost."""
    text = json.dumps(result, default=str)
    if len(text) > TOOL_RESULT_CHARS:
        text = text[:TOOL_RESULT_CHARS] + ' …"[truncated]"'
    return text


def messages_create(system: str, messages: list[dict], *,
                    tools: list[dict] | None = None,
                    max_tokens: int | None = None,
                    endpoint: str = "") -> Any:
    """One API round. Budget-gated before, usage-recorded after.

    Raises budget.BudgetExceededError if the AI allowance is used up, and
    AIError on any API failure. Returns the raw SDK Message.
    """
    budget.check_allowed()  # raises BudgetExceededError when paused
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens or MAX_OUTPUT_TOKENS,
        "system": _system_blocks(system),
        "messages": messages,
        "temperature": 0.0,
    }
    if tools:
        kwargs["tools"] = tools  # tools.py is already in Anthropic input_schema shape
    try:
        resp = client.messages.create(**kwargs)
    except budget.BudgetExceededError:
        raise
    except Exception as exc:  # anthropic.APIError and friends
        raise AIError(str(exc)) from exc

    u = resp.usage
    budget.record(
        MODEL,
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        endpoint=endpoint,
    )
    return resp


def complete(prompt: str, *, max_tokens: int = 300, endpoint: str = "complete") -> str:
    """Single-turn text completion (used by forms/how-to synonym expansion).

    Budget-gated like every other call. Returns plain text ("" on refusal).
    """
    resp = messages_create(
        "You are a concise assistant.",
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        endpoint=endpoint,
    )
    if getattr(resp, "stop_reason", None) == "refusal":
        return ""
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
