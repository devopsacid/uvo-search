"""Search use-cases: procurement search, entity search, autocomplete, vector search.

Thin orchestration over the Mongo/embedding adapters. Both the FastAPI and FastMCP
delivery layers call these in-process — there is no HTTP hop between them.
"""

import asyncio

from uvo_core.adapters.embedding import embed
from uvo_core.adapters.mongo.autocomplete import run_autocomplete
from uvo_core.adapters.mongo.procurements import fetch_procurement_detail, search_procurements
from uvo_core.adapters.mongo.subjects import SortBy, entity_search
from uvo_core.adapters.mongo.vector import vsearch

__all__ = [
    "MAX_OFFSET",
    "MAX_PAGE_SIZE",
    "SortBy",
    "clamp_page",
    "entity_search",
    "fetch_procurement_detail",
    "find_procurers",
    "find_suppliers",
    "run_autocomplete",
    "search_procurements",
    "vector_search_companies",
]

# Page bounds shared by every delivery layer (FastAPI routers and MCP tools).
MAX_PAGE_SIZE = 100
# Deep-paging bound: skip cost grows with the offset even on an index-backed sort.
MAX_OFFSET = 10_000


def clamp_page(limit: int, offset: int = 0, *, max_limit: int = MAX_PAGE_SIZE) -> tuple[int, int]:
    """Clamp ``(limit, offset)`` to the shared paging bounds."""
    return min(int(limit), max_limit), min(max(int(offset), 0), MAX_OFFSET)


async def find_suppliers(
    db,
    *,
    name_query: str | None = None,
    ico: str | None = None,
    sort_by: SortBy = "name",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Suppliers matching a name fragment or ICO, with contract counts and totals."""
    limit, offset = clamp_page(limit, offset)
    return await entity_search(
        db,
        "suppliers",
        "awards.supplier.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


async def find_procurers(
    db,
    *,
    name_query: str | None = None,
    ico: str | None = None,
    sort_by: SortBy = "name",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Procurers matching a name fragment or ICO, with contract counts and totals."""
    limit, offset = clamp_page(limit, offset)
    return await entity_search(
        db,
        "procurers",
        "procurer.ico",
        name_query=name_query,
        ico=ico,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


async def vector_search_companies(
    db, model, query: str, limit: int = 10, role: str = "all"
) -> dict:
    """Semantic vector search over company names (suppliers and procurers).

    Callers guarantee ``db`` and ``model`` are available; the None-guard that
    returns a 503-style payload stays in the delivery adapter.
    """
    vector = await embed(model, query)

    if role == "supplier":
        s_rows = await vsearch(db, "suppliers", vector, limit)
        p_rows: list[dict] = []
    elif role == "procurer":
        s_rows = []
        p_rows = await vsearch(db, "procurers", vector, limit)
    else:
        s_rows, p_rows = await asyncio.gather(
            vsearch(db, "suppliers", vector, limit),
            vsearch(db, "procurers", vector, limit),
        )

    seen: dict[str, dict] = {}
    items: list[dict] = []
    for r in s_rows:
        ico = r.get("ico") or r["_id"]
        entry = {
            "ico": ico,
            "name": r.get("name") or "",
            "roles": ["supplier"],
            "score": float(r.get("score") or 0),
        }
        seen[ico] = entry
        items.append(entry)
    for r in p_rows:
        ico = r.get("ico") or r["_id"]
        if ico in seen:
            seen[ico]["roles"].append("procurer")
        else:
            entry = {
                "ico": ico,
                "name": r.get("name") or "",
                "roles": ["procurer"],
                "score": float(r.get("score") or 0),
            }
            seen[ico] = entry
            items.append(entry)

    items.sort(key=lambda x: x["score"], reverse=True)
    return {"items": items[:limit], "total": len(items)}
