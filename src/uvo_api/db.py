# src/uvo_api/db.py
"""Lifespan-owned resource handles for the analytics API, exposed via FastAPI ``Depends``.

The API runs its queries in-process via uvo_core services, so it holds the same
resources the MCP server does: a Motor client, an optional Neo4j driver, an optional
FastEmbed model and a Redis client (rate limiting / usage metering). They are built
once by ``build_resources`` in the app lifespan, stored on ``app.state.resources`` and
closed on shutdown by ``close_resources``. There are no module-level clients.

Routers and other dependencies take them with ``Depends(get_db)`` etc. Because the
public ``/v1`` surface is a mounted sub-app (its ``request.app`` is not the parent),
``install_resources`` publishes the same object on both apps.

Contexts that never run the lifespan (``TestClient`` used without ``with``) fall back
to building the resources on first use; Motor/Neo4j/Redis clients connect lazily, so
this performs no I/O.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from uvo_api.config import ApiSettings, get_settings
from uvo_core.adapters.mongo.search_indexes import SearchIndexProbe
from uvo_core.errors import BackendUnavailable
from uvo_core.infra.clients import (
    close_quietly,
    make_mongo_client,
    make_neo4j_driver,
    make_redis,
)

logger = logging.getLogger(__name__)


@dataclass
class Resources:
    """Everything the API process shares across requests; owned by the app lifespan."""

    mongo_client: AsyncIOMotorClient
    db: AsyncIOMotorDatabase
    redis: aioredis.Redis
    neo4j_driver: Any | None = None
    index_probe: SearchIndexProbe = field(default_factory=SearchIndexProbe)
    # Loaded lazily on first vector search: the model load is slow and optional.
    _embedder: Any | None = None
    _embedder_loaded: bool = False

    def embedder(self) -> Any | None:
        """FastEmbed model, or None when unavailable (degrades vector search)."""
        if not self._embedder_loaded:
            from uvo_core.adapters.embedding import load_embedder

            self._embedder = load_embedder()
            self._embedder_loaded = True
        return self._embedder


def build_resources(settings: ApiSettings) -> Resources:
    """Create the shared clients with the configured timeouts and pool bounds."""
    mongo_client = make_mongo_client(
        settings.mongodb_uri,
        server_selection_timeout_ms=settings.mongo_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongo_connect_timeout_ms,
        max_pool_size=settings.mongo_max_pool_size,
    )
    neo4j_driver = None
    if settings.neo4j_uri and settings.neo4j_password:
        neo4j_driver = make_neo4j_driver(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            connection_timeout=settings.neo4j_connection_timeout,
            max_connection_pool_size=settings.neo4j_max_pool_size,
        )
    redis_client = make_redis(
        settings.redis_url,
        settings.redis_password,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
    )
    return Resources(
        mongo_client=mongo_client,
        db=mongo_client[settings.mongodb_database],
        redis=redis_client,
        neo4j_driver=neo4j_driver,
    )


async def close_resources(resources: Resources) -> None:
    """Close every client; one failing close never prevents the others."""
    await close_quietly("redis", resources.redis.aclose)
    if resources.neo4j_driver is not None:
        await close_quietly("neo4j driver", resources.neo4j_driver.close)
    await close_quietly("mongo client", resources.mongo_client.close)


def install_resources(app: FastAPI, resources: Resources) -> None:
    """Publish ``resources`` on ``app`` and on its mounted /v1 sub-app (if any)."""
    app.state.resources = resources
    v1_app = getattr(app.state, "v1_app", None)
    if v1_app is not None:
        v1_app.state.resources = resources


# --- FastAPI dependencies -------------------------------------------------------


def get_resources(request: Request) -> Resources:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        # No lifespan ran (TestClient without ``with``): build lazily, no I/O happens.
        logger.debug("resources not installed by lifespan; building on first use")
        resources = build_resources(get_settings())
        request.app.state.resources = resources
    return resources


ResourcesDep = Annotated[Resources, Depends(get_resources)]


def get_db(resources: ResourcesDep) -> AsyncIOMotorDatabase:
    """The shared Motor database handle."""
    return resources.db


def get_neo4j_driver(resources: ResourcesDep) -> Any | None:
    """The shared Neo4j async driver, or None when Neo4j is not configured."""
    return resources.neo4j_driver


def require_neo4j_driver(driver: Annotated[Any | None, Depends(get_neo4j_driver)]) -> Any:
    """Neo4j driver or a typed 503 (``BackendUnavailable``) when not configured."""
    if driver is None:
        raise BackendUnavailable("Neo4j not connected")
    return driver


def get_embedder(resources: ResourcesDep) -> Any | None:
    """The shared FastEmbed model, or None when unavailable."""
    return resources.embedder()


def get_redis(resources: ResourcesDep) -> aioredis.Redis:
    """The shared Redis client (rate limiting, usage metering)."""
    return resources.redis


def get_index_probe(resources: ResourcesDep) -> SearchIndexProbe:
    return resources.index_probe


Db = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
Neo4jDriver = Annotated[Any, Depends(require_neo4j_driver)]
OptionalEmbedder = Annotated[Any | None, Depends(get_embedder)]


def get_notice_repo(db: Db):
    """NoticeRepository port bound to the shared Mongo handle."""
    from uvo_core.adapters.mongo.repositories import MongoNoticeRepository

    return MongoNoticeRepository(db)


def get_company_repo(db: Db):
    """CompanyRepository port bound to the shared Mongo handle."""
    from uvo_core.adapters.mongo.repositories import MongoCompanyRepository

    return MongoCompanyRepository(db)


def get_analytics(db: Db):
    """CompanyAnalytics port bound to the shared Mongo handle."""
    from uvo_core.adapters.mongo.analytics import MongoCompanyAnalytics

    return MongoCompanyAnalytics(db)


def make_dashboard_analytics(db):
    """DashboardAnalytics port bound to a Mongo handle (also used by the lifespan warm-up)."""
    from uvo_core.adapters.mongo.dashboards import MongoDashboardAnalytics

    return MongoDashboardAnalytics(db)


def get_dashboard_analytics(db: Db):
    """DashboardAnalytics port (``/api/analytics``) bound to the shared Mongo handle."""
    return make_dashboard_analytics(db)


def get_graph_store(driver: Annotated[Any | None, Depends(get_neo4j_driver)]):
    """GraphStore port, or None when Neo4j is not configured."""
    if driver is None:
        return None
    from uvo_core.adapters.neo4j.graph import Neo4jGraphStore

    return Neo4jGraphStore(driver)
