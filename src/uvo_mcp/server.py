"""FastMCP server definition; the lifespan owns every client and closes them on shutdown."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from uvo_core.observability import CONTENT_TYPE, render_default_registry, set_ready
from uvo_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)

# The lifespan context is not reachable from plain Starlette routes, so the
# readiness probe reads the Mongo handle (and the cached search-index probe)
# from here; both are set/cleared by app_lifespan.
_runtime: dict[str, Any] = {"mongo_db": None, "index_probe": None}


@dataclass
class AppContext:
    http_client: httpx.AsyncClient
    settings: Settings
    mongo_db: Any | None = field(default=None)  # AsyncIOMotorDatabase when connected
    neo4j_driver: Any | None = field(default=None)  # neo4j.AsyncDriver when connected
    embedding_model: Any | None = field(default=None)  # fastembed TextEmbedding when loaded


async def _bootstrap_search_indexes(mongo_db) -> None:
    """Idempotently provision Atlas Search indexes; failure is logged at ERROR, never fatal."""
    from uvo_core.adapters.mongo.search_indexes import ensure_indexes

    try:
        await ensure_indexes(mongo_db)
    except Exception:  # noqa: BLE001 - serve what we can; /readyz reports missing indexes
        logger.error("ensure_indexes failed; search may be degraded", exc_info=True)


async def _stop_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        logger.debug("background task ended: %s", task.get_name(), exc_info=True)


READY_REFRESH_INTERVAL_S = 30.0


async def refresh_ready() -> None:
    """Set ``uvo_ready{service="uvo-mcp"}`` from the same checks as ``/readyz``."""
    from uvo_core.adapters.mongo.health import mongo_ready

    db = _runtime["mongo_db"]
    probe = _runtime["index_probe"]
    ok = False
    try:
        ok = bool(await mongo_ready(db) and (probe is None or await probe.ready(db)))
    except Exception:  # noqa: BLE001 - a failing probe means "not ready", never a crash
        logger.warning("readiness refresh failed", exc_info=True)
    set_ready("uvo-mcp", ok)


async def _ready_refresher() -> None:
    while True:
        await refresh_ready()
        await asyncio.sleep(READY_REFRESH_INTERVAL_S)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    from uvo_core.adapters.mongo.search_indexes import SearchIndexProbe
    from uvo_core.adapters.redis.cache_invalidation import run_cache_invalidator
    from uvo_core.infra.clients import (
        close_quietly,
        make_mongo_client,
        make_neo4j_driver,
        make_redis,
    )

    settings = get_settings()

    mongo_db = None
    mongo_client = None
    if settings.mongodb_uri:
        mongo_client = make_mongo_client(
            settings.mongodb_uri,
            server_selection_timeout_ms=settings.mongo_server_selection_timeout_ms,
            connect_timeout_ms=settings.mongo_connect_timeout_ms,
            max_pool_size=settings.mongo_max_pool_size,
        )
        mongo_db = mongo_client[settings.mongodb_database]
        logger.info("MongoDB connected: %s", settings.mongodb_database)
        await _bootstrap_search_indexes(mongo_db)

    neo4j_driver = None
    if settings.neo4j_uri and settings.neo4j_password:
        neo4j_driver = make_neo4j_driver(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            connection_timeout=settings.neo4j_connection_timeout,
            max_connection_pool_size=settings.neo4j_max_pool_size,
        )
        logger.info("Neo4j connected: %s", settings.neo4j_uri)

    from uvo_core.adapters.embedding import load_embedder

    embedding_model = load_embedder()

    # Dedicated subscriber connection: an idle pub/sub read must not time out.
    redis_client = make_redis(
        settings.redis_url,
        settings.redis_password,
        socket_timeout=None,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        health_check_interval=30,
    )
    invalidator = asyncio.create_task(run_cache_invalidator(redis_client), name="cache-invalidator")
    ready_refresher: asyncio.Task | None = None

    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            logger.info("MCP server starting, httpx client ready")
            _runtime["mongo_db"] = mongo_db
            _runtime["index_probe"] = SearchIndexProbe()
            ready_refresher = asyncio.create_task(_ready_refresher(), name="ready-refresher")
            try:
                yield AppContext(
                    http_client=client,
                    settings=settings,
                    mongo_db=mongo_db,
                    neo4j_driver=neo4j_driver,
                    embedding_model=embedding_model,
                )
            finally:
                logger.info("MCP server shutting down")
                _runtime["mongo_db"] = None
                _runtime["index_probe"] = None
    finally:
        await _stop_task(ready_refresher)
        await _stop_task(invalidator)
        await close_quietly("redis", redis_client.aclose)
        if mongo_client is not None:
            await close_quietly("mongo client", mongo_client.close)
        if neo4j_driver is not None:
            await close_quietly("neo4j driver", neo4j_driver.close)


mcp = FastMCP(
    "UVO Search",
    instructions="Search Slovak government procurement data from UVO, CRZ, ITMS, TED and NKOD",
    lifespan=app_lifespan,
    json_response=True,
    host="0.0.0.0",
    port=8000,
)

import uvo_mcp.tools.autocomplete  # noqa: F401, E402
import uvo_mcp.tools.graph  # noqa: F401, E402
import uvo_mcp.tools.procurements  # noqa: F401, E402
import uvo_mcp.tools.risk  # noqa: F401, E402
import uvo_mcp.tools.subjects  # noqa: F401, E402
import uvo_mcp.tools.vector_search  # noqa: F401, E402


@mcp.custom_route("/health", methods=["GET"], name="health_check")
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint — returns 200 OK with status information."""
    return JSONResponse({"status": "ok", "service": "uvo-mcp"})


@mcp.custom_route("/readyz", methods=["GET"], name="readiness_check")
async def readiness_check(request: Request) -> JSONResponse:
    """Readiness probe — 200 only when MongoDB answers a bounded ping and the
    required Atlas Search indexes exist (cached briefly), else 503.

    ``/health`` stays an unconditional liveness check so a database blip restarts
    nothing; this endpoint only gates traffic.
    """
    from uvo_core.adapters.mongo.health import mongo_ready

    db = _runtime["mongo_db"]
    probe = _runtime["index_probe"]
    if await mongo_ready(db) and (probe is None or await probe.ready(db)):
        return JSONResponse({"status": "ready", "service": "uvo-mcp"})
    return JSONResponse({"status": "unavailable", "service": "uvo-mcp"}, status_code=503)


@mcp.custom_route("/metrics", methods=["GET"], name="metrics")
async def metrics_endpoint(request: Request) -> Response:
    """Prometheus scrape endpoint: process, cache and readiness metrics."""
    return Response(render_default_registry(), media_type=CONTENT_TYPE)
