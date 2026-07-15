"""Red-flag scoring: pure domain functions + service over fakes, zero containers.

Behaviour reflects the domain/legal review of the scoring engine: flags are
observations with materiality guards (concentration/repeat-pair) and escalation
guards (award clustering), median-based market comparison, and a disclaimer.
"""

import pytest

from uvo_core.domain.scoring import (
    RISK_DISCLAIMER,
    RiskFlag,
    award_clustering,
    is_framework_or_dns,
    market_deviation,
    repeat_pair_share,
    risk_summary,
    supplier_concentration,
)
from uvo_core.services.risk import company_risk_profile
from uvo_core.testing import InMemoryCompanyAnalytics

# --- supplier_concentration --------------------------------------------------


def test_supplier_concentration_single_supplier_informational():
    # One vendor at low value: HHI is 1.0 but below the materiality guard, so the
    # flag reports the number without triggering (a thin market isn't a signal).
    flag = supplier_concentration([{"ico": "S1", "name": "Sole", "total_value": 1000.0}])
    assert flag.evidence["hhi"] == 1.0
    assert flag.severity == "informational"
    assert flag.triggered is False
    assert flag.score == 0.0
    assert flag.evidence["top_supplier"]["ico"] == "S1"


def test_supplier_concentration_triggers_when_material():
    # 5+ suppliers, material value, one dominant → genuine concentration.
    rows = [{"ico": "S1", "total_value": 500_000.0}] + [
        {"ico": f"S{i}", "total_value": 25_000.0} for i in range(2, 6)
    ]
    flag = supplier_concentration(rows)
    assert flag.evidence["supplier_count"] == 5
    assert flag.evidence["total_value"] == 600_000.0
    assert flag.triggered is True
    assert flag.severity == "high"
    assert flag.score > 0


def test_supplier_concentration_moderate_band_not_triggered():
    # 5 equal suppliers at material value → HHI 0.20, inside the moderate band.
    flag = supplier_concentration([{"total_value": 40_000.0} for _ in range(5)])
    assert flag.evidence["hhi"] == pytest.approx(0.2)
    assert flag.severity == "moderate"
    assert flag.triggered is False
    assert flag.score == pytest.approx(20.0)


def test_supplier_concentration_high_hhi_below_supplier_guard_is_informational():
    # High HHI + material value but only 3 suppliers → guard not met.
    rows = [
        {"ico": "S1", "total_value": 400_000.0},
        {"ico": "S2", "total_value": 50_000.0},
        {"ico": "S3", "total_value": 50_000.0},
    ]
    flag = supplier_concentration(rows)
    assert flag.evidence["hhi"] >= 0.25
    assert flag.triggered is False
    assert flag.severity == "informational"
    assert flag.score == 0.0


def test_supplier_concentration_empty():
    flag = supplier_concentration([])
    assert flag.evidence["hhi"] == 0.0
    assert flag.severity == "informational"
    assert flag.triggered is False
    assert flag.evidence["top_supplier"] is None


def test_supplier_concentration_accepts_graph_shape():
    flag = supplier_concentration(
        [
            {"supplier_ico": "S1", "supplier_name": "A", "total_value": 900.0},
            {"supplier_ico": "S2", "supplier_name": "B", "total_value": 100.0},
        ]
    )
    assert flag.evidence["top_supplier"]["ico"] == "S1"
    assert flag.evidence["hhi"] == pytest.approx(0.82)
    assert flag.triggered is False  # 2 suppliers, immaterial value


# --- repeat_pair_share -------------------------------------------------------


def test_repeat_pair_single_counterparty_informational():
    # One counterparty is definitionally concentrated but below the guard.
    flag = repeat_pair_share([{"ico": "C1", "total_value": 1000.0, "contract_count": 3}])
    assert flag.triggered is False
    assert flag.severity == "informational"
    assert flag.score == 0.0
    assert flag.evidence["top_counterparty"]["value_share"] == 1.0


