"""Build a unified COLUMN CATALOG — the semantic data dictionary across all datasets.

Analyses every harvested record, and for each distinct field produces one catalog
entry: a meaningful name + label, semantic class (TIME/PLACE/MEASURE/CATEGORY/
IDENTITY/TEXT), data type, example values, null rate, and which dataset(s) +
original field it maps to. Cryptic fields are given a best-effort name and flagged
needs_review.

The LLM/MCP reads this catalog to decide which column (and therefore which
dataset) answers a question, then fetches just that — instead of scanning rows.

    python -m ingestion.columns        # -> data/column_catalog.json + docs/COLUMN-CATALOG.md
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter, defaultdict

from .themes import classify

RAW_GLOB = "data/raw/smart.darwin.nt.gov.au/*/JSON_export_full_data.json"
OUT_JSON = "data/column_catalog.json"
OUT_MD = "docs/COLUMN-CATALOG.md"

# Abbreviation expansions to turn cryptic field names into meaningful labels.
ABBREV = {
    "tcc": "tree canopy cover", "ha": "hectares", "pc": "percent", "m2": "square metres",
    "pop": "population", "cha": "canopy change", "cpc": "canopy percent change",
    "subha": "sub-area hectares", "no": "count", "amt": "amount", "ave": "average",
    "dist": "distance", "co2": "CO2", "mwh": "megawatt hours", "fy": "financial year",
    "lga": "local government area", "abs": "ABS", "scc": "state suburb code",
}
YEAR_RE = re.compile(r"(19|20)\d{2}")
# Fields that mean the same thing across datasets -> one unified name.
SYNONYMS = {
    "suburb_name": "suburb", "abs_lga": "lga", "lga_name": "lga", "lga_name_2020": "lga",
    "year_text": "year", "census_year": "year", "fy": "financial_year",
    "fy_year": "financial_year", "count_amt": "count", "geo_point": "geo_point_2d",
}

CLASS_HINTS = [
    ("TIME", ("year", "date", "month", "fy", "period", "financial_year")),
    ("PLACE", ("suburb", "ward", "lga", "area", "geo", "lat", "lon", "region",
               "postcode", "state", "scc", "centroid", "geom")),
    ("CATEGORY", ("type", "category", "sex", "status", "class", "sector", "program",
                  "offence", "gender", "measure", "season", "provider")),
    ("IDENTITY", ("name", "title", "id", "code", "breed", "species", "organisation",
                  "councillor", "index")),
]


def infer_type(v):
    if v is None or v == "":
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, (dict, list)):
        return "geojson" if "geo" in str(v)[:30].lower() or "coordinates" in str(v) else "json"
    s = str(v)
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return "number"
    if YEAR_RE.fullmatch(s):
        return "year"
    if re.search(r"\d{4}-\d{2}-\d{2}", s):
        return "date"
    return "text"


def semantic_class(name: str, dom_type: str) -> str:
    n = name.lower()
    for cls, hints in CLASS_HINTS:
        if any(h in n for h in hints):
            return cls
    if dom_type in ("number", "year"):
        return "MEASURE"
    if dom_type in ("json", "geojson"):
        return "PLACE" if dom_type == "geojson" else "TEXT"
    return "TEXT"


def meaningful_label(name: str) -> tuple[str, bool]:
    """Return (human label, needs_review). Expands abbreviations; flags cryptic."""
    parts = re.split(r"[_\W]+", name)
    out, cryptic = [], False
    for p in parts:
        if not p:
            continue
        yr = YEAR_RE.search(p)
        base = YEAR_RE.sub("", p)
        if base in ABBREV:
            out.append(ABBREV[base])
        elif base and len(base) <= 3 and base.isalpha() and base not in ("age", "key", "raw"):
            out.append(base)
            cryptic = True            # short opaque token
        else:
            out.append(base)
        if yr:
            out.append(yr.group(0))
    label = " ".join(w for w in out if w).strip().capitalize()
    return (label or name), cryptic


def build() -> dict:
    files = sorted(glob.glob(RAW_GLOB))
    ds_for = defaultdict(dict)      # field -> {dataset_id: count}
    samples = defaultdict(list)
    types = defaultdict(Counter)
    nulls = defaultdict(lambda: [0, 0])  # field -> [null, total]

    for f in files:
        ds_dir = os.path.basename(os.path.dirname(f))
        dataset_id = f"smart.darwin.nt.gov.au:{ds_dir}"
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                ds_for[k][dataset_id] = ds_for[k].get(dataset_id, 0) + 1
                t = infer_type(v)
                if t != "null":
                    types[k][t] += 1
                nulls[k][1] += 1
                if v in (None, ""):
                    nulls[k][0] += 1
                elif len(samples[k]) < 4 and not isinstance(v, (dict, list)) and v not in samples[k]:
                    samples[k].append(v)

    columns = []
    for field in sorted(ds_for):
        dom_type = types[field].most_common(1)[0][0] if types[field] else "null"
        cls = semantic_class(field, dom_type)
        label, cryptic = meaningful_label(field)
        n_null, n_tot = nulls[field]
        tables = sorted({classify(d) for d in ds_for[field]})
        columns.append({
            "column": SYNONYMS.get(field, field),       # unified name
            "original_field": field,
            "label": label,
            "semantic_class": cls,
            "data_type": dom_type,
            "tables": tables,                            # which categorised table(s) hold it
            "appears_in": [{"dataset_id": d, "table": classify(d), "records": c}
                           for d, c in sorted(ds_for[field].items(), key=lambda x: -x[1])],
            "dataset_count": len(ds_for[field]),
            "examples": samples[field][:4],
            "null_rate": round(n_null / n_tot, 3) if n_tot else None,
            "needs_review": cryptic,
        })

    catalog = {
        "generated_from": "data/raw/smart.darwin.nt.gov.au/*",
        "total_columns": len(columns),
        "by_class": dict(Counter(c["semantic_class"] for c in columns)),
        "columns": columns,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(catalog, open(OUT_JSON, "w", encoding="utf-8"), indent=2, default=str)
    _write_md(catalog)
    return catalog


def _write_md(cat: dict) -> None:
    lines = ["# Column Catalog — unified semantic dictionary", "",
             "> Auto-generated by `python -m ingestion.columns`. The LLM/MCP reads this",
             "> to decide which column (and dataset) answers a question.", "",
             f"**{cat['total_columns']} columns** across all datasets. "
             f"By class: " + ", ".join(f"{k} {v}" for k, v in cat["by_class"].items()), "",
             "| Column | Table(s) | Class | Type | Example | Review? |",
             "|---|---|---|---|---|:--:|"]
    for c in cat["columns"]:
        ex = ", ".join(str(x)[:18] for x in c["examples"][:2])
        flag = "⚠️" if c["needs_review"] else ""
        tbls = ", ".join(c["tables"])
        lines.append(f"| `{c['column']}` ({c['label']}) | {tbls} | {c['semantic_class']} | "
                     f"{c['data_type']} | {ex} | {flag} |")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    cat = build()
    print(f"[columns] {cat['total_columns']} columns -> {OUT_JSON} + {OUT_MD}")
    print(f"          by class: {cat['by_class']}")
    review = sum(1 for c in cat['columns'] if c['needs_review'])
    print(f"          {review} cryptic columns flagged needs_review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
