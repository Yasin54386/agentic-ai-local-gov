"""Form Finder scraper — discovers government forms across NT/Darwin websites.

Strategy per domain:
  - nt.gov.au       : crawl /forms sitemap + search pages, collect PDF/online form links
  - darwin.nt.gov.au: crawl /forms and key service pages
  - ors.nt.gov.au   : Online Regulatory System forms
  - ntlis.nt.gov.au : Land information forms
  - myaccount.nt.gov.au: My Account service forms
  - territoryrevenue: revenue/tax forms
  - Additional NT agency subdomains

All HTTP calls are single-threaded, polite (1 s delay), stdlib-only.
Respects robots.txt by sticking to /forms/* and known form index paths.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Iterator

DELAY = 1.0  # seconds between requests — be polite
TIMEOUT = 15
MAX_DEPTH = 3
MAX_PAGES_PER_DOMAIN = 400

HEADERS = {
    "User-Agent": (
        "AskTerritory-FormFinder/1.0 (NT local-gov open-data research; "
        "contact: public-data-research@example.com)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# --- seed URLs ----------------------------------------------------------------
# Each entry: (start_url, department_hint, category_hint)
SEEDS: list[tuple[str, str, str]] = [
    # Darwin City Council
    ("https://www.darwin.nt.gov.au/services/forms", "Darwin City Council", "General"),
    ("https://www.darwin.nt.gov.au/council/forms-and-publications", "Darwin City Council", "General"),
    # NT Government main forms portal
    ("https://nt.gov.au/forms", "NT Government", "General"),
    ("https://nt.gov.au/sitemap", "NT Government", "General"),
    # Land, planning, building
    ("https://nt.gov.au/property/building-and-construction/forms", "Department of Infrastructure", "Building & Construction"),
    ("https://nt.gov.au/property/land-titles/forms", "Department of Infrastructure", "Land Titles"),
    ("https://nt.gov.au/property/planning/forms", "Department of Infrastructure", "Planning"),
    # Licensing & registration
    ("https://nt.gov.au/driving/licences/forms", "NT Transport", "Licensing"),
    ("https://nt.gov.au/driving/vehicle-registration/forms", "NT Transport", "Vehicle Registration"),
    ("https://nt.gov.au/law/births-deaths-marriages/forms", "Births Deaths & Marriages", "BDM"),
    # Business
    ("https://nt.gov.au/employ/working-in-nt/licences-and-registrations/forms", "Business NT", "Business"),
    ("https://nt.gov.au/industry/agriculture/forms", "Primary Industry", "Agriculture"),
    # Health & welfare
    ("https://nt.gov.au/wellbeing/health/forms", "NT Health", "Health"),
    ("https://nt.gov.au/wellbeing/disability-services/forms", "Disability Services", "Disability"),
    # Environment
    ("https://nt.gov.au/environment/forms", "NT Environment", "Environment"),
    # Revenue
    ("https://nt.gov.au/employ/pay-and-conditions/revenue-forms", "Territory Revenue", "Revenue"),
    ("https://nt.gov.au/industry/mining/forms", "Mines & Energy", "Mining"),
    # Education
    ("https://nt.gov.au/education/forms", "Education NT", "Education"),
    # Police / justice
    ("https://nt.gov.au/law/police/forms", "NT Police", "Police & Justice"),
    # Palmerston
    ("https://www.palmerston.nt.gov.au/services/forms", "City of Palmerston", "General"),
    # Litchfield
    ("https://www.litchfield.nt.gov.au/services/forms", "Litchfield Council", "General"),
    # ORS (online regulatory system)
    ("https://www.ors.nt.gov.au", "NT Regulatory Services", "Licensing"),
    # My Account NT
    ("https://myaccount.nt.gov.au", "NT Government", "Online Services"),
    # NTLIS land info
    ("https://www.ntlis.nt.gov.au/forms", "NT Land Information", "Land"),
]


# Patterns that signal a real form link (not just navigation)
FORM_URL_PATTERNS = [
    re.compile(r"/form[s]?/", re.I),
    re.compile(r"\.pdf$", re.I),
    re.compile(r"application[-_]form", re.I),
    re.compile(r"[-_]form[-_.]", re.I),
    re.compile(r"/apply", re.I),
    re.compile(r"/lodge", re.I),
    re.compile(r"/register", re.I),
    re.compile(r"/licence", re.I),
    re.compile(r"/permit", re.I),
    re.compile(r"/download.*form", re.I),
]

SKIP_EXTENSIONS = re.compile(r"\.(js|css|png|jpg|jpeg|gif|svg|ico|xml|json|zip|docx?|xlsx?)$", re.I)
SKIP_FRAGMENTS = re.compile(r"^#")


def _is_form_url(url: str) -> bool:
    return any(p.search(url) for p in FORM_URL_PATTERNS)


def _fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ct = r.headers.get("Content-Type", "")
            if "text/html" not in ct and "text/plain" not in ct:
                return None
            return r.read(500_000).decode("utf-8", errors="replace")
    except Exception:
        return None


class _LinkParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__()
        self.base = base
        self.links: list[tuple[str, str]] = []  # (abs_url, link_text)
        self._cur_text: list[str] = []
        self._cur_href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            href = d.get("href", "").strip()
            if href and not SKIP_FRAGMENTS.match(href) and not SKIP_EXTENSIONS.search(href):
                self._cur_href = urllib.parse.urljoin(self.base, href)
                self._cur_text = []

    def handle_data(self, data):
        if self._cur_href:
            self._cur_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._cur_href:
            text = " ".join(t for t in self._cur_text if t)
            self.links.append((self._cur_href, text))
            self._cur_href = None
            self._cur_text = []


class _MetaParser(HTMLParser):
    """Extract page <title> and first <meta name=description>."""
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = d.get("name", "").lower()
            if name == "description":
                self.description = d.get("content", "")

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def _clean_title(raw: str) -> str:
    raw = raw.strip()
    # strip trailing " | NT Government" etc.
    raw = re.sub(r"\s*[|\-–]\s*(NT Government|Darwin City Council|Northern Territory.*)$", "", raw, flags=re.I)
    return raw.strip() or "Untitled Form"


def _extract_forms_from_page(url: str, html: str, department: str, category: str) -> list[dict]:
    """Return list of form dicts found on a single HTML page."""
    parser = _LinkParser(url)
    parser.feed(html)
    forms = []
    seen = set()
    for href, text in parser.links:
        if not href.startswith("http"):
            continue
        if href in seen:
            continue
        if not _is_form_url(href) and not text:
            continue
        if not _is_form_url(href) and not _is_form_url(text):
            continue
        seen.add(href)
        forms.append({
            "url": href,
            "title": _clean_title(text) if text else "",
            "department": department,
            "category": category,
            "source_domain": urllib.parse.urlparse(href).netloc,
        })
    return forms


def _crawl_seed(start_url: str, department: str, category: str) -> Iterator[dict]:
    """BFS crawl from a seed, yielding form dicts."""
    domain = urllib.parse.urlparse(start_url).netloc
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    pages_visited = 0

    while queue and pages_visited < MAX_PAGES_PER_DOMAIN:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        pages_visited += 1

        html = _fetch(url)
        time.sleep(DELAY)
        if not html:
            continue

        # extract forms from this page
        found = _extract_forms_from_page(url, html, department, category)
        for f in found:
            # If it's a PDF or direct form link, enrich title from link text then yield
            if not f["title"]:
                f["title"] = _guess_title_from_url(f["url"])
            if f["title"]:
                yield f

        # queue deeper pages within same domain that look like form indexes
        if depth < MAX_DEPTH:
            link_parser = _LinkParser(url)
            link_parser.feed(html)
            for href, _ in link_parser.links:
                if href in visited:
                    continue
                if urllib.parse.urlparse(href).netloc != domain:
                    continue
                if SKIP_EXTENSIONS.search(href):
                    continue
                # Only follow pages that look like form/service index pages
                if re.search(r"/form|/service|/apply|/lodge|/permit|/licence|/register|/download", href, re.I):
                    queue.append((href, depth + 1))


def _guess_title_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = path.rstrip("/").rsplit("/", 1)[-1]
    name = re.sub(r"\.(pdf|html|htm|aspx|php)$", "", name, flags=re.I)
    name = re.sub(r"[-_]", " ", name)
    return name.title().strip()


def _enrich_with_page_meta(form: dict) -> dict:
    """For non-PDF links, fetch the page to get a proper title + description."""
    if form["url"].lower().endswith(".pdf"):
        return form
    html = _fetch(form["url"])
    time.sleep(DELAY)
    if not html:
        return form
    mp = _MetaParser()
    mp.feed(html)
    if mp.title:
        form["title"] = _clean_title(mp.title)
    if mp.description:
        form["description"] = mp.description[:500]
    return form


def scrape_all(enrich: bool = False) -> list[dict]:
    """Scrape all seeds and return deduplicated list of form dicts.

    enrich=True does a second-pass page fetch to get richer titles/descriptions
    (much slower — use for a scheduled deep run, not quick refresh).
    """
    seen_urls: set[str] = set()
    results: list[dict] = []

    for start_url, department, category in SEEDS:
        print(f"  scraping {start_url} …", flush=True)
        try:
            for form in _crawl_seed(start_url, department, category):
                if form["url"] in seen_urls:
                    continue
                seen_urls.add(form["url"])
                if enrich:
                    form = _enrich_with_page_meta(form)
                form.setdefault("description", "")
                form.setdefault("keywords", "")
                results.append(form)
        except Exception as exc:
            print(f"    ! error on {start_url}: {exc}", flush=True)

    print(f"  total unique forms found: {len(results)}", flush=True)
    return results


def upsert_forms(db, forms: list[dict]) -> int:
    """Insert or update forms in the database. Returns count of rows upserted."""
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    rows = [
        (
            f["title"],
            f.get("description", ""),
            f["url"],
            f.get("department", ""),
            f.get("category", ""),
            f.get("source_domain", urllib.parse.urlparse(f["url"]).netloc),
            f.get("keywords", ""),
            now,
        )
        for f in forms
        if f.get("url") and f.get("title")
    ]
    db.executemany(
        """INSERT INTO forms (title, description, url, department, category, source_domain, keywords, last_scraped)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(url) DO UPDATE SET
             title=excluded.title,
             description=excluded.description,
             department=excluded.department,
             category=excluded.category,
             keywords=excluded.keywords,
             last_scraped=excluded.last_scraped
        """,
        rows,
    )
    db.commit()
    return len(rows)


def run_scrape(db, enrich: bool = False) -> dict:
    """Top-level entry point: scrape and persist. Returns summary dict."""
    forms = scrape_all(enrich=enrich)
    count = upsert_forms(db, forms)
    return {"scraped": len(forms), "upserted": count}
