#!/usr/bin/env python3
"""
Event-driven sitemap watcher for Ask Territory.

Fetches NT Government sitemap.xml URLs, diffs against a cached version,
and triggers re-scraping for changed/new URLs.

Usage:
    python scripts/watch_sitemaps.py [--dry-run] [--cache-dir /path/to/cache]

Run via cron (e.g. every 6 hours) or as a one-shot job triggered by CI.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

SITEMAPS = [
    'https://nt.gov.au/sitemap.xml',
    'https://www.darwin.nt.gov.au/sitemap.xml',
    'https://pfes.nt.gov.au/sitemap.xml',
    'https://transport.nt.gov.au/sitemap.xml',
    'https://worksafe.nt.gov.au/sitemap.xml',
    'https://business.nt.gov.au/sitemap.xml',
    'https://health.nt.gov.au/sitemap.xml',
]

DEFAULT_CACHE = os.path.join(os.path.dirname(__file__), '..', 'db', 'sitemap_cache')
DELAY = 0.8


def fetch(url: str, timeout: int = 15) -> str:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AskTerritory-SitemapBot/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(2 * 1024 * 1024).decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [fetch error] {url}: {e}')
        return ''


def extract_urls(xml: str) -> set[str]:
    return set(re.findall(r'<loc>\s*(https?://[^\s<]+)\s*</loc>', xml))


def cache_path(cache_dir: str, sitemap_url: str) -> str:
    h = hashlib.md5(sitemap_url.encode()).hexdigest()[:12]
    return os.path.join(cache_dir, f'sitemap_{h}.json')


def load_cache(path: str) -> dict[str, str]:
    """Returns {url: content_hash}."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(path: str, data: dict[str, str]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def page_hash(url: str) -> str:
    content = fetch(url)
    return hashlib.sha256(content.encode()).hexdigest()[:16] if content else ''


def trigger_rescrape(urls: list[str], dry_run: bool):
    """For each changed URL, fetch its page and upsert into the DB via scraper logic."""
    if not urls:
        return
    print(f'\n{"[DRY RUN] " if dry_run else ""}Re-scraping {len(urls)} changed URLs…')

    # Add changed URLs as seeds into a temp file the scrapers can consume
    seed_file = os.path.join(os.path.dirname(__file__), '..', 'db', 'rescrape_seeds.json')
    existing = []
    if os.path.exists(seed_file):
        try:
            with open(seed_file) as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.extend(u for u in urls if u not in existing)
    if not dry_run:
        os.makedirs(os.path.dirname(seed_file), exist_ok=True)
        with open(seed_file, 'w') as f:
            json.dump(existing, f, indent=2)
        print(f'  Wrote {len(existing)} URLs to {seed_file}')
        print('  Run: python ingestion/scrape_forms.py or scrape_howto.py with --seeds flag to consume.')
    else:
        for u in urls[:10]:
            print(f'  {u}')
        if len(urls) > 10:
            print(f'  … and {len(urls)-10} more')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--cache-dir', default=DEFAULT_CACHE)
    parser.add_argument('--deep', action='store_true',
                        help='Also hash page content (slower, detects content changes not just new URLs)')
    args = parser.parse_args()

    os.makedirs(args.cache_dir, exist_ok=True)
    all_changed: list[str] = []

    for sitemap_url in SITEMAPS:
        print(f'\nChecking: {sitemap_url}')
        xml = fetch(sitemap_url)
        if not xml:
            continue

        urls = extract_urls(xml)
        print(f'  Found {len(urls)} URLs')

        cp = cache_path(args.cache_dir, sitemap_url)
        cache = load_cache(cp)

        new_urls   = urls - set(cache.keys())
        known_urls = urls & set(cache.keys())

        changed: list[str] = list(new_urls)
        print(f'  New URLs: {len(new_urls)}')

        if args.deep:
            print(f'  Deep checking {len(known_urls)} known URLs…')
            for url in known_urls:
                h = page_hash(url)
                if h and h != cache.get(url, ''):
                    changed.append(url)
                time.sleep(DELAY)
            print(f'  Content changes: {len(changed) - len(new_urls)}')

        # Update cache
        if not args.dry_run:
            for url in urls:
                cache[url] = cache.get(url, '')  # placeholder; deep fills it
            save_cache(cp, cache)

        all_changed.extend(changed)

    print(f'\nTotal changed/new URLs: {len(all_changed)}')
    trigger_rescrape(all_changed, args.dry_run)

    print('\nDone.')
    return 0 if not all_changed else 2  # exit 2 = changes found (useful in CI)


if __name__ == '__main__':
    sys.exit(main())
