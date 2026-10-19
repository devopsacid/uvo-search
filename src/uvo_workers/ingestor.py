"""Ingestor worker — reads Redis Streams and writes to Mongo + Neo4j.

Delivery contract: an entry is acknowledged only once its notice has been
written to *both* stores. Entries whose write failed stay pending and are
redelivered by the periodic reclaim; after ``ingestor_max_deliveries``
deliveries an entry is processed on its own and, if it still fails, parked in
the ``notices:dead`` stream and acknowledged so it cannot loop forever.
"""

import asyncio
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from neo4j import AsyncGraphDatabase
from pydantic_settings import BaseSettings
from redis.exceptions import RedisError

from uvo_core.domain.models import CanonicalNotice
from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.ingestion_log import IngestionLogEntry, log_event, log_events
from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch
from uvo_pipeline.loaders.neo4j import ensure_constraints, merge_notice_batch
from uvo_pipeline.pubsub import publish
from uvo_pipeline.redis_client import close_redis, get_redis, get_redis_settings
from uvo_pipeline.streams import (
    ack,
    autoclaim_stale,
    decode_entry,
    delivery_counts,
    ensure_consumer_group,
    group_stats,
    read_group,
    trim_consumed,
)
from uvo_pipeline.utils.date_validation import validate_notice_dates
from uvo_workers.errors import redact_exception
from uvo_workers.health import serve_health
from uvo_workers.metrics import build_registry

logger = logging.getLogger(__name__)

_SOURCES = ["vestnik", "crz", "ted", "itms"]
_STREAMS = [f"notices:{s}" for s in _SOURCES]
_GROUP = "ingestor"
DEAD_LETTER_STREAM = "notices:dead"
_DEAD_LETTER_MAXLEN = 10_000

# Neo4j constraint creation races uvo_mcp's identical bootstrap and can deadlock.
_BOOTSTRAP_ATTEMPTS = 3
_BOOTSTRAP_BACKOFF_SECONDS = 2.0

# Individually re-processing this many suspects and seeing *all* of them fail
# looks like a dependency outage, not poison data: dead-lettering then would
# discard good entries, so they are left pending instead.
_OUTAGE_SUSPECT_THRESHOLD = 3


class IngestorSettings(BaseSettings):
    ingestor_batch_size: int = 100
    # Deliveries before a failing entry is processed alone and, if it still
    # fails, dead-lettered.
    ingestor_max_deliveries: int = 5
    # How often (and how stale an entry must be) to reclaim pending entries,
    # independent of whether new traffic is flowing.
    ingestor_reclaim_interval_seconds: float = 30.0
    ingestor_reclaim_min_idle_ms: int = 60_000
    # Cadence for safe stream trimming + lag/PEL metric refresh.
    ingestor_maintenance_interval_seconds: float = 30.0
    health_port: int = 8095

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


@lru_cache
def get_settings() -> IngestorSettings:
    """One IngestorSettings construction per process (cached factory idiom)."""
    return IngestorSettings()


@dataclass
class IngestorContext:
    """Long-lived handles shared by the batch-processing functions."""

    db: AsyncIOMotorDatabase
    redis: object
    neo4j_driver: object
    instance_id: str
    metrics: dict = field(default_factory=dict)


@dataclass
class BatchOutcome:
    """Result of processing one group of stream entries."""

    succeeded: list[bytes] = field(default_factory=list)
    # Entries whose notice failed to write to Mongo/Neo4j (left pending).
    failed: list[tuple[bytes, dict]] = field(default_factory=list)
    # Set when the whole batch raised (infrastructure error); nothing was acked.
    error: BaseException | None = None


def is_due(last_run: float | None, now: float, interval: float) -> bool:
    """True when a periodic task last run at ``last_run`` should run again."""
    return last_run is None or (now - last_run) >= interval


async def process_batch_logs(
    db: AsyncIOMotorDatabase,
    *,
    notices: list[CanonicalNotice],
    component: str,
    instance_id: str,
    stream_name: str,
) -> list[CanonicalNotice]:
    """Validate dates on each notice, log issues, return cleaned notices.

    The cleaned list keeps the same length and order as the input so the
    caller can ack the same set of stream entry IDs. All issues of a batch
    are written with a single ``insert_many``.
    """
    source = stream_name.removeprefix("notices:")
    cleaned: list[CanonicalNotice] = []
    entries: list[IngestionLogEntry] = []
    for notice in notices:
        clean, issues = validate_notice_dates(notice)
        cleaned.append(clean)
        for issue in issues:
            entries.append(
                IngestionLogEntry(
                    level="warning",
                    event="notice_invalid_date",
                    component=component,
                    source=source,
                    source_id=notice.source_id,
                    instance_id=instance_id,
                    message=f"{issue['field']} year {issue['year']} {issue['reason']}; nulled",
                    details=issue,
                )
            )
    await log_events(db, entries)
    return cleaned


def _failed_keys(result: object) -> set[tuple[str, str]]:
    """Failed (source, source_id) pairs from a loader result (tolerates stubs)."""
    if not isinstance(result, dict):
        return set()
    return {tuple(k) for k in result.get("failed") or []}


async def dead_letter(
    ctx: IngestorContext,
    stream_name: str,
    entry_id: bytes,
    fields: dict,
    reason: str,
) -> None:
    """Best-effort copy of an entry into ``notices:dead`` for later inspection."""
    try:
        await ctx.redis.xadd(
            DEAD_LETTER_STREAM,
            {
                "stream": stream_name,
                "entry_id": entry_id,
                "error": reason,
                "payload": fields.get(b"payload", b""),
            },
            maxlen=_DEAD_LETTER_MAXLEN,
            approximate=True,
        )
    except Exception as exc:
        logger.error("ingestor: failed to dead-letter %r from %s: %s", entry_id, stream_name, exc)


async def _reject_poison(
    ctx: IngestorContext, stream_name: str, entry_id: bytes, fields: dict, exc: Exception
) -> None:
    """Log, ack and park an entry that cannot be decoded.

    Acked immediately: the failure is durably logged, and an unparseable
    payload cannot succeed on retry, so leaving it pending would redeliver it
    forever. The dead-letter write is best-effort and never blocks the ack.
    """
    logger.warning("Failed to decode entry from %s: %s", stream_name, exc)
    await log_event(
        ctx.db,
        level="warning",
        event="decode_failed",
        component="ingestor",
        source=stream_name.removeprefix("notices:"),
        instance_id=ctx.instance_id,
        message=f"decode failed: {redact_exception(exc)}",
    )
    try:
        await ack(ctx.redis, stream_name, _GROUP, [entry_id])
    except Exception as ack_exc:
        logger.error("ingestor: failed to ack poison entry from %s: %s", stream_name, ack_exc)
    await dead_letter(ctx, stream_name, entry_id, fields, str(exc))


