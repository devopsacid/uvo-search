"""Vector search MCP tool — thin wrapper over uvo_core.services.search."""

from mcp.server.fastmcp import Context

from uvo_core.services.search import vector_search_companies
from uvo_mcp.server import AppContext, mcp


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def search_companies_vector(
    ctx: Context,
    query: str,
    limit: int = 10,
    role: str = "all",
) -> dict:
    """Semantic vector search over company names (suppliers and procurers)."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None or app_ctx.embedding_model is None:
        return {"error": "Vector search not available", "status_code": 503}
    return await vector_search_companies(
        app_ctx.mongo_db, app_ctx.embedding_model, query, limit, role
    )
