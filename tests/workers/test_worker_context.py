"""WorkerContext: redis connect-or-exit, lifecycle events, shutdown."""

import asyncio
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from mongomock_motor import AsyncMongoMockClient

import uvo_workers.context as context_mod
from uvo_workers.clients import WorkerClients
from uvo_workers.context import WorkerContext

from .helpers import DB_NAME, fake_clients


def _context(clients, **kw):
    return WorkerContext(
        name="t",
        component="test-worker",
        registry_name="t",
        health_port=0,
        start_message="up",
        stop_message="down",
        clients=clients,
        **kw,
    )


@pytest.mark.asyncio
async def test_lifecycle_events_and_metrics():
    clients = fake_clients(fakeredis.aioredis.FakeRedis())
    seed = {"cycles": 0}
    async with _context(clients, metrics=seed, stop_details=lambda: {"n": 1}) as ctx:
        assert ctx.metrics is seed
        assert ctx.metrics["redis_connected"] is True
        assert ctx.metrics["instance_id"] == ctx.instance_id
        db = ctx.db

    events = [e["event"] async for e in db.ingestion_log.find()]
    assert events == ["worker_started", "worker_stopped"]
    stopped = await db.ingestion_log.find_one({"event": "worker_stopped"})
    assert stopped["details"] == {"n": 1}


@pytest.mark.asyncio
async def test_redis_failure_logs_and_exits_nonzero():
    mongo = AsyncMongoMockClient()
    broken = AsyncMock()
    broken.ping.side_effect = ConnectionError("no redis")
    clients = WorkerClients(mongo=mongo, db=mongo[DB_NAME], redis=broken)

    with pytest.raises(SystemExit) as exc_info:
        async with _context(clients):
            pytest.fail("body must not run without redis")

    assert exc_info.value.code == 1
    doc = await mongo[DB_NAME].ingestion_log.find_one({"event": "redis_connect_failed"})
    assert doc["level"] == "critical"
    assert doc["component"] == "test-worker"


@pytest.mark.asyncio
async def test_health_server_started_when_port_set(monkeypatch):
    started = asyncio.Event()

    async def fake_serve_health(port, snapshot, **kwargs):
        assert port == 4321
        assert snapshot()["redis_connected"] is True
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(context_mod, "serve_health", fake_serve_health)
    clients = fake_clients(fakeredis.aioredis.FakeRedis())
    ctx = _context(clients)
    ctx._health_port = 4321
    async with ctx:
        await asyncio.wait_for(started.wait(), timeout=2)


@pytest.mark.asyncio
async def test_sigterm_sets_stop_event():
    import os
    import signal

    clients = fake_clients(fakeredis.aioredis.FakeRedis())
    async with _context(clients) as ctx:
        assert not ctx.stop_event.is_set()
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(ctx.stop_event.wait(), timeout=2)
