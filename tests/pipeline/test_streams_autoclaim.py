"""Orphaned pending entries must be reclaimable after a consumer dies."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ResponseError

from uvo_pipeline.streams import autoclaim_stale


@pytest.mark.asyncio
async def test_autoclaim_returns_reclaimed_entries():
    redis = AsyncMock()
    # redis-py returns (next_cursor, entries, deleted_ids)
    redis.xautoclaim.return_value = (
        b"0-0",
        [(b"1700000000000-0", {b"payload": b"{}", b"hash": b"h", b"run": b"r"})],
        [],
    )
    entries = await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0")
    assert len(entries) == 1
    assert entries[0][0] == b"1700000000000-0"


@pytest.mark.asyncio
async def test_autoclaim_passes_min_idle_time():
    redis = AsyncMock()
    redis.xautoclaim.return_value = (b"0-0", [], [])
    await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0", min_idle_ms=30_000)
    kwargs = redis.xautoclaim.await_args.kwargs
    assert kwargs["min_idle_time"] == 30_000


@pytest.mark.asyncio
async def test_autoclaim_returns_empty_on_redis_error():
    """A Redis-level reclaim failure (e.g. a transient connectivity blip)
    must not take down the ingest loop."""
    redis = AsyncMock()
    redis.xautoclaim.side_effect = ResponseError("NOGROUP no such key or consumer group")
    assert await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0") == []


@pytest.mark.asyncio
async def test_autoclaim_propagates_non_redis_errors():
    """A non-Redis exception is a bug, not an operational condition — it must
    surface loudly rather than being silently swallowed as if it were a
    routine reclaim failure (which would otherwise disable reclaim forever
    with no visible signal beyond a WARNING log line)."""
    redis = AsyncMock()
    redis.xautoclaim.side_effect = TypeError("unexpected keyword argument")
    with pytest.raises(TypeError):
        await autoclaim_stale(redis, "notices:crz", "ingestor", "ingestor-0")
