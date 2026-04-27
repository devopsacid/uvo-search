"""In-process TTL cache backed by a plain dict."""

import time


class MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[dict, float]] = {}

    async def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: dict, *, ttl_seconds: int) -> None:
        self._store[key] = (value, time.monotonic() + ttl_seconds)
