"""Tool definitions exposed to the LLM, and the dispatcher that runs them.

These are the agent's "hands" — the same role MCP tools play (see docs/01).
Every tool here is READ-ONLY, so no human gate is required. When write tools
are added (e.g. raise a works order), this is exactly where the high-stakes
gate from docs/05 would wrap the dispatch.

The schemas are plain JSON Schema (name / description / input_schema), the common
function-calling shape understood by self-hosted model servers (Ollama, llama.cpp,
vLLM) — no vendor lock-in.
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
        "name": "live_weather",
        "description": "Get LIVE current weather + 5-day rain forecast for Darwin "
                       "(Open-Meteo). Use for 'what's the weather' / wet-season questions.",
        "input_schema": {"type": "object", "properties": {}},
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
                                  limit=args.get("limit", 25))
    if name == "list_suburbs":
        return repo.list_suburbs(args.get("limit", 80))
    if name == "live_weather":
        from ingestion import live
        return live.get_weather()
    if name == "flood_risk":
        from ingestion import live
        return live.flood_risk()
    return {"error": f"unknown tool: {name}"}
