# src/uvo_api/routers/ingestion.py
"""Ingestion health/analytics dashboard endpoint."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from uvo_api.db import get_db
from uvo_api.models import (
    DailyBucket,
    IngestionDashboard,
    IngestionLatestRun,
    IngestionSourceStatus,
    IngestionTimeseries,
    IngestionTotals,
)
from uvo_pipeline.health import SOURCES, collect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_STALE_THRESHOLD = 172800  # 48 h in seconds
_WARN_THRESHOLD = 86400    # 24 h in seconds
_TIMESERIES_DAYS = 30


def _coerce_dt(value) -> datetime | None:
    """Accept datetime or ISO-string; return naive-UTC datetime or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed
        except ValueError:
            return None
    return None


def _to_z(dt) -> str | None:
    """Format a datetime to ISO 8601 UTC with Z suffix, or return None.

    MongoDB always returns naive UTC datetimes; treat naive as UTC.
    """
    dt = _coerce_dt(dt)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(dt, now: datetime) -> float | None:
    dt = _coerce_dt(dt)
    if dt is None:
        return None
    # Normalise both sides to naive UTC.
    dt_naive = dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    return max(0.0, (now_naive - dt_naive).total_seconds())


def _source_status(age: float | None) -> str:
    if age is None:
        return "unknown"
    if age <= _WARN_THRESHOLD:
        return "healthy"
    if age <= _STALE_THRESHOLD:
        return "warning"
    return "stale"


async def _timeseries(db, now: datetime) -> list[DailyBucket]:
    """Aggregate daily ingestion counts per source for the last 30 days.

    `ingested_at` is stored in MongoDB as ISO-8601 string (e.g.
    "2026-04-26T01:02:00.521753"). ISO-8601 lex-sorts chronologically, so
    string comparison against an ISO threshold works correctly.
    """
    since_aware = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=_TIMESERIES_DAYS - 1)
    since = since_aware.replace(tzinfo=None)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")

    pipeline = [
        {"$match": {"ingested_at": {"$gte": since_iso}}},
        {
            "$group": {
                "_id": {
                    "date": {"$substr": ["$ingested_at", 0, 10]},
                    "source": "$source",
                },
                "count": {"$sum": 1},
            }
        },
    ]

    # Build a zero-filled day×source grid
    grid: dict[str, dict[str, int]] = {}
    for i in range(_TIMESERIES_DAYS):
        day = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        grid[day] = {s: 0 for s in SOURCES}

    async for doc in db.notices.aggregate(pipeline):
        day = doc["_id"]["date"]
        src = doc["_id"]["source"]
        if day in grid and src in SOURCES:
            grid[day][src] += doc["count"]

    return [
        DailyBucket(
            date=day,
            vestnik=grid[day]["vestnik"],
            crz=grid[day]["crz"],
            ted=grid[day]["ted"],
            uvo=grid[day]["uvo"],
            itms=grid[day]["itms"],
        )
        for day in sorted(grid)
    ]


@router.get("/ingestion", response_model=IngestionDashboard)
async def ingestion_dashboard() -> IngestionDashboard:
    db = get_db()
    now = datetime.now(UTC)

    report = await collect(db)
    ts_buckets = await _timeseries(db, now)

    raw_sources = report["sources"]
    source_statuses: list[IngestionSourceStatus] = []
    healthy_count = 0

    for s in raw_sources:
        last_at: datetime | None = s.get("last_ingested_at")
        age = _age_seconds(last_at, now)
        status = _source_status(age)
        if status == "healthy":
            healthy_count += 1

        source_statuses.append(
            IngestionSourceStatus(
                name=s["source"],
                notices=s.get("total", 0),
                last_24h=s.get("last_24h", 0),
                last_7d=s.get("last_7d", 0),
                registry=s.get("registry_entries", 0),
                skips=s.get("registry_skips", 0),
                disk_bytes=s.get("disk_bytes", 0),
                last_ingest_at=_to_z(last_at),
                age_seconds=round(age, 1) if age is not None else None,
                status=status,
            )
        )

    totals_raw = report["totals"]
    total_notices = totals_raw.get("notices", 0)
    cross_matches = totals_raw.get("cross_source_match_groups", 0)
    canonical_linked = totals_raw.get("notices_with_canonical_id", 0)
    registry_entries = totals_raw.get("registry_entries", 0)
    dedup_rate = round(cross_matches / max(total_notices, 1), 4)

    latest_raw = report["latest_run"]
    run_started: datetime | None = latest_raw.get("ingested_at")
    run_age = _age_seconds(run_started, now)

    return IngestionDashboard(
        generated_at=_to_z(now),  # type: ignore[arg-type]
        totals=IngestionTotals(
            notices=total_notices,
            registry_entries=registry_entries,
            cross_source_matches=cross_matches,
            canonical_linked=canonical_linked,
            sources_healthy=healthy_count,
            sources_total=len(SOURCES),
            last_run_age_seconds=round(run_age, 1) if run_age is not None else None,
            dedup_match_rate=dedup_rate,
        ),
        latest_run=IngestionLatestRun(
            id=latest_raw.get("run_id"),
            started_at=_to_z(run_started),
            finished_at=None,
        ),
        sources=source_statuses,
        timeseries=IngestionTimeseries(daily_ingestion=ts_buckets),
    )
