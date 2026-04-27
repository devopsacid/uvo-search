"""Read-only endpoint exposing the ingestion_log collection."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from uvo_api.db import get_db
from uvo_api.models import IngestionLogItem, IngestionLogResponse

router = APIRouter(prefix="/api/dashboard", tags=["ingestion-log"])


def _to_iso_z(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


@router.get("/ingestion-log", response_model=IngestionLogResponse)
async def get_ingestion_log(
    level: str | None = Query(None, pattern="^(info|warning|error|critical)$"),
    source: str | None = Query(None),
    event: str | None = Query(None),
    component: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> IngestionLogResponse:
    db = get_db()
    query: dict = {}
    if level:
        query["level"] = level
    if source:
        query["source"] = source
    if event:
        query["event"] = event
    if component:
        query["component"] = component

    total = await db.ingestion_log.count_documents(query)
    cursor = (
        db.ingestion_log.find(query)
        .sort("ts", -1)
        .skip(offset)
        .limit(limit)
    )
    items: list[IngestionLogItem] = []
    async for doc in cursor:
        items.append(
            IngestionLogItem(
                ts=_to_iso_z(doc.get("ts")),
                level=doc.get("level", "info"),
                event=doc.get("event", "unknown"),
                component=doc.get("component", ""),
                source=doc.get("source"),
                source_id=doc.get("source_id"),
                instance_id=doc.get("instance_id"),
                pipeline_run_id=doc.get("pipeline_run_id"),
                message=doc.get("message", ""),
                details=doc.get("details") or {},
            )
        )
    return IngestionLogResponse(total=total, items=items)
