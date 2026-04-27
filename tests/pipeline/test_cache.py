"""Unit tests for uvo_pipeline.cache backends."""

import time

import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from uvo_pipeline.cache.memory import MemoryCache
from uvo_pipeline.cache.redis import RedisCache


@pytest_asyncio.fixture
async def redis():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_memory_cache_get_set_ttl_expiry(monkeypatch):
    cache = MemoryCache()
    await cache.set("k", {"v": 1}, ttl_seconds=1)
    assert await cache.get("k") == {"v": 1}

    # Simulate expiry by fast-forwarding monotonic clock
    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 2)
    assert await cache.get("k") is None


async def test_redis_cache_get_set_returns_dict(redis):
    cache = RedisCache(redis, prefix="test:")
    await cache.set("notice-1", {"title": "foo"}, ttl_seconds=60)
    result = await cache.get("notice-1")
    assert result == {"title": "foo"}


async def test_redis_cache_ttl_applied(redis):
    cache = RedisCache(redis, prefix="test:")
    await cache.set("notice-2", {"x": 42}, ttl_seconds=10)
    ttl = await redis.ttl("test:notice-2")
    assert 0 < ttl <= 10
