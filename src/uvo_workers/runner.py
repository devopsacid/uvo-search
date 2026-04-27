"""Generic daemon loop for per-source extractor workers."""

import asyncio
import logging
import signal
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import redis.asyncio

from uvo_pipeline.locks import lock
from uvo_pipeline.redis_client import RedisSettings, close_redis, get_redis
from uvo_workers.health import serve_health

logger = logging.getLogger(__name__)


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
        raise SystemExit(1) from exc

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
                    try:
                        count = await extract(redis_client, state)
                        metrics["cycles_completed"] += 1
                        logger.info("%s: cycle complete, %d items XADDed", source, count)
                    except Exception as exc:
                        msg = f"{type(exc).__name__}: {exc}"
                        metrics["last_error"] = msg
                        logger.error("%s: extract error: %s", source, msg)
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
        await close_redis(redis_client)
        logger.info("%s: worker stopped", source)
