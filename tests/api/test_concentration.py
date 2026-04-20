# tests/api/test_concentration.py
"""Tests for procurer concentration endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_PROCURER = {
    "items": [{"ico": "12345678", "name": "Ministry of Finance", "contract_count": 3, "total_value": 1800000.0}],
    "total": 1,
}

SAMPLE_CONTRACTS = {
    "items": [
        {
            "_id": "c1",
            "title": "IT",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "awards": [{"supplier_ico": "AAA", "supplier_name": "Alpha"}],
            "final_value": 600000.0,
            "award_date": "2024-01-01",
        },
        {
            "_id": "c2",
            "title": "Roads",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "awards": [{"supplier_ico": "BBB", "supplier_name": "Beta"}],
            "final_value": 300000.0,
            "award_date": "2024-02-01",
        },
        {
            "_id": "c3",
            "title": "Supplies",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "awards": [{"supplier_ico": "AAA", "supplier_name": "Alpha"}],
            "final_value": 900000.0,
            "award_date": "2024-03-01",
        },
    ],
    "total": 3,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


def test_concentration_happy_path(client):
    with patch(
        "uvo_api.routers.procurers.call_tool",
        new=AsyncMock(side_effect=[SAMPLE_PROCURER, SAMPLE_CONTRACTS]),
    ):
        response = client.get("/api/procurers/12345678/concentration")
    assert response.status_code == 200
    body = response.json()
    assert body["procurer_ico"] == "12345678"
    assert body["procurer_name"] == "Ministry of Finance"
    assert len(body["top_suppliers"]) == 2
    # Alpha has 1500000 of 1800000 = 83.33%
    alpha = next(s for s in body["top_suppliers"] if s["ico"] == "AAA")
    assert alpha["total_value"] == pytest.approx(1500000.0)
    assert alpha["share"] == pytest.approx(83.33, rel=0.01)
    # HHI = (83.33)^2 + (16.67)^2 ≈ 6944 + 278 ≈ 7222
    assert body["hhi"] > 5000  # highly concentrated


def test_concentration_not_found(client):
    with patch(
        "uvo_api.routers.procurers.call_tool",
        new=AsyncMock(return_value={"items": [], "total": 0}),
    ):
        response = client.get("/api/procurers/00000000/concentration")
    assert response.status_code == 404


def test_concentration_top_n_param(client):
    with patch(
        "uvo_api.routers.procurers.call_tool",
        new=AsyncMock(side_effect=[SAMPLE_PROCURER, SAMPLE_CONTRACTS]),
    ):
        response = client.get("/api/procurers/12345678/concentration?top_n=1")
    assert response.status_code == 200
    body = response.json()
    assert len(body["top_suppliers"]) == 1
    # Top supplier is Alpha
    assert body["top_suppliers"][0]["ico"] == "AAA"
