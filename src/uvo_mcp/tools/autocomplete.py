"""Autocomplete across procurers, suppliers, and notices."""

import asyncio
import logging
from collections.abc import Iterable

from mcp.server.fastmcp import Context

from uvo_mcp.cache import async_ttl_cache, _make_key
from uvo_mcp.config import Settings
from uvo_mcp.server import AppContext, mcp

_settings = Settings()

logger = logging.getLogger(__name__)

_COLLECTION = {"procurer": "procurers", "supplier": "suppliers", "notice": "notices"}
_PATH = {"procurer": "name", "supplier": "name", "notice": "title"}
_ID = {"procurer": "ico", "supplier": "ico", "notice": "source_id"}
_LABEL = {"procurer": "name", "supplier": "name", "notice": "title"}


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


async def _one_collection(db, entity_type: str, query: str, limit: int) -> list[dict]:
    coll = db[_COLLECTION[entity_type]]
    pipeline = [
        {
            "$search": {
                "index": "default",
                "autocomplete": {
                    "query": query,
                    "path": _PATH[entity_type],
                    "fuzzy": {"maxEdits": 1},
                },
            }
        },
        {"$limit": limit},
        {"$project": {"_id": 1, _ID[entity_type]: 1, _LABEL[entity_type]: 1, "ico": 1}},
    ]
    rows = await coll.aggregate(pipeline).to_list(limit)
    out = []
    for r in rows:
        out.append(
            {
                "type": entity_type,
                "id": r.get(_ID[entity_type]) or str(r["_id"]),
                "label": r.get(_LABEL[entity_type], "-"),
                "sublabel": f"IČO {r['ico']}" if r.get("ico") else "",
            }
        )
    return out


@async_ttl_cache(
    maxsize=512,
    ttl=_settings.cache_ttl_search,
    key_from=lambda db, query, *, types, limit: _make_key(
        (query,), {"types": tuple(types), "limit": limit}
    ),
)
async def _run_autocomplete(db, query: str, *, types: Iterable[str], limit: int) -> dict:
    q = query.strip()
    if not q:
        return {"results": []}

    tasks = [_one_collection(db, t, q, limit) for t in types if t in _COLLECTION]
    results_per_type = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict] = []
    for bucket in results_per_type:
        if isinstance(bucket, Exception):
            logger.warning("autocomplete bucket failed: %s", bucket)
            continue
        out.extend(bucket)
    return {"results": out}


@mcp.tool()
async def search_autocomplete(
    ctx: Context,
    query: str,
    types: list[str] | None = None,
    limit: int = 5,
) -> dict:
    """Return up to `limit` suggestions per requested entity type for live search."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _run_autocomplete(
        app_ctx.mongo_db,
        query,
        types=types or ["procurer", "supplier", "notice"],
        limit=min(max(limit, 1), 20),
    )
