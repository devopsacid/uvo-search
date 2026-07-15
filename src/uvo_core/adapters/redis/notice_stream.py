"""NoticeStream port adapter — wraps Redis Streams XADD/XREADGROUP/XACK.

Extracted so extractor/ingestor workers can depend on the NoticeStream port
instead of importing uvo_pipeline.streams directly (Phase 5 write-side).
"""

from __future__ import annotations

import redis.asyncio as aioredis

from uvo_pipeline.streams import ack as _ack
from uvo_pipeline.streams import read_group as _read_group
from uvo_pipeline.streams import xadd_notice as _xadd_notice


class RedisNoticeStream:
    """NoticeStream port bound to a single source's stream (``notices:{source}``).

    ``xadd_notice`` pulls ``content_hash``/``pipeline_run_id`` off the payload
    dict itself (every CanonicalNotice payload carries both) rather than
    threading them through the port's generic single-argument signature.
    """

    def __init__(self, redis_client: aioredis.Redis, source: str, *, maxlen: int = 100_000) -> None:
        self._redis = redis_client
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

    async def read_group(self, group: str, consumer: str, count: int) -> list:
        return await _read_group(self._redis, group, consumer, [self._stream], count=count)

    async def ack(self, group: str, message_id: str) -> None:
        entry_id = message_id.encode() if isinstance(message_id, str) else message_id
        await _ack(self._redis, self._stream, group, [entry_id])
