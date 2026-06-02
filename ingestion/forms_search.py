"""Form Finder search — keyword (FTS5), fuzzy fallback, AI expansion, analytics."""
from __future__ import annotations

import re
from datetime import date

MAX_RESULTS = 50

# ── FTS5 query builder ────────────────────────────────────────────────────────

def _safe_fts_query(query: str) -> str | None:
    words = re.findall(r"\w+", query)
    words = [w.lower() for w in words if w]   # lowercase neutralises AND/OR/NOT
    if not words:
        return None
    return " OR ".join(f"{w}*" for w in words)


# ── Levenshtein (pure stdlib) ─────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    if len(a) > len(b):
        a, b = b, a
    row = list(range(len(a) + 1))
    for cb in b:
        new = [row[0] + 1]
        for i, ca in enumerate(a):
            new.append(min(row[i + 1] + 1, new[i] + 1, row[i] + (ca != cb)))
        row = new
    return row[-1]


def _vocab(db) -> set[str]:
    """Return the set of all lowercase words present in form titles."""
    rows = db.fetchall("SELECT title FROM forms")
    words: set[str] = set()
    for r in rows:
        for w in re.findall(r"[a-z]{3,}", r["title"].lower()):
            words.add(w)
    return words


# ── Search functions ──────────────────────────────────────────────────────────

