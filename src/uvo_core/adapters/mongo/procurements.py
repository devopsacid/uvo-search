"""Procurement search + detail queries over MongoDB Atlas $search.

Two query shapes, both bounded by the page rather than the corpus:

- **No text query** → plain ``find(filter).sort(publication_date -1).skip().limit()``
  plus ``count_documents(filter)``, served by the regular B-tree indexes. Atlas
  Search adds nothing here, and the old ``exists``-over-everything ``$search``
  forced mongod to sort and count every notice inside a ``$facet``.
- **Text query** → one ``$search`` whose structured filters are non-scoring
  ``compound.filter`` clauses and whose order comes from ``$search.sort``, so
  mongot hands mongod an already-filtered, already-sorted stream that
  ``$skip``/``$limit`` cut short; the total comes from ``$searchMeta`` (mongot
  only, no document fetches). Both run concurrently.

The coalesced contract value (final → estimated → 0) cannot be expressed as a
``$search`` clause, so a value filter on a text query stays a ``$match`` — placed
after the sorted ``$search`` so the page still streams, and counted over the
text-matched set only.
"""

import asyncio
import logging

from uvo_core.adapters.mongo.search_query import build_search_stage, with_filters
from uvo_core.cache import _make_key, async_ttl_cache

logger = logging.getLogger(__name__)

# Default search TTL (uvo_mcp Settings.cache_ttl_search default). Cache policy is
# consolidated in Phase 6; kept here to preserve current behaviour byte-for-byte.
_CACHE_TTL_SEARCH = 300

_SEARCH_INDEX = "default"
_TEXT_PATHS = ["title", "description", "procurer.name", "awards.supplier.name"]
_NOTICE_TYPE = "contract_award"

# B13: fields no list view reads (uvo_api._schema.map_contract_row, firma top
# contracts, unified-search zakazky, MCP list tool). Exclusion-only, so any new
# field still reaches list consumers by default; the detail fetch stays full.
NOTICE_LIST_PROJECTION: dict[str, int] = {
    "description": 0,
    "attachments": 0,
    "content_hash": 0,
    "pipeline_run_id": 0,
}


def _value_expr(value_min: float | None, value_max: float | None) -> dict | None:
    """``$expr`` on the coalesced contract value (final → estimated → 0).

    Mirrors ``uvo_api._schema.contract_value`` so totals reflect the value filter
    (plan §1.3.7).
    """
    if value_min is None and value_max is None:
        return None
    value = {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]}
    conds: list[dict] = []
    if value_min is not None:
        conds.append({"$gte": [value, value_min]})
    if value_max is not None:
        conds.append({"$lte": [value, value_max]})
    return {"$and": conds} if len(conds) > 1 else conds[0]


def _find_filter(
    *,
    cpv_codes: list[str] | None,
    procurer_id: str | None,
    supplier_ico: str | None,
    date_from: str | None,
    date_to: str | None,
    value_expr: dict | None,
) -> dict:
    """Plain MQL filter for the no-text-query path."""
    filter_: dict = {"notice_type": _NOTICE_TYPE}
    if cpv_codes:
        filter_["cpv_code"] = {"$in": cpv_codes}
    if procurer_id:
        filter_["procurer.ico"] = procurer_id
    if supplier_ico:
        filter_["awards.supplier.ico"] = supplier_ico
    if date_from:
        filter_.setdefault("publication_date", {})["$gte"] = date_from
    if date_to:
        filter_.setdefault("publication_date", {})["$lte"] = date_to
    if value_expr is not None:
        filter_["$expr"] = value_expr
    return filter_


