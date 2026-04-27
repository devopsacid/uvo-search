"""Tests for /api/dashboard/worker-status endpoint."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from uvo_api.app import create_app
from uvo_api.routers.worker_status import COMPONENTS


@pytest.fixture
def client_and_db(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://test")
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr("uvo_api.db.get_db", lambda: db)
    monkeypatch.setattr("uvo_api.routers.ingestion_log.get_db", lambda: db)
    monkeypatch.setattr("uvo_api.routers.worker_status.get_db", lambda: db)
    app = create_app()
    return TestClient(app), db


@pytest.mark.asyncio
async def test_returns_one_row_per_component_empty_db(client_and_db):
    client, _db = client_and_db
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    body = res.json()
    assert len(body["workers"]) == len(COMPONENTS)
    components_returned = {w["component"] for w in body["workers"]}
    assert components_returned == set(COMPONENTS)


@pytest.mark.asyncio
async def test_unknown_status_when_no_entries(client_and_db):
    client, _db = client_and_db
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    for worker in res.json()["workers"]:
        assert worker["status"] == "unknown"
        assert worker["last_event"] is None
        assert worker["events_24h"] == 0


@pytest.mark.asyncio
async def test_error_status_for_cycle_failed(client_and_db):
    client, db = client_and_db
    now = datetime.now(timezone.utc)
    await db.ingestion_log.insert_one({
        "ts": now - timedelta(minutes=5),
        "level": "error",
        "event": "cycle_failed",
        "component": "extractor:vestnik",
        "source": "vestnik",
        "message": "connection refused",
    })
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    workers = {w["component"]: w for w in res.json()["workers"]}
    assert workers["extractor:vestnik"]["status"] == "error"
    assert workers["extractor:vestnik"]["last_event"] == "cycle_failed"


@pytest.mark.asyncio
async def test_stale_status_when_ts_exceeds_threshold(client_and_db):
    client, db = client_and_db
    # ingestor threshold is 600s; seed an entry 20 minutes old
    old_ts = datetime.now(timezone.utc) - timedelta(seconds=1200)
    await db.ingestion_log.insert_one({
        "ts": old_ts,
        "level": "info",
        "event": "cycle_complete",
        "component": "ingestor",
        "source": None,
        "message": "done",
    })
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    workers = {w["component"]: w for w in res.json()["workers"]}
    assert workers["ingestor"]["status"] == "stale"


@pytest.mark.asyncio
async def test_events_24h_counts_cycle_complete_and_batch_written(client_and_db):
    client, db = client_and_db
    now = datetime.now(timezone.utc)
    docs = [
        {"ts": now - timedelta(hours=1), "level": "info", "event": "cycle_complete",
         "component": "extractor:crz", "message": "ok"},
        {"ts": now - timedelta(hours=2), "level": "info", "event": "batch_written",
         "component": "extractor:crz", "message": "ok"},
        # older than 24h — must not be counted
        {"ts": now - timedelta(hours=25), "level": "info", "event": "cycle_complete",
         "component": "extractor:crz", "message": "ok"},
        # different event type — must not be counted
        {"ts": now - timedelta(hours=1), "level": "info", "event": "worker_started",
         "component": "extractor:crz", "message": "ok"},
    ]
    await db.ingestion_log.insert_many(docs)
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    workers = {w["component"]: w for w in res.json()["workers"]}
    assert workers["extractor:crz"]["events_24h"] == 2


@pytest.mark.asyncio
async def test_healthy_status_for_recent_cycle_complete(client_and_db):
    client, db = client_and_db
    now = datetime.now(timezone.utc)
    await db.ingestion_log.insert_one({
        "ts": now - timedelta(minutes=10),
        "level": "info",
        "event": "cycle_complete",
        "component": "extractor:vestnik",
        "source": "vestnik",
        "message": "ok",
    })
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    workers = {w["component"]: w for w in res.json()["workers"]}
    assert workers["extractor:vestnik"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_stopped_status_for_worker_stopped_event(client_and_db):
    client, db = client_and_db
    now = datetime.now(timezone.utc)
    await db.ingestion_log.insert_one({
        "ts": now - timedelta(minutes=1),
        "level": "info",
        "event": "worker_stopped",
        "component": "dedup-worker",
        "message": "graceful shutdown",
    })
    res = client.get("/api/dashboard/worker-status")
    assert res.status_code == 200
    workers = {w["component"]: w for w in res.json()["workers"]}
    assert workers["dedup-worker"]["status"] == "stopped"
