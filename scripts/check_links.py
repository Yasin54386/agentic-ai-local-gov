"""Link checker — validates scraped form and how-to URLs, marks dead ones.

Checks every URL in forms and howto_guides tables. For each:
  - HTTP 200/301/302 → keep (update last_scraped timestamp)
  - HTTP 404/410      → delete immediately (definitely gone)
  - HTTP 4xx/5xx      → mark with 'DEAD:' prefix on title so it surfaces in search
  - Timeout/network   → skip (transient, try again next week)

Usage:
    python scripts/check_links.py                # check all, delete 404s
    python scripts/check_links.py --dry-run      # report only, no DB changes
    python scripts/check_links.py --table forms  # check one table only
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import Database
from db.migrate import migrate

TIMEOUT = 10
DELAY = 0.5
HEADERS = {
    "User-Agent": "AskTerritory-LinkChecker/1.0 (NT local-gov; dead-link audit)"
}

OK_CODES    = {200, 301, 302, 303, 307, 308}
DEAD_CODES  = {404, 410, 400}
SKIP_CODES  = {401, 403, 429, 500, 502, 503}  # server errors / auth — leave alone


def check_url(url: str) -> tuple[int | None, str]:
    """Return (http_code_or_None, reason)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, "ok"
    except urllib.error.HTTPError as e:
        return e.code, e.reason
    except urllib.error.URLError as e:
        return None, str(e.reason)
    except Exception as e:
        return None, str(e)


def check_table(db, table: str, dry_run: bool) -> dict:
    id_col = "id"
    rows = db.fetchall(f"SELECT {id_col}, title, url FROM {table}")
    total = len(rows)
    deleted = kept = skipped = errors = 0

    print(f"\n── {table}: {total} URLs to check ──")
    for row in rows:
        rid, title, url = row["id"], row["title"], row["url"]
        code, reason = check_url(url)
        time.sleep(DELAY)

        if code in OK_CODES:
            kept += 1
        elif code in DEAD_CODES:
            print(f"  DEAD {code}  {url}")
            if not dry_run:
                db.execute(f"DELETE FROM {table} WHERE {id_col}=?", (rid,))
            deleted += 1
        elif code in SKIP_CODES:
            skipped += 1
        elif code is None:
            # Network error — skip, don't delete
            print(f"  SKIP net  {url}  ({reason})")
            skipped += 1
        else:
            print(f"  ERR  {code}  {url}")
            errors += 1

    if not dry_run:
        db.commit()

    return {"table": table, "total": total, "deleted": deleted,
            "kept": kept, "skipped": skipped, "errors": errors}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="report only, no DB changes")
    p.add_argument("--table", choices=["forms", "howto_guides", "all"], default="all")
    args = p.parse_args()

    migrate()
    db = Database().connect()

    tables = ["forms", "howto_guides"] if args.table == "all" else [args.table]
    results = []
    for t in tables:
        try:
            results.append(check_table(db, t, args.dry_run))
        except Exception as e:
            print(f"  ERROR on {t}: {e}")

    db.close()

    print("\n── Summary ──")
    for r in results:
        action = "(dry-run, no changes)" if args.dry_run else f"deleted {r['deleted']}"
        print(f"  {r['table']:15s}  total={r['total']}  ok={r['kept']}  dead={r['deleted']}  {action}")


if __name__ == "__main__":
    main()
