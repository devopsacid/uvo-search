"""MCP tools for graph relationship queries via Neo4j."""

import logging

from mcp.server.fastmcp import Context

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

    async with app_ctx.neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:Procurer {ico: $ico})-[:ISSUED]->(n:Notice)-[r:AWARDED_TO]->(s:Supplier)
            RETURN s.name AS supplier_name, s.ico AS supplier_ico,
                   count(n) AS contract_count,
                   sum(r.value) AS total_value
            ORDER BY total_value DESC
            LIMIT $top_n
            """,
            ico=procurer_ico,
            top_n=top_n,
        )
        records = [dict(record) async for record in result]

    return {"procurer_ico": procurer_ico, "top_suppliers": records}


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
    if max_hops > 4:
        max_hops = 4  # safety cap

    async with app_ctx.neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (start)
            WHERE (start:Procurer OR start:Supplier) AND start.ico = $ico
            MATCH path = (start)-[*1..$max_hops]-(related)
            WHERE (related:Procurer OR related:Supplier) AND related.ico <> $ico
            RETURN DISTINCT related.name AS name, related.ico AS ico,
                   labels(related)[0] AS type,
                   length(path) AS hops
            ORDER BY hops, name
            LIMIT 50
            """,
            ico=ico,
            max_hops=max_hops,
        )
        records = [dict(record) async for record in result]

    return {"ico": ico, "related": records}


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

    async with app_ctx.neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Procurer)-[:ISSUED]->(n:Notice)-[:AWARDED_TO]->(s:Supplier)
            WHERE n.cpv_code STARTS WITH $cpv_prefix
              AND n.publication_date.year = $year
            RETURN DISTINCT
                p.ico AS procurer_ico, p.name AS procurer_name,
                s.ico AS supplier_ico, s.name AS supplier_name,
                count(n) AS contract_count,
                sum(n.final_value) AS total_value
            ORDER BY total_value DESC
            LIMIT 100
            """,
            cpv_prefix=cpv_code[:8],
            year=year,
        )
        edges = [dict(record) async for record in result]

    # Build node list from edges
    procurers = {
        e["procurer_ico"]: {"id": e["procurer_ico"], "name": e["procurer_name"], "type": "procurer"}
        for e in edges if e["procurer_ico"]
    }
    suppliers = {
        e["supplier_ico"]: {"id": e["supplier_ico"], "name": e["supplier_name"], "type": "supplier"}
        for e in edges if e["supplier_ico"]
    }

    return {
        "cpv_code": cpv_code,
        "year": year,
        "nodes": list(procurers.values()) + list(suppliers.values()),
        "edges": edges,
    }
