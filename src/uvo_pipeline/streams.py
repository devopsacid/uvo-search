"""Redis Streams helpers — XADD / XREADGROUP / XACK."""

import json

import redis.asyncio as aioredis
from redis.exceptions import ResponseError


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
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
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
