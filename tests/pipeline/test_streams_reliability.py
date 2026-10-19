"""Reliability helpers in uvo_core.adapters.redis.streams: batch XADD, backpressure,
safe trimming, paged reclaim and delivery counts."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from uvo_core.adapters.redis.streams import (
    BackpressureTimeout,
    ack,
    autoclaim_stale,
    delivery_counts,
    ensure_consumer_group,
    group_stats,
    read_group,
    trim_consumed,
    wait_for_capacity,
    xadd_many,
)

STREAM = "notices:test"
GROUP = "ingestor"


@pytest_asyncio.fixture
async def redis():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


def _payload(i: int) -> dict:
    return {"source_id": f"n-{i}", "content_hash": f"h{i}", "pipeline_run_id": "run-1"}


async def test_xadd_many_writes_all_in_order(redis):
    ids = await xadd_many(redis, "test", [_payload(i) for i in range(3)], maxlen=1000)

    assert len(ids) == 3
    entries = await redis.xrange(STREAM)
    assert [json.loads(f[b"payload"])["source_id"] for _, f in entries] == ["n-0", "n-1", "n-2"]
    assert entries[1][1][b"hash"] == b"h1"
    assert entries[1][1][b"run"] == b"run-1"


async def test_xadd_many_uses_one_non_transactional_pipeline():
    redis = AsyncMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[b"1-0", b"2-0"])
    redis.pipeline = lambda **kwargs: _PipeCtx(pipe, kwargs)

    ids = await xadd_many(redis, "test", [_payload(0), _payload(1)], maxlen=10)

    assert ids == [b"1-0", b"2-0"]
    assert pipe.xadd.call_count == 2
    assert _PipeCtx.last_kwargs == {"transaction": False}


class _PipeCtx:
    last_kwargs: dict = {}

    def __init__(self, pipe, kwargs):
        self._pipe = pipe
        _PipeCtx.last_kwargs = kwargs

    async def __aenter__(self):
        return self._pipe

    async def __aexit__(self, *exc):
        return False


async def test_xadd_many_empty_is_noop(redis):
    assert await xadd_many(redis, "test", [], maxlen=10) == []


async def test_group_stats_without_stream_reports_zero(redis):
    stats = await group_stats(redis, STREAM, GROUP)
    assert stats["backlog"] == 0
    assert stats["pending"] == 0


async def test_group_stats_without_group_uses_stream_length(redis):
    await xadd_many(redis, "test", [_payload(i) for i in range(4)], maxlen=1000)
    stats = await group_stats(redis, STREAM, GROUP)
    assert stats["backlog"] == 4


async def test_group_stats_counts_unread_and_pending(redis):
    await xadd_many(redis, "test", [_payload(i) for i in range(5)], maxlen=1000)
    await ensure_consumer_group(redis, STREAM, GROUP)
    await read_group(redis, GROUP, "c1", [STREAM], count=3, block_ms=None)

    stats = await group_stats(redis, STREAM, GROUP)

    assert stats["pending"] == 3
    # 2 unread + 3 delivered-but-unacked; fakeredis may over-report lag by one.
    assert stats["backlog"] >= 5


async def test_wait_for_capacity_returns_immediately_below_high_water(redis):
    await xadd_many(redis, "test", [_payload(0)], maxlen=1000)
    sleep = AsyncMock()
    await wait_for_capacity(redis, STREAM, GROUP, high_water=10, sleep=sleep)
    sleep.assert_not_awaited()


async def test_wait_for_capacity_pauses_until_consumer_catches_up(redis):
    await xadd_many(redis, "test", [_payload(i) for i in range(6)], maxlen=1000)
    await ensure_consumer_group(redis, STREAM, GROUP)
    sleeps = 0

    async def drain(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        got = await read_group(redis, GROUP, "c1", [STREAM], count=100, block_ms=None)
        for name, entries in got:
            await ack(redis, name, GROUP, [eid for eid, _ in entries])

    await wait_for_capacity(redis, STREAM, GROUP, high_water=3, sleep=drain)

    assert sleeps >= 1


async def test_wait_for_capacity_times_out(redis):
    await xadd_many(redis, "test", [_payload(i) for i in range(6)], maxlen=1000)
    await ensure_consumer_group(redis, STREAM, GROUP)

    async def fast_sleep(_seconds: float) -> None:
        await asyncio.sleep(0)

    with pytest.raises(BackpressureTimeout):
        await wait_for_capacity(
            redis,
            STREAM,
            GROUP,
            high_water=3,
            poll_seconds=1.0,
            max_wait_seconds=3.0,
            sleep=fast_sleep,
        )


async def test_trim_consumed_never_drops_unread_or_pending(redis):
    await xadd_many(redis, "test", [_payload(i) for i in range(10)], maxlen=1000)
    await ensure_consumer_group(redis, STREAM, GROUP)
    got = await read_group(redis, GROUP, "c1", [STREAM], count=6, block_ms=None)
    ids = [eid for eid, _ in got[0][1]]
    # Ack the first 4, leave 2 pending (ids[4], ids[5]) and 4 unread.
    await ack(redis, STREAM, GROUP, ids[:4])

    await trim_consumed(redis, STREAM, GROUP, approximate=False)

    remaining = [eid for eid, _ in await redis.xrange(STREAM)]
    assert remaining[0] == ids[4], "oldest pending entry must survive"
    assert len(remaining) == 6, "2 pending + 4 unread survive"


async def test_trim_consumed_without_group_is_noop(redis):
    await xadd_many(redis, "test", [_payload(i) for i in range(3)], maxlen=1000)
    assert await trim_consumed(redis, STREAM, GROUP, approximate=False) == 0
    assert await redis.xlen(STREAM) == 3


async def test_autoclaim_pages_through_cursor():
    redis = AsyncMock()
    page1 = [(b"1-0", {b"payload": b"{}"})]
    page2 = [(b"2-0", {b"payload": b"{}"})]
    redis.xautoclaim.side_effect = [(b"2-0", page1, []), (b"0-0", page2, [])]

    entries = await autoclaim_stale(redis, STREAM, GROUP, "c1", count=1)

    assert [e[0] for e in entries] == [b"1-0", b"2-0"]
    starts = [c.kwargs["start_id"] for c in redis.xautoclaim.await_args_list]
    assert starts == ["0-0", b"2-0"]


async def test_autoclaim_stops_at_max_pages():
    redis = AsyncMock()
    redis.xautoclaim.side_effect = [
        (b"9-0", [(b"1-0", {})], []),
        (b"9-1", [(b"2-0", {})], []),
        (b"9-2", [(b"3-0", {})], []),
        (b"9-3", [(b"4-0", {})], []),
    ]

    entries = await autoclaim_stale(redis, STREAM, GROUP, "c1", max_pages=3)

    assert redis.xautoclaim.await_count == 3
    assert len(entries) == 3


async def test_delivery_counts_increase_on_reclaim(redis):
    await xadd_many(redis, "test", [_payload(0), _payload(1)], maxlen=1000)
    await ensure_consumer_group(redis, STREAM, GROUP)
    got = await read_group(redis, GROUP, "c1", [STREAM], count=10, block_ms=None)
    ids = [eid for eid, _ in got[0][1]]

    assert await delivery_counts(redis, STREAM, GROUP, ids) == {ids[0]: 1, ids[1]: 1}

    await autoclaim_stale(redis, STREAM, GROUP, "c2", min_idle_ms=0)

    counts = await delivery_counts(redis, STREAM, GROUP, ids)
    # fakeredis' XAUTOCLAIM cursor re-visits the last entry; real Redis would not.
    assert counts[ids[0]] == 2
    assert counts[ids[1]] >= 2


async def test_delivery_counts_empty():
    assert await delivery_counts(AsyncMock(), STREAM, GROUP, []) == {}
