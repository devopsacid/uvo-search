"""FastMCP server definition with shared httpx client lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP

from uvo_mcp.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    http_client: httpx.AsyncClient
    settings: Settings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings()
    async with httpx.AsyncClient(
        base_url=settings.uvostat_base_url,
        headers={"ApiToken": settings.uvostat_api_token},
        timeout=settings.request_timeout,
    ) as client:
        logger.info("MCP server starting, httpx client ready")
        yield AppContext(http_client=client, settings=settings)
        logger.info("MCP server shutting down")


mcp = FastMCP(
    "UVO Search",
    instructions="Search Slovak government procurement data from UVOstat.sk and related sources",
    lifespan=app_lifespan,
    json_response=True,
)

import uvo_mcp.tools.procurements  # noqa: F401, E402
import uvo_mcp.tools.subjects  # noqa: F401, E402
