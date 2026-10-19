"""Shared flush step for extractor workers."""

import logging

from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_core.domain.models import CanonicalNotice

logger = logging.getLogger(__name__)


async def flush_notices(
    stream: RedisNoticeStream,
    notices: list[CanonicalNotice],
    *,
    high_water: int,
) -> int:
    """Publish ``notices`` to the stream and return how many were written.

    Waits for consumer-group capacity first (backpressure, so MAXLEN never has
    to drop unread entries), then writes the whole batch in a single pipelined
    round trip. Raises BackpressureTimeout if the consumer never catches up.
    """
    if not notices:
        return 0
    await stream.wait_for_capacity(high_water=high_water)
    await stream.xadd_many([n.model_dump(mode="json") for n in notices])
    logger.debug("flushed %d notices", len(notices))
    return len(notices)
