"""Standalone scraper runner — use for initial seed and scheduled refreshes.

    python scripts/scrape_forms.py            # quick scrape
    python scripts/scrape_forms.py --enrich   # slower deep scrape (fetches each form page for title/desc)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import Database
from db.migrate import migrate
from ingestion.forms_scraper import run_scrape


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--enrich", action="store_true", help="fetch each form page to get richer titles/descriptions (slow)")
    args = p.parse_args()

    print("Running migrations…")
    migrate()

    print("Scraping NT government forms…")
    db = Database().connect()
    try:
        result = run_scrape(db, enrich=args.enrich)
    finally:
        db.close()

    print(f"\nDone. Scraped: {result['scraped']}  Upserted: {result['upserted']}")


if __name__ == "__main__":
    main()
