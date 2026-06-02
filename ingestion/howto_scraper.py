"""How-To guide scraper — discovers procedural/guide pages across all NT government websites.

Strategy:
  - Crawl 80+ seed URLs covering every NT agency, council, and service portal
  - Identify pages that are "how to" / procedural guides (not just navigation or news)
  - Extract: title, summary (meta description or first paragraph), URL, category, department
  - BFS crawl within same domain, following links that look like guides/services/procedures
  - Polite: 0.8s delay, stdlib only, no external dependencies

Target: 1,000+ unique how-to pages.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Iterator

DELAY = 0.8
TIMEOUT = 12
MAX_DEPTH = 4
MAX_PAGES_PER_SEED = 300

HEADERS = {
    "User-Agent": (
        "AskTerritory-HowToFinder/1.0 (NT local-gov open-data research; "
        "contact: public-data-research@example.com)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

SKIP_EXT = re.compile(
    r"\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|png|jpg|jpeg|gif|svg|ico|css|js|xml|json|mp4|mp3|wav)$",
    re.I,
)

# URL path patterns that signal a procedural/guide page
HOWTO_URL_PATTERNS = [
    re.compile(r"/how[-_]to", re.I),
    re.compile(r"/how-do-i", re.I),
    re.compile(r"/apply[-_/]", re.I),
    re.compile(r"/applying", re.I),
    re.compile(r"/get[-_/]a[-_/]", re.I),
    re.compile(r"/getting[-_/]", re.I),
    re.compile(r"/register", re.I),
    re.compile(r"/renew", re.I),
    re.compile(r"/lodge", re.I),
    re.compile(r"/transfer", re.I),
    re.compile(r"/convert", re.I),
    re.compile(r"/replace", re.I),
    re.compile(r"/cancel", re.I),
    re.compile(r"/update[-_/]", re.I),
    re.compile(r"/change[-_/]", re.I),
    re.compile(r"/eligib", re.I),
    re.compile(r"/require", re.I),
    re.compile(r"/step", re.I),
    re.compile(r"/process", re.I),
    re.compile(r"/procedure", re.I),
    re.compile(r"/guide", re.I),
    re.compile(r"/checklist", re.I),
    re.compile(r"/what[-_/]you[-_/]need", re.I),
    re.compile(r"/service", re.I),
    re.compile(r"/licence", re.I),
    re.compile(r"/license", re.I),
    re.compile(r"/permit", re.I),
    re.compile(r"/certificate", re.I),
    re.compile(r"/accreditation", re.I),
    re.compile(r"/approval", re.I),
    re.compile(r"/application", re.I),
    re.compile(r"/authorisation", re.I),
    re.compile(r"/authorization", re.I),
    re.compile(r"/exemption", re.I),
    re.compile(r"/variation", re.I),
    re.compile(r"/notification", re.I),
    re.compile(r"/assessment", re.I),
    re.compile(r"/inspection", re.I),
    re.compile(r"/compliance", re.I),
    re.compile(r"/entitlement", re.I),
    re.compile(r"/concession", re.I),
    re.compile(r"/rebate", re.I),
    re.compile(r"/subsidy", re.I),
    re.compile(r"/grant", re.I),
    re.compile(r"/funding", re.I),
    re.compile(r"/support", re.I),
    re.compile(r"/assistance", re.I),
    re.compile(r"/claim", re.I),
    re.compile(r"/check", re.I),
    re.compile(r"/search", re.I),
    re.compile(r"/find[-_/]", re.I),
    re.compile(r"/report[-_/]", re.I),
    re.compile(r"/submit", re.I),
    re.compile(r"/request", re.I),
    re.compile(r"/enrol", re.I),
    re.compile(r"/enroll", re.I),
    re.compile(r"/book[-_/]", re.I),
    re.compile(r"/appoint", re.I),
    re.compile(r"/pay[-_/]", re.I),
    re.compile(r"/fees", re.I),
    re.compile(r"/cost", re.I),
]

# Link text patterns that signal a how-to page
HOWTO_TEXT_PATTERNS = [
    re.compile(r"^how\s+to\b", re.I),
    re.compile(r"^how\s+do\s+i\b", re.I),
    re.compile(r"^apply\s+for\b", re.I),
    re.compile(r"^applying\s+for\b", re.I),
    re.compile(r"^get\s+(a|an|your)\b", re.I),
    re.compile(r"^register\b", re.I),
    re.compile(r"^renew\b", re.I),
    re.compile(r"^transfer\b", re.I),
    re.compile(r"^convert\b", re.I),
    re.compile(r"^replace\b", re.I),
    re.compile(r"^lodge\b", re.I),
    re.compile(r"\blicence\b", re.I),
    re.compile(r"\bpermit\b", re.I),
    re.compile(r"\bregistration\b", re.I),
    re.compile(r"\bcertificate\b", re.I),
    re.compile(r"\bapplication\b", re.I),
    re.compile(r"\bapproval\b", re.I),
    re.compile(r"\bachre\b|\bochre\b", re.I),
    re.compile(r"\bpolice\s+check\b", re.I),
    re.compile(r"\bworking\s+with\s+children\b", re.I),
    re.compile(r"\bwwcc\b", re.I),
]

# Navigation/utility links to skip
SKIP_TEXT = re.compile(
    r"^(home|back|next|previous|print|share|skip|menu|search|login|log\s*in|sign\s*in|"
    r"contact\s*us|feedback|sitemap|accessibility|privacy|disclaimer|copyright|"
    r"terms|conditions|news|media|events|careers|jobs|about\s*us|faqs?|help|"
    r"language|translate|font|size|contrast)$",
    re.I,
)

# ── seed catalogue ─────────────────────────────────────────────────────────────
# (start_url, department, category)
SEEDS: list[tuple[str, str, str]] = [

    # ── NT Government top-level service hubs ──────────────────────────────────
    ("https://nt.gov.au/sitemap",                              "NT Government",          "All Services"),
    ("https://nt.gov.au/services",                             "NT Government",          "All Services"),

    # Driving & vehicles
    ("https://nt.gov.au/driving",                              "NT Transport",           "Driving & Vehicles"),
    ("https://nt.gov.au/driving/licences",                     "NT Transport",           "Driving Licences"),
    ("https://nt.gov.au/driving/licences/get-an-nt-licence",   "NT Transport",           "Driving Licences"),
    ("https://nt.gov.au/driving/licences/converting-interstate-licence", "NT Transport", "Driving Licences"),
    ("https://nt.gov.au/driving/licences/learner-drivers",     "NT Transport",           "Driving Licences"),
    ("https://nt.gov.au/driving/licences/heavy-vehicle",       "NT Transport",           "Driving Licences"),
    ("https://nt.gov.au/driving/vehicle-registration",         "NT Transport",           "Vehicle Registration"),
    ("https://nt.gov.au/driving/vehicle-registration/register-a-vehicle", "NT Transport","Vehicle Registration"),
    ("https://nt.gov.au/driving/vehicle-registration/transfer-registration","NT Transport","Vehicle Registration"),
    ("https://nt.gov.au/driving/vehicle-registration/renew",   "NT Transport",           "Vehicle Registration"),
    ("https://nt.gov.au/driving/traffic-offences",             "NT Transport",           "Traffic Offences"),
    ("https://nt.gov.au/driving/traffic-offences/pay-a-fine",  "NT Transport",           "Traffic Offences"),
    ("https://nt.gov.au/driving/boat-vessel-registration",     "NT Transport",           "Boating"),
    ("https://nt.gov.au/driving/boat-vessel-registration/register-a-vessel","NT Transport","Boating"),

    # Security & licensing
    ("https://nt.gov.au/law/security",                         "NT Police & Security",   "Security Licensing"),
    ("https://nt.gov.au/law/security/security-industry-licences","NT Police & Security", "Security Licensing"),
    ("https://nt.gov.au/law/security/apply-for-a-security-licence","NT Police & Security","Security Licensing"),
    ("https://nt.gov.au/employ/working-in-nt/licences-and-registrations","Business NT",  "Licensing"),
    ("https://nt.gov.au/employ/working-in-nt/licences-and-registrations/applying","Business NT","Licensing"),

    # Working with children / Ochre Card
    ("https://nt.gov.au/law/child-protection/working-with-children-ochre-card","Child Protection","Ochre Card"),
    ("https://nt.gov.au/law/child-protection/working-with-children-ochre-card/apply","Child Protection","Ochre Card"),
    ("https://nt.gov.au/law/child-protection/working-with-children-ochre-card/renew","Child Protection","Ochre Card"),
    ("https://nt.gov.au/law/child-protection",                 "Child Protection",       "Child Safety"),

    # Police checks
    ("https://nt.gov.au/law/police/police-checks",             "NT Police",              "Police Checks"),
    ("https://nt.gov.au/law/police",                           "NT Police",              "Police & Justice"),
    ("https://nt.gov.au/law/crime-and-safety",                 "NT Police",              "Safety"),

    # Births, Deaths & Marriages
    ("https://nt.gov.au/law/births-deaths-marriages",          "BDM NT",                 "Births Deaths Marriages"),
    ("https://nt.gov.au/law/births-deaths-marriages/births",   "BDM NT",                 "Births"),
    ("https://nt.gov.au/law/births-deaths-marriages/deaths",   "BDM NT",                 "Deaths"),
    ("https://nt.gov.au/law/births-deaths-marriages/marriages","BDM NT",                 "Marriages"),
    ("https://nt.gov.au/law/births-deaths-marriages/change-of-name","BDM NT",            "Name Change"),
    ("https://nt.gov.au/law/births-deaths-marriages/gender-recognition","BDM NT",        "Identity Documents"),
    ("https://nt.gov.au/law/births-deaths-marriages/register-a-birth","BDM NT",          "Births"),
    ("https://nt.gov.au/law/births-deaths-marriages/get-a-birth-certificate","BDM NT",   "Births"),

    # Property & land
    ("https://nt.gov.au/property",                             "Department of Infrastructure","Property"),
    ("https://nt.gov.au/property/building-and-construction",   "Department of Infrastructure","Building"),
    ("https://nt.gov.au/property/building-and-construction/owner-builder","Dept Infrastructure","Building"),
    ("https://nt.gov.au/property/building-and-construction/building-permit","Dept Infrastructure","Building"),
    ("https://nt.gov.au/property/land-titles",                 "Department of Infrastructure","Land Titles"),
    ("https://nt.gov.au/property/land-titles/transfer-land",   "Department of Infrastructure","Land Titles"),
    ("https://nt.gov.au/property/planning",                    "Department of Infrastructure","Planning"),
    ("https://nt.gov.au/property/planning/development-applications","Dept Infrastructure","Planning"),
    ("https://nt.gov.au/property/rates",                       "Darwin City Council",    "Rates"),
    ("https://nt.gov.au/property/renting",                     "NT Government",          "Renting"),
    ("https://nt.gov.au/property/renting/apply-for-rental",    "NT Government",          "Renting"),
    ("https://nt.gov.au/property/renting/bond",                "NT Government",          "Renting"),

    # Business & employment
    ("https://nt.gov.au/industry",                             "Business NT",            "Industry"),
    ("https://nt.gov.au/industry/start-a-business",            "Business NT",            "Business"),
    ("https://nt.gov.au/industry/start-a-business/register-a-business","Business NT",    "Business"),
    ("https://nt.gov.au/industry/start-a-business/licences-and-permits","Business NT",   "Business"),
    ("https://nt.gov.au/industry/liquor",                      "NT Liquor Commission",   "Liquor Licensing"),
    ("https://nt.gov.au/industry/liquor/apply-for-a-licence",  "NT Liquor Commission",   "Liquor Licensing"),
    ("https://nt.gov.au/industry/gambling",                    "NT Gambling Commission", "Gambling"),
    ("https://nt.gov.au/industry/gambling/apply-for-a-licence","NT Gambling Commission", "Gambling"),
    ("https://nt.gov.au/industry/mining",                      "NT Mines & Energy",      "Mining"),
    ("https://nt.gov.au/industry/mining/apply-for-tenement",   "NT Mines & Energy",      "Mining"),
    ("https://nt.gov.au/industry/agriculture",                 "Primary Industry NT",    "Agriculture"),
    ("https://nt.gov.au/industry/agriculture/permits-and-licences","Primary Industry NT","Agriculture"),
    ("https://nt.gov.au/industry/fishing",                     "Primary Industry NT",    "Fishing"),
    ("https://nt.gov.au/industry/fishing/licences-and-permits","Primary Industry NT",    "Fishing"),
    ("https://nt.gov.au/industry/tourism",                     "Tourism NT",             "Tourism"),
    ("https://nt.gov.au/industry/tourism/tourism-licences",    "Tourism NT",             "Tourism"),
    ("https://nt.gov.au/employ",                               "NT Government",          "Employment"),
    ("https://nt.gov.au/employ/working-in-nt",                 "NT Government",          "Employment"),
    ("https://nt.gov.au/employ/working-in-nt/interstate-workers","NT Government",        "Employment"),
    ("https://nt.gov.au/employ/pay-and-conditions",            "NT Government",          "Employment"),

    # Health & wellbeing
    ("https://nt.gov.au/wellbeing",                            "NT Health",              "Health"),
    ("https://nt.gov.au/wellbeing/health",                     "NT Health",              "Health"),
    ("https://nt.gov.au/wellbeing/health/medicare-and-healthcare","NT Health",           "Medicare"),
    ("https://nt.gov.au/wellbeing/health/register-with-a-gp",  "NT Health",             "Health"),
    ("https://nt.gov.au/wellbeing/disability-services",        "Disability NT",          "Disability"),
    ("https://nt.gov.au/wellbeing/disability-services/apply",  "Disability NT",          "Disability"),
    ("https://nt.gov.au/wellbeing/disability-services/ndis",   "Disability NT",          "NDIS"),
    ("https://nt.gov.au/wellbeing/aged-care",                  "Aged Care NT",           "Aged Care"),
    ("https://nt.gov.au/wellbeing/community-support",          "NT Government",          "Community Support"),
    ("https://nt.gov.au/wellbeing/housing",                    "NT Housing",             "Housing"),
    ("https://nt.gov.au/wellbeing/housing/apply-for-housing",  "NT Housing",             "Housing"),
    ("https://nt.gov.au/wellbeing/housing/home-ownership",     "NT Housing",             "Housing"),

    # Education
    ("https://nt.gov.au/education",                            "Education NT",           "Education"),
    ("https://nt.gov.au/education/schools",                    "Education NT",           "Schools"),
    ("https://nt.gov.au/education/schools/enrol-in-school",    "Education NT",           "Schools"),
    ("https://nt.gov.au/education/early-childhood",            "Education NT",           "Early Childhood"),
    ("https://nt.gov.au/education/higher-education",           "Education NT",           "Higher Education"),
    ("https://nt.gov.au/education/training",                   "Education NT",           "Training"),
    ("https://nt.gov.au/education/training/apply-for-training","Education NT",           "Training"),

    # Environment & land management
    ("https://nt.gov.au/environment",                          "NT Environment",         "Environment"),
    ("https://nt.gov.au/environment/environment-protection",   "NT Environment",         "Environment"),
    ("https://nt.gov.au/environment/parks-and-reserves",       "NT Parks",               "Parks"),
    ("https://nt.gov.au/environment/parks-and-reserves/permits","NT Parks",              "Parks"),
    ("https://nt.gov.au/environment/waste",                    "NT Environment",         "Waste"),
    ("https://nt.gov.au/environment/water",                    "NT Environment",         "Water"),
    ("https://nt.gov.au/environment/water/water-licences",     "NT Environment",         "Water"),
    ("https://nt.gov.au/environment/wildlife",                 "NT Environment",         "Wildlife"),
    ("https://nt.gov.au/environment/wildlife/permits",         "NT Environment",         "Wildlife"),

    # Revenue & taxation
    ("https://nt.gov.au/industry/finance-and-taxation",        "Territory Revenue",      "Revenue & Tax"),
    ("https://nt.gov.au/industry/finance-and-taxation/payroll-tax","Territory Revenue",  "Payroll Tax"),
    ("https://nt.gov.au/industry/finance-and-taxation/stamp-duty","Territory Revenue",   "Stamp Duty"),
    ("https://nt.gov.au/industry/finance-and-taxation/land-tax","Territory Revenue",     "Land Tax"),
    ("https://nt.gov.au/industry/finance-and-taxation/fuel-subsidies","Territory Revenue","Fuel Subsidies"),

    # Corrective services
    ("https://nt.gov.au/law/corrective-services",              "NT Corrective Services", "Corrective Services"),
    ("https://nt.gov.au/law/legal-aid",                        "NT Legal Aid",           "Legal Aid"),
    ("https://nt.gov.au/law/legal-aid/apply",                  "NT Legal Aid",           "Legal Aid"),
    ("https://nt.gov.au/law/courts",                           "NT Courts",              "Courts"),
    ("https://nt.gov.au/law/civil-disputes",                   "NT Courts",              "Civil Disputes"),

    # Firearms & weapons
    ("https://nt.gov.au/law/firearms",                         "NT Police",              "Firearms"),
    ("https://nt.gov.au/law/firearms/apply-for-licence",       "NT Police",              "Firearms"),
    ("https://nt.gov.au/law/weapons",                          "NT Police",              "Weapons"),

    # Consumer affairs
    ("https://nt.gov.au/industry/consumer-affairs",            "NT Consumer Affairs",    "Consumer Rights"),
    ("https://nt.gov.au/industry/consumer-affairs/complaints", "NT Consumer Affairs",    "Consumer Rights"),
    ("https://nt.gov.au/industry/fair-trading",                "NT Consumer Affairs",    "Fair Trading"),

    # Darwin City Council
    ("https://www.darwin.nt.gov.au/services",                  "Darwin City Council",    "Council Services"),
    ("https://www.darwin.nt.gov.au/services/rates",            "Darwin City Council",    "Rates"),
    ("https://www.darwin.nt.gov.au/services/animals-and-wildlife","Darwin City Council", "Animals"),
    ("https://www.darwin.nt.gov.au/services/waste-and-recycling","Darwin City Council",  "Waste"),
    ("https://www.darwin.nt.gov.au/services/building-and-planning","Darwin City Council","Building"),
    ("https://www.darwin.nt.gov.au/services/parks-and-recreation","Darwin City Council", "Parks"),
    ("https://www.darwin.nt.gov.au/services/roads-and-transport","Darwin City Council",  "Roads"),
    ("https://www.darwin.nt.gov.au/services/health-and-environment","Darwin City Council","Health"),
    ("https://www.darwin.nt.gov.au/business",                  "Darwin City Council",    "Business"),
    ("https://www.darwin.nt.gov.au/community",                 "Darwin City Council",    "Community"),

    # Palmerston City Council
    ("https://www.palmerston.nt.gov.au/services",              "City of Palmerston",     "Council Services"),
    ("https://www.palmerston.nt.gov.au/services/animals",      "City of Palmerston",     "Animals"),
    ("https://www.palmerston.nt.gov.au/services/waste",        "City of Palmerston",     "Waste"),
    ("https://www.palmerston.nt.gov.au/services/building",     "City of Palmerston",     "Building"),
    ("https://www.palmerston.nt.gov.au/services/rates",        "City of Palmerston",     "Rates"),
    ("https://www.palmerston.nt.gov.au/community",             "City of Palmerston",     "Community"),

    # Litchfield Council
    ("https://www.litchfield.nt.gov.au/services",              "Litchfield Council",     "Council Services"),
    ("https://www.litchfield.nt.gov.au/services/building",     "Litchfield Council",     "Building"),
    ("https://www.litchfield.nt.gov.au/services/animals",      "Litchfield Council",     "Animals"),
    ("https://www.litchfield.nt.gov.au/services/waste",        "Litchfield Council",     "Waste"),
    ("https://www.litchfield.nt.gov.au/services/rates",        "Litchfield Council",     "Rates"),
    ("https://www.litchfield.nt.gov.au/services/roads",        "Litchfield Council",     "Roads"),

    # NT Electoral Commission
    ("https://ntec.nt.gov.au",                                 "NT Electoral Commission","Electoral"),
    ("https://ntec.nt.gov.au/enrol",                           "NT Electoral Commission","Electoral"),
    ("https://ntec.nt.gov.au/how-to-vote",                     "NT Electoral Commission","Electoral"),

    # Territory Revenue Office
    ("https://treasury.nt.gov.au",                             "NT Treasury",            "Finance"),
    ("https://treasury.nt.gov.au/tro",                         "Territory Revenue",      "Revenue & Tax"),

    # NT WorkSafe
    ("https://worksafe.nt.gov.au",                             "NT WorkSafe",            "Work Health & Safety"),
    ("https://worksafe.nt.gov.au/licences-and-registrations",  "NT WorkSafe",            "WHS Licensing"),
    ("https://worksafe.nt.gov.au/licences-and-registrations/apply","NT WorkSafe",        "WHS Licensing"),
    ("https://worksafe.nt.gov.au/compensation",                "NT WorkSafe",            "Workers Compensation"),
    ("https://worksafe.nt.gov.au/compensation/claim",          "NT WorkSafe",            "Workers Compensation"),

    # NT legal bodies
    ("https://www.ntcat.nt.gov.au",                            "NTCAT",                  "Tribunal"),
    ("https://www.ntcat.nt.gov.au/how-to-apply",               "NTCAT",                  "Tribunal"),
    ("https://www.pfes.nt.gov.au",                             "NT Police Fire Emergency","Emergency Services"),
    ("https://www.pfes.nt.gov.au/fire-and-rescue/licences",    "NT Fire & Rescue",       "Fire Safety"),

    # Online regulatory system
    ("https://www.ors.nt.gov.au",                              "NT Regulatory Services", "Licensing"),

    # My Account
    ("https://myaccount.nt.gov.au",                            "NT Government",          "Online Services"),
    ("https://myaccount.nt.gov.au/help",                       "NT Government",          "Online Services"),
    ("https://myaccount.nt.gov.au/how-to",                     "NT Government",          "Online Services"),

    # Concession Registrar
    ("https://nt.gov.au/wellbeing/concessions",                "NT Government",          "Concessions"),
    ("https://nt.gov.au/wellbeing/concessions/apply",          "NT Government",          "Concessions"),

    # Alcohol & other drugs
    ("https://nt.gov.au/wellbeing/alcohol",                    "NT Health",              "Alcohol & Drugs"),

    # Remote housing
    ("https://nt.gov.au/wellbeing/housing/remote-housing",     "NT Housing",             "Remote Housing"),

    # AAPA - sacred sites
    ("https://www.aapa.nt.gov.au",                             "AAPA",                   "Sacred Sites"),
    ("https://www.aapa.nt.gov.au/certificates",                "AAPA",                   "Sacred Sites"),
    ("https://www.aapa.nt.gov.au/how-to-apply",                "AAPA",                   "Sacred Sites"),

    # Land councils
    ("https://www.nlc.org.au/our-work/land/apply-for-a-permit","Northern Land Council",  "Land Access Permits"),
    ("https://www.clc.org.au/services/permits",                "Central Land Council",   "Land Access Permits"),

    # Health registrations
    ("https://www.ahpra.gov.au/registration.aspx",             "AHPRA",                  "Health Professional Registration"),
    ("https://nt.gov.au/wellbeing/health/health-professionals","NT Health",              "Health Professionals"),
]


# ── HTML parsers ──────────────────────────────────────────────────────────────

class _LinkParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__()
        self.base = base
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            href = (d.get("href") or "").strip()
            if href and not href.startswith("#") and not SKIP_EXT.search(href):
                self._href = urllib.parse.urljoin(self.base, href)
                self._buf = []

    def handle_data(self, data):
        if self._href:
            self._buf.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = " ".join(t for t in self._buf if t)
            self.links.append((self._href, text))
            self._href = None
            self._buf = []


class _PageParser(HTMLParser):
    """Extract title, meta description, and first paragraph text."""
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.first_para = ""
        self._in_title = False
        self._in_p = False
        self._p_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            n = d.get("name", "").lower()
            p = d.get("property", "").lower()
            if n == "description" or p == "og:description":
                v = d.get("content", "").strip()
                if v and not self.description:
                    self.description = v[:400]
        elif tag == "p" and not self.first_para:
            self._in_p = True
            self._p_buf = []

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_p:
            self._p_buf.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "p" and self._in_p:
            self._in_p = False
            text = " ".join(t for t in self._p_buf if t)
            if len(text) > 40:
                self.first_para = text[:400]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ct = r.headers.get("Content-Type", "")
            if "text/html" not in ct:
                return None
            return r.read(600_000).decode("utf-8", errors="replace")
    except Exception:
        return None


def _is_howto_url(url: str) -> bool:
    return any(p.search(url) for p in HOWTO_URL_PATTERNS)


def _is_howto_text(text: str) -> bool:
    return any(p.search(text) for p in HOWTO_TEXT_PATTERNS)


def _clean_title(raw: str, dept: str = "") -> str:
    raw = raw.strip()
    for suffix in [
        r"\s*[|\-–]\s*NT Government.*",
        r"\s*[|\-–]\s*Northern Territory.*",
        r"\s*[|\-–]\s*Darwin City Council.*",
        r"\s*[|\-–]\s*City of Palmerston.*",
        r"\s*[|\-–]\s*Litchfield Council.*",
        r"\s*[|\-–]\s*nt\.gov\.au.*",
    ]:
        raw = re.sub(suffix, "", raw, flags=re.I)
    return raw.strip() or "Untitled Guide"


def _guess_title(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    name = path.rsplit("/", 1)[-1]
    name = re.sub(r"[-_]", " ", name)
    return name.title().strip()


# ── core crawl ────────────────────────────────────────────────────────────────

def _score_page(url: str, link_text: str) -> int:
    """Heuristic score — higher = more likely a how-to guide page."""
    score = 0
    if _is_howto_url(url):
        score += 2
    if _is_howto_text(link_text):
        score += 3
    if re.search(r"how[-_\s]to|how[-_\s]do[-_\s]i", url, re.I):
        score += 5
    return score


def _crawl_seed(start_url: str, department: str, category: str) -> Iterator[dict]:
    """BFS from one seed URL, yielding how-to guide dicts."""
    seed_domain = urllib.parse.urlparse(start_url).netloc
    visited: set[str] = set()
    # queue: (url, depth, link_text)
    queue: list[tuple[str, int, str]] = [(start_url, 0, "")]
    pages_done = 0

    while queue and pages_done < MAX_PAGES_PER_SEED:
        url, depth, link_text = queue.pop(0)

        # normalise: strip fragments and trailing slashes
        url = url.split("#")[0].rstrip("/") or url
        if url in visited:
            continue
        if SKIP_EXT.search(url):
            continue

        visited.add(url)
        pages_done += 1

        html = _fetch(url)
        time.sleep(DELAY)
        if not html:
            continue

        # parse title / meta
        pp = _PageParser()
        pp.feed(html)

        title = _clean_title(pp.title) if pp.title else _guess_title(url)
        summary = pp.description or pp.first_para or ""

        # yield this page if it looks like a how-to guide
        if _is_howto_url(url) or _is_howto_text(link_text) or _is_howto_text(title):
            if title and title != "Untitled Guide":
                yield {
                    "title": title,
                    "summary": summary[:400],
                    "url": url,
                    "department": department,
                    "category": category,
                    "source_domain": seed_domain,
                }

        # queue child links
        if depth < MAX_DEPTH:
            lp = _LinkParser(url)
            lp.feed(html)
            for href, text in lp.links:
                if href in visited:
                    continue
                link_domain = urllib.parse.urlparse(href).netloc
                # stay on same domain (or nt.gov.au sub-paths)
                if link_domain != seed_domain and "nt.gov.au" not in link_domain:
                    continue
                if SKIP_EXT.search(href):
                    continue
                if SKIP_TEXT.match(text):
                    continue
                score = _score_page(href, text)
                if score > 0 or depth == 0:
                    queue.append((href, depth + 1, text))


# ── public API ────────────────────────────────────────────────────────────────

def scrape_all() -> list[dict]:
    """Scrape all seeds; return deduplicated list of how-to dicts."""
    seen_urls: set[str] = set()
    results: list[dict] = []

    for start_url, department, category in SEEDS:
        print(f"  [{len(results):>4} found] scraping {start_url}", flush=True)
        try:
            for guide in _crawl_seed(start_url, department, category):
                if guide["url"] in seen_urls:
                    continue
                seen_urls.add(guide["url"])
                results.append(guide)
        except Exception as exc:
            print(f"    ! {start_url}: {exc}", flush=True)

    print(f"\n  total unique how-to pages found: {len(results)}", flush=True)
    return results


def upsert_guides(db, guides: list[dict]) -> int:
    """Upsert how-to guides into the database. Returns count inserted/updated."""
    import datetime
    now = datetime.datetime.utcnow().isoformat()

    # build tags from title words for FTS boost
    def _tags(g: dict) -> str:
        words = re.findall(r"[a-z]+", (g["title"] + " " + g["category"]).lower())
        return " ".join(sorted(set(words)))

    rows = [
        (
            g["title"],
            g.get("summary", ""),
            "[]",          # steps_json — populated by curated seed later
            json.dumps([{"label": "Go to guide", "url": g["url"]}]),  # links_json
            g.get("category", ""),
            _tags(g),
            now,
        )
        for g in guides
        if g.get("url") and g.get("title")
    ]

    db.executemany(
        """INSERT INTO howto_guides
             (title, summary, steps_json, links_json, category, tags, updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT DO NOTHING
        """,
        rows,
    )
    db.commit()
    return len(rows)


def run_scrape(db) -> dict:
    """Top-level entry: scrape + persist. Returns summary dict."""
    guides = scrape_all()
    count = upsert_guides(db, guides)
    return {"scraped": len(guides), "upserted": count}
