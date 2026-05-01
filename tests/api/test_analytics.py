# tests/api/test_analytics.py
"""Unit tests for analytics endpoints (period-summary, executive-summary)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


def _make_db(find_one_result, aggregate_results: list[list[dict]]):
    """Return a mock Motor db where find_one and repeated aggregate calls are wired up."""
    mock_db = MagicMock()

    # find_one is async
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=find_one_result)

    # aggregate returns a cursor whose to_list is async
    cursors = []
    for result in aggregate_results:
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=result)
        cursors.append(cursor)
    mock_db.__getitem__.return_value.aggregate = MagicMock(side_effect=cursors)

    return mock_db


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PROCURER_ENTITY = {"ico": "12345678", "name": "Ministry of Finance"}
SUPPLIER_ENTITY = {"ico": "87654321", "name": "Tech Corp"}


def _make_facet_result(
    total_value=1_000_000.0,
    contract_count=5,
    value_with_amount=5,
    counterparties=None,
    cpv_buckets=None,
    monthly=None,
) -> list[dict]:
    if counterparties is None:
        counterparties = [
            {"_id": "AAA", "name": "Alpha", "total_value": 600_000.0, "contract_count": 3},
            {"_id": "BBB", "name": "Beta", "total_value": 400_000.0, "contract_count": 2},
        ]
    if cpv_buckets is None:
        cpv_buckets = [
            {"_id": "72000000", "total_value": 800_000.0, "contract_count": 4},
            {"_id": "45000000", "total_value": 200_000.0, "contract_count": 1},
        ]
    if monthly is None:
        monthly = [
            {"_id": "2024-01", "total_value": 500_000.0, "contract_count": 2},
            {"_id": "2024-02", "total_value": 500_000.0, "contract_count": 3},
        ]
    return [
        {
            "totals": [
                {
                    "total_value": total_value,
                    "contract_count": contract_count,
                    "value_with_amount": value_with_amount,
                }
            ],
            "counterparties": counterparties,
            "cpv_buckets": cpv_buckets,
            "monthly": monthly,
        }
    ]


EMPTY_FACET = [
    {
        "totals": [],
        "counterparties": [],
        "cpv_buckets": [],
        "monthly": [],
    }
]


# ---------------------------------------------------------------------------
# Procurer period-summary
# ---------------------------------------------------------------------------

class TestProcurerPeriodSummary:
    def test_happy_path(self, client):
        cur = _make_facet_result()
        prior = _make_facet_result(total_value=800_000.0, contract_count=4, value_with_amount=4)
        db = _make_db(PROCURER_ENTITY, [cur, prior])

        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/12345678/period-summary")

        assert r.status_code == 200
        body = r.json()
        assert body["ico"] == "12345678"
        assert body["name"] == "Ministry of Finance"
        assert body["entity_type"] == "procurer"
        assert body["kpis"]["total_value"] == pytest.approx(1_000_000.0)
        assert body["kpis"]["contract_count"] == 5
        assert body["kpis"]["avg_value"] == pytest.approx(200_000.0)
        assert body["kpis"]["value_coverage"] == pytest.approx(1.0)
        assert body["kpis"]["unique_counterparties"] == 2
        # delta total_value_pct: (1M - 800k) / 800k * 100 = 25%
        assert body["kpis"]["deltas"]["total_value_pct"] == pytest.approx(25.0)
        assert len(body["monthly_spend"]) == 2
        assert body["monthly_spend"][0]["month"] == "2024-01"
        assert len(body["top_counterparties"]) == 2
        assert body["top_counterparties"][0]["ico"] == "AAA"
        assert body["top_counterparties"][0]["share_pct"] == pytest.approx(0.6)
        assert len(body["cpv_breakdown"]) == 2
        # concentration: shares [0.6, 0.4] → HHI = 0.36 + 0.16 = 0.52
        assert body["concentration"]["hhi"] == pytest.approx(0.52)
        assert body["concentration"]["top1_share_pct"] == pytest.approx(0.6)
        assert body["concentration"]["top3_share_pct"] == pytest.approx(1.0)

    def test_empty_period(self, client):
        db = _make_db(PROCURER_ENTITY, [EMPTY_FACET, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/12345678/period-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["kpis"]["total_value"] == 0.0
        assert body["kpis"]["contract_count"] == 0
        assert body["kpis"]["avg_value"] == 0.0
        assert body["kpis"]["value_coverage"] == 0.0
        assert body["kpis"]["deltas"]["total_value_pct"] is None
        assert body["kpis"]["deltas"]["contract_count_pct"] is None
        assert body["concentration"]["hhi"] == 0.0
        assert body["monthly_spend"] == []
        assert body["top_counterparties"] == []
        assert body["cpv_breakdown"] == []

    def test_400_inverted_dates(self, client):
        db = _make_db(PROCURER_ENTITY, [])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/12345678/period-summary?date_from=2024-06-01&date_to=2024-01-01")
        assert r.status_code == 400

    def test_404_unknown_ico(self, client):
        db = _make_db(None, [])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/00000000/period-summary")
        assert r.status_code == 404

    def test_cpv_other_row(self, client):
        """More than 10 CPV buckets → an 'other' row is appended."""
        many_cpv = [{"_id": f"{i:08d}", "total_value": 100.0, "contract_count": 1} for i in range(15)]
        cur = _make_facet_result(total_value=1500.0, contract_count=15, value_with_amount=15, cpv_buckets=many_cpv)
        db = _make_db(PROCURER_ENTITY, [cur, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/12345678/period-summary")
        assert r.status_code == 200
        codes = [row["cpv_code"] for row in r.json()["cpv_breakdown"]]
        assert "other" in codes
        assert len(codes) == 11


# ---------------------------------------------------------------------------
# Supplier period-summary
# ---------------------------------------------------------------------------

class TestSupplierPeriodSummary:
    def test_happy_path(self, client):
        cur = _make_facet_result()
        prior = _make_facet_result(total_value=500_000.0, contract_count=3, value_with_amount=3)
        db = _make_db(SUPPLIER_ENTITY, [cur, prior])

        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/suppliers/87654321/period-summary")

        assert r.status_code == 200
        body = r.json()
        assert body["entity_type"] == "supplier"
        assert body["ico"] == "87654321"
        assert body["kpis"]["total_value"] == pytest.approx(1_000_000.0)

    def test_empty_period(self, client):
        db = _make_db(SUPPLIER_ENTITY, [EMPTY_FACET, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/suppliers/87654321/period-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["kpis"]["contract_count"] == 0
        assert body["kpis"]["deltas"]["total_value_pct"] is None

    def test_400_inverted_dates(self, client):
        db = _make_db(SUPPLIER_ENTITY, [])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/suppliers/87654321/period-summary?date_from=2025-01-01&date_to=2024-01-01")
        assert r.status_code == 400

    def test_404_unknown_ico(self, client):
        db = _make_db(None, [])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/suppliers/00000000/period-summary")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# HHI edge cases
# ---------------------------------------------------------------------------

class TestHhi:
    def test_single_supplier_hhi_is_one(self, client):
        cur = _make_facet_result(
            counterparties=[
                {"_id": "ONLY", "name": "Solo Corp", "total_value": 1_000_000.0, "contract_count": 5}
            ]
        )
        db = _make_db(PROCURER_ENTITY, [cur, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/12345678/period-summary")
        assert r.status_code == 200
        assert r.json()["concentration"]["hhi"] == pytest.approx(1.0)

    def test_no_contracts_hhi_is_zero(self, client):
        db = _make_db(PROCURER_ENTITY, [EMPTY_FACET, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/procurers/12345678/period-summary")
        assert r.status_code == 200
        assert r.json()["concentration"]["hhi"] == 0.0


# ---------------------------------------------------------------------------
# Executive summary — anomaly triggers
# ---------------------------------------------------------------------------

class TestExecutiveSummary:
    def test_happy_path_no_anomalies(self, client):
        cur = _make_facet_result()
        prior = _make_facet_result()
        db = _make_db(PROCURER_ENTITY, [cur, prior])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary")
        assert r.status_code == 200
        body = r.json()
        assert "anomalies" in body
        # top1_share_pct = 0.6 < 0.7 and delta = 25% < 50% → no anomalies
        anomaly_codes = [a["code"] for a in body["anomalies"]]
        assert "single_counterparty_dominance" not in anomaly_codes
        assert "value_spike_vs_prior" not in anomaly_codes

    def test_anomaly_single_counterparty_dominance(self, client):
        cur = _make_facet_result(
            counterparties=[
                {"_id": "AAA", "name": "Alpha", "total_value": 900_000.0, "contract_count": 9},
                {"_id": "BBB", "name": "Beta", "total_value": 100_000.0, "contract_count": 1},
            ]
        )
        prior = _make_facet_result()
        db = _make_db(PROCURER_ENTITY, [cur, prior])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary")
        assert r.status_code == 200
        codes = [a["code"] for a in r.json()["anomalies"]]
        assert "single_counterparty_dominance" in codes

    def test_anomaly_value_spike_vs_prior(self, client):
        cur = _make_facet_result(total_value=1_600_000.0, contract_count=8, value_with_amount=8)
        prior = _make_facet_result(total_value=1_000_000.0, contract_count=5, value_with_amount=5)
        db = _make_db(PROCURER_ENTITY, [cur, prior])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary")
        assert r.status_code == 200
        codes = [a["code"] for a in r.json()["anomalies"]]
        assert "value_spike_vs_prior" in codes

    def test_anomaly_hhi_jump(self, client):
        # current: one dominant supplier (HHI≈1.0)
        cur = _make_facet_result(
            counterparties=[
                {"_id": "AAA", "name": "Alpha", "total_value": 990_000.0, "contract_count": 9},
                {"_id": "BBB", "name": "Beta", "total_value": 10_000.0, "contract_count": 1},
            ]
        )
        # prior: balanced (HHI≈0.5)
        prior = _make_facet_result(
            counterparties=[
                {"_id": "AAA", "name": "Alpha", "total_value": 500_000.0, "contract_count": 5},
                {"_id": "BBB", "name": "Beta", "total_value": 500_000.0, "contract_count": 5},
            ]
        )
        db = _make_db(PROCURER_ENTITY, [cur, prior])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary")
        assert r.status_code == 200
        codes = [a["code"] for a in r.json()["anomalies"]]
        assert "hhi_jump" in codes

    def test_empty_period_no_anomalies(self, client):
        db = _make_db(PROCURER_ENTITY, [EMPTY_FACET, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary")
        assert r.status_code == 200
        assert r.json()["anomalies"] == []

    def test_400_inverted_dates(self, client):
        db = _make_db(PROCURER_ENTITY, [])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary?date_from=2025-01-01&date_to=2024-01-01")
        assert r.status_code == 400

    def test_404_unknown_ico(self, client):
        db = _make_db(None, [])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/00000000/executive-summary")
        assert r.status_code == 404

    def test_supplier_entity_type(self, client):
        cur = _make_facet_result()
        prior = _make_facet_result()
        db = _make_db(SUPPLIER_ENTITY, [cur, prior])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/87654321/executive-summary?entity_type=supplier")
        assert r.status_code == 200
        assert r.json()["entity_type"] == "supplier"

    def test_no_spike_when_prior_zero(self, client):
        """value_spike rule must be skipped (delta=None) when prior period is empty."""
        cur = _make_facet_result(total_value=500_000.0, contract_count=3, value_with_amount=3)
        db = _make_db(PROCURER_ENTITY, [cur, EMPTY_FACET])
        with patch("uvo_api.routers.analytics.get_db", return_value=db):
            r = client.get("/api/companies/12345678/executive-summary")
        assert r.status_code == 200
        codes = [a["code"] for a in r.json()["anomalies"]]
        assert "value_spike_vs_prior" not in codes
