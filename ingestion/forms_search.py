"""Form Finder search — two modes:

1. keyword  : SQLite FTS5 full-text search (fast, no LLM needed)
2. ai        : keyword search + LLM synonym/intent expansion (richer results)

Both return the same list-of-dicts shape so the API handler is identical.
"""
from __future__ import annotations

import re
from typing import Any

MAX_RESULTS = 50


# --- keyword search (FTS5) ----------------------------------------------------

def _safe_fts_query(query: str) -> str | None:
    """Convert a raw user query into a safe FTS5 MATCH expression.
    Returns None if there are no usable terms (empty after stripping noise)."""
    # extract only word characters — drops quotes, operators, punctuation
    words = re.findall(r"\w+", query)
    # FTS5 treats AND/OR/NOT (uppercase) as boolean operators — quote them
    # by lowercasing, which neutralises them as plain terms.
    words = [w.lower() for w in words if w]
    if not words:
        return None
    return " OR ".join(f"{w}*" for w in words)


def keyword_search(db, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Pure FTS5 search — no LLM required."""
    query = query.strip()
    if not query:
        return []

    fts_query = _safe_fts_query(query)
    if not fts_query:
        return []

    rows = db.fetchall(
        """SELECT f.id, f.title, f.description, f.url, f.department, f.category,
                  f.source_domain, f.last_scraped,
                  bm25(forms_fts) AS score
           FROM forms_fts
           JOIN forms f ON forms_fts.rowid = f.id
           WHERE forms_fts MATCH ?
           ORDER BY score
           LIMIT ?
        """,
        (fts_query, limit),
    )
    return [_row_to_dict(r) for r in rows]


# --- AI-expanded search -------------------------------------------------------

_EXPAND_PROMPT = """\
You are a local government form search assistant.
The citizen typed: "{query}"

List up to 10 short keyword phrases that expand their intent — synonyms,
related services, common misspellings, and NT/Darwin-specific terms.
Return ONLY a JSON array of strings, nothing else.
Example: ["rates payment", "council tax", "property levy"]
"""


def ai_search(db, query: str, llm_module, limit: int = MAX_RESULTS) -> dict:
    """LLM-expanded search. Returns {"results": [...], "expanded_terms": [...]}."""
    query = query.strip()
    if not query:
        return {"results": [], "expanded_terms": []}

    expanded: list[str] = []
    try:
        import json as _json
        prompt = _EXPAND_PROMPT.format(query=query)
        raw = llm_module.complete(prompt, max_tokens=300)
        # extract JSON array from response (LLM may wrap it in markdown)
        m = re.search(r"\[.*?\]", raw, re.S)
        if m:
            expanded = _json.loads(m.group(0))
    except Exception:
        pass  # fall back to keyword-only

    all_terms = [query] + (expanded or [])
    seen_ids: set[int] = set()
    all_results: list[dict] = []

    for term in all_terms:
        rows = keyword_search(db, term, limit=limit)
        for r in rows:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_results.append(r)
        if len(all_results) >= limit:
            break

    return {
        "results": all_results[:limit],
        "expanded_terms": expanded,
    }


# --- helpers ------------------------------------------------------------------

def _row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "title": r["title"],
        "description": r["description"] or "",
        "url": r["url"],
        "department": r["department"] or "",
        "category": r["category"] or "",
        "source_domain": r["source_domain"] or "",
        "last_scraped": r["last_scraped"] or "",
    }


def stats(db) -> dict:
    row = db.fetchone("SELECT COUNT(*) AS total FROM forms")
    total = row["total"] if row else 0
    dept_rows = db.fetchall(
        "SELECT department, COUNT(*) AS cnt FROM forms GROUP BY department ORDER BY cnt DESC LIMIT 20"
    )
    cats = db.fetchall(
        "SELECT category, COUNT(*) AS cnt FROM forms GROUP BY category ORDER BY cnt DESC LIMIT 20"
    )
    return {
        "total_forms": total,
        "by_department": [{"department": r["department"], "count": r["cnt"]} for r in dept_rows],
        "by_category": [{"category": r["category"], "count": r["cnt"]} for r in cats],
    }