def keyword_search(db, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """FTS5 search — fast, no LLM required."""
    query = query.strip()
    if not query:
        return []
    fts_query = _safe_fts_query(query)
    if not fts_query:
        return []
    rows = db.fetchall(
        """SELECT f.id, f.title, f.description, f.url, f.department, f.category,
                  f.source_domain, f.last_scraped, f.status, f.fee,
                  f.requirements_json, bm25(forms_fts) AS score
           FROM forms_fts
           JOIN forms f ON forms_fts.rowid = f.id
           WHERE forms_fts MATCH ?
           ORDER BY score
           LIMIT ?""",
        (fts_query, limit),
    )
    return [_row(r) for r in rows]


def fuzzy_search(db, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Typo-tolerant fallback: LIKE search, then Levenshtein ranking.
    Called when keyword_search returns 0 results."""
    query = query.strip()
    if not query:
        return []

    # 1. LIKE search — catches partial matches and common typos
    words = re.findall(r"\w{3,}", query.lower())
    if not words:
        return []

    conditions = " AND ".join(["LOWER(title) LIKE ?"] * len(words))
    params = tuple(f"%{w}%" for w in words) + (limit,)
    rows = db.fetchall(
        f"SELECT id, title, description, url, department, category, "
        f"source_domain, last_scraped, status, fee, requirements_json "
        f"FROM forms WHERE {conditions} LIMIT ?",
        params,
    )
    if rows:
        return [_row(r) for r in rows]

    # 2. Levenshtein fallback — find closest title words
    vocab = _vocab(db)
    query_words = re.findall(r"[a-z]{3,}", query.lower())
    scored: list[tuple[int, str]] = []
    for word in query_words:
        for v in vocab:
            d = _levenshtein(word, v)
            if d <= max(1, len(word) // 4):    # allow 1 edit per 4 chars
                scored.append((d, v))
    if not scored:
        return []
    scored.sort()
    corrected = " ".join(w for _, w in scored[:4])
    return keyword_search(db, corrected, limit)


def did_you_mean(db, query: str) -> str | None:
    """Return a corrected query string when the original returned 0 results."""
    query = query.strip()
    if not query:
        return None
    words = re.findall(r"[a-z]{3,}", query.lower())
    if not words:
        return None
    vocab = _vocab(db)
    suggestions: list[str] = []
    for word in words:
        if word in vocab:
            suggestions.append(word)
            continue
        best = min(vocab, key=lambda v: _levenshtein(word, v), default=None)
        if best and _levenshtein(word, best) <= max(2, len(word) // 3):
            suggestions.append(best)
        else:
            suggestions.append(word)
    corrected = " ".join(suggestions)
    return corrected if corrected != query.lower() else None


def ai_search(db, query: str, llm_module, limit: int = MAX_RESULTS) -> dict:
    """LLM synonym expansion + keyword search."""
    query = query.strip()
    if not query:
        return {"results": [], "expanded_terms": []}
    expanded: list[str] = []
    try:
        import json as _json
        prompt = (
            f'You are an NT local government forms assistant. '
            f'The citizen typed: "{query}"\n'
            f'List up to 10 short keyword phrases that expand their intent — '
            f'synonyms, related NT services, official names, common misspellings.\n'
            f'Return ONLY a JSON array of strings, nothing else.'
        )
        raw = llm_module.complete(prompt, max_tokens=300)
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


def related_howto(db, category: str, form_id: int, limit: int = 3) -> list[dict]:
    """Return how-to guides related to a form by category or keyword match."""
    rows = db.fetchall(
        "SELECT id, title, links_json FROM howto_guides "
        "WHERE category = ? AND id != ? LIMIT ?",
        (category, form_id, limit),
    )
    if not rows:
        rows = db.fetchall(
            "SELECT id, title, links_json FROM howto_guides LIMIT ?", (limit,)
        )
    return [{"id": r["id"], "title": r["title"]} for r in rows]


# ── Search logging (anonymous) ────────────────────────────────────────────────

def log_search(db, query: str, result_count: int, mode: str = "keyword") -> None:
    """Log a search query anonymously (query text + day only, no IP, no time)."""
    try:
        db.execute(
            "INSERT INTO search_logs (query, source, result_count, mode, day) "
            "VALUES (?, 'forms', ?, ?, ?)",
            (query.strip()[:200], result_count, mode, date.today().isoformat()),
        )
        db.commit()
    except Exception:
        pass


def popular_searches(db, days: int = 7, limit: int = 10) -> list[dict]:
    """Return top search queries for the last N days."""
    from datetime import timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = db.fetchall(
        """SELECT query, COUNT(*) AS cnt, AVG(result_count) AS avg_results
           FROM search_logs
           WHERE source='forms' AND day >= ?
           GROUP BY LOWER(query)
           ORDER BY cnt DESC
           LIMIT ?""",
        (since, limit),
    )
    return [{"query": r["query"], "count": r["cnt"],
             "avg_results": round(r["avg_results"] or 0)} for r in rows]


# ── Stats ─────────────────────────────────────────────────────────────────────

def stats(db) -> dict:
    row = db.fetchone("SELECT COUNT(*) AS total FROM forms")
    total = row["total"] if row else 0
    dept_rows = db.fetchall(
        "SELECT department, COUNT(*) AS cnt FROM forms "
        "GROUP BY department ORDER BY cnt DESC LIMIT 20"
    )
    cats = db.fetchall(
        "SELECT category, COUNT(*) AS cnt FROM forms "
        "GROUP BY category ORDER BY cnt DESC LIMIT 20"
    )
    return {
        "total_forms": total,
        "by_department": [{"department": r["department"], "count": r["cnt"]} for r in dept_rows],
        "by_category":   [{"category":   r["category"],   "count": r["cnt"]} for r in cats],
    }


# ── Row deserialiser ──────────────────────────────────────────────────────────

def _row(r) -> dict:
    import json
    try:
        reqs = json.loads(r["requirements_json"] or "[]")
    except Exception:
        reqs = []
    return {
        "id":           r["id"],
        "title":        r["title"],
        "description":  r["description"] or "",
        "url":          r["url"],
        "department":   r["department"] or "",
        "category":     r["category"] or "",
        "source_domain":r["source_domain"] or "",
        "last_scraped": r["last_scraped"] or "",
        "status":       r["status"] if "status" in r.keys() else "active",
        "fee":          r["fee"] if "fee" in r.keys() else "",
        "requirements": reqs,
    }
