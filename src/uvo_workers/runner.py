"""Generic daemon loop for per-source extractor workers."""

import asyncio
import logging
import signal
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.ingestion_log import log_event
from uvo_pipeline.locks import lock
from uvo_pipeline.redis_client import RedisSettings, close_redis, get_redis
from uvo_workers.health import serve_health

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
    redis_settings: RedisSettings,
    health_port: int = 8090,
    instance_id: str | None = None,
) -> None:
    instance_id = instance_id or uuid.uuid4().hex
    pipeline_settings = PipelineSettings()
    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]
    started_at = datetime.now(UTC).isoformat()

    metrics: dict = {
        "source": source,
        "instance_id": instance_id,
        "started_at": started_at,
        "cycles_completed": 0,
        "cycles_skipped_locked": 0,
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
        logger.critical("Redis connection failed for %s: %s", source, exc)
        try:
            await log_event(
                db,
                level="critical",
                event="redis_connect_failed",
                component=f"extractor:{source}",
                source=source,
                instance_id=instance_id,
                message=str(exc),
            )
        except Exception:
            pass
        raise SystemExit(1) from exc

    await log_event(
        db,
        level="info",
        event="worker_started",
        component=f"extractor:{source}",
        source=source,
        instance_id=instance_id,
        message=f"{source} extractor up",
        details={"interval_seconds": interval_seconds},
    )

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received for %s", source)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            pass

    health_task: asyncio.Task | None = None
    if health_port:
        health_task = asyncio.create_task(
            serve_health(health_port, lambda: dict(metrics)),
            name=f"health-{source}",
        )

    state: dict = {}
    lock_key = f"extractor:lock:{source}"
    lock_ttl = max(2 * interval_seconds, 10)

    try:
        while not stop_event.is_set():
            async with lock(redis_client, lock_key, instance_id, ttl_seconds=lock_ttl) as acquired:
                if acquired:
                    error: str | None = None
                    count = 0
                    try:
                        count = await extract(redis_client, state)
                        metrics["cycles_completed"] += 1
                        logger.info("%s: cycle complete, %d items XADDed", source, count)
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        metrics["last_error"] = error
                        logger.error("%s: extract error: %s", source, error)
                    await _log_cycle_result(
                        db,
                        source=source,
                        instance_id=instance_id,
                        count=count,
                        error=error,
                    )
                else:
                    metrics["cycles_skipped_locked"] += 1
                    logger.debug("%s: lock held by other instance, skipping cycle", source)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass
    finally:
        if health_task is not None:
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
                component=f"extractor:{source}",
                source=source,
                instance_id=instance_id,
                message=f"{source}: worker stopped",
                details={
                    "cycles_completed": metrics["cycles_completed"],
                    "cycles_skipped_locked": metrics["cycles_skipped_locked"],
                },
            )
        except Exception:
            pass
        mongo_client.close()
        await close_redis(redis_client)
        logger.info("%s: worker stopped", source)