def _search_filters(
    *,
    cpv_codes: list[str] | None,
    procurer_id: str | None,
    supplier_ico: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    """Atlas Search ``compound.filter`` clauses equivalent to ``_find_filter``.

    Every path is mapped as ``token`` in the notices search index
    (uvo_mcp.search_indexes). ``publication_date`` is an ISO string, so a string
    ``range`` on the token mapping keeps the old lexicographic ``$gte``/``$lte``
    semantics exactly.
    """
    filters: list[dict] = [{"equals": {"path": "notice_type", "value": _NOTICE_TYPE}}]
    if cpv_codes:
        filters.append({"in": {"path": "cpv_code", "value": list(cpv_codes)}})
    if procurer_id:
        filters.append({"equals": {"path": "procurer.ico", "value": procurer_id}})
    if supplier_ico:
        filters.append({"equals": {"path": "awards.supplier.ico", "value": supplier_ico}})
    if date_from or date_to:
        date_range: dict = {"path": "publication_date"}
        if date_from:
            date_range["gte"] = date_from
        if date_to:
            date_range["lte"] = date_to
        filters.append({"range": date_range})
    return filters


def _stringify_ids(docs: list[dict]) -> list[dict]:
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def _find_page(db, filter_: dict, *, limit: int, offset: int) -> tuple[list[dict], int]:
    cursor = (
        db.notices.find(filter_, NOTICE_LIST_PROJECTION)
        .sort([("publication_date", -1)])
        .skip(offset)
        .limit(limit)
    )
    items, total = await asyncio.gather(cursor.to_list(limit), db.notices.count_documents(filter_))
    return items, total


def _search_pipelines(
    operator: dict, value_expr: dict | None, *, limit: int, offset: int
) -> tuple[list[dict], list[dict]]:
    """Return ``(items_pipeline, count_pipeline)`` for a text query."""
    value_match = [{"$match": {"$expr": value_expr}}] if value_expr is not None else []
    items = [
        {"$search": {"index": _SEARCH_INDEX, **operator, "sort": {"publication_date": -1}}},
        *value_match,
        {"$skip": offset},
        {"$limit": limit},
        {"$project": NOTICE_LIST_PROJECTION},
    ]
    if value_expr is None:
        count = [{"$searchMeta": {"index": _SEARCH_INDEX, **operator, "count": {"type": "total"}}}]
    else:
        count = [
            {"$search": {"index": _SEARCH_INDEX, **operator}},
            *value_match,
            {"$count": "count"},
        ]
    return items, count


def _total_from_count(rows: list[dict]) -> int:
    """Read a total from either ``$searchMeta`` (``{"count": {"total": n}}``) or
    ``$count`` (``{"count": n}``) output; no row means no match."""
    if not rows:
        return 0
    count = rows[0].get("count", 0)
    if isinstance(count, dict):
        return int(count.get("total", count.get("lowerBound", 0)))
    return int(count)


@async_ttl_cache(
    maxsize=256,
    ttl=_CACHE_TTL_SEARCH,
    key_from=lambda db, *, text_query, cpv_codes, procurer_id, supplier_ico, date_from, date_to, value_min=None, value_max=None, limit, offset: (
        _make_key(
            (),
            {
                "text_query": text_query,
                "cpv_codes": tuple(cpv_codes) if cpv_codes else None,
                "procurer_id": procurer_id,
                "supplier_ico": supplier_ico,
                "date_from": date_from,
                "date_to": date_to,
                "value_min": value_min,
                "value_max": value_max,
                "limit": limit,
                "offset": offset,
            },
        )
    ),
)
async def search_procurements(
    db,
    *,
    text_query: str | None = None,
    cpv_codes: list[str] | None = None,
    procurer_id: str | None = None,
    supplier_ico: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search contract-award notices; newest first, list projection applied."""
    value_expr = _value_expr(value_min, value_max)
    query = (text_query or "").strip()

    if not query:
        filter_ = _find_filter(
            cpv_codes=cpv_codes,
            procurer_id=procurer_id,
            supplier_ico=supplier_ico,
            date_from=date_from,
            date_to=date_to,
            value_expr=value_expr,
        )
        logger.debug("search_procurements: find path filter=%s", filter_)
        items, total = await _find_page(db, filter_, limit=limit, offset=offset)
        return {"items": _stringify_ids(items), "total": total, "limit": limit, "offset": offset}

    operator = with_filters(
        build_search_stage(query, _TEXT_PATHS),
        _search_filters(
            cpv_codes=cpv_codes,
            procurer_id=procurer_id,
            supplier_ico=supplier_ico,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    items_pipeline, count_pipeline = _search_pipelines(
        operator, value_expr, limit=limit, offset=offset
    )
    logger.debug("search_procurements: $search path items=%s", items_pipeline)
    items, count_rows = await asyncio.gather(
        db.notices.aggregate(items_pipeline).to_list(limit),
        db.notices.aggregate(count_pipeline).to_list(1),
    )
    return {
        "items": _stringify_ids(items),
        "total": _total_from_count(count_rows),
        "limit": limit,
        "offset": offset,
    }


async def fetch_procurement_detail(db, procurement_id: str) -> dict:
    """Fetch single notice from MongoDB by source_id."""
    doc = await db.notices.find_one({"source_id": procurement_id})
    if not doc:
        return {"error": f"Procurement {procurement_id} not found", "status_code": 404}
    doc["_id"] = str(doc["_id"])
    return doc
