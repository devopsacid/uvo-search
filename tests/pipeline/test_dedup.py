"""Tests for deduplication and ingestion registry."""
from datetime import date

import pytest

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalAddress
from uvo_pipeline.utils.hashing import compute_notice_hash


def _make_notice(**kwargs) -> CanonicalNotice:
    defaults = dict(
        source="uvo",
        source_id="UVO-001",
        notice_type="contract_notice",
        title="Test Notice",
        procurer=CanonicalProcurer(
            ico="12345678",
            name="Test Procurer",
            name_slug="test-procurer",
        ),
        cpv_code="45000000",
        publication_date=date(2026, 1, 15),
        estimated_value=100_000.0,
    )
    defaults.update(kwargs)
    return CanonicalNotice(**defaults)


def test_hash_is_deterministic():
    n = _make_notice()
    assert compute_notice_hash(n) == compute_notice_hash(n)


def test_hash_changes_when_title_changes():
    n1 = _make_notice(title="Original Title")
    n2 = _make_notice(title="Changed Title")
    assert compute_notice_hash(n1) != compute_notice_hash(n2)


def test_hash_changes_when_value_changes():
    n1 = _make_notice(estimated_value=100_000.0)
    n2 = _make_notice(estimated_value=200_000.0)
    assert compute_notice_hash(n1) != compute_notice_hash(n2)


def test_hash_stable_across_irrelevant_fields():
    """Fields like ingested_at and pipeline_run_id must NOT affect the hash."""
    n1 = _make_notice()
    n1.pipeline_run_id = "run-aaa"
    n2 = _make_notice()
    n2.pipeline_run_id = "run-bbb"
    assert compute_notice_hash(n1) == compute_notice_hash(n2)


def test_hash_none_procurer():
    n = _make_notice(procurer=None)
    h = compute_notice_hash(n)
    assert h.startswith("sha256:")


def test_hash_returns_sha256_prefix():
    n = _make_notice()
    h = compute_notice_hash(n)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_canonical_notice_has_content_hash_field():
    n = _make_notice()
    assert hasattr(n, "content_hash")
    assert n.content_hash is None  # default


def test_pipeline_report_has_notices_skipped():
    from datetime import datetime
    from uvo_pipeline.models import PipelineReport
    r = PipelineReport(run_id="x", mode="recent", started_at=datetime.utcnow())
    assert r.notices_skipped == 0


@pytest.mark.asyncio
async def test_ensure_indexes_creates_ingested_docs_indexes(mock_mongo_db):
    """ensure_indexes must create required indexes on ingested_docs collection."""
    from uvo_pipeline.loaders.mongo import ensure_indexes

    await ensure_indexes(mock_mongo_db)

    index_names = await mock_mongo_db.ingested_docs.index_information()
    assert "source_source_id_unique" in index_names
    assert index_names["source_source_id_unique"]["unique"] is True
    assert "pipeline_run_id" in index_names
    assert "source_ingested_at_desc" in index_names


@pytest.mark.asyncio
async def test_upsert_batch_inserts_new_notices(mock_mongo_db):
    from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch

    await ensure_indexes(mock_mongo_db)
    notices = [_make_notice(source_id="N-001"), _make_notice(source_id="N-002")]
    result = await upsert_batch(mock_mongo_db, notices)

    assert result["inserted"] == 2
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == 0

    registry_count = await mock_mongo_db.ingested_docs.count_documents({})
    assert registry_count == 2


@pytest.mark.asyncio
async def test_upsert_batch_skips_unchanged_notices(mock_mongo_db):
    from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch

    await ensure_indexes(mock_mongo_db)
    notices = [_make_notice(source_id="N-001")]

    # First run — insert
    r1 = await upsert_batch(mock_mongo_db, notices)
    assert r1["inserted"] == 1

    # Second run — same content, should be skipped
    r2 = await upsert_batch(mock_mongo_db, notices)
    assert r2["inserted"] == 0
    assert r2["updated"] == 0
    assert r2["skipped"] == 1

    # skipped_count incremented in registry
    reg = await mock_mongo_db.ingested_docs.find_one({"source": "uvo", "source_id": "N-001"})
    assert reg["skipped_count"] == 1


