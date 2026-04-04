"""Tests for orchestrator dedup function."""
import pytest
from datetime import date

from uvo_pipeline.orchestrator import _run_cross_source_dedup
from uvo_pipeline.loaders.mongo import upsert_notice
from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer


@pytest.mark.asyncio
async def test_cross_source_dedup_finds_matches(mock_mongo_db):
    """Two notices from different sources with same procurer+cpv should be linked."""
    run_id = "test-run-1"

    procurer = CanonicalProcurer(ico="12345678", name="Ministry", name_slug="ministry")

    notice_uvostat = CanonicalNotice(
        source="uvostat",
        source_id="uvo-1",
        notice_type="contract_award",
        title="IT procurement",
        procurer=procurer,
        cpv_code="72000000-5",
        publication_date=date(2024, 1, 10),
        pipeline_run_id=run_id,
    )
    notice_vestnik = CanonicalNotice(
        source="vestnik",
        source_id="vest-1",
        notice_type="contract_award",
        title="IT procurement",
        procurer=procurer,
        cpv_code="72000000-5",
        publication_date=date(2024, 1, 12),
        pipeline_run_id=run_id,
    )

    await upsert_notice(mock_mongo_db, notice_uvostat)
    await upsert_notice(mock_mongo_db, notice_vestnik)

    match_count = await _run_cross_source_dedup(mock_mongo_db, run_id)
    assert match_count >= 1

    # Check that canonical_id was set
    count_with_canonical = await mock_mongo_db.notices.count_documents(
        {"canonical_id": {"$exists": True}}
    )
    assert count_with_canonical == 2


@pytest.mark.asyncio
async def test_cross_source_dedup_ignores_same_source(mock_mongo_db):
    """Two notices from same source with same procurer+cpv should NOT be linked."""
    run_id = "test-run-2"
    procurer = CanonicalProcurer(ico="99999999", name="Agency", name_slug="agency")

    for i in range(2):
        notice = CanonicalNotice(
            source="uvostat",
            source_id=f"uvo-same-{i}",
            notice_type="contract_award",
            title=f"Procurement {i}",
            procurer=procurer,
            cpv_code="45000000-7",
            publication_date=date(2024, 2, i + 1),
            pipeline_run_id=run_id,
        )
        await upsert_notice(mock_mongo_db, notice)

    match_count = await _run_cross_source_dedup(mock_mongo_db, run_id)
    assert match_count == 0
