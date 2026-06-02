"""Pluggable LLM backend — sovereign by default, hosted by deliberate opt-in.

Default backend is a LOCAL model via Ollama (no data leaves your network). An
operator who accepts the trade-off can point at a single OpenAI-compatible
endpoint instead (a self-hosted vLLM, or a hosted provider with proper
no-training data terms). There is intentionally NO multi-provider "free-tier
ensemble": that would send citizen/government data to third parties and break
the sovereignty the project is built on.

Selection (env):
    LLM_BACKEND   = local | openai        (default: local)
    MODEL         = model name            (qwen2.5:7b-instruct | gpt-4o-mini | ...)
    OLLAMA_HOST   = http://localhost:11434           (local backend)
    LLM_BASE_URL  = https://api.openai.com/v1        (openai backend)
    LLM_API_KEY   = <key>                            (openai backend)
    LLM_FALLBACK  = 0 | 1   if 1, fall back to the OTHER backend on failure (default 0)

Standard library only. The agent loop uses the helpers here so backend
differences (tool-call ids, message shapes) stay contained.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

BACKEND = os.environ.get("LLM_BACKEND", "local").lower()
DEFAULT_MODEL = os.environ.get(
    "MODEL", "gpt-4o-mini" if BACKEND == "openai" else "qwen2.5:7b-instruct")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_FALLBACK = os.environ.get("LLM_FALLBACK", "0") == "1"

_warned = False


class LocalModelError(RuntimeError):
    pass


def describe() -> str:
    if BACKEND == "openai":
        return f"hosted (OpenAI-compatible) {DEFAULT_MODEL} @ {LLM_BASE_URL}"
    return f"local (Ollama) {DEFAULT_MODEL} @ {OLLAMA_HOST}"


def _egress_warning() -> None:
    global _warned
    if BACKEND == "openai" and not _warned:
        _warned = True
        print("⚠  LLM_BACKEND=openai: prompts (incl. data context) are sent to an "
              f"EXTERNAL service ({LLM_BASE_URL}). This is NOT sovereign. Ensure your "
              "provider's terms forbid training on your data.", file=sys.stderr)


# --------------------------------------------------------------------------- #
#  tool schema conversion (both backends use the OpenAI "function" shape)
# --------------------------------------------------------------------------- #
def _fn_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
    }} for t in tools]


def _post(url: str, body: dict, headers: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json", **headers},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LocalModelError(f"{url} {exc.code}: {exc.read().decode('utf-8','replace')}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LocalModelError(f"Cannot reach model backend at {url} ({exc})") from exc


# --------------------------------------------------------------------------- #
#  per-backend chat
# --------------------------------------------------------------------------- #
def _chat_ollama(messages, tools, model, temperature) -> dict:
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature}}
    if tools:
        body["tools"] = _fn_tools(tools)
    msg = _post(f"{OLLAMA_HOST}/api/chat", body, {}).get("message", {})
    msg.setdefault("role", "assistant")
    return msg


def _chat_openai(messages, tools, model, temperature) -> dict:
    body = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = _fn_tools(tools)
        body["tool_choice"] = "auto"
    headers = {"authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    data = _post(f"{LLM_BASE_URL}/chat/completions", body, headers)
    return (data.get("choices") or [{}])[0].get("message", {}) or {}


def chat(messages: list[dict], *, tools: list[dict] | None = None,
         model: str | None = None, temperature: float = 0.0) -> dict[str, Any]:
    """One chat turn. Returns the provider's assistant message (may hold tool_calls)."""
    _egress_warning()
    model = model or DEFAULT_MODEL
    primary = _chat_openai if BACKEND == "openai" else _chat_ollama
    other = _chat_ollama if BACKEND == "openai" else _chat_openai
    try:
        return primary(messages, tools, model, temperature)
    except LocalModelError:
        if LLM_FALLBACK:
            print("⚠  primary LLM backend failed; falling back to the other backend.",
                  file=sys.stderr)
            return other(messages, tools, model, temperature)
        raise


# --------------------------------------------------------------------------- #
#  uniform helpers used by the agent loop (hide backend message differences)
# --------------------------------------------------------------------------- #
def extract_tool_calls(msg: dict) -> list[dict]:
    """Return [{id, name, args(dict)}] from either backend's message."""
    out = []
    for i, c in enumerate(msg.get("tool_calls") or []):
        fn = c.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        out.append({"id": c.get("id") or f"call_{i}", "name": fn.get("name", ""), "args": args})
    return out


def assistant_message(msg: dict) -> dict:
    """The assistant message to append for round-tripping (kept in provider shape)."""
    m = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        m["tool_calls"] = msg["tool_calls"]
    return m


def tool_result(call_id: str, name: str, result: Any) -> dict:
    """A tool-result message. tool_call_id is required by OpenAI, ignored by Ollama."""
    content = json.dumps(result, default=str)[:12000]
    if BACKEND == "openai":
        return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}
    return {"role": "tool", "content": content}


def server_up() -> bool:
    """For local: is Ollama reachable? For openai: is it configured?"""
    if BACKEND == "openai":
        return bool(LLM_API_KEY) or "localhost" in LLM_BASE_URL or "127.0.0.1" in LLM_BASE_URL
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{OLLAMA_HOST}/api/tags"), timeout=5):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False
