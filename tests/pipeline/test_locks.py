"""Unit tests for uvo_pipeline.locks."""

import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from uvo_pipeline.locks import acquire_lock, lock, release_lock


@pytest_asyncio.fixture
async def redis():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_acquire_lock_succeeds_when_unset(redis):
    acquired = await acquire_lock(redis, "lock:test", "instance-1", ttl_seconds=30)
    assert acquired is True


async def test_acquire_lock_fails_when_held_by_other(redis):
    await acquire_lock(redis, "lock:test", "instance-1", ttl_seconds=30)
    acquired = await acquire_lock(redis, "lock:test", "instance-2", ttl_seconds=30)
    assert acquired is False


async def test_release_lock_only_by_owner(redis):
    await acquire_lock(redis, "lock:test", "instance-1", ttl_seconds=30)
    released = await release_lock(redis, "lock:test", "instance-2")
    assert released is False
    # original owner can still release
    released = await release_lock(redis, "lock:test", "instance-1")
    assert released is True


async def test_lock_context_manager_releases_on_exit(redis):
    async with lock(redis, "lock:ctx", "inst-1", 30) as acquired:
        assert acquired is True
        raw = await redis.get("lock:ctx")
        assert raw is not None

    raw = await redis.get("lock:ctx")
    assert raw is None
