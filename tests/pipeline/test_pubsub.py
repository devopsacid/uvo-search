"""Unit tests for uvo_pipeline.pubsub."""

import asyncio

import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from uvo_pipeline.pubsub import publish, subscribe


@pytest_asyncio.fixture
async def redis():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_publish_subscribe_roundtrip(redis):
    channel = "test-channel"
    received: list[dict] = []

    async def collect_one():
        async for msg in subscribe(redis, channel):
            received.append(msg)
            break  # stop after first message

    task = asyncio.create_task(collect_one())
    # Give the subscriber time to register before publishing
    await asyncio.sleep(0.05)

    await publish(redis, channel, {"event": "notice_ready", "source": "crz"})

    await asyncio.wait_for(task, timeout=2.0)
    assert len(received) == 1
    assert received[0] == {"event": "notice_ready", "source": "crz"}
