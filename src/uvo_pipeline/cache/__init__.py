"""Cache backends for ITMS and other extractors."""

from typing import Protocol

from uvo_pipeline.cache.memory import MemoryCache
from uvo_pipeline.cache.redis import RedisCache

__all__ = ["CacheBackend", "MemoryCache", "RedisCache"]


class CacheBackend(Protocol):
    async def get(self, key: str) -> dict | None: ...
    async def set(self, key: str, value: dict, *, ttl_seconds: int) -> None: ...
