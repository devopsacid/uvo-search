"""Vector search MCP tool — semantic company name search via fastembed."""

import asyncio

from mcp.server.fastmcp import Context

from uvo_mcp.cache import _make_key, async_ttl_cache
from uvo_mcp.server import AppContext, mcp


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@async_ttl_cache(
    maxsize=512,
    ttl=300,
    key_from=lambda model, text: _make_key((text,), {}),
)
async def _embed(model, text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: list(next(model.embed([text]))))


async def _vsearch(db, collection: str, vector: list[float], limit: int) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "name_embedding",
                "queryVector": vector,
                "numCandidates": max(limit * 10, 100),
                "limit": limit,
            }
        },
        {"$project": {"_id": 1, "ico": 1, "name": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    rows = await db[collection].aggregate(pipeline).to_list(limit)
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


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

    vector = await _embed(app_ctx.embedding_model, query)
    db = app_ctx.mongo_db

    if role == "supplier":
        s_rows = await _vsearch(db, "suppliers", vector, limit)
        p_rows: list[dict] = []
    elif role == "procurer":
        s_rows = []
        p_rows = await _vsearch(db, "procurers", vector, limit)
    else:
        s_rows, p_rows = await asyncio.gather(
            _vsearch(db, "suppliers", vector, limit),
            _vsearch(db, "procurers", vector, limit),
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
