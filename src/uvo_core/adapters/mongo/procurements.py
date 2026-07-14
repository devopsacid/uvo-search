"""Procurement search + detail queries over MongoDB Atlas $search."""

from uvo_core.adapters.mongo.search_query import build_search_stage
from uvo_core.cache import _make_key, async_ttl_cache

# Default search TTL (uvo_mcp Settings.cache_ttl_search default). Cache policy is
# consolidated in Phase 6; kept here to preserve current behaviour byte-for-byte.
_CACHE_TTL_SEARCH = 300


@async_ttl_cache(
    maxsize=256,
    ttl=_CACHE_TTL_SEARCH,
    key_from=lambda db, *, text_query, cpv_codes, procurer_id, supplier_ico, date_from, date_to, value_min=None, value_max=None, limit, offset: _make_key(
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
    """Query MongoDB notices via Atlas $search."""
    match_extra: dict = {"notice_type": "contract_award"}
    if cpv_codes:
        match_extra["cpv_code"] = {"$in": cpv_codes}
    if procurer_id:
        match_extra["procurer.ico"] = procurer_id
    if supplier_ico:
        match_extra["awards.supplier.ico"] = supplier_ico
    if date_from:
        match_extra.setdefault("publication_date", {})["$gte"] = date_from
    if date_to:
        match_extra.setdefault("publication_date", {})["$lte"] = date_to
    if value_min is not None or value_max is not None:
        # Filter on the coalesced contract value (final → estimated), matching
        # _schema.contract_value, so the $facet total reflects the value filter
        # instead of the old post-pagination Python drop (plan §1.3.7).
        value_expr = {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]}
        conds: list[dict] = []
        if value_min is not None:
            conds.append({"$gte": [value_expr, value_min]})
        if value_max is not None:
            conds.append({"$lte": [value_expr, value_max]})
        match_extra["$expr"] = {"$and": conds} if len(conds) > 1 else conds[0]

    search_stage = {
        "$search": {
            "index": "default",
            **build_search_stage(
                text_query or "",
                ["title", "description", "procurer.name", "awards.supplier.name"],
            ),
        }
    }

    pipeline = [
        search_stage,
        {"$match": match_extra},
        {
            "$facet": {
                "items": [
                    {"$sort": {"publication_date": -1}},
                    {"$skip": offset},
                    {"$limit": limit},
                ],
                "total": [{"$count": "count"}],
            }
        },
    ]

    cursor = db.notices.aggregate(pipeline)
    result_list = await cursor.to_list(1)
    result = result_list[0] if result_list else {"items": [], "total": []}
    items = result.get("items", [])
    for d in items:
        d["_id"] = str(d["_id"])
    total = (result.get("total") or [{"count": 0}])[0].get("count", 0)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def fetch_procurement_detail(db, procurement_id: str) -> dict:
    """Fetch single notice from MongoDB by source_id."""
    doc = await db.notices.find_one({"source_id": procurement_id})
    if not doc:
        return {"error": f"Procurement {procurement_id} not found", "status_code": 404}
    doc["_id"] = str(doc["_id"])
    return doc
