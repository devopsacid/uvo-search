"""Neo4j graph relationship queries. Each takes a live AsyncDriver and returns plain dicts."""


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
    if max_hops > 4:
        max_hops = 4  # safety cap

    async with driver.session() as session:
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


async def procurement_network(driver, cpv_code: str, year: int) -> dict:
    """Procurer-supplier network for a CPV code and year."""
    async with driver.session() as session:
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
            "id": p_ico, "label": r.get("procurer_name", "-"),
            "type": "procurer", "value": 0,
        }
        nodes[s_ico] = {
            "id": s_ico, "label": r.get("supplier_name", "-"),
            "type": "supplier", "value": 0,
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


async def ego_network(driver, ico: str, max_hops: int = 2) -> dict:
    """Return {nodes, edges} ego-network around the given ICO for frontend rendering."""
    if max_hops > 3:
        max_hops = 3

    async with driver.session() as session:
        start_result = await session.run(
            """
            MATCH (s) WHERE (s:Procurer OR s:Supplier) AND s.ico = $ico
            OPTIONAL MATCH (s)-[r]-()
            RETURN s.name AS name, s.ico AS ico,
                   labels(s)[0] AS type, count(r) AS contract_count
            """,
            ico=ico,
        )
        start_rec = await start_result.single()
        if not start_rec:
            return {"nodes": [], "edges": []}
        start = dict(start_rec)
        start["type"] = (start.get("type") or "").lower()

        result = await session.run(
            f"""
            MATCH (a {{ico: $ico}})
            MATCH path = (a)-[*1..{max_hops}]-(b)
            WHERE (b:Procurer OR b:Supplier) AND b.ico <> $ico
            WITH b, length(path) AS hops,
                 [x IN relationships(path) | x] AS rels
            RETURN DISTINCT b.name AS name, b.ico AS ico,
                   labels(b)[0] AS type, min(hops) AS hops,
                   count(*) AS contract_count,
                   sum([r IN rels WHERE type(r)='AWARDED_TO' | r.value][0]) AS total_value
            ORDER BY hops, name
            LIMIT 50
            """,
            ico=ico,
        )
        related = [dict(rec) async for rec in result]

    return _build_ego_graph(start, related)


async def cpv_network(driver, cpv_code: str, year: int) -> dict:
    """Return {nodes, edges} bipartite network for CPV prefix + year."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Procurer)-[:ISSUED]->(n:Notice)-[:AWARDED_TO]->(s:Supplier)
            WHERE n.cpv_code STARTS WITH $cpv_prefix
              AND n.publication_date.year = $year
            RETURN p.ico AS procurer_ico, p.name AS procurer_name,
                   s.ico AS supplier_ico, s.name AS supplier_name,
                   count(n) AS contract_count,
                   sum(n.final_value) AS total_value
            ORDER BY total_value DESC
            LIMIT 100
            """,
            cpv_prefix=cpv_code[:8],
            year=year,
        )
        rows = [dict(r) async for r in result]

    return _build_cpv_graph(rows)
