"""In-process TTL cache for async MCP tool helpers."""

from __future__ import annotations

import asyncio
import copy
import functools
import time
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache
from cachetools.keys import hashkey

from uvo_core.observability import CACHE_REQUESTS, CACHED_CALL_DURATION


def _make_key(args: tuple, kwargs: dict) -> tuple:
    norm: list[tuple[str, Any]] = []
    for k in sorted(kwargs):
        v = kwargs[k]
        if isinstance(v, list):
            v = tuple(v)
        norm.append((k, v))
    norm_args = tuple(tuple(a) if isinstance(a, list) else a for a in args)
    return hashkey(norm_args, tuple(norm))


# cache_clear callables of every data-dependent cache; see clear_data_caches().
_DATA_CACHE_CLEARERS: list[Callable[[], None]] = []


def clear_data_caches() -> None:
    """Drop every cache whose entries derive from ingested data.

    Called by the ``notices:written`` invalidation subscriber in both delivery
    processes (API and MCP) so fresh data surfaces without waiting for TTLs.
    Caches declared with ``depends_on_data=False`` (e.g. embeddings) are kept.
    """
    for clear in _DATA_CACHE_CLEARERS:
        clear()


def async_ttl_cache(
    *,
    maxsize: int,
    ttl: float,
    key_from: Callable | None = None,
    depends_on_data: bool = True,
    name: str | None = None,
) -> Callable:
    """Decorator for async functions. Caches by hashable args/kwargs.

    Concurrent identical calls share a single in-flight coroutine (prevents
    thundering herd). Results are deep-copied on the way out so callers may
    mutate what they receive without poisoning the cache. Pass ``key_from`` to derive the cache key from a subset
    of arguments (e.g. to skip an unhashable ``db`` handle). Caches that do
    not depend on ingested data pass ``depends_on_data=False`` so they survive
    ``clear_data_caches()``.

    ``name`` labels the Prometheus series (``uvo_cache_requests_total`` and
    ``uvo_cached_call_duration_seconds``); it defaults to ``<module tail>.<function>``.
    """

    def decorator(fn: Callable) -> Callable:
        cache_name = name or f"{fn.__module__.split('.')[-1]}.{fn.__name__}"
        hits = CACHE_REQUESTS.labels(cache=cache_name, result="hit")
        misses = CACHE_REQUESTS.labels(cache=cache_name, result="miss")
        inflight = CACHE_REQUESTS.labels(cache=cache_name, result="inflight")
        call_duration = CACHED_CALL_DURATION.labels(cache=cache_name)
        cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        pending: dict[Any, asyncio.Future] = {}

        async def timed_call(*args, **kwargs):
            misses.inc()
            started = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                call_duration.observe(time.perf_counter() - started)

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                if key_from is not None:
                    key = key_from(*args, **kwargs)
                else:
                    key = _make_key(args, kwargs)
            except TypeError:
                return await timed_call(*args, **kwargs)

            while True:
                if key in cache:
                    hits.inc()
                    return copy.deepcopy(cache[key])
                in_flight = pending.get(key)
                if in_flight is None:
                    break
                inflight.inc()
                try:
                    # shield: a cancelled waiter must not cancel the shared future.
                    return copy.deepcopy(await asyncio.shield(in_flight))
                except asyncio.CancelledError:
                    task = asyncio.current_task()
                    if in_flight.cancelled() and not (task and task.cancelling()):
                        # The leader was cancelled, not us: retry (possibly as leader).
                        continue
                    raise

            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            pending[key] = fut
            try:
                result = await timed_call(*args, **kwargs)
            except asyncio.CancelledError:
                fut.cancel()
                raise
            except BaseException as exc:
                fut.set_exception(exc)
                # Mark retrieved so a waiter-less failure doesn't log
                # "Future exception was never retrieved" at GC time.
                fut.exception()
                raise
            else:
                cache[key] = result
                fut.set_result(result)
                return copy.deepcopy(result)
            finally:
                pending.pop(key, None)

        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        if depends_on_data:
            _DATA_CACHE_CLEARERS.append(cache.clear)
        wrapper.cache_info = lambda: {  # type: ignore[attr-defined]
            "size": len(cache),
            "maxsize": cache.maxsize,
            "ttl": cache.ttl,
        }
        return wrapper

    return decorator
