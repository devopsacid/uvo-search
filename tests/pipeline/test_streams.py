"""Unit tests for uvo_pipeline.streams."""

import json

import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from uvo_pipeline.streams import (
    ack,
    decode_entry,
    ensure_consumer_group,
    read_group,
    xadd_notice,
)

STREAM = "notices:test"
GROUP = "test-group"
CONSUMER = "worker-1"


@pytest_asyncio.fixture
async def redis():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_xadd_notice_writes_payload(redis):
    entry_id = await xadd_notice(
        redis, "test", {"title": "hello"}, content_hash="abc123", run_id="run-1"
    )
    assert entry_id is not None
    entries = await redis.xrange(STREAM)
    assert len(entries) == 1
    _id, fields = entries[0]
    assert json.loads(fields[b"payload"]) == {"title": "hello"}
    assert fields[b"hash"] == b"abc123"
    assert fields[b"run"] == b"run-1"


async def test_ensure_consumer_group_idempotent(redis):
    await xadd_notice(redis, "test", {}, content_hash="h", run_id="r")
    await ensure_consumer_group(redis, STREAM, GROUP)
    # second call must not raise
    await ensure_consumer_group(redis, STREAM, GROUP)


async def test_read_group_returns_decoded_entries(redis):
    await ensure_consumer_group(redis, STREAM, GROUP)
    await xadd_notice(redis, "test", {"k": "v"}, content_hash="h1", run_id="r1")

    results = await read_group(redis, GROUP, CONSUMER, [STREAM], block_ms=None)
    assert len(results) == 1
    stream_name, entries = results[0]
    assert stream_name == STREAM
    assert len(entries) == 1
    _id, fields = entries[0]
    assert b"payload" in fields


async def test_ack_removes_entries(redis):
    await ensure_consumer_group(redis, STREAM, GROUP)
    await xadd_notice(redis, "test", {}, content_hash="h", run_id="r")
    results = await read_group(redis, GROUP, CONSUMER, [STREAM], block_ms=None)
    _stream, entries = results[0]
    entry_id, _fields = entries[0]

    acked = await ack(redis, STREAM, GROUP, [entry_id])
    assert acked == 1

    pending = await redis.xpending(STREAM, GROUP)
    assert pending["pending"] == 0


async def test_decode_entry_parses_payload():
    raw: dict[bytes, bytes] = {
        b"payload": b'{"id": 1}',
        b"hash": b"deadbeef",
        b"run": b"run-42",
    }
    decoded = decode_entry(raw)
    assert decoded["payload"] == {"id": 1}
    assert decoded["hash"] == "deadbeef"
    assert decoded["run"] == "run-42"
