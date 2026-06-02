"""How-To search — keyword (FTS5), fuzzy fallback, AI expansion, analytics."""
from __future__ import annotations

import json
import re
from datetime import date

MAX_RESULTS = 50

# ── FTS5 query builder ────────────────────────────────────────────────────────

def _safe_fts_query(query: str) -> str | None:
    words = re.findall(r"\w+", query)
    words = [w.lower() for w in words if w]
    if not words:
        return None
    return " OR ".join(f"{w}*" for w in words)


# ── Levenshtein ───────────────────────────────────────────────────────────────

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
    rows = db.fetchall("SELECT title FROM howto_guides")
    words: set[str] = set()
    for r in rows:
        for w in re.findall(r"[a-z]{3,}", r["title"].lower()):
            words.add(w)
    return words


# ── Search functions ──────────────────────────────────────────────────────────

def keyword_search(db, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    fts_query = _safe_fts_query(query)
    if not fts_query:
        return []
    rows = db.fetchall(
        """SELECT g.id, g.title, g.summary, g.steps_json, g.links_json,
                  g.category, g.updated_at, g.fee, g.processing_time,
                  g.indigenous_note, g.verified_by,
                  bm25(howto_fts) AS score
           FROM howto_fts
           JOIN howto_guides g ON howto_fts.rowid = g.id
           WHERE howto_fts MATCH ?
           ORDER BY score
           LIMIT ?""",
        (fts_query, limit),
    )
    return [_row(r) for r in rows]


def fuzzy_search(db, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Typo-tolerant fallback when FTS5 returns nothing."""
    query = query.strip()
    if not query:
        return []
    words = re.findall(r"\w{3,}", query.lower())
    if not words:
        return []
    conditions = " AND ".join(["LOWER(title) LIKE ?"] * len(words))
    params = tuple(f"%{w}%" for w in words) + (limit,)
    rows = db.fetchall(
        f"SELECT id, title, summary, steps_json, links_json, category, "
        f"updated_at, fee, processing_time, indigenous_note, verified_by "
        f"FROM howto_guides WHERE {conditions} LIMIT ?",
        params,
    )
    if rows:
        return [_row(r) for r in rows]
    # Levenshtein fallback
    vocab = _vocab(db)
    query_words = re.findall(r"[a-z]{3,}", query.lower())
    scored: list[tuple[int, str]] = []
    for word in query_words:
        for v in vocab:
            d = _levenshtein(word, v)
            if d <= max(1, len(word) // 4):
                scored.append((d, v))
    if not scored:
        return []
    scored.sort()
    corrected = " ".join(w for _, w in scored[:4])
    return keyword_search(db, corrected, limit)


def did_you_mean(db, query: str) -> str | None:
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
    query = query.strip()
    if not query:
        return {"results": [], "expanded_terms": []}
    expanded: list[str] = []
    try:
        prompt = (
            f'You are an NT local government services assistant. '
            f'The citizen typed: "{query}"\n'
            f'List up to 12 short keyword phrases expanding their intent — '
            f'synonyms, related NT services, official names, common misspellings, '
            f'and Aboriginal community context where relevant.\n'
            f'Return ONLY a JSON array of strings.'
        )
        raw = llm_module.complete(prompt, max_tokens=400)
        m = re.search(r"\[.*?\]", raw, re.S)
        if m:
            expanded = json.loads(m.group(0))
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


def related_forms(db, category: str, guide_id: int, limit: int = 3) -> list[dict]:
    """Forms related to a how-to guide by category."""
    rows = db.fetchall(
        "SELECT id, title, url, fee FROM forms WHERE category = ? LIMIT ?",
        (category, limit),
    )
    if not rows:
        rows = db.fetchall("SELECT id, title, url, fee FROM forms LIMIT ?", (limit,))
    return [{"id": r["id"], "title": r["title"],
             "url": r["url"], "fee": r["fee"] or ""} for r in rows]


# ── Search logging ────────────────────────────────────────────────────────────

def log_search(db, query: str, result_count: int, mode: str = "keyword") -> None:
    try:
        db.execute(
            "INSERT INTO search_logs (query, source, result_count, mode, day) "
            "VALUES (?, 'howto', ?, ?, ?)",
            (query.strip()[:200], result_count, mode, date.today().isoformat()),
        )
        db.commit()
    except Exception:
        pass


def popular_searches(db, days: int = 7, limit: int = 10) -> list[dict]:
    from datetime import timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = db.fetchall(
        """SELECT query, COUNT(*) AS cnt, AVG(result_count) AS avg_results
           FROM search_logs
           WHERE source='howto' AND day >= ?
           GROUP BY LOWER(query)
           ORDER BY cnt DESC
           LIMIT ?""",
        (since, limit),
    )
    return [{"query": r["query"], "count": r["cnt"],
             "avg_results": round(r["avg_results"] or 0)} for r in rows]


# ── Stats ─────────────────────────────────────────────────────────────────────

def stats(db) -> dict:
    row = db.fetchone("SELECT COUNT(*) AS total FROM howto_guides")
    total = row["total"] if row else 0
    cats = db.fetchall(
        "SELECT category, COUNT(*) AS cnt FROM howto_guides "
        "GROUP BY category ORDER BY cnt DESC LIMIT 20"
    )
    return {
        "total_guides": total,
        "by_category": [{"category": r["category"], "count": r["cnt"]} for r in cats],
    }


# ── Row deserialiser ──────────────────────────────────────────────────────────

def _row(r) -> dict:
    try:
        links = json.loads(r["links_json"] or "[]")
    except Exception:
        links = []
    try:
        steps = json.loads(r["steps_json"] or "[]")
    except Exception:
        steps = []
    keys = r.keys() if hasattr(r, "keys") else []
    return {
        "id":              r["id"],
        "title":           r["title"],
        "summary":         r["summary"] or "",
        "steps":           steps,
        "links":           links,
        "category":        r["category"] or "",
        "updated_at":      r["updated_at"] or "",
        "fee":             r["fee"] if "fee" in keys else "",
        "processing_time": r["processing_time"] if "processing_time" in keys else "",
        "indigenous_note": r["indigenous_note"] if "indigenous_note" in keys else "",
        "verified_by":     r["verified_by"] if "verified_by" in keys else "",
    }
