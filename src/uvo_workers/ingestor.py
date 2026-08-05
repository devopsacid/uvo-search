"""Ingestor worker — reads Redis Streams and writes to Mongo + Neo4j."""

import asyncio
import logging
import os
import signal
import uuid
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from neo4j import AsyncGraphDatabase
from pydantic_settings import BaseSettings

from uvo_core.domain.models import CanonicalNotice
from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.ingestion_log import log_event
from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch
from uvo_pipeline.loaders.neo4j import ensure_constraints, merge_notice_batch
from uvo_pipeline.pubsub import publish
from uvo_pipeline.redis_client import close_redis, get_redis, get_redis_settings
from uvo_pipeline.streams import (
    ack,
    autoclaim_stale,
    decode_entry,
    ensure_consumer_group,
    read_group,
)
from uvo_pipeline.utils.date_validation import validate_notice_dates
from uvo_workers.errors import redact_exception
from uvo_workers.health import serve_health
from uvo_workers.metrics import build_registry

logger = logging.getLogger(__name__)

_SOURCES = ["vestnik", "crz", "ted", "itms"]
_STREAMS = [f"notices:{s}" for s in _SOURCES]


class IngestorSettings(BaseSettings):
    ingestor_batch_size: int = 100
    health_port: int = 8095

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


@lru_cache
def get_settings() -> IngestorSettings:
    """One IngestorSettings construction per process (cached factory idiom)."""
    return IngestorSettings()


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
    caller can ack the same set of stream entry IDs.
    """
    source = stream_name.removeprefix("notices:")
    cleaned: list[CanonicalNotice] = []
    for notice in notices:
        clean, issues = validate_notice_dates(notice)
        cleaned.append(clean)
        for issue in issues:
            await log_event(
                db,
                level="warning",
                event="notice_invalid_date",
                component=component,
                source=source,
                source_id=notice.source_id,
                instance_id=instance_id,
                message=(f"{issue['field']} year {issue['year']} {issue['reason']}; nulled"),
                details=issue,
            )
    return cleaned


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
        await ensure_consumer_group(redis_client, stream, "ingestor")

    neo4j_driver = AsyncGraphDatabase.driver(
        pipeline_settings.neo4j_uri,
        auth=(pipeline_settings.neo4j_user, pipeline_settings.neo4j_password),
    )

    # The ingestor is the only writer in a worker-only deployment; the legacy
    # pipeline Job that used to provision these is excluded from the kustomize
    # base. Both helpers are idempotent, so running them on every start is safe.
    try:
        await ensure_indexes(db)
        async with neo4j_driver.session() as bootstrap_session:
            await ensure_constraints(bootstrap_session)
        logger.info("ingestor: indexes and constraints ensured")
    except Exception as exc:
        logger.error("ingestor: failed to ensure indexes/constraints: %s", exc, exc_info=True)
        await log_event(
            db,
            level="error",
            event="index_bootstrap_failed",
            component="ingestor",
            instance_id=instance_id,
            message=redact_exception(exc),
        )

    try:
        while not stop_event.is_set():
            try:
                results = await read_group(
                    redis_client,
                    "ingestor",
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

            if not results:
                reclaimed = []
                for stream in _STREAMS:
                    entries = await autoclaim_stale(redis_client, stream, "ingestor", consumer_name)
                    if entries:
                        reclaimed.append((stream, entries))
                        logger.info(
                            "ingestor: reclaimed %d stale entries from %s", len(entries), stream
                        )
                if not reclaimed:
                    continue
                results = reclaimed

            for stream_name, entries in results:
                notices: list[CanonicalNotice] = []
                entry_ids: list[bytes] = []

                for entry_id, fields in entries:
                    try:
                        decoded = decode_entry(fields)
                        notice = CanonicalNotice.model_validate(decoded["payload"])
                        notices.append(notice)
                        entry_ids.append(entry_id)
                    except Exception as exc:
                        logger.warning("Failed to decode entry from %s: %s", stream_name, exc)
                        await log_event(
                            db,
                            level="warning",
                            event="decode_failed",
                            component="ingestor",
                            source=stream_name.removeprefix("notices:"),
                            instance_id=instance_id,
                            message=f"decode failed: {redact_exception(exc)}",
                        )
                        # Ack immediately rather than leaving it pending: the
                        # failure is already durably logged above, and a
                        # payload that fails to decode/validate cannot
                        # possibly succeed on retry. Left unacked, autoclaim_stale
                        # redelivers it every idle cycle forever — a poison
                        # entry would otherwise never leave the PEL.
                        try:
                            await ack(redis_client, stream_name, "ingestor", [entry_id])
                        except Exception as ack_exc:
                            logger.error(
                                "ingestor: failed to ack poison entry from %s: %s",
                                stream_name,
                                ack_exc,
                            )
                        # Best-effort: preserve the raw payload for inspection.
                        # Never blocks acking above — a dead-letter write
                        # failure must not resurrect a poison entry.
                        try:
                            await redis_client.xadd(
                                "notices:dead",
                                {
                                    "stream": stream_name,
                                    "entry_id": entry_id,
                                    "error": str(exc),
                                    "payload": fields.get(b"payload", b""),
                                },
                                maxlen=10_000,
                                approximate=True,
                            )
                        except Exception as dead_letter_exc:
                            logger.debug(
                                "ingestor: failed to dead-letter poison entry from %s: %s",
                                stream_name,
                                dead_letter_exc,
                            )

                if not notices:
                    continue

                notices = await process_batch_logs(
                    db,
                    notices=notices,
                    component="ingestor",
                    instance_id=instance_id,
                    stream_name=stream_name,
                )

                try:
                    await upsert_batch(db, notices)
                    async with neo4j_driver.session() as neo4j_session:
                        await merge_notice_batch(neo4j_session, notices)

                    source = stream_name.removeprefix("notices:")
                    await ack(redis_client, stream_name, "ingestor", entry_ids)
                    await publish(
                        redis_client, "notices:written", {"source": source, "count": len(notices)}
                    )

                    metrics["batches_processed"] += 1
                    metrics["notices_written"] += len(notices)
                    # Clear a prior cycle's error now that a batch has written
                    # cleanly — last_error must reflect the last cycle, not
                    # "any cycle ever this process lifetime", or a single
                    # transient failure marks /readyz unready until restart.
                    metrics["last_error"] = None
                    logger.info("ingestor: wrote %d notices from %s", len(notices), stream_name)

                    await log_event(
                        db,
                        level="info",
                        event="batch_written",
                        component="ingestor",
                        source=source,
                        instance_id=instance_id,
                        message=f"wrote {len(notices)} notices from {stream_name}",
                        details={"count": len(notices)},
                    )

                except Exception as exc:
                    logger.error(
                        "ingestor: write failed for %s, not acking: %s",
                        stream_name,
                        exc,
                        exc_info=True,
                    )
                    msg = redact_exception(exc)
                    metrics["last_error"] = msg
                    await log_event(
                        db,
                        level="error",
                        event="write_failed",
                        component="ingestor",
                        source=stream_name.removeprefix("notices:"),
                        instance_id=instance_id,
                        message=msg,
                    )
                    await asyncio.sleep(1)

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
