"""Redis pub/sub cache invalidation for the analytics API.

Subscribes to the ``notices:written`` channel (published by the ingestor after
each write batch) and clears the in-process analytics caches so freshly ingested
data surfaces without waiting for each query's TTL. Debounced to at most one
clear per ``DEBOUNCE_SECONDS`` so bulk ingestion (many batches/sec) doesn't
thrash the cache.

Degrades gracefully: if Redis is unreachable the subscriber logs once and
returns; the API keeps serving from its TTL-expiring caches. This is the same
best-effort tolerance the /v1 rate limiter applies to Redis.
"""

from __future__ import annotations

import asyncio
import logging
import time

import redis.asyncio as aioredis

from uvo_api.config import get_settings
from uvo_core.adapters.mongo.analytics import clear_analytics_caches
from uvo_pipeline.pubsub import subscribe

logger = logging.getLogger(__name__)

CHANNEL = "notices:written"
DEBOUNCE_SECONDS = 60.0


async def run_cache_invalidator() -> None:
    """Long-lived task: clear analytics caches on ``notices:written`` events.

    Runs until cancelled (API shutdown). A single Redis outage ends the loop
    rather than crashing the app; on the next startup a fresh subscriber is
    created by the lifespan.
    """
    settings = get_settings()
    redis = aioredis.from_url(
        settings.redis_url,
        password=settings.redis_password or None,
        decode_responses=True,
    )
    last_clear = 0.0
    try:
        async for _msg in subscribe(redis, CHANNEL):
            now = time.monotonic()
            if now - last_clear < DEBOUNCE_SECONDS:
                continue
            last_clear = now
            clear_analytics_caches()
            logger.info("analytics caches cleared on %s event", CHANNEL)
    except asyncio.CancelledError:
        raise
    except Exception:  # Redis unreachable / dropped — degrade, don't crash
        logger.warning("cache invalidation subscriber stopped; Redis unreachable?", exc_info=True)
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass
