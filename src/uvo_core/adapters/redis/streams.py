"""Redis Streams helpers — XADD / XREADGROUP / XACK."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis
from redis.exceptions import RedisError, ResponseError

logger = logging.getLogger(__name__)

# MAXLEN is a last-resort memory bound only. Unread entries are protected by
# producer backpressure (wait_for_capacity) and acked entries are removed by
# trim_consumed (MINID), so the cap should never be what removes live data.
DEFAULT_MAXLEN_SAFETY_NET = 1_000_000


class BackpressureTimeout(RuntimeError):
    """The consumer group did not drain below the high-water mark in time."""


async def xadd_notice(
    redis: aioredis.Redis,
    source: str,
    payload: dict,
    *,
    content_hash: str,
    run_id: str,
    maxlen: int = 100_000,
) -> bytes:
    return await redis.xadd(
        f"notices:{source}",
        {
            "payload": json.dumps(payload, default=str),
            "hash": content_hash,
            "run": run_id,
        },
        maxlen=maxlen,
        approximate=True,
    )


async def xadd_many(
    redis: aioredis.Redis,
    source: str,
    payloads: list[dict],
    *,
    maxlen: int = DEFAULT_MAXLEN_SAFETY_NET,
) -> list[bytes]:
    """XADD many notice payloads in one non-transactional pipeline round trip.

    Each payload carries its own ``content_hash`` / ``pipeline_run_id`` (every
    CanonicalNotice dump does). Order is preserved.
    """
    if not payloads:
        return []
    stream = f"notices:{source}"
    async with redis.pipeline(transaction=False) as pipe:
        for payload in payloads:
            pipe.xadd(
                stream,
                {
                    "payload": json.dumps(payload, default=str),
                    "hash": payload.get("content_hash") or "",
                    "run": payload.get("pipeline_run_id") or "",
                },
                maxlen=maxlen,
                approximate=True,
            )
        return list(await pipe.execute())


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


async def group_stats(redis: aioredis.Redis, stream: str, group: str) -> dict:
    """Consumer-group health: unread lag, pending (PEL) size and total backlog.

    ``backlog`` = entries not yet fully handled = unread + delivered-but-unacked.
    When Redis cannot compute ``lag`` (nil) or the group does not exist yet, the
    stream length is used as a conservative upper bound.
    """
    length = await redis.xlen(stream)
    try:
        groups = await redis.xinfo_groups(stream)
    except ResponseError:
        groups = []
    info = next((g for g in groups if _text(g.get("name")) == group), None)
    if info is None:
        return {
            "length": length,
            "lag": length,
            "pending": 0,
            "backlog": length,
            "last_delivered_id": "0-0",
        }
    pending = int(info.get("pending") or 0)
    lag = info.get("lag")
    lag = max(0, int(lag)) if lag is not None else length
    return {
        "length": length,
        "lag": lag,
        "pending": pending,
        "backlog": lag + pending,
        "last_delivered_id": _text(info.get("last-delivered-id") or "0-0"),
    }


async def wait_for_capacity(
    redis: aioredis.Redis,
    stream: str,
    group: str,
    *,
    high_water: int,
    poll_seconds: float = 2.0,
    max_wait_seconds: float = 900.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Producer backpressure: block while the group's backlog >= ``high_water``.

    Raises BackpressureTimeout after ``max_wait_seconds`` so the extractor
    cycle fails (checkpoint not advanced) instead of overrunning the stream.
    ``high_water <= 0`` disables the check.
    """
    if high_water <= 0:
        return
    waited = 0.0
    warned = False
    while True:
        stats = await group_stats(redis, stream, group)
        if stats["backlog"] < high_water:
            if warned:
                logger.info("%s: backpressure released (backlog=%d)", stream, stats["backlog"])
            return
        if waited >= max_wait_seconds:
            raise BackpressureTimeout(
                f"{stream}: backlog {stats['backlog']} >= high-water {high_water} "
                f"after {waited:.0f}s"
            )
        if not warned:
            logger.warning(
                "%s: backlog %d >= high-water %d; pausing producer",
                stream,
                stats["backlog"],
                high_water,
            )
            warned = True
        await sleep(poll_seconds)
        waited += poll_seconds


