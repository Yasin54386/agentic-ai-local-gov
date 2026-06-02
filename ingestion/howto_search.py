"""How-To search — keyword (FTS5) and AI-expanded modes."""
from __future__ import annotations

import re

MAX_RESULTS = 50

_EXPAND_PROMPT = """\
You are an NT local government services assistant.
The citizen typed: "{query}"

List up to 12 short keyword phrases that expand their intent — synonyms,
related NT services, official names, common misspellings, and Aboriginal
community context where relevant.
Return ONLY a JSON array of strings, nothing else.
Example: ["ochre card", "working with children check", "WWCC NT", "child protection clearance"]
"""


def _safe_fts_query(query: str) -> str | None:
    words = re.findall(r"\w+", query)
    words = [w.lower() for w in words if w]  # lowercase neutralises FTS5 AND/OR/NOT operators
    if not words:
        return None
    return " OR ".join(f"{w}*" for w in words)


def keyword_search(db, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    fts_query = _safe_fts_query(query)
    if not fts_query:
        return []
    rows = db.fetchall(
        """SELECT g.id, g.title, g.summary, g.steps_json, g.links_json,
                  g.category, g.updated_at,
                  bm25(howto_fts) AS score
           FROM howto_fts
           JOIN howto_guides g ON howto_fts.rowid = g.id
           WHERE howto_fts MATCH ?
           ORDER BY score
           LIMIT ?
        """,
        (fts_query, limit),
    )
    return [_row(r) for r in rows]


def ai_search(db, query: str, llm_module, limit: int = MAX_RESULTS) -> dict:
    query = query.strip()
    if not query:
        return {"results": [], "expanded_terms": []}

    expanded: list[str] = []
    try:
        import json as _json
        prompt = _EXPAND_PROMPT.format(query=query)
        raw = llm_module.complete(prompt, max_tokens=400)
        m = re.search(r"\[.*?\]", raw, re.S)
        if m:
            expanded = _json.loads(m.group(0))
    except Exception:
        pass

    seen: set[int] = set()
    all_results: list[dict] = []
    for term in [query] + (expanded or []):
        for r in keyword_search(db, term, limit=limit):
            if r["id"] not in seen:
                seen.add(r["id"])
                all_results.append(r)
        if len(all_results) >= limit:
            break

    return {"results": all_results[:limit], "expanded_terms": expanded}


def stats(db) -> dict:
    row = db.fetchone("SELECT COUNT(*) AS total FROM howto_guides")
    total = row["total"] if row else 0
    cats = db.fetchall(
        "SELECT category, COUNT(*) AS cnt FROM howto_guides GROUP BY category ORDER BY cnt DESC LIMIT 20"
    )
    depts = db.fetchall(
        "SELECT tags, COUNT(*) AS cnt FROM howto_guides GROUP BY tags ORDER BY cnt DESC LIMIT 5"
    )
    return {
        "total_guides": total,
        "by_category": [{"category": r["category"], "count": r["cnt"]} for r in cats],
    }


def _row(r) -> dict:
    import json
    try:
        links = json.loads(r["links_json"] or "[]")
    except Exception:
        links = []
    try:
        steps = json.loads(r["steps_json"] or "[]")
    except Exception:
        steps = []
    return {
        "id": r["id"],
        "title": r["title"],
        "summary": r["summary"] or "",
        "steps": steps,
        "links": links,
        "category": r["category"] or "",
        "updated_at": r["updated_at"] or "",
    }
