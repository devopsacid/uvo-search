"""Worker status endpoint — aggregate last event per component from ingestion_log."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from uvo_api.db import get_db
from uvo_api.models import WorkerStatus, WorkerStatusResponse

router = APIRouter(prefix="/api/dashboard", tags=["worker-status"])

COMPONENTS = [
    "extractor:vestnik",
    "extractor:crz",
    "extractor:ted",
    "extractor:itms",
    "ingestor",
    "dedup-worker",
]

_STALE_THRESHOLDS: dict[str, int] = {
    "extractor:vestnik": 7200,
    "extractor:crz": 7200,
    "extractor:ted": 7200,
    "extractor:itms": 7200,
    "ingestor": 600,
    "dedup-worker": 600,
}

_ERROR_EVENTS = {"cycle_failed", "write_failed", "redis_connect_failed"}


def _to_iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_status(
    last_event: str | None,
    last_level: str | None,
    last_ts: datetime | None,
    component: str,
) -> tuple[str, float | None]:
    if last_ts is None:
        return "unknown", None

    now = datetime.now(timezone.utc)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    age = (now - last_ts).total_seconds()

    if last_event in _ERROR_EVENTS or last_level in ("error", "critical"):
        return "error", age
    if last_event == "worker_stopped":
        return "stopped", age
    threshold = _STALE_THRESHOLDS.get(component, 7200)
    if age > threshold:
        return "stale", age
    return "healthy", age


@router.get("/worker-status", response_model=WorkerStatusResponse)
async def get_worker_status() -> WorkerStatusResponse:
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    pipeline = [
        {"$match": {"component": {"$in": COMPONENTS}}},
        {"$sort": {"ts": -1}},
        {"$group": {
            "_id": "$component",
            "last_ts": {"$first": "$ts"},
            "last_level": {"$first": "$level"},
            "last_event": {"$first": "$event"},
            "last_message": {"$first": "$message"},
            "last_source": {"$first": "$source"},
            "last_instance_id": {"$first": "$instance_id"},
        }},
    ]
    rows: dict[str, dict] = {}
    async for doc in db.ingestion_log.aggregate(pipeline):
        rows[doc["_id"]] = doc

    workers: list[WorkerStatus] = []
    for component in COMPONENTS:
        doc = rows.get(component)

        last_ts: datetime | None = None
        last_event: str | None = None
        last_level: str | None = None
        last_message: str | None = None

        if doc:
            last_ts = doc.get("last_ts")
            last_event = doc.get("last_event")
            last_level = doc.get("last_level")
            last_message = doc.get("last_message")

        status, age_seconds = _derive_status(last_event, last_level, last_ts, component)

        events_24h = await db.ingestion_log.count_documents({
            "component": component,
            "ts": {"$gte": cutoff_24h},
            "event": {"$in": ["cycle_complete", "batch_written"]},
        })

        workers.append(WorkerStatus(
            component=component,
            name=component,
            status=status,
            last_event=last_event,
            last_level=last_level,
            last_message=last_message,
            last_ts=_to_iso_z(last_ts) if last_ts is not None else None,
            age_seconds=age_seconds,
            events_24h=events_24h,
        ))

    return WorkerStatusResponse(
        workers=workers,
        generated_at=_to_iso_z(now),
    )
