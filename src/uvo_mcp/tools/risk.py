"""MCP tool for the company red-flag risk profile.

Thin delivery wrapper over uvo_core.services.risk — binds the app-context Mongo
and (optional) Neo4j handles to the ports and calls the shared service in-process.
"""

import logging

from mcp.server.fastmcp import Context

from uvo_core.adapters.mongo.analytics import MongoCompanyAnalytics
from uvo_core.adapters.neo4j.graph import Neo4jGraphStore
from uvo_core.services.risk import company_risk_profile
from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def company_risk_profile_tool(ctx: Context, ico: str) -> dict:
    """Compute a company's procurement red-flag risk profile.

    Returns a 0-100 risk score, an overall band, and per-flag detail with the
    evidence used: supplier-spend concentration (HHI), single-counterparty
    dependency, contract-value deviation from the CPV market, and short-window
    award clustering. Requires MongoDB; Neo4j enriches supplier concentration
    when connected.
    """
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    analytics = MongoCompanyAnalytics(app_ctx.mongo_db)
    graph = Neo4jGraphStore(app_ctx.neo4j_driver) if app_ctx.neo4j_driver is not None else None
    return await company_risk_profile(ico, analytics, graph)
