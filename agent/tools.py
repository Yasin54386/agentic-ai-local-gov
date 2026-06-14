"""Tool definitions exposed to the LLM, and the dispatcher that runs them.

These are the agent's "hands" — the same role MCP tools play (see docs/01).
Every tool here is READ-ONLY, so no human gate is required. When write tools
are added (e.g. raise a works order), this is exactly where the high-stakes
gate from docs/05 would wrap the dispatch.

The schemas are plain JSON Schema (name / description / input_schema), the shape
the hosted model's tool-use API consumes directly.
"""
from __future__ import annotations

from typing import Any

from .repository import Repository

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_datasets",
        "description": "Search the NT/Darwin public data repository for datasets by "
                       "free-text query and/or operational domain. Returns matching "
                       "datasets with their ids, titles, record counts and a summary. "
                       "Use this first to discover which dataset can answer a question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "free-text search terms"},
                "domain": {"type": "string", "description": "optional domain filter",
                            "enum": ["infrastructure & assets", "planning & permits",
                                     "parks & environment", "waste & fleet",
                                     "finance & procurement", "community services", "other"]},
                "limit": {"type": "integer", "default": 15},
            },
        },
    },
    {
        "name": "get_dataset_info",
        "description": "Get full metadata for one dataset by its id (title, description, "
                       "publisher, record count, resources, source URL).",
        "input_schema": {
            "type": "object",
            "properties": {"dataset_id": {"type": "string"}},
            "required": ["dataset_id"],
        },
    },
    {
        "name": "get_dataset_records",
        "description": "Return actual records (rows) from a dataset's downloaded data. "
                       "Optionally filter to rows containing some text. Use this to read "
                       "the real data before answering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "contains": {"type": "string", "description": "optional substring filter"},
            },
            "required": ["dataset_id"],
        },
    },
    {
        "name": "aggregate",
        "description": "Group a dataset's records by a field and either count rows, or "
                       "sum/average a numeric field. Use for questions like 'total "
                       "expenses by ward' or 'how many animals by suburb'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "group_by": {"type": "string", "description": "field name to group by"},
                "value": {"type": "string", "description": "numeric field for sum/avg"},
                "op": {"type": "string", "enum": ["count", "sum", "avg"], "default": "count"},
            },
            "required": ["dataset_id", "group_by"],
        },
    },
    {
        "name": "repository_stats",
        "description": "Get repository-wide statistics: total datasets, breakdown by "
                       "source and by operational domain.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "neighbourhood_profile",
        "description": "Build a profile of a Darwin suburb/ward by combining EVERY "
                       "dataset that mentions it (pets, trees, infringements, census, "
                       "etc.). Use for 'tell me about <suburb>' questions.",
        "input_schema": {
            "type": "object",
            "properties": {"suburb": {"type": "string", "description": "e.g. Karama, Malak, Chan Ward"}},
            "required": ["suburb"],
        },
    },
    {
        "name": "query_unified",
        "description": "Query the unified cross-dataset table. Filter by domain, area, "
                       "year, category; optionally group_by (domain/area_name/category/"
                       "period_year/dataset_title) with op count/sum/avg. Use for "
                       "transparency questions like council spending or grants.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "area": {"type": "string"},
                "year": {"type": "integer"},
                "category": {"type": "string"},
                "group_by": {"type": "string",
                              "enum": ["domain", "area_name", "category", "period_year", "dataset_title"]},
                "op": {"type": "string", "enum": ["count", "sum", "avg"], "default": "count"},
                "table": {"type": "string", "description": "which categorised table to query "
                          "(finance/governance/demographics/economy/animals/environment/"
                          "mobility/live); default 'records' = all"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "list_suburbs",
        "description": "List the Darwin suburbs/wards that appear in the data, busiest first.",
        "input_schema": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 80}}},
    },
    {
        "name": "list_tables",
        "description": "List the categorised data tables (finance, governance, demographics, "
                       "economy, animals, environment, mobility, live) with their row counts "
                       "and datasets. Use to see how the data is organised, then query one "
                       "with query_unified(table=...).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_columns",
        "description": "Search the column catalog (semantic dictionary of all 271 data "
                       "fields) to discover WHICH column — and which dataset — holds the "
                       "answer to a question. Returns columns with their meaning, type, "
                       "and the datasets they live in. Use this FIRST to locate the right "
                       "field, then fetch with get_dataset_records/aggregate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what you're looking for, e.g. 'rainfall', 'expenses', 'population'"},
                "semantic_class": {"type": "string",
                    "enum": ["TIME", "PLACE", "MEASURE", "CATEGORY", "IDENTITY", "TEXT"],
                    "description": "optional filter by kind of column"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "suburb_lookup",
        "description": "Resolve a suburb to its council (LGA) and, for City of Darwin "
                       "suburbs, its WARD. Council money is recorded by ward, so to answer "
                       "a suburb's spending: call this to get the ward, then query the "
                       "finance table with area=<ward>.",
        "input_schema": {
            "type": "object",
            "properties": {"suburb": {"type": "string"}},
            "required": ["suburb"],
        },
    },
    {
        "name": "find_records",
        "description": "Cross-dataset co-occurrence search: return every record that "
                       "matches BOTH a place (area) AND a term (keyword). The keyword is "
                       "matched against the record's data, category, metric and dataset "
                       "title. Use for questions like 'everything about Karama and "
                       "expenses' or 'X in <suburb>'. Either filter may be empty. If it "
                       "returns 0, report that honestly (don't substitute other data).",
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {"type": "string", "description": "suburb/ward, e.g. Karama, Chan Ward"},
                "keyword": {"type": "string", "description": "concept term, e.g. cost, expense, dog, population"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "live_weather",
        "description": "Get LIVE current weather + 5-day rain forecast for Darwin "
                       "(Open-Meteo). Use for 'what's the weather' / wet-season questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_howto",
        "description": "Search NT government step-by-step how-to guides. Use when someone "
                       "asks HOW to do something — register a dog, apply for a permit, "
                       "pay a fine, get a licence, etc. Returns matching guides with their "
                       "summary, steps, and official links.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what the person wants to do or find"},
                "category": {"type": "string", "description": "optional: filter by service category (e.g. 'pets', 'planning', 'transport')"},
                "limit": {"type": "integer", "default": 8},
            },
        },
    },
    {
        "name": "search_forms",
        "description": "Search NT government forms, applications, and downloadable documents. "
                       "Use when someone needs a form, application, or official document — "
                       "building permit, dog registration form, business licence, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what form or application they need"},
                "category": {"type": "string", "description": "optional: service category filter"},
                "limit": {"type": "integer", "default": 8},
            },
        },
    },
    {
        "name": "flood_risk",
        "description": "Get an INDICATIVE wet-season flood-risk level for Darwin, derived "
                       "from the live rain forecast. Use for 'is there a flood risk' "
                       "questions. Not an official BOM warning.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(repo: Repository, name: str, args: dict[str, Any]) -> Any:
    """Run a tool by name. (Read-only — a high-stakes gate would live here.)"""
    if name == "search_datasets":
        return repo.search_datasets(args.get("query", ""), args.get("domain", ""),
                                    args.get("limit", 15))
    if name == "get_dataset_info":
        return repo.get_dataset_info(args["dataset_id"])
    if name == "get_dataset_records":
        return repo.get_dataset_records(args["dataset_id"], args.get("limit", 50),
                                        args.get("contains", ""))
    if name == "aggregate":
        return repo.aggregate(args["dataset_id"], args["group_by"],
                              args.get("value", ""), args.get("op", "count"))
    if name == "repository_stats":
        return repo.stats()
    if name == "neighbourhood_profile":
        return repo.neighbourhood_profile(args["suburb"])
    if name == "query_unified":
        return repo.query_unified(args.get("domain", ""), args.get("area", ""),
                                  args.get("year"), args.get("category", ""),
                                  args.get("group_by", ""), args.get("op", "count"),
                                  limit=args.get("limit", 25), table=args.get("table", "records"))
    if name == "list_suburbs":
        return repo.list_suburbs(args.get("limit", 80))
    if name == "list_tables":
        return repo.list_tables()
    if name == "find_columns":
        return repo.find_columns(args.get("query", ""), args.get("semantic_class", ""),
                                 args.get("limit", 20))
    if name == "suburb_lookup":
        return repo.suburb_lookup(args["suburb"])
    if name == "find_records":
        return repo.find_records(args.get("area", ""), args.get("keyword", ""),
                                 args.get("limit", 50))
    if name == "search_howto":
        return repo.search_howto(args.get("query", ""), args.get("category", ""),
                                 args.get("limit", 8))
    if name == "search_forms":
        return repo.search_forms(args.get("query", ""), args.get("category", ""),
                                 args.get("limit", 8))
    if name == "live_weather":
        from ingestion import live
        return live.get_weather()
    if name == "flood_risk":
        from ingestion import live
        return live.flood_risk()
    return {"error": f"unknown tool: {name}"}
