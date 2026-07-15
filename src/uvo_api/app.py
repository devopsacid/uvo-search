"""FastAPI application factory for the UVO analytics API."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from uvo_api.cache_invalidation import run_cache_invalidator
from uvo_api.config import get_settings
from uvo_api.routers import (
    contracts,
    dashboard,
    firma,
    graph,
    ingestion,
    ingestion_log,
    procurers,
    search,
    suppliers,
    worker_status,
)
from uvo_api.routers.firma import firmy_router
from uvo_api.routers.v1 import create_v1_app

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the analytics-cache invalidation subscriber for the app's lifetime.

    Started best-effort: a Redis outage never blocks startup or shutdown. The
    TestClient does not run the lifespan, so unit tests are unaffected.
    """
    invalidator = asyncio.create_task(run_cache_invalidator(), name="cache-invalidator")
    try:
        yield
    finally:
        invalidator.cancel()
        try:
            await invalidator
        except (asyncio.CancelledError, Exception):
            logger.debug("cache invalidator task ended", exc_info=True)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="UVO Analytics API",
        description="Aggregated analytics endpoints for Slovak government procurement data",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "uvo-api"}

    app.include_router(contracts.router)
    app.include_router(suppliers.router)
    app.include_router(procurers.router)
    app.include_router(firma.router)
    app.include_router(firmy_router)
    app.include_router(dashboard.router)
    app.include_router(ingestion.router)
    app.include_router(ingestion_log.router)
    app.include_router(worker_status.router)
    app.include_router(search.router)
    app.include_router(graph.router)

    # Public, monetizable API surface (key auth + rate limits); docs at /v1/docs.
    app.mount("/v1", create_v1_app())

    return app