async def process_entries(
    ctx: IngestorContext, stream_name: str, entries: list[tuple[bytes, dict]]
) -> BatchOutcome:
    """Decode, write and acknowledge one group of entries from ``stream_name``.

    Only entries whose notice reached both Mongo and Neo4j are acked; the rest
    stay pending for redelivery. Never raises for per-batch failures.
    """
    outcome = BatchOutcome()
    source = stream_name.removeprefix("notices:")
    notices: list[CanonicalNotice] = []
    kept: list[tuple[bytes, dict]] = []

    for entry_id, fields in entries:
        try:
            decoded = decode_entry(fields)
            notices.append(CanonicalNotice.model_validate(decoded["payload"]))
            kept.append((entry_id, fields))
        except Exception as exc:
            await _reject_poison(ctx, stream_name, entry_id, fields, exc)

    if not notices:
        return outcome

    notices = await process_batch_logs(
        ctx.db,
        notices=notices,
        component="ingestor",
        instance_id=ctx.instance_id,
        stream_name=stream_name,
    )

    try:
        failed = _failed_keys(await upsert_batch(ctx.db, notices))
        mongo_ok = [n for n in notices if (n.source, n.source_id) not in failed]
        if mongo_ok:
            async with ctx.neo4j_driver.session() as neo4j_session:
                failed |= _failed_keys(await merge_notice_batch(neo4j_session, mongo_ok))

        ok_ids: list[bytes] = []
        for (entry_id, fields), notice in zip(kept, notices, strict=True):
            if (notice.source, notice.source_id) in failed:
                outcome.failed.append((entry_id, fields))
            else:
                ok_ids.append(entry_id)
        outcome.succeeded = ok_ids

        if ok_ids:
            await ack(ctx.redis, stream_name, _GROUP, ok_ids)
            await publish(ctx.redis, "notices:written", {"source": source, "count": len(ok_ids)})
            ctx.metrics["batches_processed"] = ctx.metrics.get("batches_processed", 0) + 1
            ctx.metrics["notices_written"] = ctx.metrics.get("notices_written", 0) + len(ok_ids)
            ctx.metrics["last_success_at"] = time.time()
            logger.info("ingestor: wrote %d notices from %s", len(ok_ids), stream_name)
            await log_event(
                ctx.db,
                level="info",
                event="batch_written",
                component="ingestor",
                source=source,
                instance_id=ctx.instance_id,
                message=f"wrote {len(ok_ids)} notices from {stream_name}",
                details={"count": len(ok_ids)},
            )

        if outcome.failed:
            msg = f"{len(outcome.failed)} of {len(kept)} notices failed to write; left pending"
            logger.error("ingestor: %s (%s)", msg, stream_name)
            ctx.metrics["last_error"] = msg
            await log_event(
                ctx.db,
                level="error",
                event="partial_write_failed",
                component="ingestor",
                source=source,
                instance_id=ctx.instance_id,
                message=msg,
                details={"failed": len(outcome.failed), "total": len(kept)},
            )
        else:
            # Clear a prior cycle's error now that a batch has written cleanly:
            # last_error must reflect the last cycle, not "any cycle ever this
            # process lifetime", or one transient failure marks /readyz unready
            # until restart.
            ctx.metrics["last_error"] = None

    except Exception as exc:
        logger.error(
            "ingestor: write failed for %s, not acking: %s", stream_name, exc, exc_info=True
        )
        msg = redact_exception(exc)
        ctx.metrics["last_error"] = msg
        outcome.error = exc
        await log_event(
            ctx.db,
            level="error",
            event="write_failed",
            component="ingestor",
            source=source,
            instance_id=ctx.instance_id,
            message=msg,
        )

    return outcome


async def reclaim_pending(
    ctx: IngestorContext, settings: IngestorSettings, consumer_name: str
) -> int:
    """Reclaim stale pending entries on every stream and re-process them.

    Entries delivered fewer than ``ingestor_max_deliveries`` times are retried
    as a batch. Entries at/over the limit are processed one at a time so a
    single poison notice cannot sink its neighbours; those that still fail are
    dead-lettered and acked. Returns the number of entries reclaimed.
    """
    total = 0
    for stream in _STREAMS:
        entries = await autoclaim_stale(
            ctx.redis,
            stream,
            _GROUP,
            consumer_name,
            min_idle_ms=settings.ingestor_reclaim_min_idle_ms,
        )
        if not entries:
            continue
        total += len(entries)
        logger.info("ingestor: reclaimed %d stale entries from %s", len(entries), stream)

        counts = await delivery_counts(ctx.redis, stream, _GROUP, [eid for eid, _ in entries])
        limit = settings.ingestor_max_deliveries
        fresh = [e for e in entries if counts.get(e[0], 1) < limit]
        suspects = [e for e in entries if counts.get(e[0], 1) >= limit]

        if fresh:
            await process_entries(ctx, stream, fresh)

        outcomes = [(entry, await process_entries(ctx, stream, [entry])) for entry in suspects]
        failing = [(entry, out) for entry, out in outcomes if out.failed or out.error]
        outage = len(suspects) >= _OUTAGE_SUSPECT_THRESHOLD and len(failing) == len(suspects)
        if outage:
            logger.warning(
                "ingestor: all %d over-limit entries on %s failed individually; "
                "treating as a dependency outage, not dead-lettering",
                len(suspects),
                stream,
            )
            continue
        for (entry_id, fields), out in failing:
            if out.error is not None:
                continue  # infrastructure error, not evidence the entry is bad
            await _park_failed_entry(ctx, stream, entry_id, fields, counts.get(entry_id, limit))
    return total


