"""MCP tools for searching and retrieving procurement records."""

import logging

import httpx
from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


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
