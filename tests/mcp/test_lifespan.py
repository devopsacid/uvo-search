"""MCP lifespan owns its clients: explicit bounds, search-index bootstrap, cache invalidation (A09/A13/A14)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_core.cache import async_ttl_cache
from uvo_mcp import server
from uvo_mcp.config import Settings


@pytest.fixture
def wired(monkeypatch):
    """Patch every external factory the lifespan touches; return the fakes."""
    fakes = MagicMock()
    fakes.mongo_client = MagicMock()
    fakes.mongo_client.__getitem__.return_value = MagicMock(name="mongo_db")
    fakes.neo4j = MagicMock()
    fakes.neo4j.close = AsyncMock()
    fakes.redis = MagicMock()
    fakes.redis.aclose = AsyncMock()
    fakes.ensure = AsyncMock()

    settings = Settings(
        mongodb_uri="mongodb://x",
        neo4j_uri="bolt://n",
        neo4j_password="pw",
        mongo_max_pool_size=11,
        neo4j_max_pool_size=12,
    )
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "uvo_core.infra.clients.make_mongo_client",
        lambda uri, **kw: fakes.mongo_kwargs.update(kw) or fakes.mongo_client,
    )
    fakes.mongo_kwargs = {}
    fakes.neo4j_kwargs = {}
    monkeypatch.setattr(
        "uvo_core.infra.clients.make_neo4j_driver",
        lambda uri, user, pw, **kw: fakes.neo4j_kwargs.update(kw) or fakes.neo4j,
    )
    monkeypatch.setattr(
        "uvo_core.infra.clients.make_redis", lambda url, password=None, **kw: fakes.redis
    )
    monkeypatch.setattr("uvo_core.adapters.embedding.load_embedder", lambda: None)
    monkeypatch.setattr("uvo_core.adapters.mongo.search_indexes.ensure_indexes", fakes.ensure)

    async def idle_subscribe(redis, channel):
        await asyncio.sleep(3600)
        yield  # pragma: no cover

    monkeypatch.setattr("uvo_core.adapters.redis.cache_invalidation.subscribe", idle_subscribe)
    fakes.settings = settings
    return fakes


async def test_lifespan_creates_bounded_clients_and_closes_them(wired):
    async with server.app_lifespan(server.mcp) as ctx:
        assert ctx.mongo_db is not None
        assert ctx.neo4j_driver is wired.neo4j
        assert wired.mongo_kwargs["max_pool_size"] == 11
        assert wired.neo4j_kwargs["max_connection_pool_size"] == 12
        wired.ensure.assert_awaited_once()
        assert server._runtime["index_probe"] is not None

    wired.mongo_client.close.assert_called_once()
    wired.neo4j.close.assert_awaited_once()
    wired.redis.aclose.assert_awaited_once()
    assert server._runtime["mongo_db"] is None
    assert server._runtime["index_probe"] is None


async def test_lifespan_closes_clients_even_when_body_raises(wired):
    with pytest.raises(RuntimeError):
        async with server.app_lifespan(server.mcp):
            raise RuntimeError("boom")
    wired.mongo_client.close.assert_called_once()
    wired.neo4j.close.assert_awaited_once()
    wired.redis.aclose.assert_awaited_once()


async def test_ensure_indexes_failure_is_logged_as_error_not_fatal(wired, caplog):
    import logging

    wired.ensure.side_effect = RuntimeError("mongot unreachable")
    with caplog.at_level(logging.ERROR):
        async with server.app_lifespan(server.mcp) as ctx:
            assert ctx.mongo_db is not None  # server still starts
    assert any(r.levelno == logging.ERROR for r in caplog.records)


async def test_notices_written_event_clears_mcp_in_process_caches(wired, monkeypatch):
    """A14: the MCP process now clears its own caches on notices:written."""

    @async_ttl_cache(maxsize=4, ttl=600)
    async def probe_cache(x):
        return x

    await probe_cache(1)
    assert probe_cache.cache_info()["size"] == 1

    async def one_event(redis, channel):
        yield {"source": "crz", "count": 1}
        await asyncio.sleep(3600)

    monkeypatch.setattr("uvo_core.adapters.redis.cache_invalidation.subscribe", one_event)

    async with server.app_lifespan(server.mcp):
        for _ in range(50):
            if probe_cache.cache_info()["size"] == 0:
                break
            await asyncio.sleep(0.01)

    assert probe_cache.cache_info()["size"] == 0


async def test_sessions_share_one_process_runtime(wired):
    """Concurrent sessions reuse the same clients; they close with the last session."""
    async with server.app_lifespan(server.mcp) as first:
        async with server.app_lifespan(server.mcp) as second:
            assert second is first
        wired.mongo_client.close.assert_not_called()
        assert server._runtime["mongo_db"] is not None
    wired.mongo_client.close.assert_called_once()
    wired.ensure.assert_awaited_once()


def test_readyz_is_200_without_any_mcp_session(wired, monkeypatch):
    """/readyz must work from process start, before any client opens a session."""
    from starlette.testclient import TestClient

    wired.mongo_client.__getitem__.return_value.command = AsyncMock(return_value={"ok": 1})
    probe = MagicMock()
    probe.ready = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "uvo_core.adapters.mongo.search_indexes.SearchIndexProbe", lambda *a, **k: probe
    )
    server._runtime["mongo_db"] = None

    with TestClient(server.build_http_app()) as client:
        assert client.get("/readyz").status_code == 200
        assert client.get("/health").status_code == 200

    assert server._runtime["mongo_db"] is None
    wired.mongo_client.close.assert_called_once()


async def test_failed_index_bootstrap_schedules_background_retry(wired, monkeypatch):
    wired.ensure.return_value = False
    retried = asyncio.Event()

    async def fake_retry(db, *, ensure=None):
        retried.set()

    monkeypatch.setattr("uvo_core.adapters.mongo.search_indexes.retry_ensure_indexes", fake_retry)
    async with server.app_lifespan(server.mcp):
        await asyncio.wait_for(retried.wait(), 1)
