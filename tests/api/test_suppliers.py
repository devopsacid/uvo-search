# tests/api/test_suppliers.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from uvo_api.app import create_app

SAMPLE_SUPPLIER_RESPONSE = {
    "data": [
        {"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 10, "celkova_hodnota": 5000000.0},
        {"ico": "11111111", "nazov": "Build Co", "pocet_zakaziek": 5, "celkova_hodnota": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_CONTRACTS_FOR_SUPPLIER = {
    "data": [
        {
            "id": "1001",
            "nazov": "IT Project",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 500000.0,
            "datum_zverejnenia": "2023-06-01",
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


def test_list_suppliers(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)):
        response = client.get("/api/suppliers")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["ico"] == "87654321"
    assert body["data"][0]["name"] == "Tech Corp"
    assert body["data"][0]["contract_count"] == 10
    assert body["pagination"]["total"] == 2


def test_list_suppliers_search_by_name(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)) as mock:
        client.get("/api/suppliers?q=Tech")
    mock.assert_called_once()
    args = mock.call_args[0][1]
    assert args.get("name_query") == "Tech"


def test_list_suppliers_search_by_ico(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)) as mock:
        client.get("/api/suppliers?ico=87654321")
    args = mock.call_args[0][1]
    assert args.get("ico") == "87654321"


def test_get_supplier_detail(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(side_effect=[
        {"data": [{"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 1, "celkova_hodnota": 500000.0}], "total": 1},
        SAMPLE_CONTRACTS_FOR_SUPPLIER,
    ])):
        response = client.get("/api/suppliers/87654321")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert body["contract_count"] == 1
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["id"] == "1001"


def test_get_supplier_summary(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(side_effect=[
        {"data": [{"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 1, "celkova_hodnota": 500000.0}], "total": 1},
        SAMPLE_CONTRACTS_FOR_SUPPLIER,
    ])):
        response = client.get("/api/suppliers/87654321/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert "spend_by_year" in body
    assert body["spend_by_year"][0]["year"] == 2023


def test_get_supplier_not_found(client):
    with patch("uvo_api.routers.suppliers.call_tool", new=AsyncMock(return_value={"data": [], "total": 0})):
        response = client.get("/api/suppliers/00000000")
    assert response.status_code == 404
