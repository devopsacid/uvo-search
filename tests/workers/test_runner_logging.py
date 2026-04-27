"""Tests for run_extractor_loop's ingestion_log integration.

We test the small `_log_cycle_result` helper extracted in this task —
testing the full daemon loop is covered by integration tests.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_pipeline.ingestion_log import ensure_log_indexes
from uvo_workers.runner import _log_cycle_result


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test"]


@pytest.mark.asyncio
async def test_log_cycle_result_success(db):
    await ensure_log_indexes(db)
    await _log_cycle_result(
        db,
        source="vestnik",
        instance_id="i1",
        count=12,
        error=None,
    )
    docs = await db.ingestion_log.find().to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["event"] == "cycle_complete"
    assert docs[0]["level"] == "info"
    assert docs[0]["details"]["count"] == 12


@pytest.mark.asyncio
async def test_log_cycle_result_error(db):
    await ensure_log_indexes(db)
    await _log_cycle_result(
        db,
        source="crz",
        instance_id="i2",
        count=0,
        error="ValueError: boom",
    )
    docs = await db.ingestion_log.find().to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["event"] == "cycle_failed"
    assert docs[0]["level"] == "error"
    assert "boom" in docs[0]["message"]