async def _park_failed_entry(
    ctx: IngestorContext, stream: str, entry_id: bytes, fields: dict, deliveries: int
) -> None:
    reason = f"write failed after {deliveries} deliveries"
    logger.error("ingestor: dead-lettering %r from %s: %s", entry_id, stream, reason)
    await dead_letter(ctx, stream, entry_id, fields, reason)
    await ack(ctx.redis, stream, _GROUP, [entry_id])
    await log_event(
        ctx.db,
        level="error",
        event="entry_dead_lettered",
        component="ingestor",
        source=stream.removeprefix("notices:"),
        instance_id=ctx.instance_id,
        message=reason,
        details={"entry_id": entry_id.decode(errors="replace"), "deliveries": deliveries},
    )


async def run_maintenance(ctx: IngestorContext) -> None:
    """Trim fully-acked stream prefixes and refresh lag/PEL/dead-letter metrics."""
    lag: dict[str, int] = {}
    pending: dict[str, int] = {}
    for stream in _STREAMS:
        try:
            removed = await trim_consumed(ctx.redis, stream, _GROUP)
            if removed:
                logger.info("ingestor: trimmed %d consumed entries from %s", removed, stream)
            stats = await group_stats(ctx.redis, stream, _GROUP)
        except RedisError as exc:
            logger.warning("ingestor: maintenance failed on %s: %s", stream, exc)
            continue
        lag[stream] = stats["lag"]
        pending[stream] = stats["pending"]
    ctx.metrics["stream_lag"] = lag
    ctx.metrics["stream_pending"] = pending
    try:
        ctx.metrics["dead_letter_length"] = await ctx.redis.xlen(DEAD_LETTER_STREAM)
    except RedisError as exc:
        logger.warning("ingestor: dead-letter length unavailable: %s", exc)


