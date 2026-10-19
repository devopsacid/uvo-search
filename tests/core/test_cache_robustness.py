"""Robustness tests for uvo_core.cache.async_ttl_cache (B21)."""

import asyncio
import gc

import pytest

from uvo_core.cache import async_ttl_cache


async def test_cached_value_is_defensively_copied():
    @async_ttl_cache(maxsize=4, ttl=60)
    async def f(x):
        return {"items": [x]}

    first = await f(1)
    first["items"].append("mutated")
    second = await f(1)
    assert second == {"items": [1]}


async def test_leader_cancellation_does_not_hang_waiters():
    started = asyncio.Event()
    calls = {"n": 0}

    @async_ttl_cache(maxsize=4, ttl=60)
    async def slow(x):
        calls["n"] += 1
        if calls["n"] == 1:
            started.set()
            await asyncio.sleep(10)
        return x

    leader = asyncio.create_task(slow(1))
    await started.wait()
    waiter = asyncio.create_task(slow(1))
    await asyncio.sleep(0)
    leader.cancel()
    assert await asyncio.wait_for(waiter, timeout=2) == 1
    with pytest.raises(asyncio.CancelledError):
        await leader


async def test_failure_without_waiters_leaves_no_unretrieved_exception(caplog):
    @async_ttl_cache(maxsize=4, ttl=60)
    async def boom(x):
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await boom(1)
    gc.collect()
    assert "exception was never retrieved" not in caplog.text


async def test_failure_propagates_to_waiters_and_is_not_cached():
    calls = {"n": 0}

    @async_ttl_cache(maxsize=4, ttl=60)
    async def flaky(x):
        calls["n"] += 1
        await asyncio.sleep(0.02)
        if calls["n"] == 1:
            raise ValueError("first")
        return x

    results = await asyncio.gather(flaky(1), flaky(1), return_exceptions=True)
    assert all(isinstance(r, ValueError) for r in results)
    assert await flaky(1) == 1
