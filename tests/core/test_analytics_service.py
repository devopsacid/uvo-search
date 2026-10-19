"""Analytics use-cases over the in-memory D1 reference implementation."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from uvo_core.cache import clear_data_caches
from uvo_core.domain.analytics import DashboardFilter, FilterValidationError
from uvo_core.services import analytics as svc
from uvo_core.testing import InMemoryDashboardAnalytics

FIXTURE = Path(__file__).parent.parent / "fixtures" / "analytics_notices.json"
TODAY = date(2025, 12, 31)
ALL = DashboardFilter(date_from="2023-01-01", date_to="2025-12-31")


@pytest.fixture(scope="module")
def notices():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def fake(notices):
    return InMemoryDashboardAnalytics(notices)


def test_fixture_has_the_agreed_composition(notices):
    assert len(notices) == 30
    assert {n["source"] for n in notices} == {"vestnik", "crz", "ted", "uvo", "itms"}
    years = {(n.get("award_date") or n["publication_date"])[:4] for n in notices}
    assert years == {"2023", "2024", "2025"}
    assert len({(n.get("cpv_code") or "")[:2] for n in notices if n.get("cpv_code")}) == 6
    awards = [n for n in notices if n["notice_type"] == "contract_award"]
    assert sum(1 for n in awards if len({a["supplier"]["ico"] for a in n["awards"]}) > 1) == 2
    assert (
        sum(1 for n in notices if n.get("final_value") is None and not n.get("estimated_value"))
        == 3
    )
    assert sum(1 for n in notices if not n.get("cpv_code")) == 2
    assert sum(1 for n in notices if n.get("canonical_id")) == 2


async def test_summary_applies_defaults_and_computes_deltas(fake):
    out = await svc.summary(fake, DashboardFilter(date_from="2024-01-01", date_to="2024-12-31"))
    assert out["meta"]["definition"] == "D1"
    assert out["meta"]["filters"]["date_from"] == "2024-01-01"
    assert out["meta"]["generated_at"].endswith("Z")
    assert out["current"]["contract_count"] == 10
    assert out["current"]["total_value"] == 10_210_000.0
    assert out["current"]["supplier_count"] == 6
    prev = out["previous"]
    assert (prev["date_from"], prev["date_to"]) == ("2022-12-31", "2023-12-31")
    assert prev["contract_count"] == 9
    assert prev["total_value"] == 11_672_000.0
    assert out["deltas"]["contract_count_pct"] == pytest.approx(11.1, abs=0.05)
    assert out["deltas"]["total_value_pct"] == pytest.approx(-12.5, abs=0.05)


async def test_summary_delta_is_none_when_previous_value_is_zero(fake):
    out = await svc.summary(fake, DashboardFilter(date_from="2023-01-01", date_to="2023-12-31"))
    assert out["previous"]["contract_count"] == 0
    assert all(v is None for v in out["deltas"].values())


async def test_summary_previous_is_none_before_1993():
    stub = AsyncMock()
    stub.summary.return_value = {
        "date_from": "x",
        "date_to": "y",
        "contract_count": 1,
        "total_value": 1.0,
        "avg_value": 1.0,
        "procurer_count": 1,
        "supplier_count": 1,
    }
    out = await svc.summary(stub, DashboardFilter(date_from="1993-01-01", date_to="1995-01-01"))
    assert out["previous"] is None and out["deltas"] is not None
    assert all(v is None for v in out["deltas"].values())
    stub.summary.assert_awaited_once()


async def test_default_filter_uses_today(fake):
    out = await svc.summary(fake, DashboardFilter(), today=TODAY)
    assert out["meta"]["filters"]["date_from"] == "2021-01-01"
    assert out["meta"]["filters"]["date_to"] == "2025-12-31"


async def test_invalid_filter_raises_before_touching_the_port():
    stub = AsyncMock()
    with pytest.raises(FilterValidationError):
        await svc.summary(stub, DashboardFilter(date_from="2025-02-01", date_to="2025-01-01"))
    with pytest.raises(FilterValidationError):
        await svc.top(stub, DashboardFilter(cpv="x"), "procurer", "total_value", 10, today=TODAY)
    assert stub.method_calls == []


async def test_timeseries_wraps_meta_and_filters(fake):
    out = await svc.timeseries(fake, ALL, "quarter", None, 5)
    assert out["granularity"] == "quarter"
    assert out["points"][0]["period"] == "2023-Q1"
    assert len(out["points"]) == 12
    assert sum(p["contract_count"] for p in out["points"]) == 28
    assert out["series"] is None
    assert out["meta"]["filters"]["cpv"] is None


async def test_timeseries_split_by_source(fake):
    out = await svc.timeseries(fake, ALL, "year", "source", 3)
    keys = [s["key"] for s in out["series"]]
    assert keys[0] == "ted" and keys[-1] == "other" and len(keys) == 4
    total = sum(sum(p["total_value"] for p in s["points"]) for s in out["series"])
    assert total == pytest.approx(27_328_000.0)


async def test_top_suppliers_attribute_full_value_to_each_distinct_supplier(fake):
    out = await svc.top(fake, ALL, "supplier", "total_value", 3)
    assert [i["key"] for i in out["items"]] == ["35763469", "31322832", "44103011"]
    assert out["items"][0]["total_value"] == 20_000_000.0
    assert out["items"][0]["contract_count"] == 6
    assert out["total"] == {"total_value": 27_328_000.0, "contract_count": 28}


async def test_top_procurers_and_shares(fake):
    out = await svc.top(fake, ALL, "procurer", "total_value", 2)
    assert [i["key"] for i in out["items"]] == ["36631124", "00151742"]
    shares = sum(i["share_pct"] for i in out["items"]) + out["other"]["share_pct"]
    assert shares == pytest.approx(100.0, abs=0.2)
    assert out["other"]["contract_count"] == 28 - 6 - 8


async def test_concentration_matches_hand_computed_hhi(fake):
    out = await svc.concentration(fake, ALL, "supplier")
    assert out["entity_count"] == 6
    assert out["hhi"] == pytest.approx(4789.2, abs=0.1)
    assert out["hhi_band"] == "high"
    assert out["top"][0]["ico"] == "35763469"
    assert out["top"][-1]["cumulative_pct"] == 100.0


async def test_cpv_breakdown_includes_the_no_cpv_bucket(fake):
    out = await svc.cpv_breakdown(fake, ALL, "division")
    codes = {i["cpv_code"]: i for i in out["items"]}
    assert codes["45000000"]["total_value"] == 20_000_000.0
    assert codes["00000000"]["contract_count"] == 2
    assert out["contract_count"] == 28


async def test_filters_narrow_every_view(fake):
    f = DashboardFilter(date_from="2023-01-01", date_to="2025-12-31", source="crz", cpv="72")
    out = await svc.summary(fake, f)
    assert out["current"]["contract_count"] == 2
    assert out["current"]["total_value"] == 173_000.0


async def test_coverage_lists_all_sources(fake):
    out = await svc.coverage(fake)
    assert [s["source"] for s in out["sources"]] == ["vestnik", "crz", "ted", "uvo", "itms"]
    assert out["canonical"] == {"notices_with_canonical_id": 2, "match_groups": 2}
    assert out["sources"][0]["notices_total"] == 8
    assert out["sources"][0]["contract_awards"] == 7
    assert len(out["monthly"]) == 24
    assert "meta" not in out


async def test_warm_up_calls_each_default_aggregate_and_swallows_failures():
    stub = AsyncMock()
    stub.summary.return_value = {
        "date_from": "a",
        "date_to": "b",
        "contract_count": 0,
        "total_value": 0.0,
        "avg_value": 0.0,
        "procurer_count": 0,
        "supplier_count": 0,
    }
    stub.top.side_effect = RuntimeError("mongo is gone")
    await svc.warm_default_dashboards(stub, TODAY)
    called = {c[0] for c in stub.method_calls}
    assert {"summary", "timeseries", "top", "cpv", "coverage"} <= called
    first_filter = stub.summary.await_args_list[0].args[0]
    assert first_filter.date_from == "2021-01-01" and first_filter.date_to == "2025-12-31"


async def test_data_caches_are_cleared_by_clear_data_caches(monkeypatch, notices):
    from uvo_core.adapters.mongo import dashboards

    calls = []

    async def fake_run(db, pipeline):
        calls.append(pipeline)
        return []

    monkeypatch.setattr(dashboards, "_run", fake_run)
    clear_data_caches()
    adapter = dashboards.MongoDashboardAnalytics(object())
    await adapter.summary(ALL)
    await adapter.summary(ALL)
    assert len(calls) == 1  # second call served from the cache
    clear_data_caches()
    await adapter.summary(ALL)
    assert len(calls) == 2


def test_generated_at_helper_is_utc_z():
    assert svc.utc_now_z(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)) == "2026-01-02T03:04:05Z"
