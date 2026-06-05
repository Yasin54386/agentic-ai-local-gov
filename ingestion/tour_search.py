"""Tour Guide search, review and stats helpers."""
from __future__ import annotations

import re
import sqlite3
import time


CATEGORIES = [
    ("beaches",       "Beaches",           "🏖"),
    ("waterfalls",    "Waterfalls",         "💦"),
    ("national_parks","National Parks",     "🌿"),
    ("gorges",        "Gorges",             "🏔"),
    ("hot_springs",   "Hot Springs",        "♨️"),
    ("markets",       "Markets",            "🛒"),
    ("camping",       "Camping",            "⛺"),
    ("fishing",       "Fishing",            "🎣"),
    ("cruises",       "Cruises",            "⛵"),
    ("wildlife",      "Wildlife",           "🦘"),
    ("cultural",      "Cultural & Aboriginal", "🪃"),
    ("hiking",        "Hiking",             "🥾"),
    ("islands",       "Islands",            "🏝"),
    ("food",          "Food & Dining",      "🍽"),
]

CATEGORY_LABELS = {k: (label, emoji) for k, label, emoji in CATEGORIES}


def _safe_fts(query: str) -> str | None:
    words = re.findall(r"\w+", query.lower())
    if not words:
        return None
    return " OR ".join(f"{w}*" for w in words[:8])


def _row(r: sqlite3.Row) -> dict:
    keys = r.keys()
    d = {k: r[k] for k in keys}
    # Enrich category display
    cat = d.get("category", "")
    info = CATEGORY_LABELS.get(cat)
    d["category_label"] = info[0] if info else cat.replace("_", " ").title()
    d["category_emoji"] = info[1] if info else "📍"
    # Map URL
    if d.get("lat") and d.get("lng"):
        d["maps_url"] = f"https://www.google.com/maps?q={d['lat']},{d['lng']}"
    else:
        d["maps_url"] = ""
    return d


def search(db: sqlite3.Connection, query: str, category: str = "",
           page: int = 1, limit: int = 12) -> dict:
    offset = (page - 1) * limit
    params: list = []
    results: list[dict] = []
    total = 0

    fts = _safe_fts(query) if query else None

    if fts:
        if category:
            sql = (
                "SELECT d.*, bm25(destinations_fts) AS score "
                "FROM destinations_fts f JOIN destinations d ON d.id = f.rowid "
                "WHERE destinations_fts MATCH ? AND d.category = ? "
                "ORDER BY score LIMIT ? OFFSET ?"
            )
            count_sql = (
                "SELECT COUNT(*) FROM destinations_fts f JOIN destinations d ON d.id = f.rowid "
                "WHERE destinations_fts MATCH ? AND d.category = ?"
            )
            params = [fts, category]
        else:
            sql = (
                "SELECT d.*, bm25(destinations_fts) AS score "
                "FROM destinations_fts f JOIN destinations d ON d.id = f.rowid "
                "WHERE destinations_fts MATCH ? "
                "ORDER BY score LIMIT ? OFFSET ?"
            )
            count_sql = (
                "SELECT COUNT(*) FROM destinations_fts f JOIN destinations d ON d.id = f.rowid "
                "WHERE destinations_fts MATCH ?"
            )
            params = [fts]
    else:
        if category:
            sql = "SELECT * FROM destinations WHERE category = ? ORDER BY name LIMIT ? OFFSET ?"
            count_sql = "SELECT COUNT(*) FROM destinations WHERE category = ?"
            params = [category]
        else:
            sql = "SELECT * FROM destinations ORDER BY name LIMIT ? OFFSET ?"
            count_sql = "SELECT COUNT(*) FROM destinations"
            params = []

    try:
        count_row = db.execute(count_sql, params).fetchone()
        total = count_row[0] if count_row else 0
        rows = db.execute(sql, params + [limit, offset]).fetchall()
        results = [_row(r) for r in rows]
    except sqlite3.OperationalError:
        results = []
        total = 0

    # Attach avg rating + review count to each result
    if results:
        ids = [r["id"] for r in results]
        placeholders = ",".join("?" * len(ids))
        rating_rows = db.execute(
            f"SELECT destination_id, ROUND(AVG(rating),1) AS avg_rating, COUNT(*) AS review_count "
            f"FROM destination_reviews WHERE destination_id IN ({placeholders}) "
            f"GROUP BY destination_id",
            ids,
        ).fetchall()
        rating_map = {r["destination_id"]: r for r in rating_rows}
        for r in results:
            info = rating_map.get(r["id"])
            r["avg_rating"]    = info["avg_rating"]    if info else None
            r["review_count"]  = info["review_count"]  if info else 0

    return {
        "results": results,
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),  # ceil division
        "limit": limit,
    }


def destination_detail(db: sqlite3.Connection, dest_id: int) -> dict | None:
    row = db.execute("SELECT * FROM destinations WHERE id = ?", (dest_id,)).fetchone()
    if not row:
        return None
    d = _row(row)
    # Attach rating summary
    ri = db.execute(
        "SELECT ROUND(AVG(rating),1) AS avg_rating, COUNT(*) AS review_count "
        "FROM destination_reviews WHERE destination_id = ?",
        (dest_id,),
    ).fetchone()
    d["avg_rating"]   = ri["avg_rating"]   if ri else None
    d["review_count"] = ri["review_count"] if ri else 0
    # Rating breakdown (1–5 star counts)
    breakdown = db.execute(
        "SELECT rating, COUNT(*) AS cnt FROM destination_reviews "
        "WHERE destination_id = ? GROUP BY rating ORDER BY rating DESC",
        (dest_id,),
    ).fetchall()
    d["rating_breakdown"] = [{"rating": r["rating"], "count": r["cnt"]} for r in breakdown]
    return d


def reviews(db: sqlite3.Connection, dest_id: int,
            page: int = 1, limit: int = 3) -> dict:
    offset = (page - 1) * limit
    total_row = db.execute(
        "SELECT COUNT(*) FROM destination_reviews WHERE destination_id = ?", (dest_id,)
    ).fetchone()
    total = total_row[0] if total_row else 0
    rows = db.execute(
        "SELECT id, reviewer_name, rating, review_text, created_at "
        "FROM destination_reviews WHERE destination_id = ? "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (dest_id, limit, offset),
    ).fetchall()
    return {
        "reviews": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }


def add_review(db: sqlite3.Connection, dest_id: int, name: str,
               rating: int, text: str) -> dict:
    name = (name or "Anonymous").strip()[:80]
    text = text.strip()[:2000]
    rating = max(1, min(5, int(rating)))
    db.execute(
        "INSERT INTO destination_reviews (destination_id, reviewer_name, rating, review_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (dest_id, name, rating, text, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    db.commit()
    return {"ok": True}


def stats(db: sqlite3.Connection) -> dict:
    total_row = db.execute("SELECT COUNT(*) FROM destinations").fetchone()
    total = total_row[0] if total_row else 0
    cats = db.execute(
        "SELECT category, COUNT(*) AS cnt FROM destinations GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    return {
        "total": total,
        "by_category": [{"category": r["category"], "count": r["cnt"]} for r in cats],
        "categories": CATEGORIES,
    }