@pytest.mark.asyncio
async def test_upsert_batch_updates_changed_notices(mock_mongo_db):
    from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch

    await ensure_indexes(mock_mongo_db)
    n1 = _make_notice(source_id="N-001", title="Original")
    await upsert_batch(mock_mongo_db, [n1])

    n2 = _make_notice(source_id="N-001", title="Updated Title")
    r = await upsert_batch(mock_mongo_db, [n2])
    assert r["updated"] == 1
    assert r["skipped"] == 0

    doc = await mock_mongo_db.notices.find_one({"source": "uvo", "source_id": "N-001"})
    assert doc["title"] == "Updated Title"

    reg = await mock_mongo_db.ingested_docs.find_one({"source": "uvo", "source_id": "N-001"})
    assert reg["content_hash"] != compute_notice_hash(n1)
    assert reg["content_hash"] == compute_notice_hash(n2)


def test_pipeline_report_accumulates_skipped():
    """PipelineReport.notices_skipped must be settable and default to 0."""
    from datetime import datetime
    from uvo_pipeline.models import PipelineReport

    r = PipelineReport(run_id="x", mode="recent", started_at=datetime.utcnow())
    r.notices_skipped += 10
    assert r.notices_skipped == 10


@pytest.mark.asyncio
async def test_cross_source_dedup_pass2_matches_by_title_slug(mock_mongo_db):
    """Pass 2 must match notices without ICO by title_slug + pub_date within 7 days."""
    from datetime import datetime
    from uvo_pipeline.loaders.mongo import ensure_indexes
    from uvo_pipeline.orchestrator import _run_cross_source_dedup

    await ensure_indexes(mock_mongo_db)

    run_id = "test-run-1"
    # Two notices from different sources, no ICO, same title, dates 3 days apart
    await mock_mongo_db.notices.insert_many([
        {
            "source": "uvo",
            "source_id": "U-100",
            "title": "Rekonštrukcia cesty",
            "title_slug": "rekonstrukcia-cesty",
            "procurer": {"ico": None, "name": "Obec Test", "name_slug": "obec-test"},
            "cpv_code": None,
            "publication_date": "2026-01-10",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
        {
            "source": "vestnik",
            "source_id": "V-200",
            "title": "Rekonštrukcia cesty",
            "title_slug": "rekonstrukcia-cesty",
            "procurer": {"ico": None, "name": "Obec Test", "name_slug": "obec-test"},
            "cpv_code": None,
            "publication_date": "2026-01-13",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
    ])

    match_count = await _run_cross_source_dedup(mock_mongo_db, run_id)
    assert match_count >= 1

    matched = await mock_mongo_db.notices.find(
        {"pipeline_run_id": run_id, "canonical_id": {"$ne": None}}
    ).to_list(length=None)
    assert len(matched) == 2
    assert matched[0]["canonical_id"] == matched[1]["canonical_id"]


@pytest.mark.asyncio
async def test_cross_source_dedup_pass2_no_match_when_dates_too_far(mock_mongo_db):
    """Pass 2 must NOT match notices with pub_date more than 7 days apart."""
    from uvo_pipeline.loaders.mongo import ensure_indexes
    from uvo_pipeline.orchestrator import _run_cross_source_dedup

    await ensure_indexes(mock_mongo_db)

    run_id = "test-run-2"
    await mock_mongo_db.notices.insert_many([
        {
            "source": "uvo",
            "source_id": "U-300",
            "title": "Stavebné práce",
            "title_slug": "stavebne-prace",
            "procurer": {"ico": None, "name": "Obec B", "name_slug": "obec-b"},
            "cpv_code": None,
            "publication_date": "2026-01-01",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
        {
            "source": "vestnik",
            "source_id": "V-400",
            "title": "Stavebné práce",
            "title_slug": "stavebne-prace",
            "procurer": {"ico": None, "name": "Obec B", "name_slug": "obec-b"},
            "cpv_code": None,
            "publication_date": "2026-01-20",
            "pipeline_run_id": run_id,
            "canonical_id": None,
        },
    ])

    await _run_cross_source_dedup(mock_mongo_db, run_id)

    unmatched = await mock_mongo_db.notices.find(
        {"pipeline_run_id": run_id, "canonical_id": None}
    ).to_list(length=None)
    assert len(unmatched) == 2


def test_notice_hash_set_before_upsert():
    """Notices must have content_hash set before reaching upsert_batch."""
    from uvo_pipeline.utils.hashing import compute_notice_hash

    n = _make_notice()
    assert n.content_hash is None  # default — not set by model

    n.content_hash = compute_notice_hash(n)
    assert n.content_hash is not None
    assert n.content_hash.startswith("sha256:")
