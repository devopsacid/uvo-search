"""Dashboard aggregation tests — pure pipeline builders + CompanyAnalytics fake."""

from uvo_core.adapters.mongo.analytics import (
    _VALUE_EXPR,
    build_cpv_breakdown_pipeline,
    build_monthly_buckets_pipeline,
    build_spend_by_year_pipeline,
    build_top_entities_pipeline,
)
from uvo_core.testing import InMemoryCompanyAnalytics

NOTICES = [
    {
        "notice_type": "contract_award",
        "procurer": {"ico": "P1", "name": "Ministry"},
        "awards": [{"supplier": {"ico": "S1", "name": "Alpha"}}],
        "final_value": 500000.0,
        "award_date": "2024-03-01",
        "cpv_code": "72000000",
    },
    {
        "notice_type": "contract_award",
        "procurer": {"ico": "P1", "name": "Ministry"},
        "awards": [{"supplier": {"ico": "S2", "name": "Beta"}}],
        "final_value": 1000000.0,
        "award_date": "2023-06-15",
        "cpv_code": "45000000",
    },
    {
        "notice_type": "contract_award",
        "procurer": {"ico": "P2", "name": "City"},
        "awards": [{"supplier": {"ico": "S1", "name": "Alpha"}}],
        "estimated_value": 250000.0,  # no final_value → falls back to estimated
        "award_date": "2024-07-20",
        "cpv_code": "72000000",
    },
]


# --- pure pipeline builders -------------------------------------------------

def test_spend_by_year_pipeline_shape():
    pipeline = build_spend_by_year_pipeline(None, None)
    assert pipeline[0]["$match"] == {"notice_type": "contract_award"}
    group = pipeline[1]["$group"]
    assert group["total"] == {"$sum": _VALUE_EXPR}
    assert group["count"] == {"$sum": 1}


def test_spend_by_year_pipeline_applies_ico_filter():
    supplier = build_spend_by_year_pipeline("S1", "supplier")
    assert supplier[0]["$match"]["awards.supplier.ico"] == "S1"
    procurer = build_spend_by_year_pipeline("P1", "procurer")
    assert procurer[0]["$match"]["procurer.ico"] == "P1"


def test_cpv_breakdown_pipeline_year_bounds():
    pipeline = build_cpv_breakdown_pipeline(None, None, 2024, 2024)
    year_match = next(s for s in pipeline if "$match" in s and "_year" in s["$match"])
    assert year_match["$match"]["_year"] == {"$gte": 2024, "$lte": 2024}


def test_monthly_buckets_pipeline_year_window():
    pipeline = build_monthly_buckets_pipeline(2024)
    window = next(s for s in pipeline if "$match" in s and "_d" in s["$match"])
    assert window["$match"]["_d"] == {"$gte": "2024-", "$lt": "2025-"}


def test_top_entities_pipeline_supplier_unwinds():
    pipeline = build_top_entities_pipeline("awards.supplier.ico", unwind=True, n=5)
    assert {"$unwind": "$awards"} in pipeline
    assert pipeline[-1] == {"$limit": 5}


# --- fake computations ------------------------------------------------------

async def test_fake_spend_by_year():
    analytics = InMemoryCompanyAnalytics(NOTICES)
    rows = await analytics.spend_by_year()
    by_year = {r["_id"]: r for r in rows}
    assert by_year["2024"]["total"] == 750000.0  # 500000 final + 250000 estimated
    assert by_year["2024"]["count"] == 2
    assert by_year["2023"]["total"] == 1000000.0


async def test_fake_cpv_breakdown_year_filter():
    analytics = InMemoryCompanyAnalytics(NOTICES)
    all_rows = await analytics.cpv_breakdown()
    assert {r["_id"] for r in all_rows} == {"72000000", "45000000"}

    only_2024 = await analytics.cpv_breakdown(year_from=2024)
    assert {r["_id"] for r in only_2024} == {"72000000"}


async def test_fake_monthly_buckets():
    analytics = InMemoryCompanyAnalytics(NOTICES)
    rows = await analytics.monthly_buckets(2024)
    by_month = {r["_id"]: r for r in rows}
    assert by_month[3]["count"] == 1
    assert by_month[3]["total"] == 500000.0
    assert by_month[7]["total"] == 250000.0
    assert 6 not in by_month  # the 2023 award is excluded


async def test_fake_top_suppliers_ranked():
    analytics = InMemoryCompanyAnalytics(NOTICES)
    rows = await analytics.top_suppliers(10)
    # S1 only has final_value on one of its two awards (500000); S2 has 1000000.
    ranked = [r["_id"] for r in rows]
    assert ranked[0] == "S2"
    assert set(ranked) == {"S1", "S2"}
