"""Red-flag scoring: pure domain functions + service over fakes, zero containers."""

import pytest

from uvo_core.domain.scoring import (
    RiskFlag,
    award_clustering,
    market_deviation,
    repeat_pair_share,
    risk_summary,
    supplier_concentration,
)
from uvo_core.services.risk import company_risk_profile
from uvo_core.testing import InMemoryCompanyAnalytics

# --- supplier_concentration --------------------------------------------------


def test_supplier_concentration_monopoly():
    flag = supplier_concentration([{"ico": "S1", "name": "Sole", "total_value": 1000.0}])
    assert flag.evidence["hhi"] == 1.0
    assert flag.severity == "high"
    assert flag.triggered is True
    assert flag.score == 100.0
    assert flag.evidence["top_supplier"]["ico"] == "S1"


def test_supplier_concentration_moderate_band_not_triggered():
    # 5 equal suppliers → HHI 0.20, inside the 0.15–0.25 moderate band.
    flag = supplier_concentration([{"total_value": 200.0} for _ in range(5)])
    assert flag.evidence["hhi"] == pytest.approx(0.2)
    assert flag.severity == "moderate"
    assert flag.triggered is False


def test_supplier_concentration_empty():
    flag = supplier_concentration([])
    assert flag.evidence["hhi"] == 0.0
    assert flag.severity == "low"
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


# --- repeat_pair_share -------------------------------------------------------


def test_repeat_pair_single_counterparty():
    flag = repeat_pair_share([{"ico": "C1", "total_value": 1000.0, "contract_count": 3}])
    assert flag.triggered is True
    assert flag.severity == "high"
    assert flag.score == 100.0
    assert flag.evidence["top_counterparty"]["value_share"] == 1.0


def test_repeat_pair_majority_triggers_moderate():
    flag = repeat_pair_share(
        [
            {"ico": "C1", "total_value": 600.0, "contract_count": 3},
            {"ico": "C2", "total_value": 400.0, "contract_count": 2},
        ]
    )
    assert flag.triggered is True
    assert flag.severity == "moderate"
    assert flag.score == 60.0


def test_repeat_pair_balanced_not_triggered():
    flag = repeat_pair_share(
        [
            {"ico": "C1", "total_value": 300.0, "contract_count": 1},
            {"ico": "C2", "total_value": 300.0, "contract_count": 1},
            {"ico": "C3", "total_value": 400.0, "contract_count": 1},
        ]
    )
    assert flag.triggered is False
    assert flag.severity == "low"


def test_repeat_pair_empty_and_zero_value():
    assert repeat_pair_share([]).triggered is False
    assert repeat_pair_share([{"total_value": 0.0, "contract_count": 1}]).score == 0.0


# --- market_deviation --------------------------------------------------------


def test_market_deviation_flags_outlier():
    company = [{"_id": "72000000", "count": 2, "total": 2000.0}]  # avg 1000
    market = [{"_id": "72000000", "count": 10, "total": 2000.0}]  # avg 200
    flag = market_deviation(company, market)
    assert flag.triggered is True
    assert flag.evidence["worst"]["multiple"] == 5.0
    assert flag.severity == "moderate"
    assert flag.score == pytest.approx(83.3, abs=0.1)


def test_market_deviation_high_severity():
    company = [{"_id": "72000000", "count": 1, "total": 1200.0}]  # avg 1200
    market = [{"_id": "72000000", "count": 10, "total": 2000.0}]  # avg 200 → 6×
    flag = market_deviation(company, market)
    assert flag.severity == "high"
    assert flag.score == 100.0


def test_market_deviation_thin_market_ignored():
    company = [{"_id": "72000000", "count": 1, "total": 5000.0}]
    market = [{"_id": "72000000", "count": 3, "total": 600.0}]  # below min sample
    flag = market_deviation(company, market)
    assert flag.triggered is False
    assert flag.evidence["worst"] is None


def test_market_deviation_empty_cpv():
    flag = market_deviation([], [{"_id": "72000000", "count": 10, "total": 2000.0}])
    assert flag.triggered is False
    assert flag.evidence["compared_cpv_count"] == 0


# --- award_clustering --------------------------------------------------------


def test_award_clustering_detects_burst():
    dates = ["2024-01-01", "2024-01-05", "2024-01-10", "2024-01-20"]
    flag = award_clustering(dates)
    assert flag.evidence["max_awards_in_window"] == 4
    assert flag.triggered is True
    assert flag.severity == "moderate"
    assert flag.score == 60.0
    assert flag.evidence["window"] == ("2024-01-01", "2024-01-20")


def test_award_clustering_spread_out_not_triggered():
    flag = award_clustering(["2024-01-01", "2024-03-01", "2024-06-01"])
    assert flag.evidence["max_awards_in_window"] == 1
    assert flag.triggered is False


def test_award_clustering_empty_and_single():
    assert award_clustering([]).evidence["max_awards_in_window"] == 0
    assert award_clustering([]).triggered is False
    assert award_clustering(["2024-01-01"]).evidence["max_awards_in_window"] == 1


def test_award_clustering_high_severity():
    dates = [f"2024-01-{day:02d}" for day in range(1, 9)]  # 8 within 30 days
    flag = award_clustering(dates)
    assert flag.severity == "high"
    assert flag.score == 100.0


# --- risk_summary ------------------------------------------------------------


def _flag(code: str, score: float) -> RiskFlag:
    return RiskFlag(code=code, triggered=score >= 50, severity="high", score=score, summary="")


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


# --- service over the in-memory fake ----------------------------------------


def _award(procurer, supplier, value, date, cpv="72000000"):
    return {
        "notice_type": "contract_award",
        "procurer": {"ico": procurer, "name": procurer},
        "awards": [{"supplier": {"ico": supplier, "name": supplier}}],
        "final_value": value,
        "cpv_code": cpv,
        "award_date": date,
    }


async def test_service_all_one_supplier_high_risk():
    notices = [_award("P1", "S1", 1000.0, f"2024-01-{day:02d}") for day in (1, 3, 6, 9, 12)]
    analytics = InMemoryCompanyAnalytics(notices)
    profile = await company_risk_profile("P1", analytics, graph=None)

    assert profile["ico"] == "P1"
    assert len(profile["flags"]) == 4
    by_code = {f["code"]: f for f in profile["flags"]}
    assert by_code["supplier_concentration"]["triggered"] is True
    assert by_code["repeat_pair_share"]["triggered"] is True
    assert by_code["award_clustering"]["triggered"] is True
    assert profile["risk_band"] in {"moderate", "high"}


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
    # A single award to one supplier is definitionally full concentration.
    by_code = {f["code"]: f for f in profile["flags"]}
    assert by_code["supplier_concentration"]["evidence"]["hhi"] == 1.0


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
