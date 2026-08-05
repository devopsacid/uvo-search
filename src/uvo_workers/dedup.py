"""Dedup worker — triggers cross-source deduplication on write events."""

import asyncio
import logging
import signal
import time
import uuid
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.dedup import run_cross_source_dedup
from uvo_pipeline.ingestion_log import log_event
from uvo_pipeline.loaders.mongo import recompute_entity_stats
from uvo_pipeline.pubsub import subscribe
from uvo_pipeline.redis_client import close_redis, get_redis, get_redis_settings
from uvo_workers.errors import redact_exception
from uvo_workers.health import serve_health
from uvo_workers.metrics import build_registry

logger = logging.getLogger(__name__)

# Dedup performs a quadratic scan over a 30-day window. The ingestor publishes
# notices:written once per batch, so a short debounce means a full re-scan every
# few seconds during backfill. This is a floor on how often the scan may start,
# independent of how many write notifications arrive.
MIN_DEDUP_INTERVAL_SECONDS = 300.0


def should_run(last_run_monotonic: float | None, now_monotonic: float) -> bool:
    """True when enough time has passed since the last dedup pass."""
    if last_run_monotonic is None:
        return True
    return (now_monotonic - last_run_monotonic) >= MIN_DEDUP_INTERVAL_SECONDS


def next_debounced_action(
    *,
    debounce_remaining: float,
    last_dedup_run: float | None,
    now: float,
) -> tuple[str, float | None]:
    """Decide what the timer loop does this tick for a pending write signal.

    Returns (action, sleep_for):
      - "sleep_debounce": still inside the debounce window; sleep sleep_for
        and re-check. `pending` must NOT be cleared.
      - "sleep_floor": debounce satisfied but the MIN_DEDUP_INTERVAL_SECONDS
        floor isn't yet; sleep sleep_for and re-check. `pending` must NOT be
        cleared here either — clearing it would drop the deferred run
        entirely (nothing re-sets `pending` until the next notices:written
        message), so the final batch of a burst would silently wait for the
        much longer interval fallback instead of firing as soon as the floor
        opens.
      - "run": the caller should clear `pending` and run the dedup pass now.
    """
    if debounce_remaining > 0:
        return "sleep_debounce", debounce_remaining
    if not should_run(last_dedup_run, now):
        # should_run(None, ...) is always True, so a False result here
        # guarantees last_dedup_run is a float.
        floor_remaining = MIN_DEDUP_INTERVAL_SECONDS - (now - last_dedup_run)  # type: ignore[operator]
        return "sleep_floor", max(floor_remaining, 0.1)
    return "run", None


class DedupWorkerSettings(BaseSettings):
    dedup_interval_seconds: int = 3600
    dedup_debounce_seconds: int = 5
    dedup_window_days: int = 30
    health_port: int = 8096

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


@lru_cache
def get_settings() -> DedupWorkerSettings:
    """One DedupWorkerSettings construction per process (cached factory idiom)."""
    return DedupWorkerSettings()


async def run_dedup_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    pipeline_settings = get_pipeline_settings()
    redis_settings = get_redis_settings()
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
                message=redact_exception(exc),
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

    metrics_registry = build_registry("dedup-worker")
    health_task = asyncio.create_task(
        serve_health(settings.health_port, lambda: dict(metrics), registry=metrics_registry),
        name="health-dedup",
    )

    pending = asyncio.Event()
    trigger_lock = asyncio.Lock()
    # Initialise to monotonic-now so the interval-elapsed branch doesn't trigger
    # immediately on startup (would otherwise see elapsed == time.monotonic()).
    last_write_time: list[float] = [time.monotonic()]
    # Floor on how often a dedup pass may actually start, independent of the
    # debounce above. last_dedup_run stays None until the first run so the
    # very first pass is never blocked.
    last_dedup_run: list[float | None] = [None]

    async def _run_dedup() -> None:
        # Reuse the worker's single long-lived Motor client (log_mongo_client)
        # instead of opening a fresh one per dedup run (plan §1.3.5) — this
        # runs on every debounced write and on every interval tick, so a
        # per-call client was the highest-frequency connection churn here.
        db = log_db
        try:
            logger.info("dedup: running cross-source dedup (window=%dd)", settings.dedup_window_days)
            match_groups = await run_cross_source_dedup(
                db, run_id=None, window_days=settings.dedup_window_days
            )
            metrics["dedup_runs"] += 1
            metrics["last_run_at"] = time.time()
            # Clear a prior cycle's error now that a pass completed cleanly —
            # last_error must reflect the last cycle, not "any cycle ever
            # this process lifetime", or a transient failure marks /readyz
            # unready until restart.
            metrics["last_error"] = None
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
            # Refresh denormalized entity stats on the same debounced cadence.
            # Recompute (not inline $inc) — see scripts/backfill_entity_stats.py.
            # Isolated so a stats failure never marks the dedup cycle failed.
            try:
                stats = await recompute_entity_stats(db)
                logger.info(
                    "dedup: recomputed entity stats (procurers=%d, suppliers=%d)",
                    stats.get("procurers_updated", 0),
                    stats.get("suppliers_updated", 0),
                )
            except Exception as exc:
                logger.error("dedup: entity-stats recompute failed: %s", exc)
        except Exception as exc:
            logger.error("dedup: run failed: %s", exc, exc_info=True)
            msg = redact_exception(exc)
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
                now = time.monotonic()
                action, sleep_for = next_debounced_action(
                    debounce_remaining=debounce_remaining,
                    last_dedup_run=last_dedup_run[0],
                    now=now,
                )
                if action == "sleep_debounce":
                    await asyncio.sleep(sleep_for)
                    continue
                if action == "sleep_floor":
                    # `pending` is deliberately left set — see
                    # next_debounced_action's docstring for why clearing it
                    # here would drop the deferred run.
                    logger.debug(
                        "dedup: within minimum interval, deferring trigger for %.1fs",
                        sleep_for,
                    )
                    await asyncio.sleep(sleep_for)
                    continue
                async with trigger_lock:
                    pending.clear()
                last_dedup_run[0] = now
                await _run_dedup()
            elif elapsed_since_poll >= settings.dedup_interval_seconds:
                last_write_time[0] = time.monotonic()
                last_dedup_run[0] = time.monotonic()
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
