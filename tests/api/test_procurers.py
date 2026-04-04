# tests/api/test_procurers.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_PROCURER_RESPONSE = {
    "data": [
        {
            "ico": "12345678",
            "nazov": "Ministry of Finance",
            "pocet_zakaziek": 20,
            "celkova_hodnota": 10000000.0,
        },
    ],
    "total": 1,
}

SAMPLE_CONTRACTS_FOR_PROCURER = {
    "data": [
        {
            "id": "2001",
            "nazov": "Cloud Services",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 300000.0,
            "datum_zverejnenia": "2023-03-10",
            "cpv_kod": "72000000",
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
        "uvo_api.routers.procurers.call_tool", new=AsyncMock(return_value=SAMPLE_PROCURER_RESPONSE)
    ):
        response = client.get("/api/procurers")
    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["ico"] == "12345678"
    assert body["data"][0]["name"] == "Ministry of Finance"
    assert body["data"][0]["contract_count"] == 20
    assert body["pagination"]["total"] == 1


def test_get_procurer_detail(client):
    with patch(
        "uvo_api.routers.procurers.call_tool",
        new=AsyncMock(
            side_effect=[
                SAMPLE_PROCURER_RESPONSE,
                SAMPLE_CONTRACTS_FOR_PROCURER,
            ]
        ),
    ):
        response = client.get("/api/procurers/12345678")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "12345678"
    assert body["contract_count"] == 20
    assert len(body["contracts"]) == 1
    assert len(body["top_suppliers"]) == 1
    assert body["top_suppliers"][0]["ico"] == "87654321"


def test_get_procurer_summary(client):
    with patch(
        "uvo_api.routers.procurers.call_tool",
        new=AsyncMock(
            side_effect=[
                SAMPLE_PROCURER_RESPONSE,
                SAMPLE_CONTRACTS_FOR_PROCURER,
            ]
        ),
    ):
        response = client.get("/api/procurers/12345678/summary")
    assert response.status_code == 200
    body = response.json()
    assert "spend_by_year" in body
    assert body["spend_by_year"][0]["year"] == 2023


def test_get_procurer_not_found(client):
    with patch(
        "uvo_api.routers.procurers.call_tool", new=AsyncMock(return_value={"data": [], "total": 0})
    ):
        response = client.get("/api/procurers/00000000")
    assert response.status_code == 404
