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
    # second call must not raise (BUSYGROUP is swallowed)
    await ensure_consumer_group(redis, STREAM, GROUP)


async def test_ensure_consumer_group_creates_from_id_zero(redis):
    """Group must start at id="0", not "$", or pre-existing entries are lost.

    If an extractor XADDs before the ingestor creates the group ("$" =
    tail-only), those entries become permanently unreadable by the group.
    "0" replays the whole stream, which is safe since ingestion is
    idempotent.
    """
    await xadd_notice(redis, "test", {"pre": "existing"}, content_hash="h0", run_id="r0")

    await ensure_consumer_group(redis, STREAM, GROUP)

    results = await read_group(redis, GROUP, CONSUMER, [STREAM], block_ms=None)
    assert len(results) == 1
    stream_name, entries = results[0]
    assert stream_name == STREAM
    assert len(entries) == 1
    _id, fields = entries[0]
    assert json.loads(fields[b"payload"]) == {"pre": "existing"}


async def test_ensure_consumer_group_tolerates_busygroup_after_id_zero(redis):
    """A second call against a stream with new entries must not raise,
    and must not affect entries already pending for existing consumers."""
    await xadd_notice(redis, "test", {"n": 1}, content_hash="h1", run_id="r1")
    await ensure_consumer_group(redis, STREAM, GROUP)

    # Read the first entry into the group's pending list.
    await read_group(redis, GROUP, CONSUMER, [STREAM], block_ms=None)

    # A second XADD followed by a repeat ensure_consumer_group call (e.g. a
    # second extractor instance racing the ingestor) must not raise and must
    # not reset the group's position.
    await xadd_notice(redis, "test", {"n": 2}, content_hash="h2", run_id="r2")
    await ensure_consumer_group(redis, STREAM, GROUP)

    results = await read_group(redis, GROUP, CONSUMER, [STREAM], block_ms=None)
    assert len(results) == 1
    _stream_name, entries = results[0]
    assert len(entries) == 1
    _id, fields = entries[0]
    assert json.loads(fields[b"payload"]) == {"n": 2}


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
