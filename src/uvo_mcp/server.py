"""FastMCP server definition with shared httpx client lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from uvo_mcp.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    http_client: httpx.AsyncClient
    settings: Settings
    mongo_db: Any | None = field(default=None)      # AsyncIOMotorDatabase when connected
    neo4j_driver: Any | None = field(default=None)  # neo4j.AsyncDriver when connected


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings()

    mongo_db = None
    mongo_client = None
    if settings.mongodb_uri:
        from motor.motor_asyncio import AsyncIOMotorClient

        from uvo_mcp.search_indexes import ensure_indexes

        mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
        mongo_db = mongo_client[settings.mongodb_database]
        logger.info("MongoDB connected: %s", settings.mongodb_database)
        try:
            await ensure_indexes(mongo_db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_indexes failed: %s", exc)

    neo4j_driver = None
    if settings.neo4j_uri and settings.neo4j_password:
        from neo4j import AsyncGraphDatabase
        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("Neo4j connected: %s", settings.neo4j_uri)

    async with httpx.AsyncClient(
        timeout=settings.request_timeout,
    ) as client:
        logger.info("MCP server starting, httpx client ready")
        yield AppContext(
            http_client=client,
            settings=settings,
            mongo_db=mongo_db,
            neo4j_driver=neo4j_driver,
        )
        logger.info("MCP server shutting down")

    if mongo_client:
        mongo_client.close()
    if neo4j_driver:
        await neo4j_driver.close()


mcp = FastMCP(
    "UVO Search",
    instructions="Search Slovak government procurement data from UVO, CRZ, ITMS, TED and NKOD",
    lifespan=app_lifespan,
    json_response=True,
    host="0.0.0.0",
    port=8000,
)

import uvo_mcp.tools.procurements  # noqa: F401, E402
import uvo_mcp.tools.subjects  # noqa: F401, E402
import uvo_mcp.tools.graph  # noqa: F401, E402
import uvo_mcp.tools.autocomplete  # noqa: F401, E402


@mcp.custom_route("/health", methods=["GET"], name="health_check")
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint — returns 200 OK with status information."""
    return JSONResponse({"status": "ok", "service": "uvo-mcp"})
