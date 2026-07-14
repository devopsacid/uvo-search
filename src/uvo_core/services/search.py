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
    "SortBy",
    "entity_search",
    "fetch_procurement_detail",
    "run_autocomplete",
    "search_procurements",
    "vector_search_companies",
]


async def vector_search_companies(db, model, query: str, limit: int = 10, role: str = "all") -> dict:
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
