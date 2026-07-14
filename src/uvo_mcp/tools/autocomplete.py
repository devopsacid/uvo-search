"""Autocomplete MCP tool — thin wrapper over uvo_core.adapters.mongo.autocomplete."""

import logging

from mcp.server.fastmcp import Context

from uvo_core.adapters.mongo.autocomplete import run_autocomplete
from uvo_mcp.server import AppContext, mcp

# Re-exported for tests / backwards compatibility (shared cache object).
_run_autocomplete = run_autocomplete

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def search_autocomplete(
    ctx: Context,
    query: str,
    types: list[str] | None = None,
    limit: int = 5,
) -> dict:
    """Return up to `limit` suggestions per requested entity type for live search."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await run_autocomplete(
        app_ctx.mongo_db,
        query,
        types=types or ["procurer", "supplier", "notice"],
        limit=min(max(limit, 1), 20),
    )
