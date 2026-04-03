"""MCP tools for searching procurers (contracting authorities) and suppliers."""
import logging

import httpx
from mcp.server.fastmcp import Context

from uvo_mcp.server import AppContext, mcp

logger = logging.getLogger(__name__)


def _get_app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def find_procurer(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search for contracting authorities (procurers) in the Slovak UVO registry."""
    app_ctx = _get_app_context(ctx)
    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }
    if name_query:
        params["text"] = name_query
    if ico:
        params["ico"] = ico

    try:
        response = await app_ctx.http_client.get("/api/obstaravatelia", params=params)
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
async def find_supplier(
    ctx: Context,
    name_query: str | None = None,
    ico: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search for suppliers (awarded contractors) in the Slovak UVO registry."""
    app_ctx = _get_app_context(ctx)
    params: dict = {
        "limit": min(limit, app_ctx.settings.max_page_size),
        "offset": max(offset, 0),
    }
    if name_query:
        params["text"] = name_query
    if ico:
        params["ico"] = ico

    try:
        response = await app_ctx.http_client.get("/api/dodavatelia", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"API returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        return {"error": f"Connection error: {exc}", "status_code": 0}
