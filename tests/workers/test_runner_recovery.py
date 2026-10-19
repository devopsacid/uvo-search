"""A successful extract cycle must clear a previous cycle's last_error (P19)."""

import asyncio

import fakeredis.aioredis
import pytest
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.runner as runner_mod
from uvo_core.adapters.redis.client import RedisSettings
from uvo_workers.runner import run_extractor_loop


@pytest.mark.asyncio
async def test_last_error_cleared_after_successful_cycle(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(runner_mod, "AsyncIOMotorClient", AsyncMongoMockClient)

    async def fake_get(url=None, password=None):
        return fake_redis

    async def fake_close(client):
        pass

    monkeypatch.setattr(runner_mod, "get_redis", fake_get)
    monkeypatch.setattr(runner_mod, "close_redis", fake_close)

    snapshots = []

    async def fake_serve_health(port, snapshot, **kwargs):
        snapshots.append(snapshot)
        await asyncio.Event().wait()

    monkeypatch.setattr(runner_mod, "serve_health", fake_serve_health)

    calls = [0]
    done = asyncio.Event()

    async def extract(redis, state):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("transient upstream failure")
        done.set()
        return 3

    task = asyncio.create_task(
        run_extractor_loop(
            source="flaky",
            interval_seconds=0,
            extract=extract,
            redis_settings=RedisSettings(redis_url="redis://x:6379/0", redis_password=""),
            health_port=9999,
            instance_id="t",
        )
    )
    try:
        await asyncio.wait_for(done.wait(), timeout=5)
        await asyncio.sleep(0.05)
        snap = snapshots[0]()
        assert snap["last_error"] is None
        assert snap["cycles_completed"] >= 1
        assert snap["last_success_at"] is not None
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, SystemExit):
            pass
