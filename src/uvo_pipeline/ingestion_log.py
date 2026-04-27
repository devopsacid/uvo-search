"""Centralized ingestion event log — one Mongo doc per event.

Used by extractors and the ingestor to record lifecycle transitions,
batches written, and warnings/errors. Documents expire after 30 days
via a TTL index on `ts`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

LogLevel = Literal["info", "warning", "error", "critical"]
LogEvent = Literal[
    "worker_started",
    "worker_stopped",
    "cycle_complete",
    "cycle_failed",
    "batch_written",
    "decode_failed",
    "write_failed",
    "redis_connect_failed",
    "notice_invalid_date",
    "validation_summary",
]


class IngestionLogEntry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: LogLevel
    event: LogEvent
    component: str  # e.g. "ingestor", "extractor:vestnik", "dedup-worker"
    source: str | None = None
    source_id: str | None = None
    instance_id: str | None = None
    pipeline_run_id: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


async def ensure_log_indexes(db: AsyncIOMotorDatabase) -> None:
    """Indexes for query patterns (recent entries, per-source, per-level) + 30-day TTL."""
    await db.ingestion_log.create_index([("ts", -1)], name="ts_desc")
    await db.ingestion_log.create_index(
        [("source", 1), ("ts", -1)], name="source_ts_desc"
    )
    await db.ingestion_log.create_index(
        [("level", 1), ("ts", -1)], name="level_ts_desc"
    )
    await db.ingestion_log.create_index(
        [("ts", 1)],
        name="ts_ttl",
        expireAfterSeconds=30 * 24 * 60 * 60,
    )


async def log_event(
    db: AsyncIOMotorDatabase,
    *,
    level: LogLevel,
    event: LogEvent,
    component: str,
    message: str,
    source: str | None = None,
    source_id: str | None = None,
    instance_id: str | None = None,
    pipeline_run_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write one log entry. Never raises — logging must not break the pipeline."""
    entry = IngestionLogEntry(
        level=level,
        event=event,
        component=component,
        message=message,
        source=source,
        source_id=source_id,
        instance_id=instance_id,
        pipeline_run_id=pipeline_run_id,
        details=details or {},
    )
    try:
        await db.ingestion_log.insert_one(entry.model_dump(mode="python"))
    except Exception:
        # Logging must never crash the worker; swallow and continue.
        # Real failures will show up in stdout via the regular Python logger.
        pass
