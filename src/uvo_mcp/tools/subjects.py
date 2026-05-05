"""MCP tools for searching procurers and suppliers via Atlas $search."""

import logging
from typing import Literal

from mcp.server.fastmcp import Context

from uvo_mcp.cache import _make_key, async_ttl_cache
from uvo_mcp.config import Settings
from uvo_mcp.search_query import build_search_stage
from uvo_mcp.server import AppContext, mcp

_settings = Settings()

logger = logging.getLogger(__name__)

SortBy = Literal["name", "contract_count", "total_value"]


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


def _sort_spec(sort_by: SortBy) -> dict:
    return {
        "name": {"name": 1},
        "contract_count": {"contract_count": -1},
        "total_value": {"total_value": -1},
    }[sort_by]


@async_ttl_cache(
    maxsize=256,
    ttl=_settings.cache_ttl_entity,
    key_from=lambda db, collection, lookup_match_field, *, name_query, ico, sort_by, limit, offset: _make_key(
        (collection, lookup_match_field),
        {"name_query": name_query, "ico": ico, "sort_by": sort_by, "limit": limit, "offset": offset},
    ),
)
async def _run_entity_search(
    db,
    collection: str,
    lookup_match_field: str,
    *,
    name_query: str | None,
    ico: str | None,
    sort_by: SortBy,
    limit: int,
    offset: int,
) -> dict:
    if ico:
        filter_ = {"ico": ico}
        total = await db[collection].count_documents(filter_)
        docs = await db[collection].find(filter_).skip(offset).limit(limit).to_list(limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return {"items": docs, "total": total, "limit": limit, "offset": offset}

    search_stage = {
        "$search": {"index": "default", **build_search_stage(name_query or "", ["name"])}
    }

    # awards.supplier.ico traverses an array, so $expr returns an array of values;
    # $eq against scalar is always false. Wrap with $isArray/$in for both code paths.
    lookup_stages: list[dict] = [
        {
            "$lookup": {
                "from": "notices",
                "let": {"ico": "$ico"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$ne": ["$$ico", None]},
                                    {"$ne": ["$$ico", ""]},
                                    {
                                        "$or": [
                                            {"$eq": [f"${lookup_match_field}", "$$ico"]},
                                            {
                                                "$in": [
                                                    "$$ico",
                                                    {
                                                        "$cond": [
                                                            {"$isArray": f"${lookup_match_field}"},
                                                            f"${lookup_match_field}",
                                                            [],
                                                        ]
                                                    },
                                                ]
                                            },
                                        ]
                                    },
                                ]
                            }
                        }
                    },
                    {"$project": {"_id": 0, "final_value": 1}},
                ],
                "as": "_notices",
            }
        },
        {
            "$addFields": {
                "contract_count": {"$size": "$_notices"},
                "total_value": {
                    "$sum": {
                        "$map": {
                            "input": "$_notices",
                            "as": "n",
                            "in": {"$ifNull": ["$$n.final_value", 0]},
                        }
                    }
                },
            }
        },
        {"$project": {"_notices": 0}},
    ]

    items_stages: list[dict] = [{"$sort": _sort_spec(sort_by)}]
    if sort_by == "name":
        # Sorting by name doesn't depend on lookup output — paginate first,
        # run the expensive lookup only on the page we return.
        items_stages += [{"$skip": offset}, {"$limit": limit}, *lookup_stages]
        pipeline = [search_stage, {"$facet": {"items": items_stages, "total": [{"$count": "count"}]}}]
    else:
        # Sorting by aggregate fields requires the lookup before $sort.
        items_stages += [{"$skip": offset}, {"$limit": limit}]
        pipeline = [
            search_stage,
            *lookup_stages,
            {"$facet": {"items": items_stages, "total": [{"$count": "count"}]}},
        ]

    cursor = db[collection].aggregate(pipeline)
    result_list = await cursor.to_list(1)
    result = result_list[0] if result_list else {"items": [], "total": []}
    items = result.get("items", [])
    for d in items:
        d["_id"] = str(d["_id"])
    total = (result.get("total") or [{"count": 0}])[0].get("count", 0)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    sort_by: SortBy = "name",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search procurers by name substring, wildcard, or phrase."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _run_entity_search(
        app_ctx.mongo_db,
        "procurers",
        "procurer.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )


@mcp.tool()
async def find_supplier(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    sort_by: SortBy = "name",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search suppliers by name substring, wildcard, or phrase."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _run_entity_search(
        app_ctx.mongo_db,
        "suppliers",
        "awards.supplier.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )
