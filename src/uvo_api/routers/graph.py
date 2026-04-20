# src/uvo_api/routers/graph.py
"""Graph endpoints — ego network and CPV bipartite network (Cytoscape-compatible)."""

from fastapi import APIRouter, HTTPException, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import CytoEdge, CytoEdgeData, CytoNode, CytoNodeData, GraphResponse

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _nodes_edges_from_mcp(raw: dict) -> GraphResponse:
    """Convert the {nodes, edges} dict returned by MCP graph tools to Cytoscape format."""
    if "error" in raw:
        raise HTTPException(status_code=503, detail=raw["error"])

    raw_nodes: list[dict] = raw.get("nodes", [])
    raw_edges: list[dict] = raw.get("edges", [])

    cyto_nodes = [
        CytoNode(
            data=CytoNodeData(
                id=str(n.get("id") or ""),
                label=str(n.get("label") or n.get("name") or ""),
                type=str(n.get("type") or "supplier"),
                value=float(n.get("value") or n.get("contract_count") or 0),
            )
        )
        for n in raw_nodes
        if n.get("id")
    ]

    cyto_edges = []
    for i, e in enumerate(raw_edges):
        src = str(e.get("from") or e.get("source") or "")
        tgt = str(e.get("to") or e.get("target") or "")
        if not src or not tgt:
            continue
        cyto_edges.append(
            CytoEdge(
                data=CytoEdgeData(
                    id=f"e{i}",
                    source=src,
                    target=tgt,
                    label=str(e.get("label") or ""),
                    value=float(e.get("value") or 0),
                )
            )
        )

    return GraphResponse(nodes=cyto_nodes, edges=cyto_edges)


@router.get("/ego/{ico}", response_model=GraphResponse)
async def ego_graph(
    ico: str,
    hops: int = Query(2, ge=1, le=3),
) -> GraphResponse:
    """Ego network around an entity (ICO). Returns Cytoscape-compatible JSON."""
    raw = await call_tool("graph_ego_network", {"ico": ico, "max_hops": hops})
    if not raw.get("nodes") and not raw.get("error"):
        raise HTTPException(status_code=404, detail=f"No graph data found for ICO {ico}")
    return _nodes_edges_from_mcp(raw)


@router.get("/cpv/{cpv}", response_model=GraphResponse)
async def cpv_graph(
    cpv: str,
    year: int = Query(..., ge=2010, le=2100),
) -> GraphResponse:
    """Bipartite procurer-supplier network for a CPV prefix and year."""
    raw = await call_tool("graph_cpv_network", {"cpv_code": cpv, "year": year})
    return _nodes_edges_from_mcp(raw)