async def run_ingestor() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    pipeline_settings = get_pipeline_settings()
    redis_settings = get_redis_settings()
    instance_id = uuid.uuid4().hex
    # Consumer name must be stable across restarts so this pod's own pending
    # entries are redelivered to it via XAUTOCLAIM. Kubernetes sets HOSTNAME
    # to the pod name (stable for a StatefulSet, stable-enough for a
    # Deployment pod across in-place restarts). instance_id stays random for
    # log correlation of a single process lifetime.
    consumer_name = os.environ.get("HOSTNAME") or f"ingestor-{instance_id[:8]}"

    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]

    metrics: dict = {
        "instance_id": instance_id,
        "batches_processed": 0,
        "notices_written": 0,
        "last_error": None,
        "last_success_at": None,
        "stream_lag": {},
        "stream_pending": {},
        "dead_letter_length": 0,
        "redis_connected": False,
    }

    try:
        redis_client = await get_redis(
            url=redis_settings.redis_url,
            password=redis_settings.redis_password or None,
        )
        await redis_client.ping()
        metrics["redis_connected"] = True
    except Exception as exc:
        logger.critical("Redis connection failed: %s", exc)
        try:
            await log_event(
                db,
                level="critical",
                event="redis_connect_failed",
                component="ingestor",
                instance_id=instance_id,
                message=f"Redis connection failed: {redact_exception(exc)}",
            )
        except Exception:
            pass
        mongo_client.close()
        raise SystemExit(1) from exc

    await log_event(
        db,
        level="info",
        event="worker_started",
        component="ingestor",
        instance_id=instance_id,
        message="ingestor up",
        details={"streams": _STREAMS},
    )

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received, stopping ingestor")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            pass

    metrics_registry = build_registry("ingestor")
    health_task = asyncio.create_task(
        serve_health(settings.health_port, lambda: dict(metrics), registry=metrics_registry),
        name="health-ingestor",
    )

    # Ensure consumer groups exist for all source streams
    for stream in _STREAMS:
        await ensure_consumer_group(redis_client, stream, _GROUP)

    neo4j_driver = AsyncGraphDatabase.driver(
        pipeline_settings.neo4j_uri,
        auth=(pipeline_settings.neo4j_user, pipeline_settings.neo4j_password),
    )

    # The ingestor is the only writer in a worker-only deployment; the legacy
    # pipeline Job that used to provision these is excluded from the kustomize
    # base. Both helpers are idempotent, so running them on every start is safe.
    # Retried: uvo_mcp provisions the same Neo4j constraints at its own startup,
    # and two concurrent CREATE CONSTRAINT statements deadlock on the label lock
    # (Neo.TransientError.Transaction.DeadlockDetected). Whichever loses simply
    # needs to try again — the winner's constraints already satisfy it.
    for attempt in range(1, _BOOTSTRAP_ATTEMPTS + 1):
        try:
            await ensure_indexes(db)
            async with neo4j_driver.session() as bootstrap_session:
                await ensure_constraints(bootstrap_session)
            logger.info("ingestor: indexes and constraints ensured")
            break
        except Exception as exc:
            if attempt < _BOOTSTRAP_ATTEMPTS:
                delay = _BOOTSTRAP_BACKOFF_SECONDS * attempt
                logger.warning(
                    "ingestor: index/constraint bootstrap attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt,
                    _BOOTSTRAP_ATTEMPTS,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("ingestor: failed to ensure indexes/constraints: %s", exc, exc_info=True)
            await log_event(
                db,
                level="error",
                event="index_bootstrap_failed",
                component="ingestor",
                instance_id=instance_id,
                message=redact_exception(exc),
            )

    ctx = IngestorContext(
        db=db,
        redis=redis_client,
        neo4j_driver=neo4j_driver,
        instance_id=instance_id,
        metrics=metrics,
    )
    last_reclaim: float | None = None
    last_maintenance: float | None = None

    try:
        while not stop_event.is_set():
            try:
                results = await read_group(
                    redis_client,
                    _GROUP,
                    consumer_name,
                    _STREAMS,
                    count=settings.ingestor_batch_size,
                    block_ms=5000,
                )
            except Exception as exc:
                logger.error("read_group failed: %s", exc, exc_info=True)
                metrics["last_error"] = redact_exception(exc)
                await asyncio.sleep(1)
                continue

            backoff = False
            for stream_name, entries in results:
                outcome = await process_entries(ctx, stream_name, entries)
                backoff = backoff or outcome.error is not None
            if backoff:
                await asyncio.sleep(1)

            # Periodic work runs whether or not traffic is flowing: under
            # sustained load read_group never comes back empty, which used to
            # starve reclaim and strand pending entries indefinitely.
            now = time.monotonic()
            if is_due(last_reclaim, now, settings.ingestor_reclaim_interval_seconds):
                last_reclaim = now
                try:
                    await reclaim_pending(ctx, settings, consumer_name)
                except Exception as exc:
                    logger.error("ingestor: reclaim failed: %s", exc, exc_info=True)
            if is_due(last_maintenance, now, settings.ingestor_maintenance_interval_seconds):
                last_maintenance = now
                await run_maintenance(ctx)

    finally:
        health_task.cancel()
        try:
            await health_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await log_event(
                db,
                level="info",
                event="worker_stopped",
                component="ingestor",
                instance_id=instance_id,
                message="ingestor shutting down",
                details={
                    "batches_processed": metrics["batches_processed"],
                    "notices_written": metrics["notices_written"],
                },
            )
        except Exception:
            pass
        mongo_client.close()
        await neo4j_driver.close()
        await close_redis(redis_client)
        logger.info("ingestor stopped")


if __name__ == "__main__":
    asyncio.run(run_ingestor())
