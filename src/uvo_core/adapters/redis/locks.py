"""Redis distributed lock via SET NX EX + WATCH/MULTI/EXEC CAS release.

WATCH is used instead of EVAL so the unit tests work against fakeredis without
the optional `lupa` Lua extension. Semantics are equivalent on real Redis.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.exceptions import WatchError


async def acquire_lock(
    redis: aioredis.Redis,
    key: str,
    instance_id: str,
    ttl_seconds: int,
) -> bool:
    result = await redis.set(key, instance_id, nx=True, ex=ttl_seconds)
    return result is True


async def release_lock(
    redis: aioredis.Redis,
    key: str,
    instance_id: str,
) -> bool:
    expected = instance_id.encode() if isinstance(instance_id, str) else instance_id
    async with redis.pipeline(transaction=True) as pipe:
        try:
            await pipe.watch(key)
            current = await pipe.get(key)
            if current != expected:
                await pipe.unwatch()
                return False
            pipe.multi()
            pipe.delete(key)
            results = await pipe.execute()
        except WatchError:
            return False
    return bool(results and results[0])


@asynccontextmanager
async def lock(
    redis: aioredis.Redis,
    key: str,
    instance_id: str,
    ttl_seconds: int,
) -> AsyncGenerator[bool, None]:
    acquired = await acquire_lock(redis, key, instance_id, ttl_seconds)
    try:
        yield acquired
    finally:
        if acquired:
            await release_lock(redis, key, instance_id)
