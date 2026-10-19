"""Procurer/supplier entity search over Atlas $search with per-row contract stats.

Three query shapes:

- ``ico`` → exact ``find`` on the unique ``ico`` index.
- empty name query → indexed ``find({}).sort(...)`` (B22). The old ``$search
  exists`` + ``$facet`` sorted and counted the whole collection in memory just to
  list the top N; ``contract_count`` / ``total_value`` / ``name`` now have B-tree
  indexes (``uvo_pipeline.loaders.mongo.ensure_indexes``) that serve the sort.
- name query → ``$search`` + ``$facet``, bounded by the text-matched set.

Every list path drops ``name_embedding`` (384 floats per row) — B13.
"""

import asyncio
from typing import Literal

from uvo_core.adapters.mongo.search_query import build_search_stage
from uvo_core.cache import _make_key, async_ttl_cache

# Default entity TTL (uvo_mcp Settings.cache_ttl_entity default).
_CACHE_TTL_ENTITY = 3600

SortBy = Literal["name", "contract_count", "total_value"]

ENTITY_LIST_PROJECTION: dict[str, int] = {"name_embedding": 0}

_STAT_FIELDS = ("contract_count", "total_value")


def _sort_spec(sort_by: SortBy) -> dict:
    return {
        "name": {"name": 1},
        "contract_count": {"contract_count": -1},
        "total_value": {"total_value": -1},
    }[sort_by]


def _find_sort(sort_by: SortBy) -> list[tuple[str, int]]:
    """Index-backed sort for the empty-query listing, ``_id`` tie-break for
    stable pagination (matches the ``(<field>, _id)`` compound indexes)."""
    return [*_sort_spec(sort_by).items(), ("_id", 1)]


def _finalise(docs: list[dict], *, default_stats: bool) -> list[dict]:
    for d in docs:
        d["_id"] = str(d["_id"])
        if default_stats:
            # Same defaults as the $ifNull stage on the $search path: entities not
            # yet covered by recompute_entity_stats report 0.
            for field in _STAT_FIELDS:
                if d.get(field) is None:
                    d[field] = 0
    return docs


@async_ttl_cache(
    maxsize=256,
    ttl=_CACHE_TTL_ENTITY,
    key_from=lambda db, collection, lookup_match_field, *, name_query, ico, sort_by, limit, offset: (
        _make_key(
            (collection, lookup_match_field),
            {
                "name_query": name_query,
                "ico": ico,
                "sort_by": sort_by,
                "limit": limit,
                "offset": offset,
            },
        )
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
    coll = db[collection]
    if ico:
        filter_ = {"ico": ico}
        total = await coll.count_documents(filter_)
        docs = (
            await coll.find(filter_, ENTITY_LIST_PROJECTION)
            .skip(offset)
            .limit(limit)
            .to_list(limit)
        )
        return {
            "items": _finalise(docs, default_stats=False),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    query = (name_query or "").strip()
    if not query:
        cursor = (
            coll.find({}, ENTITY_LIST_PROJECTION)
            .sort(_find_sort(sort_by))
            .skip(offset)
            .limit(limit)
        )
        # Unfiltered listing: the collection-metadata count is O(1); an exact
        # count_documents({}) would scan the whole collection.
        docs, total = await asyncio.gather(cursor.to_list(limit), coll.estimated_document_count())
        return {
            "items": _finalise(docs, default_stats=True),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    search_stage = {"$search": {"index": "default", **build_search_stage(query, ["name"])}}

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
    pipeline = [
        search_stage,
        {"$project": ENTITY_LIST_PROJECTION},
        {"$facet": {"items": items_stages, "total": [{"$count": "count"}]}},
    ]

    cursor = coll.aggregate(pipeline)
    result_list = await cursor.to_list(1)
    result = result_list[0] if result_list else {"items": [], "total": []}
    items = _finalise(result.get("items", []), default_stats=False)
    total = (result.get("total") or [{"count": 0}])[0].get("count", 0)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
