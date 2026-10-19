"""Redis Pub/Sub helpers."""

import json
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis


async def publish(redis: aioredis.Redis, channel: str, message: dict) -> int:
    return await redis.publish(channel, json.dumps(message, default=str))


async def subscribe(redis: aioredis.Redis, channel: str) -> AsyncGenerator[dict, None]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                yield json.loads(msg["data"])
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
