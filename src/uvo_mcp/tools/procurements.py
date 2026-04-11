"""MCP tools for searching and retrieving procurement records."""

import logging

import httpx
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
    """Query MongoDB notices collection."""
    filter_: dict = {"notice_type": "contract_award"}

    if text_query:
        filter_["$text"] = {"$search": text_query}
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

    total = await db.notices.count_documents(filter_)
    cursor = db.notices.find(filter_).sort("publication_date", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)

    # Convert ObjectId to string for JSON serialization
    for doc in docs:
        doc["_id"] = str(doc["_id"])

    return {"data": docs, "total": total, "limit": limit, "offset": offset}


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

    if app_ctx.mongo_db is not None:
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

    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }
    if text_query:
        params["text"] = text_query
    if cpv_codes:
        params["cpv[]"] = cpv_codes
    if procurer_id:
        params["obstaravatel_id"] = procurer_id
    if supplier_ico:
        params["dodavatel_ico"] = supplier_ico
    if date_from:
        params["datum_zverejnenia_od"] = date_from
    if date_to:
        params["datum_zverejnenia_do"] = date_to

    try:
        response = await app_ctx.http_client.get("/api/ukoncene_obstaravania", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        return {"error": f"Connection error: {exc}", "status_code": 0}


@mcp.tool()
async def get_procurement_detail(ctx: Context, procurement_id: str) -> dict:
    """Get full details of a specific procurement."""
    app_ctx = _get_app_context(ctx)

    if app_ctx.mongo_db is not None:
        return await _get_mongo_procurement_detail(app_ctx.mongo_db, procurement_id)

    try:
        response = await app_ctx.http_client.get(
            "/api/ukoncene_obstaravania", params={"id[]": procurement_id}
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("data"):
            return {
                "error": f"Procurement {procurement_id} not found",
                "status_code": 404,
            }
        return data["data"][0]
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        return {"error": f"Connection error: {exc}", "status_code": 0}
