"""Tests for the per-source health report — staleness detection (Fix 5)."""

from datetime import UTC, datetime, timedelta

import pytest

from uvo_pipeline.health import collect, render_json, render_text


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


@pytest.mark.asyncio
async def test_recent_source_is_not_stale(mock_mongo_db):
    now = datetime.now(UTC)
    await mock_mongo_db.notices.insert_one({
        "source": "vestnik",
        "source_id": "V-1",
        "ingested_at": _iso(now - timedelta(hours=2)),
        "publication_date": "2026-01-01",
    })

    report = await collect(mock_mongo_db, stale_threshold_days=14)
    vestnik = next(s for s in report["sources"] if s["source"] == "vestnik")

    assert vestnik["stale"] is False
    assert vestnik["days_since_last_ingest"] < 1


@pytest.mark.asyncio
async def test_source_stale_after_threshold(mock_mongo_db):
    """Regression for the ITMS incident: a source quiet >14 days must be flagged stale."""
    now = datetime.now(UTC)
    await mock_mongo_db.notices.insert_one({
        "source": "itms",
        "source_id": "I-1",
        "ingested_at": _iso(now - timedelta(days=68)),
        "publication_date": "2026-01-01",
    })

    report = await collect(mock_mongo_db, stale_threshold_days=14)
    itms = next(s for s in report["sources"] if s["source"] == "itms")

    assert itms["stale"] is True
    assert itms["days_since_last_ingest"] == pytest.approx(68, abs=1)


@pytest.mark.asyncio
async def test_source_with_no_notices_is_stale(mock_mongo_db):
    """A source with zero notices ever ingested must be flagged stale, not silently '-'."""
    report = await collect(mock_mongo_db, stale_threshold_days=14)
    uvo = next(s for s in report["sources"] if s["source"] == "uvo")

    assert uvo["total"] == 0
    assert uvo["days_since_last_ingest"] is None
    assert uvo["stale"] is True


@pytest.mark.asyncio
async def test_stale_threshold_is_configurable(mock_mongo_db):
    now = datetime.now(UTC)
    await mock_mongo_db.notices.insert_one({
        "source": "crz",
        "source_id": "C-1",
        "ingested_at": _iso(now - timedelta(days=5)),
        "publication_date": "2026-01-01",
    })

    lenient = await collect(mock_mongo_db, stale_threshold_days=14)
    strict = await collect(mock_mongo_db, stale_threshold_days=1)

    crz_lenient = next(s for s in lenient["sources"] if s["source"] == "crz")
    crz_strict = next(s for s in strict["sources"] if s["source"] == "crz")

    assert crz_lenient["stale"] is False
    assert crz_strict["stale"] is True


@pytest.mark.asyncio
async def test_render_text_includes_stale_marker(mock_mongo_db):
    now = datetime.now(UTC)
    await mock_mongo_db.notices.insert_one({
        "source": "itms",
        "source_id": "I-1",
        "ingested_at": _iso(now - timedelta(days=68)),
        "publication_date": "2026-01-01",
    })

    report = await collect(mock_mongo_db, stale_threshold_days=14)
    text = render_text(report)

    assert "STALE" in text
    assert "itms" in text


@pytest.mark.asyncio
async def test_render_json_includes_stale_fields(mock_mongo_db):
    report = await collect(mock_mongo_db, stale_threshold_days=14)
    text = render_json(report)

    assert "days_since_last_ingest" in text
    assert "stale" in text
    assert "stale_threshold_days" in text
