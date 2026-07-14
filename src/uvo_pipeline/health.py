"""Source health report — per-source ingestion stats from MongoDB."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

from uvo_pipeline.config import PipelineSettings

logger = logging.getLogger(__name__)

SOURCES = ["vestnik", "crz", "ted", "uvo", "itms"]

DEFAULT_STALE_THRESHOLD_DAYS = 14


def _parse_ts(v: Any) -> datetime | None:
    """Coerce a Mongo-stored timestamp (BSON datetime or ISO-8601 string) to an aware datetime."""
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


async def collect(
    db: AsyncIOMotorDatabase, *, stale_threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS
) -> dict[str, Any]:
    now = datetime.now(UTC)
    # `ingested_at` is stored as ISO-8601 string; ISO lex-sorts chronologically,
    # so string-vs-string comparisons work. Build ISO thresholds.
    now_naive = now.replace(tzinfo=None)
    day_ago_iso = (now_naive - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    week_ago_iso = (now_naive - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

    # Per-source aggregates from notices collection
    pipeline = [
        {"$group": {
            "_id": "$source",
            "total": {"$sum": 1},
            "last_ingested": {"$max": "$ingested_at"},
            "last_publication": {"$max": "$publication_date"},
            "last_24h": {"$sum": {"$cond": [{"$gte": ["$ingested_at", day_ago_iso]}, 1, 0]}},
            "last_7d": {"$sum": {"$cond": [{"$gte": ["$ingested_at", week_ago_iso]}, 1, 0]}},
        }},
    ]
    rows = {r["_id"]: r async for r in db.notices.aggregate(pipeline)}

    # Per-source BSON size — separate pipeline so mongomock environments without
    # $bsonSize support fall through to 0 instead of breaking the whole report.
    size_rows: dict[str, int] = {}
    try:
        size_pipeline = [
            {"$group": {"_id": "$source", "disk_bytes": {"$sum": {"$bsonSize": "$$ROOT"}}}},
        ]
        async for r in db.notices.aggregate(size_pipeline):
            size_rows[r["_id"]] = int(r.get("disk_bytes") or 0)
    except OperationFailure as exc:
        logger.debug("disk_bytes aggregation unavailable: %s", exc)

    # Checkpoint per source
    checkpoints = {
        c["source"]: c async for c in db.pipeline_state.find({})
    }

    sources = []
    for s in SOURCES:
        row = rows.get(s, {})
        cp = checkpoints.get("pipeline", {})  # current orchestrator uses single "pipeline" checkpoint
        last_ingested_at = row.get("last_ingested")
        last_ts = _parse_ts(last_ingested_at)
        days_since_last_ingest = (
            round((now - last_ts).total_seconds() / 86400, 2) if last_ts is not None else None
        )
        # No ingested_at at all (source never populated) counts as stale too —
        # that's what let ITMS sit silently exhausted for two months.
        stale = days_since_last_ingest is None or days_since_last_ingest > stale_threshold_days
        sources.append({
            "source": s,
            "total": row.get("total", 0),
            "last_24h": row.get("last_24h", 0),
            "last_7d": row.get("last_7d", 0),
            "last_ingested_at": last_ingested_at,
            "last_publication_date": row.get("last_publication"),
            "last_run_at": cp.get("last_run_at"),
            "disk_bytes": size_rows.get(s, 0),
            "days_since_last_ingest": days_since_last_ingest,
            "stale": stale,
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
        "stale_threshold_days": stale_threshold_days,
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
    """Render elapsed time since `v`.

    `v` is stored as an ISO-8601 string in Mongo (see upsert_batch), not a
    BSON datetime, so this must parse strings too — previously the isinstance
    check only accepted datetime and silently returned "—" for every row.
    """
    parsed = _parse_ts(v)
    if parsed is None:
        return "—"
    delta = now - parsed
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
    lines.append(f"Stale threshold: >{report.get('stale_threshold_days', DEFAULT_STALE_THRESHOLD_DAYS)} days")
    lines.append("")
    lines.append(
        f"{'source':<8} {'notices':>8} {'24h':>6} {'7d':>7} "
        f"{'registry':>9} {'skips':>7} {'last ingest':>20} {'age':>8} {'days':>7} {'stale':>6}"
    )
    lines.append("-" * 96)
    for s in report["sources"]:
        lines.append(
            f"{s['source']:<8} "
            f"{s['total']:>8} "
            f"{s['last_24h']:>6} "
            f"{s['last_7d']:>7} "
            f"{s.get('registry_entries', 0):>9} "
            f"{s.get('registry_skips', 0):>7} "
            f"{_fmt_dt(s['last_ingested_at']):>20} "
            f"{_age(s['last_ingested_at'], now):>8} "
            f"{s.get('days_since_last_ingest') if s.get('days_since_last_ingest') is not None else '—':>7} "
            f"{'STALE' if s.get('stale') else 'ok':>6}"
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


async def run_health(
    settings: PipelineSettings,
    *,
    as_json: bool = False,
    stale_threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS,
) -> str:
    client = AsyncIOMotorClient(settings.mongodb_uri)
    try:
        db = client[settings.mongodb_database]
        report = await collect(db, stale_threshold_days=stale_threshold_days)
    finally:
        client.close()
    return render_json(report) if as_json else render_text(report)
