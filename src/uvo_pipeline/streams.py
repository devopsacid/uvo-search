"""Redis Streams helpers — XADD / XREADGROUP / XACK."""

import json
import logging

import redis.asyncio as aioredis
from redis.exceptions import RedisError, ResponseError

logger = logging.getLogger(__name__)


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
    return [(name.decode() if isinstance(name, bytes) else name, entries) for name, entries in result]


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
) -> list[tuple[bytes, dict]]:
    """Reclaim entries pending longer than min_idle_ms from dead consumers.

    Consumer names are per-pod. When a pod dies mid-batch its delivered but
    unacked entries stay in the PEL under a name that never returns, so
    without this they are stranded permanently and the PEL grows without
    bound. Returns entries in the same shape read_group yields.

    Only RedisError (connectivity blips, transient protocol errors) is
    swallowed. A non-Redis exception here is a bug, not an operational
    condition — letting it propagate surfaces it loudly (the ingestor loop
    crashes and the pod restarts) instead of silently disabling reclaim
    forever behind an indistinguishable "xautoclaim failed" warning.
    """
    try:
        _cursor, entries, _deleted = await redis.xautoclaim(
            name=stream,
            groupname=group,
            consumername=consumer,
            min_idle_time=min_idle_ms,
            start_id="0-0",
            count=count,
        )
    except RedisError as exc:
        logger.warning("xautoclaim failed on %s: %s", stream, exc)
        return []
    return list(entries or [])
