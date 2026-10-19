"""Factories for the shared Mongo / Neo4j / Redis clients.

Every client is built with explicit connect/selection timeouts and pool bounds so
an unreachable backend fails fast (and surfaces as a 503) instead of hanging a
request for the driver's default 30s. Values are plain keyword arguments so the
delivery packages can feed them from their own settings; the defaults here are
the fallback.

Clients are *not* cached: the owner (an application lifespan) creates them once,
keeps them on its state object and closes them on shutdown.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

DEFAULT_MONGO_SERVER_SELECTION_TIMEOUT_MS = 5_000
DEFAULT_MONGO_CONNECT_TIMEOUT_MS = 5_000
DEFAULT_MONGO_MAX_POOL_SIZE = 50
DEFAULT_NEO4J_CONNECTION_TIMEOUT_S = 5.0
DEFAULT_NEO4J_MAX_POOL_SIZE = 50
DEFAULT_REDIS_SOCKET_TIMEOUT_S = 5.0
DEFAULT_REDIS_CONNECT_TIMEOUT_S = 5.0


def make_mongo_client(
    uri: str,
    *,
    server_selection_timeout_ms: int = DEFAULT_MONGO_SERVER_SELECTION_TIMEOUT_MS,
    connect_timeout_ms: int = DEFAULT_MONGO_CONNECT_TIMEOUT_MS,
    max_pool_size: int = DEFAULT_MONGO_MAX_POOL_SIZE,
) -> AsyncIOMotorClient:
    """Motor client with bounded server selection, connect time and pool size."""
    return AsyncIOMotorClient(
        uri,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        connectTimeoutMS=connect_timeout_ms,
        maxPoolSize=max_pool_size,
    )


def make_neo4j_driver(
    uri: str,
    user: str,
    password: str,
    *,
    connection_timeout: float = DEFAULT_NEO4J_CONNECTION_TIMEOUT_S,
    max_connection_pool_size: int = DEFAULT_NEO4J_MAX_POOL_SIZE,
) -> Any:
    """Async Neo4j driver with a bounded connect time and pool size."""
    from neo4j import AsyncGraphDatabase

    return AsyncGraphDatabase.driver(
        uri,
        auth=(user, password),
        connection_timeout=connection_timeout,
        max_connection_pool_size=max_connection_pool_size,
    )


def make_redis(
    url: str,
    password: str | None = None,
    *,
    decode_responses: bool = True,
    socket_timeout: float | None = DEFAULT_REDIS_SOCKET_TIMEOUT_S,
    socket_connect_timeout: float | None = DEFAULT_REDIS_CONNECT_TIMEOUT_S,
    health_check_interval: int = 0,
) -> aioredis.Redis:
    """Async Redis client with explicit socket timeouts.

    Long-lived pub/sub consumers must pass ``socket_timeout=None`` (an idle
    channel would otherwise raise a read timeout) and a non-zero
    ``health_check_interval`` so dead connections are still detected.
    """
    return aioredis.from_url(
        url,
        password=password or None,
        decode_responses=decode_responses,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        health_check_interval=health_check_interval,
    )


async def close_quietly(label: str, closer: Callable[[], Any]) -> None:
    """Call ``closer`` (a ``close``/``aclose`` method), await it if needed, never raise."""
    try:
        result = closer()
        if inspect.isawaitable(result):
            await result
        logger.debug("%s closed", label)
    except Exception:  # noqa: BLE001 - shutdown must not fail on one client
        logger.warning("closing %s failed", label, exc_info=True)
