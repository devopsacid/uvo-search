# tests/api/test_suppliers.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_SUPPLIER_RESPONSE = {
    "items": [
        {
            "ico": "87654321",
            "name": "Tech Corp",
            "contract_count": 10,
            "total_value": 5000000.0,
        },
        {"ico": "11111111", "name": "Build Co", "contract_count": 5, "total_value": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_CONTRACTS_FOR_SUPPLIER = {
    "items": [
        {
            "_id": "1001",
            "title": "IT Project",
            "procurer": {"ico": "12345678", "name": "Ministry"},
            "awards": [{"supplier_ico": "87654321", "supplier_name": "Tech Corp"}],
            "final_value": 500000.0,
            "publication_date": "2023-06-01",
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


def test_list_suppliers(client):
    with patch(
        "uvo_api.routers.suppliers.run_query", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)
    ):
        response = client.get("/api/suppliers")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["ico"] == "87654321"
    assert body["data"][0]["name"] == "Tech Corp"
    assert body["data"][0]["contract_count"] == 10
    assert body["pagination"]["total"] == 2


def test_list_suppliers_search_by_name(client):
    with patch(
        "uvo_api.routers.suppliers.run_query", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)
    ) as mock:
        client.get("/api/suppliers?q=Tech")
    mock.assert_called_once()
    args = mock.call_args[0][1]
    assert args.get("name_query") == "Tech"


def test_list_suppliers_search_by_ico(client):
    with patch(
        "uvo_api.routers.suppliers.run_query", new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE)
    ) as mock:
        client.get("/api/suppliers?ico=87654321")
    args = mock.call_args[0][1]
    assert args.get("ico") == "87654321"


def test_get_supplier_detail(client):
    with patch(
        "uvo_api.routers.suppliers.run_query",
        new=AsyncMock(
            side_effect=[
                {
                    "items": [
                        {
                            "ico": "87654321",
                            "name": "Tech Corp",
                            "contract_count": 1,
                            "total_value": 500000.0,
                        }
                    ],
                    "total": 1,
                },
                SAMPLE_CONTRACTS_FOR_SUPPLIER,
            ]
        ),
    ):
        response = client.get("/api/suppliers/87654321")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert body["contract_count"] == 1
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["id"] == "1001"


def test_get_supplier_summary(client):
    with patch(
        "uvo_api.routers.suppliers.run_query",
        new=AsyncMock(
            side_effect=[
                {
                    "items": [
                        {
                            "ico": "87654321",
                            "name": "Tech Corp",
                            "contract_count": 1,
                            "total_value": 500000.0,
                        }
                    ],
                    "total": 1,
                },
                SAMPLE_CONTRACTS_FOR_SUPPLIER,
            ]
        ),
    ):
        response = client.get("/api/suppliers/87654321/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert "spend_by_year" in body
    assert body["spend_by_year"][0]["year"] == 2023


def test_get_supplier_not_found(client):
    with patch(
        "uvo_api.routers.suppliers.run_query", new=AsyncMock(return_value={"data": [], "total": 0})
    ):
        response = client.get("/api/suppliers/00000000")
    assert response.status_code == 404
