"""The risk profile's independent reads must be issued concurrently (B10)."""

import asyncio

from uvo_core.services.risk import company_risk_profile


class _BarrierAnalytics:
    """Each read waits until all of them are in flight; serial awaits would deadlock."""

    def __init__(self, expected: int) -> None:
        self._expected = expected
        self._arrived = 0
        self._all_in = asyncio.Event()

    async def _rendezvous(self, value):
        self._arrived += 1
        if self._arrived >= self._expected:
            self._all_in.set()
        await asyncio.wait_for(self._all_in.wait(), timeout=1)
        return value

    async def core_stats(self, ico):
        return await self._rendezvous({"cpv": []})

    async def partners(self, ico, role, sort_by, limit, offset):
        return await self._rendezvous({"items": []})

    async def market_cpv(self, limit=20):
        return await self._rendezvous([])

    async def award_timeline(self, ico):
        return await self._rendezvous([])


class _Graph:
    def __init__(self, analytics: _BarrierAnalytics) -> None:
        self._analytics = analytics

    async def supplier_concentration(self, ico, top_n=10):
        return await self._analytics._rendezvous({"top_suppliers": []})


async def test_risk_reads_are_concurrent():
    analytics = _BarrierAnalytics(expected=5)
    profile = await company_risk_profile("123", analytics, _Graph(analytics))
    assert profile["ico"] == "123"
