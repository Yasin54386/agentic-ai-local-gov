#!/usr/bin/env python3
"""
Monthly freshness checker for How-To Hub guides.

Fetches the live HTML for each guide's first official link, compares it to the
stored summary/steps via the AI model, and flags guides that may have changed.

Usage:
    python scripts/check_freshness.py [--limit N] [--dry-run]

Flags stale guides by printing their title and URL. Does NOT auto-update — a
human reviews and re-runs the scraper for flagged URLs.
"""

import argparse
import http.client
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

DB_PATH  = os.path.join(os.path.dirname(__file__), '..', 'db', 'askterritory.db')
OLLAMA   = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
MODEL    = os.environ.get('MODEL', 'qwen2.5:7b-instruct')
DELAY    = 1.2   # seconds between HTTP requests


def fetch_text(url: str, timeout: int = 10) -> str:
    """Return plain text content of a URL (strips HTML tags)."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AskTerritory-FreshnessBot/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(65536).decode('utf-8', errors='replace')
        # Strip tags, collapse whitespace
        text = re.sub(r'<[^>]+>', ' ', raw)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000]
    except Exception as e:
        return f'[fetch error: {e}]'


def ask_llm(prompt: str) -> str:
    parsed = urllib.parse.urlparse(OLLAMA)
    host   = parsed.hostname or 'localhost'
    port   = parsed.port or 11434
    body   = json.dumps({'model': MODEL, 'prompt': prompt, 'stream': False}).encode()
    conn   = http.client.HTTPConnection(host, port, timeout=30)
    try:
        conn.request('POST', '/api/generate', body=body,
                     headers={'Content-Type': 'application/json'})
        resp = conn.getresponse()
        data = json.loads(resp.read())
        return data.get('response', '').strip()
    except Exception as e:
        return f'[llm error: {e}]'
    finally:
        conn.close()


def load_guides(limit: int) -> list[dict]:
    db = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        'SELECT id, title, summary, steps_json, links_json FROM howto_guides '
        'WHERE links_json != "[]" ORDER BY RANDOM() LIMIT ?', (limit,)
    ).fetchall()
    db.close()
    guides = []
    for r in rows:
        links = json.loads(r['links_json'] or '[]')
        if links:
            guides.append({'id': r['id'], 'title': r['title'],
                           'summary': r['summary'] or '', 'url': links[0].get('url','')})
    return guides


def check_guide(guide: dict) -> bool:
    """Return True if guide appears stale."""
    live = fetch_text(guide['url'])
    if live.startswith('[fetch error'):
        print(f"  SKIP (fetch error): {guide['title']}")
        return False

    prompt = (
        f"You are checking if an NT government web page has changed significantly.\n\n"
        f"STORED SUMMARY: {guide['summary'][:500]}\n\n"
        f"LIVE PAGE EXCERPT: {live[:2000]}\n\n"
        f"Has the page content changed significantly from the stored summary? "
        f"Reply with only YES or NO."
    )
    answer = ask_llm(prompt).upper()
    return answer.startswith('YES')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=50, help='Number of guides to check (default 50)')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be checked without calling LLM')
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f'DB not found: {DB_PATH}')
        sys.exit(1)

    guides = load_guides(args.limit)
    print(f'Checking freshness of {len(guides)} guides…\n')

    stale = []
    for i, g in enumerate(guides, 1):
        print(f'[{i}/{len(guides)}] {g["title"]}')
        if args.dry_run:
            print(f'  DRY RUN — would fetch: {g["url"]}')
            continue
        if check_guide(g):
            print(f'  *** STALE — {g["url"]}')
            stale.append(g)
        else:
            print(f'  ok')
        time.sleep(DELAY)

    print(f'\n--- Freshness check complete ---')
    print(f'Checked: {len(guides)}  Stale: {len(stale)}')
    if stale:
        print('\nStale guides to re-scrape:')
        for g in stale:
            print(f'  {g["title"]}')
            print(f'  {g["url"]}')


if __name__ == '__main__':
    main()
