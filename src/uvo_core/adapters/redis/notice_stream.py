"""NoticeStream port adapter — wraps Redis Streams XADD/XREADGROUP/XACK.

Extracted so extractor/ingestor workers can depend on the NoticeStream port
instead of importing uvo_core.adapters.redis.streams directly (Phase 5 write-side).
"""

from __future__ import annotations

import redis.asyncio as aioredis

from uvo_core.adapters.redis.streams import DEFAULT_MAXLEN_SAFETY_NET
from uvo_core.adapters.redis.streams import ack as _ack
from uvo_core.adapters.redis.streams import read_group as _read_group
from uvo_core.adapters.redis.streams import wait_for_capacity as _wait_for_capacity
from uvo_core.adapters.redis.streams import xadd_many as _xadd_many
from uvo_core.adapters.redis.streams import xadd_notice as _xadd_notice


class RedisNoticeStream:
    """NoticeStream port bound to a single source's stream (``notices:{source}``).

    ``xadd_notice`` pulls ``content_hash``/``pipeline_run_id`` off the payload
    dict itself (every CanonicalNotice payload carries both) rather than
    threading them through the port's generic single-argument signature.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        source: str,
        *,
        maxlen: int = DEFAULT_MAXLEN_SAFETY_NET,
        group: str = "ingestor",
    ) -> None:
        self._redis = redis_client
        self._group = group
        self._source = source
        self._stream = f"notices:{source}"
        self._maxlen = maxlen

    async def xadd_notice(self, payload: dict) -> str:
        entry_id = await _xadd_notice(
            self._redis,
            self._source,
            payload,
            content_hash=payload.get("content_hash"),
            run_id=payload.get("pipeline_run_id"),
            maxlen=self._maxlen,
        )
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id

    async def xadd_many(self, payloads: list[dict]) -> list[str]:
        """XADD many payloads in one non-transactional pipeline round trip."""
        ids = await _xadd_many(self._redis, self._source, payloads, maxlen=self._maxlen)
        return [i.decode() if isinstance(i, bytes) else i for i in ids]

    async def wait_for_capacity(self, *, high_water: int, **kwargs) -> None:
        """Block while the consumer group's backlog is at/above ``high_water``."""
        await _wait_for_capacity(
            self._redis, self._stream, self._group, high_water=high_water, **kwargs
        )

    async def read_group(self, group: str, consumer: str, count: int) -> list:
        return await _read_group(self._redis, group, consumer, [self._stream], count=count)

    async def ack(self, group: str, message_id: str) -> None:
        entry_id = message_id.encode() if isinstance(message_id, str) else message_id
        await _ack(self._redis, self._stream, group, [entry_id])
