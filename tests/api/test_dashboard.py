# tests/api/test_dashboard.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from uvo_api.app import create_app

SAMPLE_CONTRACTS = {
    "data": [
        {
            "id": "1",
            "nazov": "IT Project",
            "obstaravatel": {"ico": "12345678", "nazov": "Ministry"},
            "dodavatelia": [{"ico": "87654321", "nazov": "Tech Corp"}],
            "hodnota_zmluvy": 500000.0,
            "datum_zverejnenia": "2024-03-01",
            "cpv_kod": "72000000",
        },
        {
            "id": "2",
            "nazov": "Road Works",
            "obstaravatel": {"ico": "11111111", "nazov": "NDS"},
            "dodavatelia": [{"ico": "22222222", "nazov": "Build Co"}],
            "hodnota_zmluvy": 1000000.0,
            "datum_zverejnenia": "2023-06-15",
            "cpv_kod": "45000000",
        },
    ],
    "total": 2,
}

SAMPLE_SUPPLIERS = {
    "data": [
        {"ico": "87654321", "nazov": "Tech Corp", "pocet_zakaziek": 10, "celkova_hodnota": 5000000.0},
        {"ico": "22222222", "nazov": "Build Co", "pocet_zakaziek": 5, "celkova_hodnota": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_PROCURERS = {
    "data": [
        {"ico": "12345678", "nazov": "Ministry", "pocet_zakaziek": 15, "celkova_hodnota": 8000000.0},
    ],
    "total": 1,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def test_dashboard_summary(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(side_effect=[
        SAMPLE_CONTRACTS, SAMPLE_SUPPLIERS,
    ])):
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
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_SUPPLIERS)):
        response = client.get("/api/dashboard/top-suppliers")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert body[0]["ico"] == "87654321"
    assert body[0]["total_value"] == 5000000.0


def test_dashboard_top_procurers(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_PROCURERS)):
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
