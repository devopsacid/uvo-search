"""Only one dedup worker may run a dedup pass at a time (P17)."""

import fakeredis.aioredis
import pytest

from uvo_workers.dedup import DEDUP_LOCK_KEY, run_under_lock


@pytest.mark.asyncio
async def test_runs_and_releases_when_lock_free():
    redis = fakeredis.aioredis.FakeRedis()
    ran = []

    async def work():
        ran.append(await redis.get(DEDUP_LOCK_KEY))

    assert await run_under_lock(redis, "inst-a", 60, work) is True

    assert ran == [b"inst-a"], "lock held while running"
    assert await redis.get(DEDUP_LOCK_KEY) is None, "lock released afterwards"


@pytest.mark.asyncio
async def test_skips_when_another_instance_holds_the_lock():
    redis = fakeredis.aioredis.FakeRedis()
    await redis.set(DEDUP_LOCK_KEY, "inst-b", nx=True, ex=60)
    ran = []

    async def work():
        ran.append(True)

    assert await run_under_lock(redis, "inst-a", 60, work) is False

    assert ran == []
    assert await redis.get(DEDUP_LOCK_KEY) == b"inst-b", "other holder untouched"


@pytest.mark.asyncio
async def test_releases_lock_when_work_raises():
    redis = fakeredis.aioredis.FakeRedis()

    async def work():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_under_lock(redis, "inst-a", 60, work)

    assert await redis.get(DEDUP_LOCK_KEY) is None
