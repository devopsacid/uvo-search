# src/uvo_api/routers/search.py
"""Unified entity search across suppliers and procurers."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from uvo_api.mcp_client import call_tool

router = APIRouter(prefix="/api/search", tags=["search"])


class EntityHit(BaseModel):
    ico: str
    name: str
    type: str  # "supplier" | "procurer"
    contract_count: int
    total_value: float


class EntitySearchResponse(BaseModel):
    items: list[EntityHit]


def _as_hit(item: dict, kind: str) -> EntityHit:
    return EntityHit(
        ico=str(item.get("ico") or ""),
        name=item.get("name") or "",
        type=kind,
        contract_count=int(item.get("contract_count") or 0),
        total_value=float(item.get("total_value") or 0),
    )


@router.get("/entities", response_model=EntitySearchResponse)
async def search_entities(
    q: str = Query("", description="Name fragment; empty returns top suppliers/procurers."),
    limit: int = Query(10, ge=1, le=50),
) -> EntitySearchResponse:
    """Search suppliers and procurers by name, merged and sorted by relevance.

    The MCP `find_supplier` / `find_procurer` tools do the matching; we merge
    results and rank: exact name match first, then name prefix match, then
    anything else, with ties broken by contract count (desc).
    """
    per = max(1, limit // 2 + 2)
    args: dict = {"limit": per}
    if q:
        args["name_query"] = q

    supp_result = await call_tool("find_supplier", args)
    proc_result = await call_tool("find_procurer", args)

    hits: list[EntityHit] = []
    for s in supp_result.get("items", []):
        hits.append(_as_hit(s, "supplier"))
    for p in proc_result.get("items", []):
        hits.append(_as_hit(p, "procurer"))

    needle = q.strip().lower()
    def rank(h: EntityHit) -> tuple:
        n = h.name.lower()
        exact = 0 if n == needle else 1
        prefix = 0 if needle and n.startswith(needle) else 1
        return (exact, prefix, -h.contract_count)

    hits.sort(key=rank)
    return EntitySearchResponse(items=hits[:limit])
