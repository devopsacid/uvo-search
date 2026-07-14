# tests/api/test_contracts.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_MCP_RESPONSE = {
    "items": [
        {
            "_id": "1001",
            "title": "IT Infrastructure",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "awards": [{"supplier_ico": "87654321", "supplier_name": "Tech Corp"}],
            "final_value": 150000.0,
            "publication_date": "2024-01-15",
            "cpv_code": "72000000",
        }
    ],
    "total": 1,
}

EMPTY_MCP_RESPONSE = {"items": [], "total": 0}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def _repo(*, search=None, detail=None):
    repo = MagicMock()
    repo.search = AsyncMock(return_value=search)
    repo.get_by_source_id = AsyncMock(return_value=detail)
    return repo


def test_list_contracts_returns_paginated_response(client):
    repo = _repo(search=SAMPLE_MCP_RESPONSE)
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["total"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "1001"


def test_list_contracts_maps_fields_correctly(client):
    repo = _repo(search=SAMPLE_MCP_RESPONSE)
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts")
    row = response.json()["data"][0]
    assert row["title"] == "IT Infrastructure"
    assert row["procurer_name"] == "Ministry of Finance"
    assert row["procurer_ico"] == "12345678"
    assert row["supplier_name"] == "Tech Corp"
    assert row["supplier_ico"] == "87654321"
    assert row["value"] == 150000.0
    assert row["year"] == 2024


def test_list_contracts_pushes_value_filter_into_query(client):
    repo = _repo(search=EMPTY_MCP_RESPONSE)
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts?value_min=1000&value_max=5000")
    assert response.status_code == 200
    # The filter is pushed into the repository query, not applied post-pagination.
    _, kwargs = repo.search.call_args
    assert kwargs["value_min"] == 1000
    assert kwargs["value_max"] == 5000


def test_list_contracts_empty_result(client):
    repo = _repo(search=EMPTY_MCP_RESPONSE)
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["pagination"]["total"] == 0


def test_get_contract_detail_returns_detail(client):
    detail = {
        "_id": "1001",
        "title": "IT Infrastructure",
        "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
        "awards": [{"ico": "87654321", "supplier_ico": "87654321", "supplier_name": "Tech Corp"}],
        "final_value": 150000.0,
        "publication_date": "2024-01-15",
        "cpv_code": "72000000",
    }
    repo = _repo(detail=detail)
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts/1001")
    assert response.status_code == 200
    assert response.json()["id"] == "1001"
    assert response.json()["all_suppliers"][0]["ico"] == "87654321"


def test_get_contract_detail_not_found(client):
    repo = _repo(detail={"error": "not found", "status_code": 404})
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts/9999")
    assert response.status_code == 404
