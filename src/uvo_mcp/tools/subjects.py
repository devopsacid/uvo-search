"""MCP tools for searching procurers and suppliers via Atlas $search.

Thin delivery wrappers over uvo_core.services.search.
"""

import logging

from mcp.server.fastmcp import Context

from uvo_core.services.search import SortBy, entity_search
from uvo_mcp.server import AppContext, mcp

# Re-exported for tests / backwards compatibility (shared cache object).
_run_entity_search = entity_search

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


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
    return await entity_search(
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
    return await entity_search(
        app_ctx.mongo_db,
        "suppliers",
        "awards.supplier.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )
