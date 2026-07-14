"""MCP tools for searching and retrieving procurement records.

Thin delivery wrappers over uvo_core.services.search — the query logic lives there
and is shared in-process with the FastAPI adapter.
"""

import logging

from mcp.server.fastmcp import Context

from uvo_core.services.search import fetch_procurement_detail, search_procurements
from uvo_mcp.server import AppContext, mcp

# Re-exported for tests and backwards compatibility; the cached query object is
# defined once in uvo_core so `.cache_clear()` targets the same cache both layers use.
_search_mongo_procurements = search_procurements

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def search_completed_procurements(
    ctx: Context,
    text_query: str | None = None,
    cpv_codes: list[str] | None = None,
    procurer_id: str | None = None,
    supplier_ico: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search completed government procurements from Slovak UVO registry."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await search_procurements(
        app_ctx.mongo_db,
        text_query=text_query,
        cpv_codes=cpv_codes,
        procurer_id=procurer_id,
        supplier_ico=supplier_ico,
        date_from=date_from,
        date_to=date_to,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )


@mcp.tool()
async def get_procurement_detail(ctx: Context, procurement_id: str) -> dict:
    """Get full details of a specific procurement."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await fetch_procurement_detail(app_ctx.mongo_db, procurement_id)
