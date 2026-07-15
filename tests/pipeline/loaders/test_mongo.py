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
    assert result2["skipped"] == 3

    count = await mock_mongo_db.notices.count_documents({})
    assert count == 3


@pytest.mark.asyncio
async def test_upsert_batch_bulk_write_mixed_counts(mock_mongo_db):
    """A single bulk_write call must still classify each notice correctly as
    inserted/updated/skipped — the bulk_write conversion must not collapse the
    per-document distinction that update_one's `upserted_id` used to give us."""
    # Seed two notices so this batch exercises all three branches in one call.
    seeded = [_notice("mix-unchanged", "Same title"), _notice("mix-changed", "Old title")]
    await upsert_batch(mock_mongo_db, seeded)

    mixed_batch = [
        _notice("mix-unchanged", "Same title"),  # unchanged -> skipped
        _notice("mix-changed", "New title"),  # content differs -> updated
        _notice("mix-new", "Brand new"),  # not seen before -> inserted
    ]
    result = await upsert_batch(mock_mongo_db, mixed_batch)

    assert result["inserted"] == 1
    assert result["updated"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == 0

    changed_doc = await mock_mongo_db.notices.find_one({"source_id": "mix-changed"})
    assert changed_doc["title"] == "New title"

    reg_unchanged = await mock_mongo_db.ingested_docs.find_one({"source_id": "mix-unchanged"})
    assert reg_unchanged["skipped_count"] == 1


@pytest.mark.asyncio
async def test_upsert_batch_dedupes_shared_entities_within_batch(mock_mongo_db):
    """Two notices in the same batch sharing a procurer ICO must upsert to one
    procurer doc via bulk_write, with sources accumulated (not overwritten) —
    the same $addToSet semantics the old per-doc find_one_and_update gave."""
    n1 = CanonicalNotice(
        source="vestnik",
        source_id="shared-1",
        notice_type="contract_award",
        title="First",
        procurer=CanonicalProcurer(
            ico="99999999", name="Shared Procurer", name_slug="shared-procurer", sources=["vestnik"],
        ),
        awards=[CanonicalAward(
            supplier=CanonicalSupplier(
                ico="11112222", name="Shared Supplier", name_slug="shared-supplier", sources=["vestnik"],
            ),
            value=1000.0, currency="EUR",
        )],
    )
    n2 = CanonicalNotice(
        source="crz",
        source_id="shared-2",
        notice_type="contract_award",
        title="Second",
        procurer=CanonicalProcurer(
            ico="99999999", name="Shared Procurer", name_slug="shared-procurer", sources=["crz"],
        ),
        awards=[CanonicalAward(
            supplier=CanonicalSupplier(
                ico="11112222", name="Shared Supplier", name_slug="shared-supplier", sources=["crz"],
            ),
            value=2000.0, currency="EUR",
        )],
    )

    await upsert_batch(mock_mongo_db, [n1, n2])

    procurer_count = await mock_mongo_db.procurers.count_documents({"ico": "99999999"})
    assert procurer_count == 1
    procurer = await mock_mongo_db.procurers.find_one({"ico": "99999999"})
    assert set(procurer["sources"]) == {"vestnik", "crz"}

    supplier_count = await mock_mongo_db.suppliers.count_documents({"ico": "11112222"})
    assert supplier_count == 1
    supplier = await mock_mongo_db.suppliers.find_one({"ico": "11112222"})
    assert set(supplier["sources"]) == {"vestnik", "crz"}