def test_repeat_pair_majority_triggers_moderate():
    flag = repeat_pair_share(
        [
            {"ico": "C1", "total_value": 60_000.0, "contract_count": 3, "role": "supplier"},
            {"ico": "C2", "total_value": 20_000.0, "contract_count": 2, "role": "supplier"},
            {"ico": "C3", "total_value": 20_000.0, "contract_count": 1, "role": "supplier"},
        ]
    )
    assert flag.triggered is True
    assert flag.severity == "moderate"
    assert flag.score == 60.0
    assert flag.evidence["subject_role"] == "procurer"


def test_repeat_pair_high_share_triggers_high():
    flag = repeat_pair_share(
        [
            {"ico": "C1", "total_value": 80_000.0, "contract_count": 3, "role": "procurer"},
            {"ico": "C2", "total_value": 10_000.0, "contract_count": 1, "role": "procurer"},
            {"ico": "C3", "total_value": 10_000.0, "contract_count": 1, "role": "procurer"},
        ]
    )
    assert flag.triggered is True
    assert flag.severity == "high"
    assert flag.score == 80.0
    # Top counterparty is a procurer → the subject sits in the supplier role.
    assert flag.evidence["subject_role"] == "supplier"


def test_repeat_pair_balanced_not_triggered():
    flag = repeat_pair_share(
        [
            {"ico": "C1", "total_value": 30_000.0, "contract_count": 1, "role": "supplier"},
            {"ico": "C2", "total_value": 30_000.0, "contract_count": 1, "role": "supplier"},
            {"ico": "C3", "total_value": 40_000.0, "contract_count": 1, "role": "supplier"},
        ]
    )
    assert flag.triggered is False
    assert flag.severity == "low"


def test_repeat_pair_below_materiality_guard_informational():
    # Dominant share but only 2 counterparties → guard not met.
    flag = repeat_pair_share(
        [
            {"ico": "C1", "total_value": 100_000.0, "contract_count": 3, "role": "supplier"},
            {"ico": "C2", "total_value": 50_000.0, "contract_count": 1, "role": "supplier"},
        ]
    )
    assert flag.triggered is False
    assert flag.severity == "informational"
    assert flag.score == 0.0


def test_repeat_pair_empty_and_zero_value():
    assert repeat_pair_share([]).triggered is False
    assert repeat_pair_share([{"total_value": 0.0, "contract_count": 1}]).score == 0.0


# --- market_deviation --------------------------------------------------------


def test_market_deviation_flags_outlier():
    company = [{"_id": "72000000", "count": 2, "total": 2000.0}]  # avg 1000
    market = [{"_id": "72000000", "count": 20, "total": 4000.0, "median": 200.0}]
    flag = market_deviation(company, market)
    assert flag.triggered is True
    assert flag.evidence["worst"]["multiple"] == 5.0
    assert flag.evidence["worst"]["market_baseline"] == 200.0
    assert flag.severity == "moderate"
    assert flag.score == pytest.approx(83.3, abs=0.1)


def test_market_deviation_high_severity():
    company = [{"_id": "72000000", "count": 1, "total": 1200.0}]  # avg 1200
    market = [{"_id": "72000000", "count": 20, "total": 4000.0, "median": 200.0}]  # 6×
    flag = market_deviation(company, market)
    assert flag.severity == "high"
    assert flag.score == 100.0


def test_market_deviation_thin_market_ignored():
    company = [{"_id": "72000000", "count": 1, "total": 5000.0}]
    market = [{"_id": "72000000", "count": 10, "total": 600.0, "median": 60.0}]  # <20 sample
    flag = market_deviation(company, market)
    assert flag.triggered is False
    assert flag.evidence["worst"] is None


def test_market_deviation_median_is_robust_to_outliers():
    # A single huge contract drags the mean (500k) but not the median (100).
    company = [{"_id": "72000000", "count": 1, "total": 1000.0}]  # avg 1000
    market = [{"_id": "72000000", "count": 20, "total": 10_000_000.0, "median": 100.0}]
    flag = market_deviation(company, market)
    assert flag.triggered is True  # 1000 / 100 = 10× on the median
    assert flag.evidence["worst"]["market_baseline"] == 100.0


def test_market_deviation_mean_fallback_when_no_median():
    company = [{"_id": "72000000", "count": 1, "total": 1000.0}]  # avg 1000
    market = [{"_id": "72000000", "count": 20, "total": 4000.0}]  # no median → mean 200
    flag = market_deviation(company, market)
    assert flag.triggered is True
    assert flag.evidence["worst"]["market_baseline"] == 200.0


def test_market_deviation_empty_cpv():
    flag = market_deviation(
        [], [{"_id": "72000000", "count": 20, "total": 2000.0, "median": 100.0}]
    )
    assert flag.triggered is False
    assert flag.evidence["compared_cpv_count"] == 0


# --- award_clustering --------------------------------------------------------


def _awards(dates, cpv="72000000", value=1000.0):
    return [{"date": d, "cpv_code": cpv, "value": value} for d in dates]


def test_award_clustering_detects_burst():
    flag = award_clustering(_awards(["2024-01-01", "2024-01-05", "2024-01-10", "2024-01-20"]))
    assert flag.evidence["max_awards_in_window"] == 4
    assert flag.triggered is True
    assert flag.severity == "moderate"
    assert flag.score == 60.0
    assert flag.evidence["window"] == ("2024-01-01", "2024-01-20")
    assert flag.evidence["shared_cpv_division"] == "72"


def test_award_clustering_spread_out_not_triggered():
    flag = award_clustering(_awards(["2024-01-01", "2024-03-01", "2024-06-01"]))
    assert flag.evidence["max_awards_in_window"] == 1
    assert flag.triggered is False
    assert flag.severity == "low"


def test_award_clustering_empty_and_single():
    assert award_clustering([]).evidence["max_awards_in_window"] == 0
    assert award_clustering([]).triggered is False
    assert award_clustering(_awards(["2024-01-01"])).evidence["max_awards_in_window"] == 1


def test_award_clustering_high_severity_by_count():
    dates = [f"2024-01-{day:02d}" for day in range(1, 9)]  # 8 within 30 days
    flag = award_clustering(_awards(dates))
    assert flag.severity == "high"
    assert flag.score == 100.0


def test_award_clustering_mixed_cpv_division_not_escalated():
    # Guard A: 4 awards in-window but across different CPV divisions → neutral
    # "award frequency", does not trigger.
    awards = [
        {"date": "2024-01-01", "cpv_code": "72000000", "value": 1000.0},
        {"date": "2024-01-05", "cpv_code": "45000000", "value": 1000.0},
        {"date": "2024-01-10", "cpv_code": "30000000", "value": 1000.0},
        {"date": "2024-01-20", "cpv_code": "90000000", "value": 1000.0},
    ]
    flag = award_clustering(awards)
    assert flag.evidence["max_awards_in_window"] == 4
    assert flag.triggered is False
    assert flag.severity == "informational"
    assert flag.evidence["shared_cpv_division"] is None


def test_award_clustering_near_goods_ceiling_high_severity():
    # Guard B: shared division, summed value within [0.7, 1.0]× of the €180k
    # goods/services ceiling → escalated to high.
    flag = award_clustering(
        _awards(
            ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"],
            cpv="30000000",
            value=35_000.0,  # 4 × 35k = 140k ∈ [126k, 180k]
        )
    )
    assert flag.triggered is True
    assert flag.severity == "high"
    assert flag.evidence["approaches_low_value_ceiling"] is True


def test_award_clustering_near_works_ceiling_high_severity():
    # Division 45 → the €300k works ceiling; 4 × 60k = 240k ∈ [210k, 300k].
    flag = award_clustering(
        _awards(
            ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"],
            cpv="45000000",
            value=60_000.0,
        )
    )
    assert flag.triggered is True
    assert flag.severity == "high"
    assert flag.evidence["approaches_low_value_ceiling"] is True


