"""Async token-bucket rate limiter."""

import asyncio
import time


class RateLimiter:
    """Token-bucket rate limiter for async code."""

    def __init__(self, rate: int, per: float = 60.0):
        """rate: max calls per `per` seconds."""
        self._rate = rate
        self._per = per
        self._tokens = float(rate)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._rate, self._tokens + elapsed * (self._rate / self._per))
            self._last = now
            if self._tokens < 1:
                wait = (1 - self._tokens) * (self._per / self._rate)
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1
