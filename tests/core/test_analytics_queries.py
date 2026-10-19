"""Caching, ordering and full-population aggregation behaviour of the Mongo analytics adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_core.adapters.mongo import analytics
from uvo_core.adapters.mongo.analytics import (
    MongoCompanyAnalytics,
    clear_analytics_caches,
    entity_profile,
    top_contracts_by_value,
)


@pytest.fixture(autouse=True)
def _fresh_caches():
    clear_analytics_caches()
    yield
    clear_analytics_caches()


@pytest.fixture
def mongomock_year_expr(monkeypatch):
    """mongomock lacks $substrCP; swap in the equivalent $substr for the year bucket."""
    monkeypatch.setattr(
        analytics,
        "_YEAR_STR",
        {"$substr": [{"$ifNull": [analytics._DATE_EXPR, "0000"]}, 0, 4]},
    )


def _counting_db(rows: list[dict]):
    """A db double whose notices.aggregate(...).to_list() counts invocations."""
    to_list = AsyncMock(return_value=rows)
    notices = MagicMock()
    notices.aggregate.return_value.to_list = to_list
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: notices
    return db, notices


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("spend_by_year", ()),
        ("cpv_breakdown", ()),
        ("monthly_buckets", (2024,)),
        ("top_suppliers", (10,)),
        ("top_procurers", (10,)),
    ],
)
async def test_dashboard_aggregates_are_cached(method, args):
    db, notices = _counting_db([{"_id": "x", "total": 1, "count": 1}])
    svc = MongoCompanyAnalytics(db)

    first = await getattr(svc, method)(*args)
    second = await getattr(svc, method)(*args)

    assert first == second
    assert notices.aggregate.call_count == 1


async def test_award_timeline_is_cached_and_runs_both_pipelines_once():
    db, notices = _counting_db([{"date": "2024-01-01"}])
    svc = MongoCompanyAnalytics(db)

    await svc.award_timeline("111")
    await svc.award_timeline("111")

    assert notices.aggregate.call_count == 2  # procurer-side + supplier-side, once


async def test_clear_analytics_caches_covers_dashboard_aggregates():
    db, notices = _counting_db([])
    svc = MongoCompanyAnalytics(db)
    await svc.spend_by_year()
    await svc.top_suppliers(10)
    await svc.monthly_buckets(2024)
    clear_analytics_caches()
    await svc.spend_by_year()
    await svc.top_suppliers(10)
    await svc.monthly_buckets(2024)
    assert notices.aggregate.call_count == 6


def _notice(sid, procurer, supplier, value, date="2024-05-01"):
    return {
        "source": "vestnik",
        "source_id": sid,
        "notice_type": "contract_award",
        "title": f"T{sid}",
        "procurer": {"ico": procurer, "name": f"P{procurer}"},
        "awards": [{"supplier": {"ico": supplier, "name": f"S{supplier}"}}],
        "final_value": value,
        "award_date": date,
        "publication_date": date,
    }


async def test_top_contracts_by_value_sorts_largest_first_for_supplier():
    db = AsyncMongoMockClient()["top_contracts_supplier"]
    await db.notices.insert_many(
        [
            _notice("a", "P1", "S1", 100.0),
            _notice("b", "P1", "S1", 900.0, "2020-01-01"),
            _notice("c", "P2", "S1", 500.0),
            _notice("d", "P2", "S9", 99999.0),
        ]
    )
    items = await top_contracts_by_value(db, "S1", "supplier", limit=2)
    assert [i["final_value"] for i in items] == [900.0, 500.0]
    assert all(isinstance(i["_id"], str) for i in items)


async def test_top_contracts_by_value_procurer_role():
    db = AsyncMongoMockClient()["top_contracts_procurer"]
    await db.notices.insert_many(
        [_notice("a", "P1", "S1", 10.0), _notice("b", "P1", "S2", 30.0), _notice("c", "P2", "S1", 99.0)]
    )
    items = await top_contracts_by_value(db, "P1", "procurer", limit=5)
    assert [i["final_value"] for i in items] == [30.0, 10.0]


async def test_entity_profile_covers_full_population_beyond_100_rows(mongomock_year_expr):
    db = AsyncMongoMockClient()["profile_full"]
    docs = [_notice(f"n{i}", "P1", f"S{i % 150}", 10.0, f"{2015 + i % 5}-03-01") for i in range(300)]
    await db.notices.insert_many(docs)

    profile = await entity_profile(db, "P1", "procurer")

    assert profile["contract_count"] == 300
    assert profile["total_value"] == pytest.approx(3000.0)
    assert profile["years_active"] == [2015, 2016, 2017, 2018, 2019]
    assert sum(y["total_value"] for y in profile["spend_by_year"]) == pytest.approx(3000.0)
    # 150 equal-share suppliers: HHI = 150 * (100/150)^2 = 66.7
    assert profile["hhi"] == pytest.approx(10000 / 150, rel=1e-3)
    assert profile["partner_count"] == 150
    assert len(profile["partners"]) <= 10


async def test_entity_profile_supplier_role_counterparties_are_procurers(mongomock_year_expr):
    db = AsyncMongoMockClient()["profile_supplier"]
    await db.notices.insert_many(
        [_notice("a", "P1", "S1", 60.0), _notice("b", "P2", "S1", 40.0), _notice("c", "P2", "S2", 5.0)]
    )
    profile = await entity_profile(db, "S1", "supplier")
    assert profile["contract_count"] == 2
    assert {p["ico"] for p in profile["partners"]} == {"P1", "P2"}
    assert profile["partners"][0]["ico"] == "P1"
    assert profile["hhi"] == pytest.approx(60**2 + 40**2)


async def test_entity_profile_empty(mongomock_year_expr):
    db = AsyncMongoMockClient()["profile_empty"]
    profile = await entity_profile(db, "NOPE", "procurer")
    assert profile["contract_count"] == 0
    assert profile["hhi"] == 0.0
    assert profile["partners"] == []


async def test_partners_agg_all_runs_both_sides(monkeypatch):
    """role=all must issue both aggregations (concurrently) and merge them."""
    db = AsyncMongoMockClient()["partners_all"]
    await db.notices.insert_many([_notice("a", "P1", "S1", 10.0), _notice("b", "S1", "S2", 20.0)])
    result = await analytics._firma_partners_agg(db, "S1", "all", "value", 25, 0)
    assert result["total"] == 2
    assert {r["role"] for r in result["items"]} == {"procurer", "supplier"}
