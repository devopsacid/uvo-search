"""In-process TTL cache for async MCP tool helpers."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable

from cachetools import TTLCache
from cachetools.keys import hashkey


def _make_key(args: tuple, kwargs: dict) -> tuple:
    norm: list[tuple[str, Any]] = []
    for k in sorted(kwargs):
        v = kwargs[k]
        if isinstance(v, list):
            v = tuple(v)
        norm.append((k, v))
    norm_args = tuple(tuple(a) if isinstance(a, list) else a for a in args)
    return hashkey(norm_args, tuple(norm))


def async_ttl_cache(*, maxsize: int, ttl: float, key_from: Callable | None = None) -> Callable:
    """Decorator for async functions. Caches by hashable args/kwargs.

    Concurrent identical calls share a single in-flight coroutine (prevents
    thundering herd). Pass ``key_from`` to derive the cache key from a subset
    of arguments (e.g. to skip an unhashable ``db`` handle).
    """

    def decorator(fn: Callable) -> Callable:
        cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        pending: dict[Any, asyncio.Future] = {}

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                if key_from is not None:
                    key = key_from(*args, **kwargs)
                else:
                    key = _make_key(args, kwargs)
            except TypeError:
                return await fn(*args, **kwargs)

            if key in cache:
                return cache[key]

            if key in pending:
                return await pending[key]

            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            pending[key] = fut
            try:
                result = await fn(*args, **kwargs)
                cache[key] = result
                fut.set_result(result)
                return result
            except Exception as exc:
                fut.set_exception(exc)
                raise
            finally:
                pending.pop(key, None)

        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        wrapper.cache_info = lambda: {  # type: ignore[attr-defined]
            "size": len(cache),
            "maxsize": cache.maxsize,
            "ttl": cache.ttl,
        }
        return wrapper

    return decorator
