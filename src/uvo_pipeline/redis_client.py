"""Async Redis client factory."""

import os

import redis.asyncio as aioredis
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""


async def get_redis(
    url: str | None = None,
    password: str | None = None,
) -> aioredis.Redis:
    resolved_url = url or os.environ.get("REDIS_URL", "redis://redis:6379/0")
    resolved_password = password or os.environ.get("REDIS_PASSWORD", "") or None
    return aioredis.from_url(resolved_url, password=resolved_password, decode_responses=False)


async def close_redis(client: aioredis.Redis) -> None:
    await client.aclose()
