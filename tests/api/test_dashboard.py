# tests/api/test_dashboard.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_CONTRACTS = {
    "items": [
        {
            "_id": "1",
            "title": "IT Project",
            "procurer": {"ico": "12345678", "name": "Ministry"},
            "awards": [{"supplier": {"ico": "87654321", "name": "Tech Corp"}}],
            "final_value": 500000.0,
            "publication_date": "2024-03-01",
            "cpv_code": "72000000",
            "status": "active",
        },
        {
            "_id": "2",
            "title": "Road Works",
            "procurer": {"ico": "11111111", "name": "NDS"},
            "awards": [{"supplier": {"ico": "22222222", "name": "Build Co"}}],
            "final_value": 1000000.0,
            "publication_date": "2023-06-15",
            "cpv_code": "45000000",
            "status": "closed",
        },
    ],
    "total": 2,
}

SAMPLE_SUPPLIERS = {
    "items": [
        {
            "ico": "87654321",
            "name": "Tech Corp",
            "contract_count": 10,
            "total_value": 5000000.0,
        },
        {"ico": "22222222", "name": "Build Co", "contract_count": 5, "total_value": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_PROCURERS = {
    "items": [
        {
            "ico": "12345678",
            "name": "Ministry",
            "contract_count": 15,
            "total_value": 8000000.0,
        },
    ],
    "total": 1,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def test_dashboard_summary(client):
    with patch(
        "uvo_api.routers.dashboard.call_tool",
        new=AsyncMock(
            side_effect=[
                SAMPLE_CONTRACTS,
                SAMPLE_SUPPLIERS,
                SAMPLE_PROCURERS,
            ]
        ),
    ):
        response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_count"] == 2
    assert body["total_value"] == 1500000.0
    assert body["avg_value"] == 750000.0
    assert body["active_suppliers"] == 2


def test_dashboard_spend_by_year(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/spend-by-year")
    assert response.status_code == 200
    body = response.json()
    years = {item["year"] for item in body}
    assert 2024 in years
    assert 2023 in years


def test_dashboard_top_suppliers(client):
    mock_rows = [
        {
            "_id": "31410952",
            "name": "MICROCOMP - Computersystém s r. o.",
            "total_value": 1_921_158_287.63,
            "contract_count": 77,
        },
        {
            "_id": "35919001",
            "name": "Národná diaľničná spoločnosť, a.s.",
            "total_value": 1_379_825_579.55,
            "contract_count": 373,
        },
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_rows)
    mock_collection = MagicMock()
    mock_collection.aggregate.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("uvo_api.routers.dashboard.get_db", return_value=mock_db):
        response = client.get("/api/dashboard/top-suppliers")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["ico"] == "31410952"
    assert body[0]["name"] == "MICROCOMP - Computersystém s r. o."
    assert body[0]["total_value"] == 1_921_158_287.63
    assert body[0]["contract_count"] == 77
    assert body[0]["total_value"] >= body[1]["total_value"]


def test_dashboard_top_procurers(client):
    mock_rows = [{"_id": "12345678", "name": "Ministry", "total_value": 8000000.0, "contract_count": 15}]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_rows)
    mock_collection = MagicMock()
    mock_collection.aggregate.return_value = mock_cursor
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch("uvo_api.routers.dashboard.get_db", return_value=mock_db):
        response = client.get("/api/dashboard/top-procurers")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["ico"] == "12345678"
    assert body[0]["total_spend"] == 8000000.0


def test_dashboard_by_cpv(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-cpv")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    cpv_codes = {item["cpv_code"] for item in body}
    assert "72000000" in cpv_codes or "45000000" in cpv_codes


def test_dashboard_recent(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/recent")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == "1"
