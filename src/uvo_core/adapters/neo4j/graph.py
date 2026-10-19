"""Neo4j graph relationship queries. Each takes a live AsyncDriver and returns plain dicts."""

from __future__ import annotations

from neo4j import Query

# Server-side cap for interactive graph queries (seconds).
_QUERY_TIMEOUT_S = 10
# Public/interactive ego-network hop ceiling and result bound. Procurer -> Notice ->
# Supplier is 2 hops, so 2 already covers every direct counterparty.
_EGO_MAX_HOPS = 2
_EGO_RESULT_LIMIT = 50
_ORG_REL_TYPES = "ISSUED|AWARDED_TO"


def _timed(text: str) -> Query:
    """Wrap Cypher in a Query carrying a server-side transaction timeout."""
    return Query(text, timeout=_QUERY_TIMEOUT_S)


def _clamp_hops(max_hops: int, ceiling: int) -> int:
    """Clamp a caller-supplied hop count to [1, ceiling] (Cypher can't parametrise it)."""
    return max(1, min(int(max_hops), ceiling))


def _year_range(year: int) -> tuple[str, str]:
    """ISO start (inclusive) / end (exclusive) dates for an index-friendly year filter."""
    return f"{int(year):04d}-01-01", f"{int(year) + 1:04d}-01-01"


class Neo4jGraphStore:
    """GraphStore port binding a live Neo4j AsyncDriver to the query functions."""

    def __init__(self, driver) -> None:
        self._driver = driver

    async def ego_network(self, ico: str, max_hops: int = 2) -> dict:
        return await ego_network(self._driver, ico, max_hops)

    async def cpv_network(self, cpv_code: str, year: int) -> dict:
        return await cpv_network(self._driver, cpv_code, year)

    async def supplier_concentration(self, procurer_ico: str, top_n: int = 10) -> dict:
        return await supplier_concentration(self._driver, procurer_ico, top_n)


async def supplier_concentration(driver, procurer_ico: str, top_n: int = 10) -> dict:
    """Top N suppliers by awarded contract value for a contracting authority."""
    async with driver.session() as session:
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


async def related_organisations(driver, ico: str, max_hops: int = 2) -> dict:
    """Organisations connected through shared procurement contracts, up to max_hops."""
    # Cypher cannot parametrise a variable-length bound, so interpolate a clamped int.
    max_hops = _clamp_hops(max_hops, 4)

    async with driver.session() as session:
        result = await session.run(
            _timed(
                f"""
            MATCH (start:Procurer|Supplier {{ico: $ico}})
            MATCH path = (start)-[:{_ORG_REL_TYPES}*1..{max_hops}]-(related:Procurer|Supplier)
            WHERE related.ico <> $ico
            RETURN DISTINCT related.name AS name, related.ico AS ico,
                   labels(related)[0] AS type,
                   length(path) AS hops
            ORDER BY hops, name
            LIMIT 50
            """
            ),
            ico=ico,
        )
        records = [dict(record) async for record in result]

    return {"ico": ico, "related": records}


async def procurement_network(driver, cpv_code: str, year: int) -> dict:
    """Procurer-supplier network for a CPV code and year."""
    start, end = _year_range(year)
    async with driver.session() as session:
        result = await session.run(
            _timed(
                """
            MATCH (p:Procurer)-[:ISSUED]->(n:Notice)-[:AWARDED_TO]->(s:Supplier)
            WHERE n.cpv_code STARTS WITH $cpv_prefix
              AND n.publication_date >= date($start)
              AND n.publication_date < date($end)
            RETURN DISTINCT
                p.ico AS procurer_ico, p.name AS procurer_name,
                s.ico AS supplier_ico, s.name AS supplier_name,
                count(n) AS contract_count,
                sum(n.final_value) AS total_value
            ORDER BY total_value DESC
            LIMIT 100
            """
            ),
            cpv_prefix=cpv_code[:8],
            start=start,
            end=end,
        )
        edges = [dict(record) async for record in result]

    # Build node list from edges
    procurers = {
        e["procurer_ico"]: {"id": e["procurer_ico"], "name": e["procurer_name"], "type": "procurer"}
        for e in edges
        if e["procurer_ico"]
    }
    suppliers = {
        e["supplier_ico"]: {"id": e["supplier_ico"], "name": e["supplier_name"], "type": "supplier"}
        for e in edges
        if e["supplier_ico"]
    }

    return {
        "cpv_code": cpv_code,
        "year": year,
        "nodes": list(procurers.values()) + list(suppliers.values()),
        "edges": edges,
    }


