"""Self-hosted model client — talks to a LOCAL Ollama server. Standard library only.

No external API, no SDK, no API key. Points at http://localhost:11434 by default
(override with OLLAMA_HOST). The model is Qwen2.5-7B-Instruct by default
(override with MODEL) — Apache-2.0 licensed, runs entirely on your own server.

Ollama's /api/chat endpoint supports function/tool calling for tool-capable
models (Qwen2.5 included), which is what drives the agent loop in agent.py.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("MODEL", "qwen2.5:7b-instruct")
CHAT_URL = f"{OLLAMA_HOST}/api/chat"
TAGS_URL = f"{OLLAMA_HOST}/api/tags"


class LocalModelError(RuntimeError):
    pass


def server_up() -> bool:
    """True if a local Ollama server is reachable."""
    try:
        req = urllib.request.Request(TAGS_URL)
        with urllib.request.urlopen(req, timeout=5):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


def to_ollama_tools(tools: list[dict]) -> list[dict]:
    """Convert our plain JSON-Schema tool defs to Ollama's function-call shape."""
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


def chat(messages: list[dict], *, tools: list[dict] | None = None,
         model: str = DEFAULT_MODEL, temperature: float = 0.0) -> dict[str, Any]:
    """Single non-streaming chat turn against the local model.

    Returns the response `message` dict, which may contain `tool_calls`.
    """
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if tools:
        body["tools"] = to_ollama_tools(tools)
    req = urllib.request.Request(
        CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise LocalModelError(f"Ollama {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LocalModelError(
            f"Cannot reach local model server at {OLLAMA_HOST}. "
            f"Is Ollama running? ({exc})"
        ) from exc
    return payload.get("message", {})