def test_award_clustering_value_above_ceiling_not_escalated():
    # Summed value above the ceiling → outside the low-value regime, so it is a
    # normal cluster (moderate), not a splitting footprint.
    flag = award_clustering(
        _awards(
            ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"],
            cpv="30000000",
            value=100_000.0,  # 400k > 180k ceiling
        )
    )
    assert flag.triggered is True
    assert flag.severity == "moderate"
    assert flag.evidence["approaches_low_value_ceiling"] is False


# --- is_framework_or_dns -----------------------------------------------------


def test_is_framework_or_dns():
    assert is_framework_or_dns("Rámcová dohoda") is True
    assert is_framework_or_dns("Dynamický nákupný systém") is True
    assert is_framework_or_dns("Verejná súťaž") is False
    assert is_framework_or_dns(None) is False


# --- risk_summary ------------------------------------------------------------


def _flag(code: str, score: float, evidence: dict | None = None) -> RiskFlag:
    return RiskFlag(
        code=code,
        triggered=score >= 50,
        severity="high",
        score=score,
        summary="",
        evidence=evidence or {},
    )


def test_risk_summary_weighted_blend_all_max():
    flags = [
        _flag("supplier_concentration", 100.0),
        _flag("repeat_pair_share", 100.0),
        _flag("market_deviation", 100.0),
        _flag("award_clustering", 100.0),
    ]
    out = risk_summary(flags)
    assert out["risk_score"] == 100.0
    assert out["risk_band"] == "high"
    assert set(out["triggered_flags"]) == {
        "supplier_concentration",
        "repeat_pair_share",
        "market_deviation",
        "award_clustering",
    }


def test_risk_summary_low_when_zero():
    flags = [_flag("supplier_concentration", 0.0), _flag("repeat_pair_share", 0.0)]
    out = risk_summary(flags)
    assert out["risk_score"] == 0.0
    assert out["risk_band"] == "low"
    assert out["triggered_flags"] == []


def test_risk_summary_single_flag_weighted():
    # Only concentration at 50 → 0.30*50 / 0.30 = 50 (weighted average).
    out = risk_summary([_flag("supplier_concentration", 50.0)])
    assert out["risk_score"] == 50.0
    assert out["risk_band"] == "moderate"


def test_risk_summary_downweights_supplier_side_repeat_pair():
    base = _flag("supplier_concentration", 0.0)
    as_procurer = _flag("repeat_pair_share", 100.0, {"subject_role": "procurer"})
    as_supplier = _flag("repeat_pair_share", 100.0, {"subject_role": "supplier"})
    procurer_score = risk_summary([base, as_procurer])["risk_score"]
    supplier_score = risk_summary([base, as_supplier])["risk_score"]
    assert supplier_score < procurer_score


# --- service over the in-memory fake ----------------------------------------


def _award(procurer, supplier, value, date, cpv="72000000", procedure_type=None):
    return {
        "notice_type": "contract_award",
        "procurer": {"ico": procurer, "name": procurer},
        "awards": [{"supplier": {"ico": supplier, "name": supplier}}],
        "final_value": value,
        "cpv_code": cpv,
        "award_date": date,
        "procedure_type": procedure_type,
    }


async def test_service_single_supplier_not_flagged_as_high_risk():
    # A single supplier is definitionally concentrated but, per the review, not a
    # risk signal on its own — only the (dense, same-CPV) award cluster fires.
    notices = [_award("P1", "S1", 1000.0, f"2024-01-{day:02d}") for day in (1, 3, 6, 9, 12)]
    analytics = InMemoryCompanyAnalytics(notices)
    profile = await company_risk_profile("P1", analytics, graph=None)

    assert profile["ico"] == "P1"
    assert len(profile["flags"]) == 4
    by_code = {f["code"]: f for f in profile["flags"]}
    assert by_code["supplier_concentration"]["triggered"] is False
    assert by_code["repeat_pair_share"]["triggered"] is False
    assert by_code["award_clustering"]["triggered"] is True
    assert profile["risk_band"] == "low"
    assert profile["disclaimer"] == RISK_DISCLAIMER


