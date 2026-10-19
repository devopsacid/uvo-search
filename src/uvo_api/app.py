"""FastAPI application factory for the UVO analytics API."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from uvo_api.config import get_settings
from uvo_api.db import (
    Db,
    build_resources,
    close_resources,
    get_index_probe,
    install_resources,
    make_dashboard_analytics,
)
from uvo_api.errors import register_error_handlers
from uvo_api.metrics import install_metrics, start_background
from uvo_api.routers import (
    analytics,
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
from uvo_core.adapters.mongo.health import mongo_ready
from uvo_core.adapters.mongo.search_indexes import SearchIndexProbe, ensure_indexes
from uvo_core.adapters.redis.cache_invalidation import run_cache_invalidator
from uvo_core.infra.clients import close_quietly, make_redis
from uvo_core.services.analytics import warm_default_dashboards

logger = logging.getLogger(__name__)

# Delay before the dashboard warm-up so startup (index bootstrap, probes) is not contended.
_WARMUP_DELAY_SECONDS = 5.0


async def _warm_dashboards(db, delay: float = _WARMUP_DELAY_SECONDS) -> None:
    """Pre-compute the landing-page aggregates; best effort, never raises."""
    try:
        await asyncio.sleep(delay)
        await warm_default_dashboards(make_dashboard_analytics(db))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - warm-up is an optimisation, not a dependency
        logger.warning("dashboard warm-up failed", exc_info=True)


async def _stop_task(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        logger.debug("background task ended: %s", task.get_name(), exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the app's clients: create on startup, bootstrap indexes, close on shutdown.

    The Redis cache-invalidation subscriber is best-effort: an outage never blocks
    startup or shutdown. The TestClient does not run the lifespan (unless used as a
    context manager), so unit tests are unaffected.
    """
    settings = get_settings()
    resources = build_resources(settings)
    install_resources(app, resources)

    try:
        await ensure_indexes(resources.db)
    except Exception:  # noqa: BLE001 - serve what we can; /readyz reports missing indexes
        logger.error("ensure_indexes failed; search may be degraded", exc_info=True)

    # Dedicated subscriber connection: an idle pub/sub read must not hit a socket timeout.
    subscriber_redis = make_redis(
        settings.redis_url,
        settings.redis_password,
        socket_timeout=None,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        health_check_interval=30,
    )
    invalidator = asyncio.create_task(
        run_cache_invalidator(
            subscriber_redis,
            # Re-warm the landing-page aggregates right after each clear (spec §7.3).
            after_clear=lambda: _warm_dashboards(resources.db, delay=0),
        ),
        name="cache-invalidator",
    )
    warmup = asyncio.create_task(_warm_dashboards(resources.db), name="dashboard-warmup")
    metrics_tasks = start_background(app)
    try:
        yield
    finally:
        for task in metrics_tasks:
            await _stop_task(task)
        await _stop_task(warmup)
        await _stop_task(invalidator)
        await close_quietly("subscriber redis", subscriber_redis.aclose)
        await close_resources(resources)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="UVO Analytics API",
        description="Aggregated analytics endpoints for Slovak government procurement data",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # No cookies or sessions are used; credentialed CORS is pure risk.
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )

    register_error_handlers(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "uvo-api"}

    @app.get("/readyz")
    async def readyz(
        response: Response,
        db: Db,
        probe: Annotated[SearchIndexProbe, Depends(get_index_probe)],
    ) -> dict:
        """Readiness: 200 only when MongoDB answers a bounded ping and the required
        Atlas Search indexes exist (cached briefly); /health stays liveness."""
        if await mongo_ready(db) and await probe.ready(db):
            return {"status": "ready", "service": "uvo-api"}
        response.status_code = 503
        return {"status": "unavailable", "service": "uvo-api"}

    app.include_router(contracts.router)
    app.include_router(suppliers.router)
    app.include_router(procurers.router)
    app.include_router(firma.router)
    app.include_router(firmy_router)
    app.include_router(dashboard.router)
    app.include_router(analytics.router)
    app.include_router(ingestion.router)
    app.include_router(ingestion_log.router)
    app.include_router(worker_status.router)
    app.include_router(search.router)
    app.include_router(graph.router)

    # Public, monetizable API surface (key auth + rate limits); docs at /v1/docs.
    v1_app = create_v1_app()
    app.state.v1_app = v1_app  # lets install_resources share the lifespan clients with /v1
    app.mount("/v1", v1_app)

    # After routers and the mount so the middleware wraps everything; adds GET /metrics.
    install_metrics(app)

    return app
