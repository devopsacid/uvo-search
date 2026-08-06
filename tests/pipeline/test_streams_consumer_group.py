"""Consumer groups must start at the stream head, not the tail.

Regression test only — ensure_consumer_group was already fixed to use id="0"
before this Phase 2 pass started (see streams.py docstring). Kept here to pin
the behaviour against regression.
"""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ResponseError

from uvo_pipeline.streams import ensure_consumer_group


@pytest.mark.asyncio
async def test_group_created_from_stream_head():
    """id='0' replays entries already in the stream; id='$' would skip them."""
    redis = AsyncMock()
    await ensure_consumer_group(redis, "notices:crz", "ingestor")
    redis.xgroup_create.assert_awaited_once_with("notices:crz", "ingestor", id="0", mkstream=True)


@pytest.mark.asyncio
async def test_existing_group_is_tolerated():
    redis = AsyncMock()
    redis.xgroup_create.side_effect = ResponseError("BUSYGROUP Consumer Group name already exists")
    await ensure_consumer_group(redis, "notices:crz", "ingestor")


@pytest.mark.asyncio
async def test_other_response_errors_propagate():
    redis = AsyncMock()
    redis.xgroup_create.side_effect = ResponseError("WRONGTYPE")
    with pytest.raises(ResponseError):
        await ensure_consumer_group(redis, "notices:crz", "ingestor")
