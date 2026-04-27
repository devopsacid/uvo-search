"""Dedup worker — triggers cross-source deduplication on write events."""

import asyncio
import logging
import signal
import time

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.dedup import run_cross_source_dedup
from uvo_pipeline.pubsub import subscribe
from uvo_pipeline.redis_client import RedisSettings, close_redis, get_redis
from uvo_workers.health import serve_health

logger = logging.getLogger(__name__)


class DedupWorkerSettings(BaseSettings):
    dedup_interval_seconds: int = 3600
    dedup_debounce_seconds: int = 5
    dedup_window_days: int = 30
    health_port: int = 8096

    model_config = {"env_file": ".env", "extra": "ignore"}


async def run_dedup_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = DedupWorkerSettings()
    pipeline_settings = PipelineSettings()
    redis_settings = RedisSettings()

    metrics: dict = {
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
        raise SystemExit(1) from exc

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
    last_write_time: list[float] = [0.0]  # mutable container for closure

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
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            logger.error("dedup: run failed: %s", msg)
            metrics["last_error"] = msg
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
        logger.info("dedup worker stopped")


if __name__ == "__main__":
    asyncio.run(run_dedup_worker())
