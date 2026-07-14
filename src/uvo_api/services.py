"""In-process bridge from the FastAPI routers to the uvo_core query services.

Replaces the former HTTP hop through the MCP server: the same service functions the
MCP tools expose are now called in-process, using the API's own
Mongo/Neo4j/embedder handles. Routers pass the historical ``(tool_name, args)`` shape;
this keeps a single, uniform seam while the per-query pipelines live in uvo_core.

Phase 3 will replace this dispatcher with direct repository calls in the routers.
"""

from typing import Any

from uvo_api.db import get_db, get_embedder, get_neo4j_driver
from uvo_core.services.graph import cpv_network, ego_network
from uvo_core.services.search import (
    entity_search,
    fetch_procurement_detail,
    search_procurements,
    vector_search_companies,
)

# Matches the MCP tools' max_page_size clamp so behaviour is identical to the old hop.
_MAX_PAGE_SIZE = 100


async def run_query(tool_name: str, args: dict[str, Any]) -> dict:
    """Dispatch a query by its (historical MCP) tool name to the in-process service."""
    if tool_name == "find_supplier":
        return await _entity(args, "suppliers", "awards.supplier.ico")
    if tool_name == "find_procurer":
        return await _entity(args, "procurers", "procurer.ico")
    if tool_name == "search_completed_procurements":
        return await search_procurements(
            get_db(),
            text_query=args.get("text_query"),
            cpv_codes=args.get("cpv_codes"),
            procurer_id=args.get("procurer_id"),
            supplier_ico=args.get("supplier_ico"),
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            limit=min(int(args.get("limit", 20)), _MAX_PAGE_SIZE),
            offset=max(int(args.get("offset", 0)), 0),
        )
    if tool_name == "get_procurement_detail":
        return await fetch_procurement_detail(get_db(), args["procurement_id"])
    if tool_name == "search_companies_vector":
        model = get_embedder()
        if model is None:
            return {"error": "Vector search not available", "status_code": 503}
        return await vector_search_companies(
            get_db(),
            model,
            args["query"],
            int(args.get("limit", 10)),
            args.get("role", "all"),
        )
    if tool_name == "graph_ego_network":
        driver = get_neo4j_driver()
        if driver is None:
            return {"error": "Neo4j not connected", "status_code": 503}
        return await ego_network(driver, args["ico"], int(args.get("max_hops", 2)))
    if tool_name == "graph_cpv_network":
        driver = get_neo4j_driver()
        if driver is None:
            return {"error": "Neo4j not connected", "status_code": 503}
        return await cpv_network(driver, args["cpv_code"], int(args["year"]))
    raise ValueError(f"Unknown query: {tool_name}")


async def _entity(args: dict[str, Any], collection: str, lookup_match_field: str) -> dict:
    return await entity_search(
        get_db(),
        collection,
        lookup_match_field,
        name_query=args.get("name_query"),
        ico=args.get("ico"),
        sort_by=args.get("sort_by", "name"),
        limit=min(int(args.get("limit", 20)), _MAX_PAGE_SIZE),
        offset=max(int(args.get("offset", 0)), 0),
    )
