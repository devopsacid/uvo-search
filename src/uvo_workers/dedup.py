"""Dedup worker — triggers cross-source deduplication on write events."""

import asyncio
import logging
import signal
import time
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.dedup import run_cross_source_dedup
from uvo_pipeline.ingestion_log import log_event
from uvo_pipeline.pubsub import subscribe
from uvo_pipeline.redis_client import RedisSettings, close_redis, get_redis
from uvo_workers.health import serve_health

logger = logging.getLogger(__name__)


class DedupWorkerSettings(BaseSettings):
    dedup_interval_seconds: int = 3600
    dedup_debounce_seconds: int = 5
    dedup_window_days: int = 30
    health_port: int = 8096

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


async def run_dedup_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = DedupWorkerSettings()
    pipeline_settings = PipelineSettings()
    redis_settings = RedisSettings()
    instance_id = uuid.uuid4().hex

    log_mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    log_db = log_mongo_client[pipeline_settings.mongodb_database]

    metrics: dict = {
        "instance_id": instance_id,
        "dedup_runs": 0,
        "last_run_at": None,
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
                log_db,
                level="critical",
                event="redis_connect_failed",
                component="dedup-worker",
                instance_id=instance_id,
                message=str(exc),
            )
        except Exception:
            pass
        log_mongo_client.close()
        raise SystemExit(1) from exc

    await log_event(
        log_db,
        level="info",
        event="worker_started",
        component="dedup-worker",
        instance_id=instance_id,
        message="dedup worker up",
        details={"window_days": settings.dedup_window_days},
    )

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received, stopping dedup worker")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            pass

    health_task = asyncio.create_task(
        serve_health(settings.health_port, lambda: dict(metrics)),
        name="health-dedup",
    )

    pending = asyncio.Event()
    trigger_lock = asyncio.Lock()
    # Initialise to monotonic-now so the interval-elapsed branch doesn't trigger
    # immediately on startup (would otherwise see elapsed == time.monotonic()).
    last_write_time: list[float] = [time.monotonic()]

    async def _run_dedup() -> None:
        mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
        db = mongo_client[pipeline_settings.mongodb_database]
        try:
            logger.info("dedup: running cross-source dedup (window=%dd)", settings.dedup_window_days)
            match_groups = await run_cross_source_dedup(
                db, run_id=None, window_days=settings.dedup_window_days
            )
            metrics["dedup_runs"] += 1
            metrics["last_run_at"] = time.time()
            logger.info("dedup: found %d match groups", match_groups)
            await log_event(
                db,
                level="info",
                event="cycle_complete",
                component="dedup-worker",
                instance_id=instance_id,
                message=f"dedup found {match_groups} match groups",
                details={"match_groups": match_groups, "window_days": settings.dedup_window_days},
            )
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            logger.error("dedup: run failed: %s", msg)
            metrics["last_error"] = msg
            try:
                await log_event(
                    db,
                    level="error",
                    event="cycle_failed",
                    component="dedup-worker",
                    instance_id=instance_id,
                    message=msg,
                )
            except Exception:
                pass
        finally:
            mongo_client.close()

    async def _subscriber() -> None:
        async for _msg in subscribe(redis_client, "notices:written"):
            if stop_event.is_set():
                break
            async with trigger_lock:
                last_write_time[0] = time.monotonic()
                pending.set()

    async def _timer() -> None:
        while not stop_event.is_set():
            elapsed_since_poll = time.monotonic() - last_write_time[0]
            if pending.is_set():
                debounce_remaining = settings.dedup_debounce_seconds - (
                    time.monotonic() - last_write_time[0]
                )
                if debounce_remaining > 0:
                    await asyncio.sleep(debounce_remaining)
                    continue
                async with trigger_lock:
                    pending.clear()
                await _run_dedup()
            elif elapsed_since_poll >= settings.dedup_interval_seconds:
                last_write_time[0] = time.monotonic()
                await _run_dedup()
            else:
                await asyncio.sleep(1)

    subscriber_task = asyncio.create_task(_subscriber(), name="dedup-subscriber")
    timer_task = asyncio.create_task(_timer(), name="dedup-timer")

    try:
        await stop_event.wait()
    finally:
        subscriber_task.cancel()
        timer_task.cancel()
        health_task.cancel()
        for t in (subscriber_task, timer_task, health_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        await close_redis(redis_client)
        try:
            await log_event(
                log_db,
                level="info",
                event="worker_stopped",
                component="dedup-worker",
                instance_id=instance_id,
                message="dedup worker shutting down",
                details={"dedup_runs": metrics["dedup_runs"]},
            )
        except Exception:
            pass
        log_mongo_client.close()
        logger.info("dedup worker stopped")


if __name__ == "__main__":
    asyncio.run(run_dedup_worker())
