"""Tiny, dependency-free HTTP helper with timeouts and retry/backoff.

Stdlib only (urllib). Used by every source adapter so retry behaviour and the
User-Agent are consistent across the whole harvester.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "nt-localgov-datafabric-harvester/0.1 (independent research; Darwin NT)"
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 4
BACKOFF_BASE = 2  # seconds: 2, 4, 8, 16


def _request(url: str, *, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_err = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE ** (attempt + 1))
    raise RuntimeError(f"GET failed after {MAX_RETRIES} attempts: {url}\n  {last_err}")


def get_json(url: str, *, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """GET a URL and parse the response as JSON."""
    raw = _request(url, params=params, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


def get_bytes(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """GET a URL and return raw bytes (for downloading data files)."""
    return _request(url, timeout=timeout)