async def trim_consumed(
    redis: aioredis.Redis, stream: str, group: str, *, approximate: bool = True
) -> int:
    """Delete only entries every delivery of which has been acked.

    Safe bound = oldest pending id if the PEL is non-empty, else the group's
    last-delivered id; everything strictly older is acked. Unread and pending
    entries are never touched. Returns the number of entries removed.
    """
    stats = await group_stats(redis, stream, group)
    if stats["last_delivered_id"] == "0-0":
        return 0
    safe = stats["last_delivered_id"]
    if stats["pending"] > 0:
        summary = await redis.xpending(stream, group)
        oldest = summary.get("min") if isinstance(summary, dict) else None
        if oldest is None:
            return 0
        safe = _text(oldest)
    try:
        removed = await redis.xtrim(stream, minid=safe, approximate=approximate)
    except RedisError as exc:
        logger.warning("xtrim failed on %s: %s", stream, exc)
        return 0
    return int(removed or 0)


async def delivery_counts(
    redis: aioredis.Redis, stream: str, group: str, entry_ids: list[bytes]
) -> dict[bytes, int]:
    """Times each pending entry has been delivered (XPENDING extended form)."""
    if not entry_ids:
        return {}
    async with redis.pipeline(transaction=False) as pipe:
        for entry_id in entry_ids:
            pipe.xpending_range(stream, group, min=entry_id, max=entry_id, count=1)
        results = await pipe.execute()
    counts: dict[bytes, int] = {}
    for entry_id, rows in zip(entry_ids, results, strict=True):
        if rows:
            counts[entry_id] = int(rows[0].get("times_delivered") or 1)
    return counts


async def ensure_consumer_group(redis: aioredis.Redis, stream: str, group: str) -> None:
    """Create the consumer group starting at id="0" (not "$").

    "$" (tail-only) makes the group blind to any entries already XADDed
    before the group exists — if an extractor starts before the ingestor,
    those entries are permanently unreadable by the group. "0" replays the
    whole stream from the beginning, which is safe because ingestion is
    idempotent (upserts keyed on content_hash).
    """
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def read_group(
    redis: aioredis.Redis,
    group: str,
    consumer: str,
    streams: list[str],
    *,
    count: int = 100,
    block_ms: int | None = 5000,
) -> list[tuple[str, list[tuple[bytes, dict]]]]:
    """Read pending entries. block_ms=None polls non-blocking; 0 blocks forever (Redis semantics)."""
    stream_args = {s: ">" for s in streams}
    kwargs: dict = {"count": count}
    if block_ms is not None:
        kwargs["block"] = block_ms
    result = await redis.xreadgroup(group, consumer, streams=stream_args, **kwargs)
    if not result:
        return []
    return [
        (name.decode() if isinstance(name, bytes) else name, entries) for name, entries in result
    ]


async def ack(redis: aioredis.Redis, stream: str, group: str, entry_ids: list[bytes]) -> int:
    if not entry_ids:
        return 0
    return await redis.xack(stream, group, *entry_ids)


def decode_entry(fields: dict[bytes, bytes]) -> dict:
    return {
        "payload": json.loads(fields[b"payload"]),
        "hash": fields[b"hash"].decode(),
        "run": fields[b"run"].decode(),
    }


async def autoclaim_stale(
    redis: aioredis.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    min_idle_ms: int = 60_000,
    count: int = 100,
    max_pages: int = 10,
) -> list[tuple[bytes, dict]]:
    """Reclaim entries pending longer than min_idle_ms from dead consumers.

    Consumer names are per-pod. When a pod dies mid-batch its delivered but
    unacked entries stay in the PEL under a name that never returns, so
    without this they are stranded permanently and the PEL grows without
    bound. Pages through the XAUTOCLAIM cursor (up to ``max_pages`` x ``count``
    entries) and returns entries in the same shape read_group yields.

    Only RedisError (connectivity blips, transient protocol errors) is
    swallowed. A non-Redis exception here is a bug, not an operational
    condition — letting it propagate surfaces it loudly (the ingestor loop
    crashes and the pod restarts) instead of silently disabling reclaim
    forever behind an indistinguishable "xautoclaim failed" warning.
    """
    claimed: list[tuple[bytes, dict]] = []
    start_id: bytes | str = "0-0"
    seen: set[bytes] = set()
    try:
        for _ in range(max_pages):
            cursor, entries, _deleted = await redis.xautoclaim(
                name=stream,
                groupname=group,
                consumername=consumer,
                min_idle_time=min_idle_ms,
                start_id=start_id,
                count=count,
            )
            fresh = [e for e in (entries or []) if e[0] not in seen]
            if not fresh:
                break
            seen.update(e[0] for e in fresh)
            claimed.extend(fresh)
            if _text(cursor) == "0-0":
                break
            start_id = cursor
    except RedisError as exc:
        logger.warning("xautoclaim failed on %s: %s", stream, exc)
    return claimed
