"""Generic daemon loop for per-source extractor workers."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase

from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore
from uvo_core.adapters.mongo.ingestion_log import log_event
from uvo_core.adapters.redis.client import RedisSettings
from uvo_core.adapters.redis.locks import lock
from uvo_workers.clients import WorkerClients
from uvo_workers.context import WorkerContext
from uvo_workers.errors import redact_exception

logger = logging.getLogger(__name__)


async def _log_cycle_result(
    db: AsyncIOMotorDatabase,
    *,
    source: str,
    instance_id: str,
    count: int,
    error: str | None,
) -> None:
    if error is None:
        await log_event(
            db,
            level="info",
            event="cycle_complete",
            component=f"extractor:{source}",
            source=source,
            instance_id=instance_id,
            message=f"{source}: {count} items XADDed",
            details={"count": count},
        )
    else:
        await log_event(
            db,
            level="error",
            event="cycle_failed",
            component=f"extractor:{source}",
            source=source,
            instance_id=instance_id,
            message=error,
        )


async def run_extractor_loop(
    *,
    source: str,
    interval_seconds: int,
    extract: Callable[[redis.asyncio.Redis, dict], Awaitable[int]],
    redis_settings: RedisSettings | None = None,
    health_port: int = 8090,
    instance_id: str | None = None,
    clients: WorkerClients | None = None,
) -> None:
    metrics: dict = {
        "source": source,
        "started_at": datetime.now(UTC).isoformat(),
        "cycles_completed": 0,
        "cycles_skipped_locked": 0,
        "last_error": None,
        "last_success_at": None,
    }
    async with WorkerContext(
        name=source,
        component=f"extractor:{source}",
        source=source,
        registry_name=f"extractor-{source}",
        health_port=health_port,
        metrics=metrics,
        redis_settings=redis_settings,
        clients=clients,
        instance_id=instance_id,
        start_message=f"{source} extractor up",
        start_details={"interval_seconds": interval_seconds},
        stop_message=f"{source}: worker stopped",
        stop_details=lambda: {
            "cycles_completed": metrics["cycles_completed"],
            "cycles_skipped_locked": metrics["cycles_skipped_locked"],
        },
    ) as ctx:
        # Hand the context's long-lived db handle to the extract callable via
        # state. The leading underscore marks loop-owned plumbing, distinct
        # from a worker's own state (e.g. ITMS's itms_min_id).
        state: dict = {"_checkpoint_store": MongoCheckpointStore(ctx.db)}
        lock_key = f"extractor:lock:{source}"
        lock_ttl = max(2 * interval_seconds, 10)

        while not ctx.stop_event.is_set():
            async with lock(ctx.redis, lock_key, ctx.instance_id, ttl_seconds=lock_ttl) as acquired:
                if acquired:
                    error: str | None = None
                    count = 0
                    try:
                        count = await extract(ctx.redis, state)
                        metrics["cycles_completed"] += 1
                        # last_error must describe the *latest* cycle: a single
                        # transient failure would otherwise keep /readyz
                        # unready until restart.
                        metrics["last_error"] = None
                        metrics["last_success_at"] = time.time()
                        logger.info("%s: cycle complete, %d items XADDed", source, count)
                    except Exception as exc:
                        logger.error("%s: extract error: %s", source, exc, exc_info=True)
                        error = redact_exception(exc)
                        metrics["last_error"] = error
                    await _log_cycle_result(
                        ctx.db,
                        source=source,
                        instance_id=ctx.instance_id,
                        count=count,
                        error=error,
                    )
                else:
                    metrics["cycles_skipped_locked"] += 1
                    logger.debug("%s: lock held by other instance, skipping cycle", source)

            try:
                await asyncio.wait_for(ctx.stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass
