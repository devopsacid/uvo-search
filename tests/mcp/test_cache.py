import asyncio

from uvo_mcp.cache import async_ttl_cache


async def test_hits_reuse_cached_result():
    calls = {"n": 0}

    @async_ttl_cache(maxsize=8, ttl=60)
    async def f(x):
        calls["n"] += 1
        return x * 2

    assert await f(3) == 6
    assert await f(3) == 6
    assert calls["n"] == 1


async def test_different_args_miss():
    calls = {"n": 0}

    @async_ttl_cache(maxsize=8, ttl=60)
    async def f(x):
        calls["n"] += 1
        return x

    await f(1)
    await f(2)
    assert calls["n"] == 2


async def test_key_from_lets_callers_ignore_first_arg():
    from uvo_mcp.cache import _make_key

    calls = {"n": 0}

    @async_ttl_cache(
        maxsize=8,
        ttl=60,
        key_from=lambda db, q, *, limit: _make_key((q,), {"limit": limit}),
    )
    async def f(db, q, *, limit):
        calls["n"] += 1
        return (q, limit)

    db1 = object()
    db2 = object()
    assert await f(db1, "fakulta", limit=5) == ("fakulta", 5)
    assert await f(db2, "fakulta", limit=5) == ("fakulta", 5)
    assert calls["n"] == 1


async def test_concurrent_calls_share_inflight():
    started = 0

    @async_ttl_cache(maxsize=8, ttl=60)
    async def slow(x):
        nonlocal started
        started += 1
        await asyncio.sleep(0.05)
        return x

    results = await asyncio.gather(slow(1), slow(1), slow(1))
    assert results == [1, 1, 1]
    assert started == 1
