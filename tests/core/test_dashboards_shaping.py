"""Pure shaping of raw aggregate rows into the dashboard read-models."""

from datetime import UTC, datetime

import pytest

from uvo_core.adapters.mongo.dashboards import (
    shape_concentration,
    shape_coverage,
    shape_cpv,
    shape_summary,
    shape_timeseries,
    shape_top,
)
from uvo_core.domain.analytics import DashboardFilter

F = DashboardFilter(date_from="2024-01-01", date_to="2024-06-30")


def test_shape_summary_computes_average_and_defaults_missing_facets_to_zero():
    rows = [{"totals": [{"count": 4, "total": 1000.0}], "procurers": [{"n": 2}], "suppliers": []}]
    out = shape_summary(rows, F)
    assert out == {
        "date_from": "2024-01-01",
        "date_to": "2024-06-30",
        "contract_count": 4,
        "total_value": 1000.0,
        "avg_value": 250.0,
        "procurer_count": 2,
        "supplier_count": 0,
    }


def test_shape_summary_empty_corpus():
    out = shape_summary([{"totals": [], "procurers": [], "suppliers": []}], F)
    assert out["contract_count"] == 0 and out["avg_value"] == 0.0
    assert shape_summary([], F)["total_value"] == 0.0


def test_monthly_series_is_zero_filled_over_the_range():
    rows = [
        {"_id": {"period": "2024-02"}, "count": 2, "total": 100.0},
        {"_id": {"period": "2024-05"}, "count": 1, "total": 50.0},
    ]
    out = shape_timeseries(rows, F, "month", None, 5)
    assert [p["period"] for p in out["points"]] == [
        "2024-01",
        "2024-02",
        "2024-03",
        "2024-04",
        "2024-05",
        "2024-06",
    ]
    assert out["points"][0] == {
        "period": "2024-01",
        "contract_count": 0,
        "total_value": 0.0,
        "avg_value": 0.0,
    }
    assert out["points"][1]["avg_value"] == 50.0
    assert out["series"] is None and out["granularity"] == "month"


def test_quarter_series_sums_months():
    rows = [
        {"_id": {"period": "2024-01"}, "count": 1, "total": 10.0},
        {"_id": {"period": "2024-03"}, "count": 3, "total": 30.0},
        {"_id": {"period": "2024-04"}, "count": 2, "total": 20.0},
    ]
    out = shape_timeseries(rows, F, "quarter", None, 5)
    assert [(p["period"], p["contract_count"], p["total_value"]) for p in out["points"]] == [
        ("2024-Q1", 4, 40.0),
        ("2024-Q2", 2, 20.0),
    ]
    assert out["points"][0]["avg_value"] == 10.0


def test_year_series_accepts_year_resolution_rows():
    f = DashboardFilter(date_from="2022-01-01", date_to="2024-12-31")
    rows = [{"_id": {"period": "2023"}, "count": 5, "total": 500.0}]
    out = shape_timeseries(rows, f, "year", None, 5)
    assert [p["period"] for p in out["points"]] == ["2022", "2023", "2024"]
    assert out["points"][1]["total_value"] == 500.0


def test_split_series_keeps_top_n_and_folds_the_rest_into_other():
    rows = [
        {"_id": {"period": "2024-01", "key": "45000000"}, "count": 1, "total": 100.0},
        {"_id": {"period": "2024-02", "key": "45000000"}, "count": 1, "total": 100.0},
        {"_id": {"period": "2024-01", "key": "72000000"}, "count": 1, "total": 50.0},
        {"_id": {"period": "2024-01", "key": "33000000"}, "count": 2, "total": 10.0},
        {"_id": {"period": "2024-02", "key": "90000000"}, "count": 1, "total": 5.0},
    ]
    out = shape_timeseries(rows, F, "month", "cpv_division", 2)
    assert [s["key"] for s in out["series"]] == ["45000000", "72000000", "other"]
    other = out["series"][-1]
    assert other["label"] == "Ostatné"
    assert other["points"][0]["total_value"] == 10.0 and other["points"][1]["total_value"] == 5.0
    # points stay the grand total across all keys
    assert out["points"][0]["total_value"] == 160.0
    assert out["points"][0]["contract_count"] == 4
    # every series is zero-filled over the same periods
    assert all(len(s["points"]) == 6 for s in out["series"])


