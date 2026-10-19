"""Dedup worker — triggers cross-source deduplication on write events."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from uvo_core.adapters.mongo.dedup import run_cross_source_dedup
from uvo_core.adapters.mongo.ingestion_log import log_event
from uvo_core.adapters.mongo.loaders import recompute_entity_stats
from uvo_core.adapters.redis.locks import lock
from uvo_core.adapters.redis.pubsub import subscribe
from uvo_workers.clients import WorkerClients
from uvo_workers.context import WorkerContext
from uvo_workers.errors import redact_exception
from uvo_workers.settings import WorkerSettings, settings_factory

logger = logging.getLogger(__name__)

# Dedup performs a quadratic scan over a 30-day window. The ingestor publishes
# notices:written once per batch, so a short debounce means a full re-scan every
# few seconds during backfill. This is a floor on how often the scan may start,
# independent of how many write notifications arrive.
MIN_DEDUP_INTERVAL_SECONDS = 300.0


DEDUP_LOCK_KEY = "dedup:lock"


async def run_under_lock(
    redis_client,
    instance_id: str,
    ttl_seconds: int,
    work: Callable[[], Awaitable[None]],
) -> bool:
    """Run ``work`` only if this instance wins the cross-replica dedup lock.

    Dedup + entity-stats recompute are full-window scans and write
    ``canonical_id``; two replicas running them concurrently double the load
    and race on the same documents. Returns False when another instance holds
    the lock (the run is skipped, not queued).
    """
    async with lock(redis_client, DEDUP_LOCK_KEY, instance_id, ttl_seconds=ttl_seconds) as acquired:
        if not acquired:
            logger.info("dedup: another instance holds %s; skipping run", DEDUP_LOCK_KEY)
            return False
        await work()
        return True


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


class DedupWorkerSettings(WorkerSettings):
    dedup_interval_seconds: int = 3600
    dedup_debounce_seconds: int = 5
    dedup_window_days: int = 30
    # Must exceed a worst-case dedup + stats pass; the lock auto-expires if the holder dies.
    dedup_lock_ttl_seconds: int = 1800
    health_port: int = 8096


get_settings = settings_factory(DedupWorkerSettings)


async def run_dedup_worker(clients: WorkerClients | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    seed: dict = {"dedup_runs": 0, "last_run_at": None, "last_error": None}

    async with WorkerContext(
        name="dedup",
        component="dedup-worker",
        registry_name="dedup-worker",
        health_port=settings.health_port,
        metrics=seed,
        clients=clients,
        start_message="dedup worker up",
        start_details={"window_days": settings.dedup_window_days},
        stop_message="dedup worker shutting down",
        stop_details=lambda: {"dedup_runs": wctx.metrics["dedup_runs"]},
    ) as wctx:
        await _serve_dedup(wctx, settings)


async def _serve_dedup(wctx: WorkerContext, settings: DedupWorkerSettings) -> None:
    redis_client = wctx.redis
    metrics = wctx.metrics
    instance_id = wctx.instance_id
    stop_event = wctx.stop_event

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
        await run_under_lock(
            redis_client, instance_id, settings.dedup_lock_ttl_seconds, _run_dedup_locked
        )

    async def _run_dedup_locked() -> None:
        # Reuse the worker's single long-lived Motor client (the context's db)
        # instead of opening a fresh one per dedup run - this runs on every
        # debounced write and on every interval tick.
        db = wctx.db
        try:
            logger.info(
                "dedup: running cross-source dedup (window=%dd)", settings.dedup_window_days
            )
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
        for t in (subscriber_task, timer_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


if __name__ == "__main__":
    asyncio.run(run_dedup_worker())
