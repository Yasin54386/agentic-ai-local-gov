"""Standalone how-to scraper — initial seed and scheduled refreshes.

    python scripts/scrape_howto.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import Database
from db.migrate import migrate
from ingestion.howto_scraper import run_scrape


def main():
    print("Running migrations…")
    migrate()
    print("Scraping NT government how-to guides…")
    db = Database().connect()
    try:
        result = run_scrape(db)
    finally:
        db.close()
    print(f"\nDone. Scraped: {result['scraped']}  Upserted: {result['upserted']}")


if __name__ == "__main__":
    main()
