"""Procurer/supplier entity search over Atlas $search with per-row contract stats."""

from typing import Literal

from uvo_core.adapters.mongo.search_query import build_search_stage
from uvo_core.cache import _make_key, async_ttl_cache

# Default entity TTL (uvo_mcp Settings.cache_ttl_entity default).
_CACHE_TTL_ENTITY = 3600

SortBy = Literal["name", "contract_count", "total_value"]


def _sort_spec(sort_by: SortBy) -> dict:
    return {
        "name": {"name": 1},
        "contract_count": {"contract_count": -1},
        "total_value": {"total_value": -1},
    }[sort_by]


@async_ttl_cache(
    maxsize=256,
    ttl=_CACHE_TTL_ENTITY,
    key_from=lambda db, collection, lookup_match_field, *, name_query, ico, sort_by, limit, offset: _make_key(
        (collection, lookup_match_field),
        {"name_query": name_query, "ico": ico, "sort_by": sort_by, "limit": limit, "offset": offset},
    ),
)
async def entity_search(
    db,
    collection: str,
    lookup_match_field: str,
    *,
    name_query: str | None,
    ico: str | None,
    sort_by: SortBy,
    limit: int,
    offset: int,
) -> dict:
    if ico:
        filter_ = {"ico": ico}
        total = await db[collection].count_documents(filter_)
        docs = await db[collection].find(filter_).skip(offset).limit(limit).to_list(limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return {"items": docs, "total": total, "limit": limit, "offset": offset}

    search_stage = {
        "$search": {"index": "default", **build_search_stage(name_query or "", ["name"])}
    }

    # Read the denormalized contract stats stored on the entity docs (maintained
    # by loaders.mongo.recompute_entity_stats) instead of a per-row $lookup that
    # scanned `notices` for every result row. $ifNull defaults entities not yet
    # covered by a recompute pass to 0 so the hot path never touches `notices`.
    add_stats = {
        "$addFields": {
            "contract_count": {"$ifNull": ["$contract_count", 0]},
            "total_value": {"$ifNull": ["$total_value", 0]},
        }
    }
    items_stages: list[dict] = [
        add_stats,
        {"$sort": _sort_spec(sort_by)},
        {"$skip": offset},
        {"$limit": limit},
    ]
    pipeline = [search_stage, {"$facet": {"items": items_stages, "total": [{"$count": "count"}]}}]

    cursor = db[collection].aggregate(pipeline)
    result_list = await cursor.to_list(1)
    result = result_list[0] if result_list else {"items": [], "total": []}
    items = result.get("items", [])
    for d in items:
        d["_id"] = str(d["_id"])
    total = (result.get("total") or [{"count": 0}])[0].get("count", 0)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
