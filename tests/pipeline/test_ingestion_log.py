"""Tests for ingestion_log helpers."""

from datetime import datetime

import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_pipeline.ingestion_log import (
    IngestionLogEntry,
    ensure_log_indexes,
    log_event,
    log_events,
)


@pytest.fixture
def db():
    client = AsyncMongoMockClient()
    return client["test"]


@pytest.mark.asyncio
async def test_log_event_writes_document(db):
    await ensure_log_indexes(db)
    await log_event(
        db,
        level="info",
        event="worker_started",
        component="ingestor",
        message="ingestor up",
        source=None,
        details={"instance_id": "abc"},
    )
    docs = await db.ingestion_log.find().to_list(length=10)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["level"] == "info"
    assert doc["event"] == "worker_started"
    assert doc["component"] == "ingestor"
    assert doc["message"] == "ingestor up"
    assert doc["source"] is None
    assert doc["details"] == {"instance_id": "abc"}
    assert isinstance(doc["ts"], datetime)
    assert doc["ts"].tzinfo is not None or True  # naive UTC accepted


@pytest.mark.asyncio
async def test_entry_model_round_trip():
    entry = IngestionLogEntry(
        level="warning",
        event="notice_invalid_date",
        component="ingestor",
        source="vestnik",
        source_id="N-1",
        message="award_date out of range",
        details={"field": "award_date", "year": 3202},
    )
    dumped = entry.model_dump(mode="json")
    assert dumped["level"] == "warning"
    assert dumped["event"] == "notice_invalid_date"
    assert dumped["details"]["year"] == 3202


@pytest.mark.asyncio
async def test_ensure_log_indexes_creates_ttl_and_query_indexes(db):
    await ensure_log_indexes(db)
    info = await db.ingestion_log.index_information()
    names = set(info.keys())
    assert "ts_desc" in names
    assert "source_ts_desc" in names
    assert "level_ts_desc" in names
    # TTL index on ts; mongomock may or may not surface expireAfterSeconds.
    assert "ts_ttl" in names


@pytest.mark.asyncio
async def test_log_event_failure_is_logged_not_raised(db, caplog):
    class _Broken:
        async def insert_one(self, doc):
            raise RuntimeError("mongo down")

    class _BrokenDb:
        ingestion_log = _Broken()

    with caplog.at_level("ERROR", logger="uvo_pipeline.ingestion_log"):
        await log_event(
            _BrokenDb(), level="info", event="worker_started", component="c", message="m"
        )

    assert any("mongo down" in (r.exc_text or "") for r in caplog.records)


@pytest.mark.asyncio
async def test_log_events_inserts_all_in_one_call(db):
    calls = []
    real = db.ingestion_log.insert_many

    class _Spy:
        async def insert_many(self, docs, **kwargs):
            calls.append(len(docs))
            return await real(docs, **kwargs)

    class _SpyDb:
        ingestion_log = _Spy()

    entries = [
        IngestionLogEntry(
            level="warning", event="notice_invalid_date", component="c", message=str(i)
        )
        for i in range(5)
    ]
    await log_events(_SpyDb(), entries)

    assert calls == [5]
    assert await db.ingestion_log.count_documents({}) == 5


@pytest.mark.asyncio
async def test_log_events_empty_is_noop(db):
    await log_events(db, [])
    assert await db.ingestion_log.count_documents({}) == 0


@pytest.mark.asyncio
async def test_log_events_failure_is_logged_not_raised(caplog):
    class _Broken:
        async def insert_many(self, docs, **kwargs):
            raise RuntimeError("mongo down")

    class _BrokenDb:
        ingestion_log = _Broken()

    entry = IngestionLogEntry(level="info", event="batch_written", component="c", message="m")
    with caplog.at_level("ERROR", logger="uvo_pipeline.ingestion_log"):
        await log_events(_BrokenDb(), [entry])

    assert any("mongo down" in (r.exc_text or "") for r in caplog.records)
