"""Redis pub/sub cache invalidation shared by the API and MCP lifespans.

Subscribes to the ``notices:written`` channel (published by the ingestor after
each write batch) and clears the in-process data caches so freshly ingested
data surfaces without waiting for each query's TTL. Debounced (leading +
trailing) to at most one clear per ``DEBOUNCE_SECONDS`` so bulk ingestion (many
batches/sec) doesn't thrash the cache but never leaves it stale afterwards.

Degrades gracefully: if Redis is unreachable the subscriber logs once and
returns; the process keeps serving from its TTL-expiring caches.

The Redis client is owned by the caller (the lifespan creates and closes it).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis

from uvo_core.adapters.redis.pubsub import subscribe
from uvo_core.cache import clear_data_caches

logger = logging.getLogger(__name__)

CHANNEL = "notices:written"
DEBOUNCE_SECONDS = 60.0


async def run_cache_invalidator(
    redis: aioredis.Redis,
    on_invalidate: Callable[[], None] = clear_data_caches,
    after_clear: Callable[[], Awaitable[None]] | None = None,
    debounce: float = DEBOUNCE_SECONDS,
) -> None:
    """Long-lived task: call ``on_invalidate`` on ``notices:written`` events.

    Debounce is leading + trailing: the first event clears immediately; events
    arriving inside the window schedule exactly one trailing clear at the window
    end, so the tail of an ingestion burst is never left stale. ``after_clear``
    (e.g. the analytics warm-up) runs as a best-effort background task after each
    clear; at most one runs at a time and its failures are only logged.

    Runs until cancelled (shutdown). A Redis outage ends the loop rather than
    crashing the app; the next startup creates a fresh subscriber.
    """
    # -inf, not 0.0: time.monotonic() counts from boot, so on a host up for
    # less than the window a 0.0 seed makes the first event look like it
    # arrived inside the debounce window and the first invalidation is skipped.
    last_clear = float("-inf")
    trailing: asyncio.Task | None = None
    follow_up: asyncio.Task | None = None

    async def _run_after_clear() -> None:
        try:
            await after_clear()  # type: ignore[misc]
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - warm-up is an optimisation
            logger.warning("post-invalidation hook failed", exc_info=True)

    def _clear(reason: str) -> None:
        nonlocal last_clear, follow_up
        last_clear = time.monotonic()
        on_invalidate()
        logger.info("data caches cleared (%s) on %s event", reason, CHANNEL)
        if after_clear is not None and (follow_up is None or follow_up.done()):
            follow_up = asyncio.create_task(_run_after_clear(), name="post-invalidation")

    async def _trailing_clear(delay: float) -> None:
        await asyncio.sleep(delay)
        _clear("trailing")

    def _trailing_pending() -> bool:
        return trailing is not None and not trailing.done()

    try:
        async for _msg in subscribe(redis, CHANNEL):
            now = time.monotonic()
            if now - last_clear >= debounce and not _trailing_pending():
                _clear("leading")
            elif not _trailing_pending():
                trailing = asyncio.create_task(
                    _trailing_clear(max(0.0, last_clear + debounce - now)), name="cache-trailing"
                )
        # Stream ended with a trailing clear still scheduled: apply it now.
        if _trailing_pending():
            trailing.cancel()  # type: ignore[union-attr]
            _clear("flush")
    except asyncio.CancelledError:
        raise
    except Exception:  # Redis unreachable / dropped — degrade, don't crash
        logger.warning("cache invalidation subscriber stopped; Redis unreachable?", exc_info=True)
        if _trailing_pending():
            trailing.cancel()  # type: ignore[union-attr]
            _clear("flush")
    finally:
        for task in (trailing, follow_up):
            if task is not None and not task.done():
                task.cancel()
