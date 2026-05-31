"""Lightweight keyword classifier mapping a dataset to one of the 6 operational
domains from the framework. Deterministic and transparent (no ML) so the
classification is explainable — important for the governance layer.
"""
from __future__ import annotations

# Order matters: first domain whose keywords match wins.
DOMAIN_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("infrastructure & assets", (
        "road", "bridge", "footpath", "drain", "asset", "infrastructure",
        "street", "lighting", "building", "facility", "kerb", "pavement",
    )),
    ("planning & permits", (
        "plan", "permit", "development", "zoning", "land use", "subdivision",
        "title", "cadastr", "application", "da ", "lot",
    )),
    ("parks & environment", (
        "park", "tree", "canopy", "wildlife", "garden", "reserve", "environment",
        "vegetation", "biodiversity", "water quality", "air quality", "climate",
        "emission", "landfill gas", "stream", "drainage",
    )),
    ("waste & fleet", (
        "waste", "bin", "recycl", "rubbish", "garbage", "fleet", "vehicle",
        "micromobility", "transport", "parking",
    )),
    ("finance & procurement", (
        "budget", "finance", "expenditure", "revenue", "rates", "grant",
        "sponsorship", "contract", "tender", "procurement", "economy",
        "expenses", "capital", "fee",
    )),
    ("community services", (
        "population", "census", "ancestry", "language", "community", "animal",
        "registration", "infringement", "councillor", "election", "health",
        "education", "culture", "sport", "demographic", "country of birth",
    )),
]


def classify(text: str) -> str:
    """Return the best-guess operational domain for a dataset given its text."""
    t = (text or "").lower()
    for domain, keywords in DOMAIN_KEYWORDS:
        if any(kw in t for kw in keywords):
            return domain
    return "other"
