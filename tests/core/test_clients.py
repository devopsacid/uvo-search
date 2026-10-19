"""Client factories set explicit timeouts and pool bounds (A09)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_core.infra import clients


def test_make_mongo_client_passes_explicit_limits(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        clients, "AsyncIOMotorClient", lambda uri, **kw: seen.update(uri=uri, **kw) or "client"
    )
    out = clients.make_mongo_client(
        "mongodb://x", server_selection_timeout_ms=1234, connect_timeout_ms=2345, max_pool_size=7
    )
    assert out == "client"
    assert seen == {
        "uri": "mongodb://x",
        "serverSelectionTimeoutMS": 1234,
        "connectTimeoutMS": 2345,
        "maxPoolSize": 7,
    }


def test_make_mongo_client_defaults_are_bounded():
    client = clients.make_mongo_client("mongodb://u:p@localhost:27017")
    try:
        assert client.delegate.options.server_selection_timeout == pytest.approx(5.0)
        assert client.delegate.options.pool_options.max_pool_size == 50
    finally:
        client.close()


def test_make_neo4j_driver_passes_timeouts(monkeypatch):
    import neo4j

    seen = {}

    def fake_driver(uri, **kw):
        seen.update(uri=uri, **kw)
        return "driver"

    monkeypatch.setattr(neo4j.AsyncGraphDatabase, "driver", fake_driver)
    out = clients.make_neo4j_driver(
        "bolt://n", "u", "p", connection_timeout=3.5, max_connection_pool_size=9
    )
    assert out == "driver"
    assert seen["auth"] == ("u", "p")
    assert seen["connection_timeout"] == 3.5
    assert seen["max_connection_pool_size"] == 9


def test_make_redis_sets_socket_timeouts(monkeypatch):
    seen = {}
    monkeypatch.setattr(clients.aioredis, "from_url", lambda url, **kw: seen.update(url=url, **kw))
    clients.make_redis("redis://r", "pw", socket_timeout=2.0, socket_connect_timeout=1.0)
    assert seen["socket_timeout"] == 2.0
    assert seen["socket_connect_timeout"] == 1.0
    assert seen["password"] == "pw"


def test_make_redis_blank_password_becomes_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(clients.aioredis, "from_url", lambda url, **kw: seen.update(**kw))
    clients.make_redis("redis://r", "")
    assert seen["password"] is None


@pytest.mark.asyncio
async def test_close_quietly_handles_sync_async_and_errors():
    sync = MagicMock()
    await clients.close_quietly("sync", sync)
    sync.assert_called_once()

    asyn = AsyncMock()
    await clients.close_quietly("async", asyn)
    asyn.assert_awaited_once()

    await clients.close_quietly("boom", MagicMock(side_effect=RuntimeError("x")))  # no raise
