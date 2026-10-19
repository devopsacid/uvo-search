# tests/api/test_procurers.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_PROCURER_RESPONSE = {
    "items": [
        {
            "ico": "12345678",
            "name": "Ministry of Finance",
            "contract_count": 20,
            "total_value": 10000000.0,
        },
    ],
    "total": 1,
}

SAMPLE_CONTRACTS_FOR_PROCURER = {
    "items": [
        {
            "_id": "2001",
            "title": "Cloud Services",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "awards": [{"supplier": {"ico": "87654321", "name": "Tech Corp"}}],
            "final_value": 300000.0,
            "publication_date": "2023-03-10",
            "cpv_code": "72000000",
        }
    ],
    "total": 1,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def test_list_procurers(client):
    with patch(
        "uvo_api.routers.procurers.run_query", new=AsyncMock(return_value=SAMPLE_PROCURER_RESPONSE)
    ):
        response = client.get("/api/procurers")
    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["ico"] == "12345678"
    assert body["data"][0]["name"] == "Ministry of Finance"
    assert body["data"][0]["contract_count"] == 20
    assert body["pagination"]["total"] == 1


PROFILE = {
    "contract_count": 150,
    "total_value": 20_000_000.0,
    "spend_by_year": [
        {"year": 2019, "total_value": 5_000_000.0},
        {"year": 2023, "total_value": 15_000_000.0},
    ],
    "years_active": [2019, 2023],
    "partners": [
        {"ico": "87654321", "name": "Tech Corp", "contract_count": 120, "total_value": 18e6},
        {"ico": "11111111", "name": "Other", "contract_count": 30, "total_value": 2e6},
    ],
    "partner_total_value": 20_000_000.0,
    "partner_count": 2,
    "hhi": 8200.0,
}


def _entity_patches(procurer):
    return (
        patch("uvo_api.routers.procurers.get_db", return_value=MagicMock()),
        patch(
            "uvo_api.routers.procurers.get_entity_by_ico",
            new=AsyncMock(return_value={"supplier": None, "procurer": procurer}),
        ),
        patch("uvo_api.routers.procurers.entity_profile", new=AsyncMock(return_value=PROFILE)),
    )


def test_get_procurer_detail_uses_full_population_aggregates(client):
    p1, p2, p3 = _entity_patches(SAMPLE_PROCURER_RESPONSE["items"][0])
    with (
        p1,
        p2,
        p3,
        patch(
            "uvo_api.routers.procurers.run_query",
            new=AsyncMock(return_value=SAMPLE_CONTRACTS_FOR_PROCURER),
        ),
    ):
        response = client.get("/api/procurers/12345678")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "12345678"
    assert body["contract_count"] == 20
    assert len(body["contracts"]) == 1
    # supplier relations / years come from the aggregation, not the 1 listed contract
    assert [s["ico"] for s in body["top_suppliers"]] == ["87654321", "11111111"]
    assert body["top_suppliers"][0]["contract_count"] == 120
    assert body["years_active"] == [2019, 2023]
    # nested award.supplier shape is read for the listed rows
    assert body["contracts"][0]["supplier_ico"] == "87654321"


def test_get_procurer_summary_uses_profile_and_skips_contract_search(client):
    p1, p2, p3 = _entity_patches(SAMPLE_PROCURER_RESPONSE["items"][0])
    run = AsyncMock()
    with p1, p2, p3, patch("uvo_api.routers.procurers.run_query", new=run):
        response = client.get("/api/procurers/12345678/summary")
    assert response.status_code == 200
    body = response.json()
    assert [y["year"] for y in body["spend_by_year"]] == [2019, 2023]
    run.assert_not_called()


def test_get_procurer_summary_falls_back_to_profile_totals(client):
    p1, p2, p3 = _entity_patches({"ico": "12345678", "name": "No stats"})
    with p1, p2, p3:
        response = client.get("/api/procurers/12345678/summary")
    body = response.json()
    assert body["contract_count"] == 150
    assert body["total_spend"] == 20_000_000.0


def test_get_procurer_not_found(client):
    p1, p2, p3 = _entity_patches(None)
    with p1, p2, p3:
        response = client.get("/api/procurers/00000000")
    assert response.status_code == 404
