"""MCP tools for graph relationship queries via Neo4j.

Thin delivery wrappers over uvo_core.services.graph.
"""

import logging

from mcp.server.fastmcp import Context

from uvo_core.adapters.neo4j.graph import _build_cpv_graph, _build_ego_graph  # noqa: F401
from uvo_core.services import graph as graph_svc
from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def find_supplier_concentration(
    ctx: Context,
    procurer_ico: str,
    top_n: int = 10,
) -> dict:
    """Find top N suppliers by contract value for a given contracting authority.

    Returns suppliers ranked by total awarded contract value, useful for
    identifying concentration risk (one supplier dominating contracts).
    Requires Neo4j graph database to be connected.
    """
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}
    return await graph_svc.supplier_concentration(app_ctx.neo4j_driver, procurer_ico, top_n)


@mcp.tool()
async def find_related_organisations(
    ctx: Context,
    ico: str,
    max_hops: int = 2,
) -> dict:
    """Find organisations connected through shared procurement contracts.

    Traverses the contract graph up to max_hops away from the given company
    (identified by ICO). Returns connected procurers and suppliers.
    Requires Neo4j graph database to be connected.
    """
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}
    return await graph_svc.related_organisations(app_ctx.neo4j_driver, ico, max_hops)


@mcp.tool()
async def get_procurement_network(
    ctx: Context,
    cpv_code: str,
    year: int,
) -> dict:
    """Return the procurer-supplier network for a CPV code and year.

    Returns nodes and edges for the bipartite graph of procurers and suppliers
    connected through contracts in the given CPV category and year.
    Suitable for frontend graph rendering.
    Requires Neo4j graph database to be connected.
    """
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}
    return await graph_svc.procurement_network(app_ctx.neo4j_driver, cpv_code, year)


@mcp.tool()
async def graph_ego_network(ctx: Context, ico: str, max_hops: int = 2) -> dict:
    """Return {nodes, edges} ego-network around the given ICO for frontend rendering."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}
    return await graph_svc.ego_network(app_ctx.neo4j_driver, ico, max_hops)


@mcp.tool()
async def graph_cpv_network(ctx: Context, cpv_code: str, year: int) -> dict:
    """Return {nodes, edges} bipartite network for CPV prefix + year."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.neo4j_driver is None:
        return {"error": "Neo4j not connected", "status_code": 503}
    return await graph_svc.cpv_network(app_ctx.neo4j_driver, cpv_code, year)
