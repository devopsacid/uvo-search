"""Tests for uvo_workers.runner."""

import asyncio
from contextlib import asynccontextmanager

import fakeredis.aioredis
import pytest

import uvo_workers.runner as runner_mod
from uvo_pipeline.redis_client import RedisSettings
from uvo_workers.runner import run_extractor_loop


def _fake_redis_settings() -> RedisSettings:
    return RedisSettings(redis_url="redis://localhost:6379/0", redis_password="")


async def _patch_redis(fake_redis):
    """Context manager that injects FakeRedis into the runner module."""

    class _Ctx:
        def __init__(self):
            self._orig_get = runner_mod.get_redis
            self._orig_close = runner_mod.close_redis

        async def __aenter__(self):
            async def fake_get(url=None, password=None):
                return fake_redis

            async def fake_close(client):
                pass

            runner_mod.get_redis = fake_get
            runner_mod.close_redis = fake_close
            return self

        async def __aexit__(self, *_):
            runner_mod.get_redis = self._orig_get
            runner_mod.close_redis = self._orig_close

    return _Ctx()


@pytest.mark.asyncio
async def test_runner_runs_two_cycles():
    fake_redis = fakeredis.aioredis.FakeRedis()
    counter = [0]
    stop_after = asyncio.Event()

    async def extract(redis, state):
        counter[0] += 1
        if counter[0] >= 2:
            stop_after.set()
        return counter[0]

    ctx = await _patch_redis(fake_redis)
    async with ctx:
        loop_task = asyncio.create_task(
            run_extractor_loop(
                source="test_source",
                interval_seconds=0,
                extract=extract,
                redis_settings=_fake_redis_settings(),
                health_port=0,
                instance_id="test-instance",
            )
        )
        await asyncio.wait_for(stop_after.wait(), timeout=5.0)
        loop_task.cancel()
        try:
            await loop_task
        except (asyncio.CancelledError, SystemExit):
            pass

    assert counter[0] == 2


@pytest.mark.asyncio
async def test_runner_skips_when_lock_held_by_other():
    """Pre-acquire the lock with a different instance; runner should skip."""
    fake_redis = fakeredis.aioredis.FakeRedis()
    counter = [0]
    ran_one_cycle = asyncio.Event()

    async def extract(redis, state):
        counter[0] += 1
        return 0

    # Pre-acquire lock as a different instance
    lock_key = "extractor:lock:locked_source"
    await fake_redis.set(lock_key, "other-instance", nx=True, ex=600)

    original_lock = runner_mod.lock

    @asynccontextmanager
    async def patched_lock(redis, key, instance_id, ttl_seconds):
        async with original_lock(redis, key, instance_id, ttl_seconds) as acquired:
            if not acquired:
                ran_one_cycle.set()
            yield acquired

    runner_mod.lock = patched_lock
    ctx = await _patch_redis(fake_redis)

    try:
        async with ctx:
            loop_task = asyncio.create_task(
                run_extractor_loop(
                    source="locked_source",
                    interval_seconds=0,
                    extract=extract,
                    redis_settings=_fake_redis_settings(),
                    health_port=0,
                    instance_id="my-instance",
                )
            )
            await asyncio.wait_for(ran_one_cycle.wait(), timeout=5.0)
            loop_task.cancel()
            try:
                await loop_task
            except (asyncio.CancelledError, SystemExit):
                pass
    finally:
        runner_mod.lock = original_lock

    assert counter[0] == 0


@pytest.mark.asyncio
async def test_runner_records_last_error_and_continues():
    """Extract raises on cycle 1, succeeds on cycle 2. Runner continues after error."""
    fake_redis = fakeredis.aioredis.FakeRedis()
    call_count = [0]
    two_calls = asyncio.Event()

    async def extract(redis, state):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("cycle 1 failure")
        if call_count[0] >= 2:
            two_calls.set()
        return 5

    ctx = await _patch_redis(fake_redis)
    async with ctx:
        loop_task = asyncio.create_task(
            run_extractor_loop(
                source="error_source",
                interval_seconds=0,
                extract=extract,
                redis_settings=_fake_redis_settings(),
                health_port=0,
                instance_id="err-instance",
            )
        )
        await asyncio.wait_for(two_calls.wait(), timeout=5.0)
        loop_task.cancel()
        try:
            await loop_task
        except (asyncio.CancelledError, SystemExit):
            pass

    # cycle 1 raised, cycle 2 succeeded — runner did not exit on the error
    assert call_count[0] >= 2
