import asyncio
from unittest.mock import AsyncMock, MagicMock

from mongomock_motor import AsyncMongoMockClient

from uvo_core.adapters.mongo.health import mongo_ready


async def test_ready_when_ping_succeeds():
    assert await mongo_ready(AsyncMongoMockClient()["ok"]) is True


async def test_not_ready_without_handle():
    assert await mongo_ready(None) is False


async def test_not_ready_when_ping_raises():
    db = MagicMock()
    db.command = AsyncMock(side_effect=RuntimeError("boom"))
    assert await mongo_ready(db) is False


async def test_not_ready_when_ping_hangs_is_bounded():
    async def _hang(*args, **kwargs):
        await asyncio.sleep(30)

    db = MagicMock()
    db.command = _hang
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await mongo_ready(db, timeout=0.05) is False
    assert loop.time() - started < 1
