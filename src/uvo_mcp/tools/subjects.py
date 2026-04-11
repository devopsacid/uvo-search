"""MCP tools for searching procurers (contracting authorities) and suppliers."""

import logging

from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


async def _search_mongo_procurers(
    db,
    *,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Query MongoDB procurers collection."""
    filter_: dict = {}
    if name_query:
        filter_["$text"] = {"$search": name_query}
    if ico:
        filter_["ico"] = ico

    total = await db.procurers.count_documents(filter_)
    cursor = db.procurers.find(filter_).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return {"data": docs, "total": total, "limit": limit, "offset": offset}


async def _search_mongo_suppliers(
    db,
    *,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Query MongoDB suppliers collection."""
    filter_: dict = {}
    if name_query:
        filter_["$text"] = {"$search": name_query}
    if ico:
        filter_["ico"] = ico

    total = await db.suppliers.count_documents(filter_)
    cursor = db.suppliers.find(filter_).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return {"data": docs, "total": total, "limit": limit, "offset": offset}


@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search for contracting authorities (procurers) in the Slovak UVO registry."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _search_mongo_procurers(
        app_ctx.mongo_db,
        name_query=name_query,
        ico=ico,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )


@mcp.tool()
async def find_supplier(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search for suppliers (awarded contractors) in the Slovak UVO registry."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _search_mongo_suppliers(
        app_ctx.mongo_db,
        name_query=name_query,
        ico=ico,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )
