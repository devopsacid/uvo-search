"""Tests for MongoDB upsert loader."""

import pytest

from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch, upsert_notice
from uvo_pipeline.models import (
    CanonicalAward,
    CanonicalNotice,
    CanonicalProcurer,
    CanonicalSupplier,
)


def _notice(source_id: str = "test-1", title: str = "Test notice") -> CanonicalNotice:
    return CanonicalNotice(
        source="vestnik",
        source_id=source_id,
        notice_type="contract_award",
        title=title,
        procurer=CanonicalProcurer(ico="12345678", name="Test Procurer", name_slug="test-procurer"),
        awards=[
            CanonicalAward(
                supplier=CanonicalSupplier(ico="87654321", name="Test Supplier", name_slug="test-supplier"),
                value=10000.0,
                currency="EUR",
            )
        ],
        cpv_code="72000000-5",
    )


@pytest.mark.asyncio
async def test_ensure_indexes_succeeds(mock_mongo_db):
    await ensure_indexes(mock_mongo_db)


@pytest.mark.asyncio
async def test_upsert_notice_inserts_new(mock_mongo_db):
    notice = _notice("new-1", "Brand new notice")
    doc_id = await upsert_notice(mock_mongo_db, notice)
    assert doc_id is not None
    stored = await mock_mongo_db.notices.find_one({"source_id": "new-1"})
    assert stored["title"] == "Brand new notice"
    assert stored["source"] == "vestnik"


@pytest.mark.asyncio
async def test_upsert_notice_updates_existing(mock_mongo_db):
    notice = _notice("dup-1", "Version 1")
    await upsert_notice(mock_mongo_db, notice)

    notice_v2 = _notice("dup-1", "Version 2")
    await upsert_notice(mock_mongo_db, notice_v2)

    count = await mock_mongo_db.notices.count_documents({"source_id": "dup-1"})
    assert count == 1, "Should not create duplicate"
    stored = await mock_mongo_db.notices.find_one({"source_id": "dup-1"})
    assert stored["title"] == "Version 2"


@pytest.mark.asyncio
async def test_upsert_batch_returns_counts(mock_mongo_db):
    notices = [_notice(f"batch-{i}", f"Notice {i}") for i in range(5)]
    result = await upsert_batch(mock_mongo_db, notices, batch_size=3)
    assert result["inserted"] == 5
    assert result["updated"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_upsert_batch_idempotent(mock_mongo_db):
    notices = [_notice(f"idem-{i}") for i in range(3)]
    await upsert_batch(mock_mongo_db, notices)
    result2 = await upsert_batch(mock_mongo_db, notices)
    assert result2["inserted"] == 0
    assert result2["updated"] == 3

    count = await mock_mongo_db.notices.count_documents({})
    assert count == 3
