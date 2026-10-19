"""API lifespan owns its clients: install on startup, close on shutdown (A09/A13/A14)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from uvo_api import app as app_module
from uvo_api import db as api_db
from uvo_core.cache import async_ttl_cache


def _resources():
    return api_db.Resources(
        mongo_client=MagicMock(name="mongo_client"),
        db=MagicMock(name="db"),
        redis=MagicMock(name="redis", aclose=AsyncMock()),
        neo4j_driver=MagicMock(name="neo4j", close=AsyncMock()),
    )


@pytest.fixture
def wired(monkeypatch):
    resources = _resources()
    subscriber = MagicMock(name="subscriber_redis", aclose=AsyncMock())
    ensure = AsyncMock()
    monkeypatch.setattr(app_module, "build_resources", lambda settings: resources)
    monkeypatch.setattr(app_module, "make_redis", lambda *a, **kw: subscriber)
    monkeypatch.setattr(app_module, "ensure_indexes", ensure)

    async def idle(redis, channel):
        await asyncio.sleep(3600)
        yield  # pragma: no cover

    monkeypatch.setattr("uvo_core.adapters.redis.cache_invalidation.subscribe", idle)
    return resources, subscriber, ensure


def test_lifespan_installs_resources_on_app_and_v1_and_bootstraps_indexes(wired):
    resources, _, ensure = wired
    app = app_module.create_app()
    with TestClient(app):
        assert app.state.resources is resources
        assert app.state.v1_app.state.resources is resources
        ensure.assert_awaited_once_with(resources.db)


def test_lifespan_closes_every_client_on_shutdown(wired):
    resources, subscriber, _ = wired
    with TestClient(app_module.create_app()):
        resources.mongo_client.close.assert_not_called()
    resources.mongo_client.close.assert_called_once()
    resources.neo4j_driver.close.assert_awaited_once()
    resources.redis.aclose.assert_awaited_once()  # rate-limit client
    subscriber.aclose.assert_awaited_once()  # cache-invalidation client


def test_ensure_indexes_failure_is_logged_as_error_and_not_fatal(wired, caplog):
    _, _, ensure = wired
    ensure.side_effect = RuntimeError("mongot unreachable")
    with caplog.at_level("ERROR"):
        with TestClient(app_module.create_app()) as client:
            assert client.get("/health").status_code == 200
    assert any(
        r.levelname == "ERROR" and "ensure_indexes" in r.getMessage() for r in caplog.records
    )


def test_notices_written_event_clears_api_caches(wired, monkeypatch):
    @async_ttl_cache(maxsize=4, ttl=600)
    async def probe_cache(x):
        return x

    asyncio.run(probe_cache(1))
    assert probe_cache.cache_info()["size"] == 1

    async def one_event(redis, channel):
        yield {"source": "crz", "count": 1}
        await asyncio.sleep(3600)

    monkeypatch.setattr("uvo_core.adapters.redis.cache_invalidation.subscribe", one_event)

    import time

    with TestClient(app_module.create_app()):
        for _ in range(100):
            if probe_cache.cache_info()["size"] == 0:
                break
            time.sleep(0.01)
    assert probe_cache.cache_info()["size"] == 0


def test_get_resources_falls_back_without_lifespan(monkeypatch):
    """TestClient used without ``with`` never runs the lifespan; resources build lazily."""
    built = []
    resources = _resources()
    monkeypatch.setattr(api_db, "build_resources", lambda settings: built.append(1) or resources)
    client = TestClient(app_module.create_app())
    monkeypatch.setattr(app_module, "mongo_ready", AsyncMock(return_value=False))
    client.get("/readyz")
    client.get("/readyz")
    assert built == [1]  # built once, then reused from app.state


def test_failed_index_bootstrap_schedules_background_retry(wired, monkeypatch):
    """A fresh DB has no collections yet: the first attempt fails, a retry task takes over."""
    resources, _, ensure = wired
    ensure.return_value = False
    attempts = []

    async def fake_retry(db, *, ensure):
        attempts.append(db)

    monkeypatch.setattr(app_module, "retry_ensure_indexes", fake_retry)
    with TestClient(app_module.create_app()):
        pass
    assert attempts == [resources.db]


def test_successful_index_bootstrap_does_not_retry(wired, monkeypatch):
    _, _, ensure = wired
    ensure.return_value = True
    retry = AsyncMock()
    monkeypatch.setattr(app_module, "retry_ensure_indexes", retry)
    with TestClient(app_module.create_app()):
        pass
    retry.assert_not_called()
