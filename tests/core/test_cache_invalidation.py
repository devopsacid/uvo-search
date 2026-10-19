"""Tests for the shared notices:written cache-invalidation subscriber (A14)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_core.adapters.redis import cache_invalidation
from uvo_core.cache import async_ttl_cache, clear_data_caches


def _counter():
    calls = {"n": 0}
    return calls, lambda: calls.__setitem__("n", calls["n"] + 1)


def test_clear_analytics_caches_runs():
    from uvo_core.adapters.mongo import analytics

    analytics.clear_analytics_caches()  # smoke: must not raise
    assert analytics._market_cpv_agg.cache_info()["size"] == 0
    assert analytics._firma_core_agg.cache_info()["size"] == 0
    assert analytics._firma_partners_agg.cache_info()["size"] == 0


@pytest.mark.asyncio
async def test_clear_data_caches_clears_registered_but_not_opted_out():
    @async_ttl_cache(maxsize=4, ttl=60)
    async def data_dependent(x):
        return x

    @async_ttl_cache(maxsize=4, ttl=60, depends_on_data=False)
    async def stable(x):
        return x

    await data_dependent(1)
    await stable(1)
    clear_data_caches()
    assert data_dependent.cache_info()["size"] == 0
    assert stable.cache_info()["size"] == 1


def test_clear_data_caches_covers_mcp_side_caches():
    """MCP's entity/procurement/autocomplete caches are in the registry too."""
    from uvo_core.adapters.mongo.subjects import entity_search

    entity_search.cache_clear()
    clear_data_caches()  # must reach caches beyond analytics; smoke-checked by registry size
    from uvo_core import cache

    assert len(cache._DATA_CACHE_CLEARERS) >= 10


@pytest.mark.asyncio
async def test_debounces_burst_to_single_clear(monkeypatch):
    """A burst clears once immediately, plus one trailing flush (not one per event)."""
    calls, on_invalidate = _counter()

    async def fake_subscribe(redis, channel):
        for _ in range(10):
            yield {"source": "crz", "count": 1}

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator(MagicMock(), on_invalidate)

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_first_event_clears_on_a_freshly_booted_host(monkeypatch):
    """The first event must clear even when time.monotonic() is near zero.

    time.monotonic() counts from boot. Seeding last_clear to 0.0 made the first
    event on a host up for less than DEBOUNCE_SECONDS look like it arrived
    inside the debounce window, silently skipping the first invalidation.
    """
    calls, on_invalidate = _counter()
    monkeypatch.setattr(cache_invalidation.time, "monotonic", lambda: 0.5)

    async def fake_subscribe(redis, channel):
        yield {"source": "crz", "count": 1}

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator(MagicMock(), on_invalidate)

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_default_callback_clears_data_caches(monkeypatch):
    """Without an explicit callback the shared registry is cleared (what MCP relies on)."""

    @async_ttl_cache(maxsize=4, ttl=60)
    async def cached(x):
        return x

    await cached(1)
    assert cached.cache_info()["size"] == 1

    async def fake_subscribe(redis, channel):
        yield {"source": "crz", "count": 1}

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)
    await cache_invalidation.run_cache_invalidator(MagicMock())

    assert cached.cache_info()["size"] == 0


@pytest.mark.asyncio
async def test_redis_error_degrades_without_raising(monkeypatch):
    """An unreachable Redis ends the loop quietly instead of crashing the app."""

    async def failing_subscribe(redis, channel):
        raise ConnectionError("redis down")
        yield  # pragma: no cover — makes this an async generator

    monkeypatch.setattr(cache_invalidation, "subscribe", failing_subscribe)

    await cache_invalidation.run_cache_invalidator(AsyncMock())  # must not raise


@pytest.mark.asyncio
async def test_events_inside_window_get_one_trailing_clear(monkeypatch):
    """Leading + trailing debounce: a burst yields an immediate clear and one trailing clear."""
    calls, on_invalidate = _counter()

    async def fake_subscribe(redis, channel):
        for _ in range(10):
            yield {"source": "crz", "count": 1}
        await asyncio.sleep(0.2)  # outlive the trailing timer, as the real subscriber would

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator(MagicMock(), on_invalidate, debounce=0.05)

    assert calls["n"] == 2  # leading + exactly one trailing


@pytest.mark.asyncio
async def test_no_trailing_clear_when_window_saw_one_event(monkeypatch):
    calls, on_invalidate = _counter()

    async def fake_subscribe(redis, channel):
        yield {"source": "crz", "count": 1}
        await asyncio.sleep(0.15)

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator(MagicMock(), on_invalidate, debounce=0.05)

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_pending_trailing_clear_is_flushed_when_stream_ends(monkeypatch):
    """Events seen but not yet applied must not be lost when the subscriber stops."""
    calls, on_invalidate = _counter()

    async def fake_subscribe(redis, channel):
        yield {"source": "crz", "count": 1}
        yield {"source": "crz", "count": 1}

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator(MagicMock(), on_invalidate, debounce=30.0)

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_after_clear_hook_runs_after_each_clear_and_failures_are_swallowed(monkeypatch):
    order: list[str] = []

    async def after_clear():
        order.append("warm")
        raise RuntimeError("warm-up blew up")

    async def fake_subscribe(redis, channel):
        yield {"source": "crz", "count": 1}
        await asyncio.sleep(0.05)

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator(
        MagicMock(), lambda: order.append("clear"), after_clear=after_clear
    )

    assert order == ["clear", "warm"]