def test_split_by_source_labels_are_the_source_names():
    rows = [{"_id": {"period": "2024-01", "key": "crz"}, "count": 1, "total": 1.0}]
    out = shape_timeseries(rows, F, "month", "source", 5)
    assert out["series"][0]["key"] == "crz" and out["series"][0]["label"] == "crz"
    assert all(s["key"] != "other" for s in out["series"])  # nothing folded, no empty bucket


def _top_rows():
    return [
        {
            "total": [{"count": 10, "total": 1000.0}],
            "items": [
                {"_id": "A", "name": "Alpha", "count": 3, "total": 500.0},
                {"_id": "B", "name": None, "count": 2, "total": 300.0},
            ],
        }
    ]


def test_shape_top_shares_and_other_bucket_sum_to_100():
    out = shape_top(_top_rows(), "supplier", "total_value", 10)
    assert out["total"] == {"total_value": 1000.0, "contract_count": 10}
    assert out["items"][0] == {
        "key": "A",
        "label": "Alpha",
        "ico": "A",
        "total_value": 500.0,
        "contract_count": 3,
        "share_pct": 50.0,
    }
    assert out["items"][1]["label"] == "B"  # unnamed entity falls back to its ico
    assert out["other"] == {"total_value": 200.0, "contract_count": 5, "share_pct": 20.0}
    total_share = sum(i["share_pct"] for i in out["items"]) + out["other"]["share_pct"]
    assert total_share == pytest.approx(100.0, abs=0.2)


def test_shape_top_cpv_division_has_no_ico_and_a_label():
    rows = [
        {
            "total": [{"count": 2, "total": 100.0}],
            "items": [{"_id": "45000000", "count": 2, "total": 100.0}],
        }
    ]
    out = shape_top(rows, "cpv_division", "total_value", 10)
    item = out["items"][0]
    assert item["ico"] is None and item["key"] == "45000000"
    assert item["label"] and item["label"] != ""
    assert out["other"]["share_pct"] == 0.0


def test_shape_top_count_metric_shares_by_count():
    out = shape_top(_top_rows(), "supplier", "contract_count", 10)
    assert out["metric"] == "contract_count"
    assert out["items"][0]["share_pct"] == 30.0


def test_shape_top_never_reports_negative_other_for_multi_supplier_overlap():
    rows = [
        {
            "total": [{"count": 1, "total": 100.0}],
            "items": [
                {"_id": "A", "name": "A", "count": 1, "total": 100.0},
                {"_id": "B", "name": "B", "count": 1, "total": 100.0},
            ],
        }
    ]
    out = shape_top(rows, "supplier", "total_value", 10)
    assert out["other"]["total_value"] == 0.0
    assert out["other"]["contract_count"] == 0
    assert out["other"]["share_pct"] == 0.0


def test_shape_top_empty():
    out = shape_top([{"total": [], "items": []}], "procurer", "total_value", 10)
    assert out["items"] == [] and out["total"] == {"total_value": 0.0, "contract_count": 0}


def test_shape_concentration_computes_hhi_cr_and_cumulative_shares():
    rows = [
        {
            "totals": [{"total": 100.0, "sumsq": 50.0**2 + 30.0**2 + 20.0**2, "n": 3}],
            "top": [
                {"_id": "A", "name": "Alpha", "total": 50.0},
                {"_id": "B", "name": "Beta", "total": 30.0},
                {"_id": "C", "name": None, "total": 20.0},
            ],
        }
    ]
    out = shape_concentration(rows, "supplier")
    assert out["hhi"] == pytest.approx(3800.0)
    assert out["hhi_band"] == "high"
    assert out["cr4_pct"] == 100.0 and out["cr10_pct"] == 100.0
    assert out["entity_count"] == 3 and out["total_value"] == 100.0
    assert [t["cumulative_pct"] for t in out["top"]] == [50.0, 80.0, 100.0]
    assert out["top"][2]["name"] == "C"
    assert out["top"][0]["ico"] == "A"


