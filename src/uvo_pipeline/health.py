"""Source health report — per-source ingestion stats from MongoDB."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from uvo_pipeline.config import PipelineSettings

SOURCES = ["vestnik", "crz", "ted", "uvo", "itms"]


async def collect(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    # Per-source aggregates from notices collection
    pipeline = [
        {"$group": {
            "_id": "$source",
            "total": {"$sum": 1},
            "last_ingested": {"$max": "$ingested_at"},
            "last_publication": {"$max": "$publication_date"},
            "last_24h": {"$sum": {"$cond": [{"$gte": ["$ingested_at", day_ago]}, 1, 0]}},
            "last_7d": {"$sum": {"$cond": [{"$gte": ["$ingested_at", week_ago]}, 1, 0]}},
        }},
    ]
    rows = {r["_id"]: r async for r in db.notices.aggregate(pipeline)}

    # Checkpoint per source
    checkpoints = {
        c["source"]: c async for c in db.pipeline_state.find({})
    }

    sources = []
    for s in SOURCES:
        row = rows.get(s, {})
        cp = checkpoints.get("pipeline", {})  # current orchestrator uses single "pipeline" checkpoint
        sources.append({
            "source": s,
            "total": row.get("total", 0),
            "last_24h": row.get("last_24h", 0),
            "last_7d": row.get("last_7d", 0),
            "last_ingested_at": row.get("last_ingested"),
            "last_publication_date": row.get("last_publication"),
            "last_run_at": cp.get("last_run_at"),
        })

    # Cross-source dedup stats
    total_matches = await db.cross_source_matches.count_documents({})
    total_notices = await db.notices.count_documents({})
    canonical_notices = await db.notices.count_documents({"canonical_id": {"$ne": None}})

    # Ingestion registry stats (per-source)
    registry_pipeline = [
        {"$group": {
            "_id": "$source",
            "registered": {"$sum": 1},
            "total_skips": {"$sum": "$skipped_count"},
            "last_seen": {"$max": "$last_seen_at"},
        }},
    ]
    registry_rows = {
        r["_id"]: r async for r in db.ingested_docs.aggregate(registry_pipeline)
    }
    registry_total = await db.ingested_docs.count_documents({})
    for s in sources:
        reg = registry_rows.get(s["source"], {})
        s["registry_entries"] = reg.get("registered", 0)
        s["registry_skips"] = reg.get("total_skips", 0)
        s["registry_last_seen"] = reg.get("last_seen")

    # Latest pipeline run (infer from most recent ingested_at + run_id)
    latest_doc = await db.notices.find_one(
        {"pipeline_run_id": {"$ne": None}},
        sort=[("ingested_at", -1)],
        projection={"pipeline_run_id": 1, "ingested_at": 1},
    )

    return {
        "generated_at": now,
        "totals": {
            "notices": total_notices,
            "cross_source_match_groups": total_matches,
            "notices_with_canonical_id": canonical_notices,
            "registry_entries": registry_total,
        },
        "latest_run": {
            "run_id": latest_doc.get("pipeline_run_id") if latest_doc else None,
            "ingested_at": latest_doc.get("ingested_at") if latest_doc else None,
        },
        "sources": sources,
    }


def _fmt_dt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M UTC")
    return str(v)


def _age(v: Any, now: datetime) -> str:
    if not isinstance(v, datetime):
        return "—"
    # Normalize to aware UTC
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    delta = now - v
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    minutes = (delta.seconds % 3600) // 60
    return f"{minutes}m ago"


def render_text(report: dict[str, Any]) -> str:
    now = report["generated_at"]
    lines = []
    lines.append(f"UVO-Search Source Health — {_fmt_dt(now)}")
    lines.append("=" * 72)
    t = report["totals"]
    lines.append(
        f"Total notices: {t['notices']:>8}   "
        f"Registry entries: {t['registry_entries']:>8}   "
        f"Cross-source groups: {t['cross_source_match_groups']:>5}   "
        f"Canonical-linked: {t['notices_with_canonical_id']:>6}"
    )
    lr = report["latest_run"]
    lines.append(f"Latest run: {lr.get('run_id') or '—'}  ({_fmt_dt(lr.get('ingested_at'))})")
    lines.append("")
    lines.append(
        f"{'source':<8} {'notices':>8} {'24h':>6} {'7d':>7} "
        f"{'registry':>9} {'skips':>7} {'last ingest':>20} {'age':>8}"
    )
    lines.append("-" * 80)
    for s in report["sources"]:
        lines.append(
            f"{s['source']:<8} "
            f"{s['total']:>8} "
            f"{s['last_24h']:>6} "
            f"{s['last_7d']:>7} "
            f"{s.get('registry_entries', 0):>9} "
            f"{s.get('registry_skips', 0):>7} "
            f"{_fmt_dt(s['last_ingested_at']):>20} "
            f"{_age(s['last_ingested_at'], now):>8}"
        )
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "isoformat"):
            return o.isoformat()
        raise TypeError(f"Not serializable: {type(o)}")

    return json.dumps(report, default=default, indent=2)


async def run_health(settings: PipelineSettings, *, as_json: bool = False) -> str:
    client = AsyncIOMotorClient(settings.mongodb_uri)
    try:
        db = client[settings.mongodb_database]
        report = await collect(db)
    finally:
        client.close()
    return render_json(report) if as_json else render_text(report)