def _build_ego_graph(start: dict, related: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    nodes[start["ico"]] = {
        "id": start["ico"],
        "label": start.get("name", "-"),
        "type": start.get("type", "procurer"),
        "value": start.get("contract_count", 0),
    }
    for r in related:
        rid = r.get("ico")
        if not rid:
            continue
        nodes[rid] = {
            "id": rid,
            "label": r.get("name", "-"),
            "type": (r.get("type") or "").lower() or "supplier",
            "value": r.get("contract_count", 0),
        }
        edges.append(
            {
                "from": start["ico"],
                "to": rid,
                "label": f"{r.get('contract_count', 0)} zmlúv",
                "value": r.get("total_value", 0),
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


def _build_cpv_graph(rows: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for r in rows:
        p_ico, s_ico = r.get("procurer_ico"), r.get("supplier_ico")
        if not p_ico or not s_ico:
            continue
        nodes[p_ico] = {
            "id": p_ico,
            "label": r.get("procurer_name", "-"),
            "type": "procurer",
            "value": 0,
        }
        nodes[s_ico] = {
            "id": s_ico,
            "label": r.get("supplier_name", "-"),
            "type": "supplier",
            "value": 0,
        }
        edges.append(
            {
                "from": p_ico,
                "to": s_ico,
                "label": f"{r.get('contract_count', 0)} zmlúv",
                "value": r.get("total_value", 0),
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


async def ego_network(driver, ico: str, max_hops: int = _EGO_MAX_HOPS) -> dict:
    """Return {nodes, edges} ego-network around the given ICO for frontend rendering.

    Bounded on every axis: labelled anchor/target nodes, organisation-relevant
    relationship types only, hops capped at ``_EGO_MAX_HOPS``, result rows capped
    at ``_EGO_RESULT_LIMIT`` and a server-side query timeout.
    """
    max_hops = _clamp_hops(max_hops, _EGO_MAX_HOPS)

    async with driver.session() as session:
        start_result = await session.run(
            _timed(
                """
            MATCH (s:Procurer|Supplier {ico: $ico})
            OPTIONAL MATCH (s)-[r]-()
            WITH s, count(r) AS degree
            WITH collect({name: s.name, type: labels(s)[0], degree: degree}) AS roles
            WHERE size(roles) > 0
            RETURN roles
            """
            ),
            ico=ico,
        )
        start_rec = await start_result.single()
        if not start_rec:
            return {"nodes": [], "edges": []}
        # One ICO can exist as both a Procurer and a Supplier node. Fold them into a
        # single anchor: summed degree, primary role = the node with the larger degree.
        roles = start_rec["roles"]
        primary = max(roles, key=lambda role: role["degree"])
        start = {
            "name": primary["name"],
            "ico": ico,
            "type": (primary.get("type") or "").lower(),
            "contract_count": sum(role["degree"] for role in roles),
        }

        result = await session.run(
            _timed(
                f"""
            MATCH (a:Procurer|Supplier {{ico: $ico}})
            MATCH path = (a)-[:{_ORG_REL_TYPES}*1..{max_hops}]-(b:Procurer|Supplier)
            WHERE b.ico <> $ico
            WITH b, length(path) AS hops,
                 head([r IN relationships(path) WHERE type(r) = 'AWARDED_TO' | r.value])
                     AS awarded_value
            RETURN b.name AS name, b.ico AS ico,
                   labels(b)[0] AS type, min(hops) AS hops,
                   count(*) AS contract_count,
                   sum(awarded_value) AS total_value
            ORDER BY hops, name
            LIMIT $limit
            """
            ),
            ico=ico,
            limit=_EGO_RESULT_LIMIT,
        )
        related = [dict(rec) async for rec in result]

    return _build_ego_graph(start, related)


async def cpv_network(driver, cpv_code: str, year: int) -> dict:
    """Return {nodes, edges} bipartite network for CPV prefix + year."""
    start, end = _year_range(year)
    async with driver.session() as session:
        result = await session.run(
            _timed(
                """
            MATCH (p:Procurer)-[:ISSUED]->(n:Notice)-[:AWARDED_TO]->(s:Supplier)
            WHERE n.cpv_code STARTS WITH $cpv_prefix
              AND n.publication_date >= date($start)
              AND n.publication_date < date($end)
            RETURN p.ico AS procurer_ico, p.name AS procurer_name,
                   s.ico AS supplier_ico, s.name AS supplier_name,
                   count(n) AS contract_count,
                   sum(n.final_value) AS total_value
            ORDER BY total_value DESC
            LIMIT 100
            """
            ),
            cpv_prefix=cpv_code[:8],
            start=start,
            end=end,
        )
        rows = [dict(r) async for r in result]

    return _build_cpv_graph(rows)
