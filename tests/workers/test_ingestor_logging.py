"""Tests for ingestor's date-validation + log_event integration.

We don't spin up the full daemon — we test the hot-path helper that
processes one batch (refactored out of run_ingestor in this task).
"""
from datetime import date

import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_pipeline.ingestion_log import ensure_log_indexes
from uvo_pipeline.models import CanonicalNotice
from uvo_workers.ingestor import process_batch_logs  # to be created


def _notice(source_id: str, **overrides) -> CanonicalNotice:
    base = dict(
        source="vestnik",
        source_id=source_id,
        notice_type="contract_award",
        title="T",
    )
    base.update(overrides)
    return CanonicalNotice(**base)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test"]


@pytest.mark.asyncio
async def test_process_batch_logs_clamps_bad_dates_and_logs(db):
    await ensure_log_indexes(db)

    notices = [
        _notice("OK1", publication_date=date(2025, 1, 1)),
        _notice("BAD1", publication_date=date(3202, 1, 15)),
        _notice("BAD2", award_date=date(2502, 6, 1)),
    ]

    cleaned = await process_batch_logs(
        db,
        notices=notices,
        component="ingestor",
        instance_id="inst-1",
        stream_name="notices:vestnik",
    )

    # Bad dates nulled
    by_id = {n.source_id: n for n in cleaned}
    assert by_id["OK1"].publication_date == date(2025, 1, 1)
    assert by_id["BAD1"].publication_date is None
    assert by_id["BAD2"].award_date is None

    # One log entry per bad field
    entries = await db.ingestion_log.find(
        {"event": "notice_invalid_date"}
    ).to_list(length=10)
    assert len(entries) == 2
    assert {e["source_id"] for e in entries} == {"BAD1", "BAD2"}
    for e in entries:
        assert e["level"] == "warning"
        assert e["component"] == "ingestor"
        assert e["source"] == "vestnik"
        assert "field" in e["details"]
        assert "year" in e["details"]