async def test_service_genuine_multi_signal_high_risk():
    # 5+ suppliers, one dominant, plus a dense same-CPV near-ceiling cluster to it.
    dominant = [
        _award("P1", "S1", 40_000.0, d, cpv="30000000")
        for d in ("2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22")
    ]
    tail = [_award("P1", f"S{i}", 5_000.0, "2024-02-01", cpv="30000000") for i in range(2, 7)]
    analytics = InMemoryCompanyAnalytics(dominant + tail)
    profile = await company_risk_profile("P1", analytics, graph=None)

    by_code = {f["code"]: f for f in profile["flags"]}
    assert by_code["supplier_concentration"]["triggered"] is True
    assert by_code["repeat_pair_share"]["triggered"] is True
    assert by_code["award_clustering"]["triggered"] is True
    assert by_code["award_clustering"]["evidence"]["approaches_low_value_ceiling"] is True
    assert profile["risk_band"] in {"moderate", "high"}


async def test_service_framework_excluded_from_clustering():
    # The same dense cluster, but marked as framework call-offs → excluded.
    notices = [
        _award("P1", "S1", 40_000.0, d, cpv="30000000", procedure_type="Rámcová dohoda")
        for d in ("2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22")
    ]
    analytics = InMemoryCompanyAnalytics(notices)
    profile = await company_risk_profile("P1", analytics, graph=None)
    by_code = {f["code"]: f for f in profile["flags"]}
    assert by_code["award_clustering"]["triggered"] is False


async def test_service_no_contracts_is_low_risk():
    analytics = InMemoryCompanyAnalytics([])
    profile = await company_risk_profile("UNKNOWN", analytics, graph=None)
    assert profile["risk_score"] == 0.0
    assert profile["risk_band"] == "low"
    assert all(f["triggered"] is False for f in profile["flags"])


async def test_service_single_contract_does_not_crash():
    analytics = InMemoryCompanyAnalytics([_award("P1", "S1", 1000.0, "2024-01-01")])
    profile = await company_risk_profile("P1", analytics, graph=None)
    assert len(profile["flags"]) == 4
    by_code = {f["code"]: f for f in profile["flags"]}
    # A single award to one supplier is definitionally full concentration...
    assert by_code["supplier_concentration"]["evidence"]["hhi"] == 1.0
    # ...but not material, so it does not trigger.
    assert by_code["supplier_concentration"]["triggered"] is False


async def test_service_empty_cpv_no_market_flag():
    notices = [_award("P1", "S1", 1000.0, f"2024-0{m}-01", cpv=None) for m in (1, 2, 3)]
    analytics = InMemoryCompanyAnalytics(notices)
    profile = await company_risk_profile("P1", analytics, graph=None)
    by_code = {f["code"]: f for f in profile["flags"]}
    assert by_code["market_deviation"]["triggered"] is False


class _FakeGraphStore:
    """Minimal GraphStore fake exercising the graph-sourced supplier rows path."""

    def __init__(self, top_suppliers):
        self._top = top_suppliers

    async def supplier_concentration(self, procurer_ico, top_n=10):
        return {"procurer_ico": procurer_ico, "top_suppliers": self._top}


async def test_service_uses_graph_when_present():
    notices = [_award("P1", "S1", 1000.0, "2024-01-01")]
    analytics = InMemoryCompanyAnalytics(notices)
    graph = _FakeGraphStore(
        [
            {"supplier_ico": "S1", "supplier_name": "A", "total_value": 500.0, "contract_count": 1},
            {"supplier_ico": "S2", "supplier_name": "B", "total_value": 500.0, "contract_count": 1},
        ]
    )
    profile = await company_risk_profile("P1", analytics, graph=graph)
    by_code = {f["code"]: f for f in profile["flags"]}
    # Two-way even split from the graph → HHI 0.5, not the fake analytics single row.
    assert by_code["supplier_concentration"]["evidence"]["hhi"] == pytest.approx(0.5)
