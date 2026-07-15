"""Tests for the notices:written analytics-cache invalidation subscriber."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_api import cache_invalidation


@pytest.fixture
def fake_redis(monkeypatch):
    client = MagicMock()
    client.aclose = AsyncMock()
    monkeypatch.setattr(cache_invalidation.aioredis, "from_url", lambda *a, **kw: client)
    return client


def test_clear_analytics_caches_runs():
    from uvo_core.adapters.mongo import analytics

    analytics.clear_analytics_caches()  # smoke: must not raise
    assert analytics._market_cpv_agg.cache_info()["size"] == 0
    assert analytics._firma_core_agg.cache_info()["size"] == 0
    assert analytics._firma_partners_agg.cache_info()["size"] == 0


@pytest.mark.asyncio
async def test_debounces_burst_to_single_clear(monkeypatch, fake_redis):
    """A burst of events within the debounce window clears the caches once."""
    calls = {"n": 0}
    monkeypatch.setattr(cache_invalidation, "clear_analytics_caches", lambda: calls.__setitem__("n", calls["n"] + 1))

    async def fake_subscribe(redis, channel):
        for _ in range(10):
            yield {"source": "crz", "count": 1}

    monkeypatch.setattr(cache_invalidation, "subscribe", fake_subscribe)

    await cache_invalidation.run_cache_invalidator()

    assert calls["n"] == 1
    fake_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_error_degrades_without_raising(monkeypatch, fake_redis):
    """An unreachable Redis ends the loop quietly instead of crashing the app."""

    async def failing_subscribe(redis, channel):
        raise ConnectionError("redis down")
        yield  # pragma: no cover — makes this an async generator

    monkeypatch.setattr(cache_invalidation, "subscribe", failing_subscribe)

    await cache_invalidation.run_cache_invalidator()  # must not raise
    fake_redis.aclose.assert_awaited_once()
