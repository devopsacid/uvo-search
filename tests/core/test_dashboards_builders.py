"""Pure pipeline builders for the analytics dashboards (metric definition D1)."""

import json

import pytest

from uvo_core.adapters.mongo.dashboards import (
    build_concentration_pipeline,
    build_coverage_pipelines,
    build_cpv_pipeline,
    build_match,
    build_summary_pipeline,
    build_timeseries_pipeline,
    build_top_pipeline,
)
from uvo_core.domain.analytics import DATE_EXPR, VALUE_EXPR, DashboardFilter

F = DashboardFilter(date_from="2022-01-01", date_to="2026-10-19")


def _walk(node):
    """Yield every dict/list node of a pipeline (to search for operators)."""
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _has_key(pipeline, key) -> bool:
    return any(isinstance(n, dict) and key in n for n in _walk(pipeline))


def test_match_is_the_index_friendly_d1_shape():
    assert build_match(F) == {
        "notice_type": "contract_award",
        "$or": [
            {"award_date": {"$gte": "2022-01-01", "$lte": "2026-10-19"}},
            {
                "award_date": None,
                "publication_date": {"$gte": "2022-01-01", "$lte": "2026-10-19"},
            },
        ],
    }


def test_match_adds_optional_filters_with_anchored_cpv_regex():
    f = DashboardFilter(
        date_from="2022-01-01",
        date_to="2022-12-31",
        cpv="45",
        source="crz",
        procurer_ico="00151742",
        supplier_ico="35763469",
    )
    match = build_match(f)
    assert match["cpv_code"] == {"$regex": "^45"}
    assert match["source"] == "crz"
    assert match["procurer.ico"] == "00151742"
    assert match["awards.supplier.ico"] == "35763469"


def test_every_pipeline_starts_with_the_match_stage():
    pipelines = [
        build_summary_pipeline(F),
        build_timeseries_pipeline(F, "month", None, 5),
        build_top_pipeline(F, "procurer", "total_value", 10),
        build_concentration_pipeline(F, "supplier"),
        build_cpv_pipeline(F, "division"),
    ]
    for pipeline in pipelines:
        assert pipeline[0] == {"$match": build_match(F)}


def test_summary_counts_distinct_suppliers_with_set_union_not_plain_unwind():
    pipeline = build_summary_pipeline(F)
    text = json.dumps(pipeline)
    assert "$setUnion" in text
    assert "$unwind" in text  # only over the de-duplicated per-notice supplier set
    assert not any(
        isinstance(n, dict) and n.get("$unwind") in ("$awards", {"path": "$awards"})
        for n in _walk(pipeline)
    )
    facet = next(s["$facet"] for s in pipeline if "$facet" in s)
    assert set(facet) == {"totals", "procurers", "suppliers"}


def test_summary_value_uses_d1_coalesce():
    assert VALUE_EXPR in list(_walk(build_summary_pipeline(F)))


def _substr_lengths(pipeline) -> set[int]:
    return {n["$substrCP"][2] for n in _walk(pipeline) if isinstance(n, dict) and "$substrCP" in n}


def test_timeseries_groups_by_period_prefix_of_the_d1_date():
    month = build_timeseries_pipeline(F, "month", None, 5)
    group = next(s["$group"] for s in month if "$group" in s)
    assert group["_id"] == {"period": {"$substrCP": [DATE_EXPR, 0, 7]}}
    year = build_timeseries_pipeline(F, "year", None, 5)
    group = next(s["$group"] for s in year if "$group" in s)
    assert group["_id"] == {"period": {"$substrCP": [DATE_EXPR, 0, 4]}}


def test_timeseries_split_adds_a_key_to_the_group_id():
    source = build_timeseries_pipeline(F, "month", "source", 5)
    group = next(s["$group"] for s in source if "$group" in s)
    assert set(group["_id"]) == {"period", "key"}
    plain = build_timeseries_pipeline(F, "month", None, 5)
    assert set(next(s["$group"] for s in plain if "$group" in s)["_id"]) == {"period"}


def test_timeseries_rejects_unknown_split():
    with pytest.raises(ValueError):
        build_timeseries_pipeline(F, "month", "bogus", 5)


def test_top_supplier_pipeline_dedupes_per_notice_and_limits():
    pipeline = build_top_pipeline(F, "supplier", "contract_count", 7)
    facet = next(s["$facet"] for s in pipeline if "$facet" in s)
    assert set(facet) == {"total", "items"}
    assert "$setUnion" in json.dumps(pipeline)
    assert {"$limit": 7} in facet["items"]
    sort = next(s["$sort"] for s in facet["items"] if "$sort" in s)
    assert list(sort)[0] == "count"


def test_top_rejects_unknown_dimension_and_metric():
    with pytest.raises(ValueError):
        build_top_pipeline(F, "bogus", "total_value", 5)
    with pytest.raises(ValueError):
        build_top_pipeline(F, "procurer", "bogus", 5)


def test_concentration_groups_by_ico_then_facets_totals_and_top():
    pipeline = build_concentration_pipeline(F, "supplier")
    group_idx = next(i for i, s in enumerate(pipeline) if "$group" in s)
    facet_idx = next(i for i, s in enumerate(pipeline) if "$facet" in s)
    assert group_idx < facet_idx
    facet = pipeline[facet_idx]["$facet"]
    assert set(facet) == {"totals", "top"}
    assert {"$limit": 10} in facet["top"]
    totals_group = facet["totals"][0]["$group"]
    assert set(totals_group) == {"_id", "total", "sumsq", "n"}


def test_cpv_pipeline_division_and_group_use_two_and_three_digit_buckets():
    assert 2 in _substr_lengths(build_cpv_pipeline(F, "division"))
    assert 3 in _substr_lengths(build_cpv_pipeline(F, "group"))
    assert 3 not in _substr_lengths(build_cpv_pipeline(F, "division"))


def test_coverage_pipelines_cover_sources_monthly_and_canonical():
    pipelines = build_coverage_pipelines("2024-11")
    assert set(pipelines) == {"sources", "monthly", "canonical"}
    sources_group = next(s["$group"] for s in pipelines["sources"] if "$group" in s)
    assert sources_group["_id"] == "$source"
    assert {"notices_total", "contract_awards", "last_ingested", "last_publication"} <= set(
        sources_group
    )
    assert pipelines["monthly"][0] == {"$match": {"publication_date": {"$gte": "2024-11"}}}


async def test_ensure_indexes_creates_the_two_dashboard_indexes():
    from unittest.mock import AsyncMock, MagicMock

    from uvo_core.adapters.mongo.loaders import ensure_indexes

    db = MagicMock()
    for coll in (db.notices, db.procurers, db.suppliers):
        coll.create_index = AsyncMock()
    try:
        await ensure_indexes(db)
    except Exception:  # noqa: BLE001 - later setup steps use collections this fake lacks
        pass
    created = {c.kwargs.get("name"): c.args[0] for c in db.notices.create_index.call_args_list}
    assert created["notice_type_award_date_desc"] == [("notice_type", 1), ("award_date", -1)]
    assert created["source_notice_type_publication_date_desc"] == [
        ("source", 1),
        ("notice_type", 1),
        ("publication_date", -1),
    ]
