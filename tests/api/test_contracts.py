# tests/api/test_contracts.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_MCP_RESPONSE = {
    "data": [
        {
            "id": "1001",
            "nazov": "IT Infrastructure",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 150000.0,
            "datum_zverejnenia": "2024-01-15",
            "cpv_kod": "72000000",
        }
    ],
    "total": 1,
}

EMPTY_MCP_RESPONSE = {"data": [], "total": 0}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def test_list_contracts_returns_paginated_response(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=SAMPLE_MCP_RESPONSE)):
        response = client.get("/api/contracts")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["total"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "1001"


def test_list_contracts_maps_fields_correctly(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=SAMPLE_MCP_RESPONSE)):
        response = client.get("/api/contracts")
    row = response.json()["data"][0]
    assert row["title"] == "IT Infrastructure"
    assert row["procurer_name"] == "Ministry of Finance"
    assert row["procurer_ico"] == "12345678"
    assert row["supplier_name"] == "Tech Corp"
    assert row["supplier_ico"] == "87654321"
    assert row["value"] == 150000.0
    assert row["year"] == 2024


def test_list_contracts_empty_result(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=EMPTY_MCP_RESPONSE)):
        response = client.get("/api/contracts")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["pagination"]["total"] == 0


def test_get_contract_detail_returns_detail(client):
    detail = {
        "id": "1001",
        "nazov": "IT Infrastructure",
        "obstaravatel": {"ico": "12345678", "nazov": "Ministry of Finance"},
        "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
        "hodnota_zmluvy": 150000.0,
        "datum_zverejnenia": "2024-01-15",
        "cpv_kod": "72000000",
    }
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value=detail)):
        response = client.get("/api/contracts/1001")
    assert response.status_code == 200
    assert response.json()["id"] == "1001"
    assert response.json()["all_suppliers"][0]["ico"] == "87654321"


def test_get_contract_detail_not_found(client):
    with patch("uvo_api.routers.contracts.call_tool", new=AsyncMock(return_value={"error": "not found", "status_code": 404})):
        response = client.get("/api/contracts/9999")
    assert response.status_code == 404
