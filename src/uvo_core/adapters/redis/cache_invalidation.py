"""Redis pub/sub cache invalidation shared by the API and MCP lifespans.

Subscribes to the ``notices:written`` channel (published by the ingestor after
each write batch) and clears the in-process data caches so freshly ingested
data surfaces without waiting for each query's TTL. Debounced to at most one
clear per ``DEBOUNCE_SECONDS`` so bulk ingestion (many batches/sec) doesn't
thrash the cache.

Degrades gracefully: if Redis is unreachable the subscriber logs once and
returns; the process keeps serving from its TTL-expiring caches.

The Redis client is owned by the caller (the lifespan creates and closes it).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import redis.asyncio as aioredis

from uvo_core.adapters.redis.pubsub import subscribe
from uvo_core.cache import clear_data_caches

logger = logging.getLogger(__name__)

CHANNEL = "notices:written"
DEBOUNCE_SECONDS = 60.0


async def run_cache_invalidator(
    redis: aioredis.Redis,
    on_invalidate: Callable[[], None] = clear_data_caches,
) -> None:
    """Long-lived task: call ``on_invalidate`` on ``notices:written`` events.

    Runs until cancelled (shutdown). A Redis outage ends the loop rather than
    crashing the app; the next startup creates a fresh subscriber.
    """
    # -inf, not 0.0: time.monotonic() counts from boot, so on a host up for
    # less than DEBOUNCE_SECONDS a 0.0 seed makes the first event look like it
    # arrived inside the debounce window and the first invalidation is skipped.
    last_clear = float("-inf")
    try:
        async for _msg in subscribe(redis, CHANNEL):
            now = time.monotonic()
            if now - last_clear < DEBOUNCE_SECONDS:
                continue
            last_clear = now
            on_invalidate()
            logger.info("data caches cleared on %s event", CHANNEL)
    except asyncio.CancelledError:
        raise
    except Exception:  # Redis unreachable / dropped — degrade, don't crash
        logger.warning("cache invalidation subscriber stopped; Redis unreachable?", exc_info=True)
