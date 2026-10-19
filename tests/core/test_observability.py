"""Core observability: cache counters, ready gauge, default-registry rendering."""

import asyncio

from prometheus_client import REGISTRY

from uvo_core import observability
from uvo_core.cache import async_ttl_cache


def _sample(name: str, labels: dict) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_cache_counts_miss_then_hit_and_times_the_miss():
    @async_ttl_cache(maxsize=4, ttl=60, name="t_obs.basic")
    async def f(x):
        return x

    miss0 = _sample("uvo_cache_requests_total", {"cache": "t_obs.basic", "result": "miss"})
    hit0 = _sample("uvo_cache_requests_total", {"cache": "t_obs.basic", "result": "hit"})
    dur0 = _sample("uvo_cached_call_duration_seconds_count", {"cache": "t_obs.basic"})

    await f(1)
    await f(1)

    assert _sample("uvo_cache_requests_total", {"cache": "t_obs.basic", "result": "miss"}) == (
        miss0 + 1
    )
    assert _sample("uvo_cache_requests_total", {"cache": "t_obs.basic", "result": "hit"}) == (
        hit0 + 1
    )
    # Only the underlying call (the miss) is timed.
    assert _sample("uvo_cached_call_duration_seconds_count", {"cache": "t_obs.basic"}) == dur0 + 1


async def test_cache_counts_inflight_for_concurrent_identical_calls():
    gate = asyncio.Event()

    @async_ttl_cache(maxsize=4, ttl=60, name="t_obs.inflight")
    async def slow(x):
        await gate.wait()
        return x

    labels = {"cache": "t_obs.inflight"}
    tasks = [asyncio.create_task(slow(1)) for _ in range(3)]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(*tasks)

    assert _sample("uvo_cache_requests_total", {**labels, "result": "miss"}) == 1
    assert _sample("uvo_cache_requests_total", {**labels, "result": "inflight"}) == 2


async def test_default_cache_name_is_module_tail_dot_function():
    @async_ttl_cache(maxsize=1, ttl=60)
    async def some_agg():
        return 1

    await some_agg()
    name = f"{__name__.split('.')[-1]}.some_agg"
    assert _sample("uvo_cache_requests_total", {"cache": name, "result": "miss"}) == 1


async def test_failed_call_is_still_a_miss_and_not_cached():
    @async_ttl_cache(maxsize=1, ttl=60, name="t_obs.fail")
    async def boom():
        raise RuntimeError("x")

    for _ in range(2):
        try:
            await boom()
        except RuntimeError:
            pass
    assert _sample("uvo_cache_requests_total", {"cache": "t_obs.fail", "result": "miss"}) == 2


def test_set_ready_toggles_gauge_per_service():
    observability.set_ready("t-svc", False)
    assert _sample("uvo_ready", {"service": "t-svc"}) == 0
    observability.set_ready("t-svc", True)
    assert _sample("uvo_ready", {"service": "t-svc"}) == 1


def test_render_default_registry_contains_core_families():
    observability.set_ready("t-render", True)
    text = observability.render_default_registry().decode()
    assert 'uvo_ready{service="t-render"} 1.0' in text
    assert observability.CONTENT_TYPE.startswith("text/plain; version=0.0.4")
