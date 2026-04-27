# tests/api/test_ingestion_log.py
"""Tests for /api/dashboard/ingestion-log endpoint."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from uvo_api.app import create_app
from uvo_api.db import get_db
from uvo_pipeline.ingestion_log import ensure_log_indexes


@pytest.fixture
def client_and_db(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr("uvo_api.db.get_db", lambda: db)
    monkeypatch.setattr("uvo_api.routers.ingestion_log.get_db", lambda: db)
    app = create_app()
    return TestClient(app), db


@pytest.mark.asyncio
async def _seed(db):
    await ensure_log_indexes(db)
    now = datetime.now(timezone.utc)
    docs = [
        {
            "ts": now - timedelta(minutes=i),
            "level": "info" if i % 2 == 0 else "warning",
            "event": "batch_written" if i % 2 == 0 else "notice_invalid_date",
            "component": "ingestor",
            "source": "vestnik" if i < 3 else "crz",
            "source_id": f"N{i}",
            "instance_id": "i1",
            "pipeline_run_id": None,
            "message": f"event {i}",
            "details": {"i": i},
        }
        for i in range(6)
    ]
    await db.ingestion_log.insert_many(docs)


@pytest.mark.asyncio
async def test_returns_recent_entries_sorted_desc(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res = client.get("/api/dashboard/ingestion-log")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 6
    items = body["items"]
    assert len(items) == 6
    # Newest first
    timestamps = [it["ts"] for it in items]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_filter_by_level(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res = client.get("/api/dashboard/ingestion-log?level=warning")
    assert res.status_code == 200
    body = res.json()
    assert all(it["level"] == "warning" for it in body["items"])
    assert len(body["items"]) == 3


@pytest.mark.asyncio
async def test_filter_by_source_and_event(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res = client.get(
        "/api/dashboard/ingestion-log?source=vestnik&event=batch_written"
    )
    assert res.status_code == 200
    body = res.json()
    assert all(
        it["source"] == "vestnik" and it["event"] == "batch_written"
        for it in body["items"]
    )


@pytest.mark.asyncio
async def test_limit_and_offset(client_and_db):
    client, db = client_and_db
    await _seed(db)
    res1 = client.get("/api/dashboard/ingestion-log?limit=2&offset=0")
    res2 = client.get("/api/dashboard/ingestion-log?limit=2&offset=2")
    items1 = res1.json()["items"]
    items2 = res2.json()["items"]
    assert len(items1) == 2 and len(items2) == 2
    assert {i["source_id"] for i in items1}.isdisjoint(
        {i["source_id"] for i in items2}
    )
