"""Shared HTTP fetch-with-retry for the extractors.

Transient failures (timeouts, connection errors, 429, 5xx) are retried with
exponential backoff and full jitter, honouring ``Retry-After``. Non-transient
responses (2xx, 3xx, 4xx other than 429) are returned untouched so the caller
decides what a 404 means.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def parse_retry_after(value: str | None) -> float | None:
    """Seconds to wait from a ``Retry-After`` header (delta-seconds or HTTP date)."""
    if not value:
        return None
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


async def fetch_with_retry(
    request: Callable[[], Awaitable[httpx.Response]],
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_statuses: frozenset[int] = RETRYABLE_STATUSES,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    jitter: Callable[[], float] = random.random,
    label: str = "http",
) -> httpx.Response:
    """Call ``request()`` until it yields a non-retryable response.

    Raises the last transport error, or ``HTTPStatusError`` for the last
    retryable response, once ``max_attempts`` is exhausted.
    """
    sleep = sleep or _default_sleep
    for attempt in range(1, max_attempts + 1):
        try:
            response = await request()
        except httpx.TransportError as exc:
            if attempt >= max_attempts:
                logger.error("%s: giving up after %d attempts: %s", label, attempt, exc)
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * jitter()
            logger.warning(
                "%s: %s (attempt %d/%d); retrying in %.1fs",
                label,
                type(exc).__name__,
                attempt,
                max_attempts,
                delay,
            )
            await sleep(delay)
            continue

        if response.status_code not in retry_statuses:
            return response

        if attempt >= max_attempts:
            logger.error(
                "%s: HTTP %d after %d attempts; giving up", label, response.status_code, attempt
            )
            response.raise_for_status()
            return response  # pragma: no cover - raise_for_status raises for 429/5xx

        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            delay = min(max_delay, retry_after)
        else:
            delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * jitter()
        logger.warning(
            "%s: HTTP %d (attempt %d/%d); retrying in %.1fs",
            label,
            response.status_code,
            attempt,
            max_attempts,
            delay,
        )
        await sleep(delay)

    raise RuntimeError(f"{label}: max_attempts must be >= 1")  # pragma: no cover
