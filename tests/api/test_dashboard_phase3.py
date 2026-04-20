# tests/api/test_dashboard_phase3.py
"""Phase 3 dashboard endpoint tests: by-cpv with year filters and by-month."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_CONTRACTS = {
    "items": [
        {
            "_id": "1",
            "title": "IT Project",
            "procurer": {"ico": "12345678", "name": "Ministry"},
            "awards": [{"supplier_ico": "87654321", "supplier_name": "Tech Corp"}],
            "final_value": 500000.0,
            "award_date": "2024-03-01",
            "cpv_code": "72000000",
        },
        {
            "_id": "2",
            "title": "Road Works",
            "procurer": {"ico": "11111111", "name": "NDS"},
            "awards": [{"supplier_ico": "22222222", "supplier_name": "Build Co"}],
            "final_value": 1000000.0,
            "award_date": "2023-06-15",
            "cpv_code": "45000000",
        },
    ],
    "total": 2,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


def test_by_cpv_no_year_filter(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-cpv")
    assert response.status_code == 200
    body = response.json()
    cpv_codes = {item["cpv_code"] for item in body}
    assert "72000000" in cpv_codes
    assert "45000000" in cpv_codes


def test_by_cpv_year_from_filter(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-cpv?year_from=2024")
    assert response.status_code == 200
    body = response.json()
    cpv_codes = {item["cpv_code"] for item in body}
    # Only 2024 contract (72000000) should survive
    assert "72000000" in cpv_codes
    assert "45000000" not in cpv_codes


def test_by_cpv_year_to_filter(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-cpv?year_to=2023")
    assert response.status_code == 200
    body = response.json()
    cpv_codes = {item["cpv_code"] for item in body}
    assert "45000000" in cpv_codes
    assert "72000000" not in cpv_codes


def test_by_month_returns_12_buckets(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-month?year=2024")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 12
    months = [b["month"] for b in body]
    assert months == list(range(1, 13))


def test_by_month_counts_correctly(client):
    with patch("uvo_api.routers.dashboard.call_tool", new=AsyncMock(return_value=SAMPLE_CONTRACTS)):
        response = client.get("/api/dashboard/by-month?year=2024")
    assert response.status_code == 200
    body = response.json()
    # 2024-03-01 → month 3 should have 1 contract
    march = next(b for b in body if b["month"] == 3)
    assert march["contract_count"] == 1
    assert march["total_value"] == 500000.0
    # Month 6 in 2024 should be 0 (the road works are 2023)
    june = next(b for b in body if b["month"] == 6)
    assert june["contract_count"] == 0


def test_by_month_missing_year_param(client):
    response = client.get("/api/dashboard/by-month")
    assert response.status_code == 422
