"""MCP tools for searching and retrieving procurement records."""

import logging

from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


async def _search_mongo_procurements(
    db,
    *,
    text_query: str | None = None,
    cpv_codes: list[str] | None = None,
    procurer_id: str | None = None,
    supplier_ico: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Query MongoDB notices via Atlas $search."""
    from uvo_mcp.search_query import build_search_stage

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


async def _get_mongo_procurement_detail(db, procurement_id: str) -> dict:
    """Fetch single notice from MongoDB by source_id."""
    doc = await db.notices.find_one({"source_id": procurement_id})
    if not doc:
        return {"error": f"Procurement {procurement_id} not found", "status_code": 404}
    doc["_id"] = str(doc["_id"])
    return doc


@mcp.tool()
async def search_completed_procurements(
    ctx: Context,
    text_query: str | None = None,
    cpv_codes: list[str] | None = None,
    procurer_id: str | None = None,
    supplier_ico: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search completed government procurements from Slovak UVO registry."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _search_mongo_procurements(
        app_ctx.mongo_db,
        text_query=text_query,
        cpv_codes=cpv_codes,
        procurer_id=procurer_id,
        supplier_ico=supplier_ico,
        date_from=date_from,
        date_to=date_to,
        limit=min(limit, app_ctx.settings.max_page_size),
        offset=max(offset, 0),
    )


@mcp.tool()
async def get_procurement_detail(ctx: Context, procurement_id: str) -> dict:
    """Get full details of a specific procurement."""
    app_ctx = _get_app_context(ctx)
    if app_ctx.mongo_db is None:
        return {"error": "MongoDB not configured", "status_code": 503}
    return await _get_mongo_procurement_detail(app_ctx.mongo_db, procurement_id)
