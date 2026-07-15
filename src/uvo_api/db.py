# src/uvo_api/db.py
"""Lazy shared resource handles for the analytics API.

The API now runs its queries in-process via uvo_core services, so it holds the same
resources the MCP server does: a Motor client, an optional Neo4j driver, and an
optional FastEmbed model. All are created lazily on first use (mirroring the existing
get_db pattern and keeping TestClient — which does not run the app lifespan — working).
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from uvo_api.config import get_settings

_client: AsyncIOMotorClient | None = None
_neo4j_driver: Any | None = None
_embedder: Any | None = None
_embedder_loaded = False


def get_db() -> AsyncIOMotorDatabase:
    """Return the shared Motor database handle, creating the client on first call."""
    global _client
    settings = get_settings()
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client[settings.mongodb_database]


def get_neo4j_driver() -> Any | None:
    """Return the shared Neo4j async driver, or None when Neo4j is not configured."""
    global _neo4j_driver
    settings = get_settings()
    if not settings.neo4j_uri or not settings.neo4j_password:
        return None
    if _neo4j_driver is None:
        from neo4j import AsyncGraphDatabase

        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _neo4j_driver


def get_embedder() -> Any | None:
    """Return the shared FastEmbed model, or None when unavailable (degrades vector search)."""
    global _embedder, _embedder_loaded
    if not _embedder_loaded:
        from uvo_core.adapters.embedding import load_embedder

        _embedder = load_embedder()
        _embedder_loaded = True
    return _embedder


def get_notice_repo():
    """NoticeRepository port bound to the shared Mongo handle."""
    from uvo_core.adapters.mongo.repositories import MongoNoticeRepository

    return MongoNoticeRepository(get_db())


def get_company_repo():
    """CompanyRepository port bound to the shared Mongo handle."""
    from uvo_core.adapters.mongo.repositories import MongoCompanyRepository

    return MongoCompanyRepository(get_db())


def get_analytics():
    """CompanyAnalytics port bound to the shared Mongo handle."""
    from uvo_core.adapters.mongo.analytics import MongoCompanyAnalytics

    return MongoCompanyAnalytics(get_db())


def get_graph_store():
    """GraphStore port, or None when Neo4j is not configured."""
    driver = get_neo4j_driver()
    if driver is None:
        return None
    from uvo_core.adapters.neo4j.graph import Neo4jGraphStore

    return Neo4jGraphStore(driver)