def test_shape_concentration_empty_is_low_zero():
    out = shape_concentration([{"totals": [], "top": []}], "procurer")
    assert out["hhi"] == 0 and out["hhi_band"] == "low"
    assert out["entity_count"] == 0 and out["top"] == []
    assert out["dimension"] == "procurer"


def test_shape_cpv_sorts_by_value_and_computes_shares():
    rows = [
        {"_id": "72000000", "count": 1, "total": 25.0},
        {"_id": "45000000", "count": 3, "total": 75.0},
        {"_id": "00000000", "count": 1, "total": 0.0},
    ]
    out = shape_cpv(rows, "division")
    assert out["level"] == "division"
    assert out["total_value"] == 100.0 and out["contract_count"] == 5
    assert [i["cpv_code"] for i in out["items"]] == ["45000000", "72000000", "00000000"]
    assert out["items"][0]["prefix"] == "45" and out["items"][0]["share_pct"] == 75.0
    assert out["items"][2]["label_sk"] == "Bez CPV"
    assert sum(i["share_pct"] for i in out["items"]) == pytest.approx(100.0, abs=0.2)


def test_shape_cpv_group_level_falls_back_to_code_label():
    out = shape_cpv([{"_id": "45200000", "count": 1, "total": 1.0}], "group")
    assert out["items"][0]["prefix"] == "452"
    assert out["items"][0]["label_sk"]  # label or the code itself, never empty


NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def test_shape_coverage_lists_all_five_sources_with_status_and_quality():
    sources = [
        {
            "_id": "crz",
            "notices_total": 10,
            "contract_awards": 8,
            "last_publication": "2026-10-18",
            "last_ingested": "2026-10-19T08:00:00",
            "with_value": 4,
            "with_cpv": 8,
            "with_supplier": 2,
            "with_procurer": 8,
        },
        {
            "_id": "vestnik",
            "notices_total": 5,
            "contract_awards": 5,
            "last_publication": "2026-09-01",
            "last_ingested": "2026-09-01T08:00:00",
            "with_value": 5,
            "with_cpv": 5,
            "with_supplier": 5,
            "with_procurer": 5,
        },
    ]
    monthly = [{"_id": {"period": "2026-10", "source": "crz"}, "count": 7}]
    out = shape_coverage(sources, monthly, 12, 5, NOW)

    assert [s["source"] for s in out["sources"]] == ["vestnik", "crz", "ted", "uvo", "itms"]
    by = {s["source"]: s for s in out["sources"]}
    assert by["crz"]["status"] == "healthy"
    assert by["crz"]["age_seconds"] == pytest.approx(4 * 3600)
    assert by["crz"]["expected_cadence_seconds"] == 3600
    assert by["crz"]["quality"] == {
        "with_value_pct": 50.0,
        "with_cpv_pct": 100.0,
        "with_supplier_ico_pct": 25.0,
        "with_procurer_ico_pct": 100.0,
    }
    assert by["vestnik"]["status"] == "stale"
    assert by["ted"]["status"] == "unknown" and by["ted"]["notices_total"] == 0
    assert by["ted"]["last_ingested_at"] is None
    assert by["uvo"]["status"] == "legacy" and by["uvo"]["expected_cadence_seconds"] is None
    assert out["canonical"] == {"notices_with_canonical_id": 12, "match_groups": 5}
    assert out["generated_at"].endswith("Z")


def test_shape_coverage_monthly_is_24_zero_filled_months_ending_now():
    monthly = [{"_id": {"period": "2026-10", "source": "crz"}, "count": 7}]
    out = shape_coverage([], monthly, 0, 0, NOW)
    assert len(out["monthly"]) == 24
    assert out["monthly"][0]["period"] == "2024-11"
    assert out["monthly"][-1] == {
        "period": "2026-10",
        "vestnik": 0,
        "crz": 7,
        "ted": 0,
        "uvo": 0,
        "itms": 0,
    }


def test_shape_coverage_quality_is_zero_when_no_contract_awards():
    sources = [{"_id": "ted", "notices_total": 3, "contract_awards": 0}]
    out = shape_coverage(sources, [], 0, 0, NOW)
    ted = next(s for s in out["sources"] if s["source"] == "ted")
    assert ted["quality"]["with_value_pct"] == 0.0
