# tests/api/test_dashboard_ingestion.py
"""Unit tests for GET /api/dashboard/ingestion."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from uvo_api.app import create_app

SOURCES = ["vestnik", "crz", "ted", "uvo", "itms"]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_db():
    client = AsyncMongoMockClient()
    db = client["uvo_search_test"]
    yield db
    client.close()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://localhost:27017")
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_notices(db, source: str, count: int, ingested_at: datetime) -> None:
    """Insert `count` minimal notice documents for a source."""
    docs = [
        {
            "source": source,
            "source_id": f"{source}-{i}",
            "ingested_at": ingested_at,
            "pipeline_run_id": "run-abc",
        }
        for i in range(count)
    ]
    if docs:
        await db.notices.insert_many(docs)


async def _seed_registry(db, source: str, count: int, skipped: int) -> None:
    docs = [
        {
            "source": source,
            "source_id": f"{source}-reg-{i}",
            "content_hash": f"hash-{i}",
            "last_seen_at": _now(),
            "skipped_count": skipped,
        }
        for i in range(count)
    ]
    if docs:
        await db.ingested_docs.insert_many(docs)


# ---------------------------------------------------------------------------
# Tests: response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_shape(client, mock_db):
    """Full endpoint returns all required top-level keys with correct types."""
    now = _now()
    await _seed_notices(mock_db, "vestnik", 5, now - timedelta(hours=1))
    await _seed_registry(mock_db, "vestnik", 5, 0)

    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    body = resp.json()

    assert "generated_at" in body
    assert "totals" in body
    assert "latest_run" in body
    assert "sources" in body
    assert "timeseries" in body

    totals = body["totals"]
    for key in (
        "notices",
        "registry_entries",
        "cross_source_matches",
        "canonical_linked",
        "sources_healthy",
        "sources_total",
        "dedup_match_rate",
    ):
        assert key in totals, f"missing totals.{key}"

    lr = body["latest_run"]
    assert "id" in lr
    assert "started_at" in lr
    assert "finished_at" in lr

    ts = body["timeseries"]
    assert "daily_ingestion" in ts


# ---------------------------------------------------------------------------
# Tests: sources always contains all 5 names
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sources_always_five(client, mock_db):
    """sources list must contain exactly the 5 expected names even with no data."""
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    body = resp.json()
    names = [s["name"] for s in body["sources"]]
    assert sorted(names) == sorted(SOURCES)
    assert len(names) == 5


# ---------------------------------------------------------------------------
# Tests: status thresholds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hours_ago, expected_status",
    [
        (23, "healthy"),   # < 24 h
        (30, "warning"),   # 24 h < x < 48 h
        (50, "stale"),     # > 48 h
    ],
)
@pytest.mark.asyncio
async def test_status_thresholds(client, mock_db, hours_ago, expected_status):
    ingested_at = _now() - timedelta(hours=hours_ago)
    await _seed_notices(mock_db, "vestnik", 1, ingested_at)

    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    body = resp.json()
    vestnik = next(s for s in body["sources"] if s["name"] == "vestnik")
    assert vestnik["status"] == expected_status, (
        f"expected {expected_status} for {hours_ago}h age, got {vestnik['status']}"
    )


@pytest.mark.asyncio
async def test_status_unknown_when_no_notices(client, mock_db):
    """Source with no notices must report status=unknown."""
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    body = resp.json()
    for s in body["sources"]:
        assert s["status"] == "unknown"
        assert s["last_ingest_at"] is None


# ---------------------------------------------------------------------------
# Tests: timeseries shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_has_30_entries(client, mock_db):
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    daily = resp.json()["timeseries"]["daily_ingestion"]
    assert len(daily) == 30


@pytest.mark.asyncio
async def test_timeseries_has_all_source_keys(client, mock_db):
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    daily = resp.json()["timeseries"]["daily_ingestion"]
    for entry in daily:
        for src in SOURCES:
            assert src in entry, f"missing source '{src}' in timeseries entry {entry['date']}"


@pytest.mark.asyncio
async def test_timeseries_ascending_dates(client, mock_db):
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    dates = [e["date"] for e in resp.json()["timeseries"]["daily_ingestion"]]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_timeseries_counts_ingested_today(client, mock_db):
    """Notices ingested today must show up in today's timeseries bucket."""
    now = _now()
    await _seed_notices(mock_db, "crz", 3, now - timedelta(hours=2))

    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    daily = resp.json()["timeseries"]["daily_ingestion"]
    today_str = now.strftime("%Y-%m-%d")
    today = next((e for e in daily if e["date"] == today_str), None)
    assert today is not None
    assert today["crz"] == 3


@pytest.mark.asyncio
async def test_timeseries_zeros_for_missing_days(client, mock_db):
    """Days with no ingestion must be zero-filled, not absent."""
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    daily = resp.json()["timeseries"]["daily_ingestion"]
    for entry in daily:
        for src in SOURCES:
            assert isinstance(entry[src], int)
            assert entry[src] >= 0


# ---------------------------------------------------------------------------
# Tests: totals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_totals_sources_total_is_five(client, mock_db):
    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    assert resp.json()["totals"]["sources_total"] == 5


@pytest.mark.asyncio
async def test_sources_healthy_counts_only_healthy(client, mock_db):
    """Only sources with age <= 24 h count toward sources_healthy."""
    now = _now()
    # vestnik: healthy (1 h ago)
    await _seed_notices(mock_db, "vestnik", 1, now - timedelta(hours=1))
    # crz: warning (30 h ago)
    await _seed_notices(mock_db, "crz", 1, now - timedelta(hours=30))
    # rest: no data → unknown

    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    assert resp.json()["totals"]["sources_healthy"] == 1


@pytest.mark.asyncio
async def test_dedup_match_rate_zero_when_no_matches(client, mock_db):
    await _seed_notices(mock_db, "vestnik", 10, _now() - timedelta(hours=1))

    with patch("uvo_api.routers.ingestion.get_db", return_value=mock_db):
        resp = client.get("/api/dashboard/ingestion")

    assert resp.status_code == 200
    assert resp.json()["totals"]["dedup_match_rate"] == 0.0
