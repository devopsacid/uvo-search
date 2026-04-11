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
