"""Redis-backed cache using SETEX / GET with JSON serialisation."""

import json

import redis.asyncio as aioredis


class RedisCache:
    def __init__(self, redis: aioredis.Redis, *, prefix: str = "") -> None:
        self._redis = redis
        self._prefix = prefix

    async def get(self, key: str) -> dict | None:
        raw = await self._redis.get(self._prefix + key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: dict, *, ttl_seconds: int) -> None:
        await self._redis.setex(self._prefix + key, ttl_seconds, json.dumps(value, default=str))
