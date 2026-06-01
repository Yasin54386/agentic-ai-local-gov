"""Theme classification — groups datasets into a handful of categorised tables.

Used by both the table builder (ingestion/tables.py) and the column catalog
(ingestion/columns.py) so a column's table assignment is consistent everywhere.
Rules are ordered; the first matching rule wins.
"""
from __future__ import annotations

# (table_name, description, substrings that identify a dataset_id)
THEME_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("finance",      "Council money: expenses, capital spend, grants",
        ("councillor-expenses", "capital_expenditure", "sponsorship", "grant")),
    ("governance",   "Council decisions and meetings",
        ("councillor-decisions", "decision", "meeting")),
    ("demographics", "ABS census & population: people, ancestry, language, country of birth",
        ("abs-", "census", "population-by-lga", "ancestry", "country-of-birth",
         "language", "person-characteristics", "-g01", "-g08", "-g09", "-g13")),
    ("economy",      "Economy, industry and business activity",
        ("economy", "total-economy", "industry")),
    ("animals",      "Animal registrations and infringements",
        ("animal", "cod-animal", "pet")),
    ("environment",  "Trees, canopy, wildlife, birds, landfill/waste",
        ("tree", "canopy", "garden", "wildlife", "bird", "landfill", "gas-generation")),
    ("mobility",     "Micromobility and transport movement",
        ("micromobility", "mobility", "neuron", "beam", "scooter")),
    ("live",         "Live snapshots fed in via MCP (weather, flood)",
        ("live:",)),
]

THEMES = [name for name, _, _ in THEME_RULES]
THEME_DESCRIPTIONS = {name: desc for name, desc, _ in THEME_RULES}
DEFAULT_THEME = "other"


def classify(dataset_id: str) -> str:
    """Map a dataset/canonical id to its themed table name."""
    d = (dataset_id or "").lower()
    for name, _desc, subs in THEME_RULES:
        if any(s in d for s in subs):
            return name
    return DEFAULT_THEME
