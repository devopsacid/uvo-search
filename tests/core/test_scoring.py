"""Domain scoring tests — pure functions + port fakes, zero containers."""

import pytest

from uvo_core.domain.scoring import cpv_concentration
from uvo_core.testing import InMemoryCompanyAnalytics


def test_cpv_concentration_monopoly():
    shares, hhi = cpv_concentration([1000.0])
    assert shares == [1.0]
    assert hhi == 1.0


def test_cpv_concentration_even_split():
    shares, hhi = cpv_concentration([500.0, 500.0])
    assert shares == [0.5, 0.5]
    assert hhi == pytest.approx(0.5)


def test_cpv_concentration_known_mix():
    # 0.8 / 0.2 → 0.64 + 0.04 = 0.68  (matches the /v1 profile assertion)
    shares, hhi = cpv_concentration([4_000_000.0, 1_000_000.0])
    assert shares == pytest.approx([0.8, 0.2])
    assert hhi == pytest.approx(0.68)


def test_cpv_concentration_empty_and_zero():
    assert cpv_concentration([]) == ([], 0.0)
    assert cpv_concentration([0.0, 0.0]) == ([0.0, 0.0], 0.0)


@pytest.mark.asyncio
async def test_cpv_concentration_over_fake_core_stats():
    notices = [
        {"awards": [{"supplier": {"ico": "S1"}}], "cpv_code": "72000000", "final_value": 4_000_000.0},
        {"awards": [{"supplier": {"ico": "S1"}}], "cpv_code": "48000000", "final_value": 1_000_000.0},
    ]
    analytics = InMemoryCompanyAnalytics(notices)
    core = await analytics.core_stats("S1")
    values = [float(r["total"]) for r in core["cpv"]]
    _, hhi = cpv_concentration(values)
    assert hhi == pytest.approx(0.68)
