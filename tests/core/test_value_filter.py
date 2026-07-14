"""Regression: value_min/value_max filter the query, so totals stay correct
across pages (plan §1.3.7 — the old post-pagination Python filter reset the
total to the current page length and dropped rows mid-page)."""

from uvo_core.testing import InMemoryNoticeRepository

NOTICES = [
    {"_id": str(i), "notice_type": "contract_award", "final_value": v}
    for i, v in enumerate([100.0, 200.0, 300.0, 400.0, 500.0])
]


async def test_value_min_total_consistent_across_pages():
    repo = InMemoryNoticeRepository(NOTICES)

    page0 = await repo.search(value_min=250, limit=2, offset=0)
    page1 = await repo.search(value_min=250, limit=2, offset=2)

    # 300, 400, 500 pass the filter → total is 3 on every page.
    assert page0["total"] == 3
    assert page1["total"] == 3
    assert [n["final_value"] for n in page0["items"]] == [300.0, 400.0]
    assert [n["final_value"] for n in page1["items"]] == [500.0]


async def test_value_range_filters_both_bounds():
    repo = InMemoryNoticeRepository(NOTICES)
    result = await repo.search(value_min=200, value_max=400, limit=10, offset=0)
    assert result["total"] == 3
    assert [n["final_value"] for n in result["items"]] == [200.0, 300.0, 400.0]


async def test_no_filter_returns_full_corpus():
    repo = InMemoryNoticeRepository(NOTICES)
    result = await repo.search(limit=10, offset=0)
    assert result["total"] == 5
