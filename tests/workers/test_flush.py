"""Shared extractor flush: backpressure first, then one pipelined XADD batch."""

from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis

from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_core.domain.models import CanonicalNotice
from uvo_workers.flush import flush_notices


def _notice(i: int) -> CanonicalNotice:
    return CanonicalNotice(
        source="crz", source_id=f"C-{i}", notice_type="contract_award", title=f"t{i}"
    )


async def test_flush_notices_writes_all_and_returns_count():
    redis_client = fakeredis.aioredis.FakeRedis()
    stream = RedisNoticeStream(redis_client, "crz")

    written = await flush_notices(stream, [_notice(i) for i in range(4)], high_water=100)

    assert written == 4
    assert await redis_client.xlen("notices:crz") == 4


async def test_flush_notices_empty_does_nothing():
    stream = MagicMock()
    stream.wait_for_capacity = AsyncMock()
    stream.xadd_many = AsyncMock()

    assert await flush_notices(stream, [], high_water=10) == 0

    stream.wait_for_capacity.assert_not_awaited()
    stream.xadd_many.assert_not_awaited()


async def test_flush_notices_waits_for_capacity_before_xadd():
    calls: list[str] = []
    stream = MagicMock()
    stream.wait_for_capacity = AsyncMock(side_effect=lambda **kw: calls.append("wait"))
    stream.xadd_many = AsyncMock(side_effect=lambda payloads: calls.append("add"))

    await flush_notices(stream, [_notice(1)], high_water=7)

    assert calls == ["wait", "add"]
    stream.wait_for_capacity.assert_awaited_once_with(high_water=7)
