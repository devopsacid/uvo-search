"""Centralized ingestion event log — one Mongo doc per event.

Used by extractors and the ingestor to record lifecycle transitions,
batches written, and warnings/errors. Documents expire after 30 days
via a TTL index on `ts`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
    "index_bootstrap_failed",
    "entry_dead_lettered",
    "partial_write_failed",
]


class IngestionLogEntry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
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
    await db.ingestion_log.create_index([("source", 1), ("ts", -1)], name="source_ts_desc")
    await db.ingestion_log.create_index([("level", 1), ("ts", -1)], name="level_ts_desc")
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
        # Logging must never crash the worker, but a dead log sink must not be
        # invisible either: record the failure (with traceback) on stderr.
        logger.exception("ingestion_log: failed to write %s event for %s", event, component)


async def log_events(db: AsyncIOMotorDatabase, entries: list[IngestionLogEntry]) -> None:
    """Write many log entries in one ``insert_many``. Never raises."""
    if not entries:
        return
    try:
        await db.ingestion_log.insert_many(
            [e.model_dump(mode="python") for e in entries], ordered=False
        )
    except Exception:
        logger.exception("ingestion_log: failed to write batch of %d events", len(entries))
