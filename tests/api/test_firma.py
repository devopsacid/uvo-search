# tests/api/test_firma.py
"""Tests for GET /api/firma/{ico} — unified company profile endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

# ------------------------------------------------------------------
# Sample MCP responses — use "items" key as the real MCP tools do
# ------------------------------------------------------------------

SUPPLIER_RESULT = {
    "items": [
        {
            "ico": "87654321",
            "name": "Tech Corp s.r.o.",
            "contract_count": 10,
            "total_value": 5_000_000.0,
        }
    ],
    "total": 1,
}

PROCURER_RESULT = {
    "items": [
        {
            "ico": "12345678",
            "name": "Ministry of Finance",
            "contract_count": 20,
            "total_value": 10_000_000.0,
        }
    ],
    "total": 1,
}

EMPTY_RESULT: dict = {"items": [], "total": 0}

SUPPLIER_CONTRACTS = {
    "items": [
        {
            "_id": "c001",
            "title": "IT Infrastructure",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "final_value": 2_000_000.0,
            "award_date": "2023-06-15",
            "cpv_code": "72000000",
            "status": "closed",
            "awards": [],
        },
        {
            "_id": "c002",
            "title": "Software Licenses",
            "procurer": {"ico": "99999999", "name": "Tax Office"},
            "final_value": 500_000.0,
            "award_date": "2022-03-10",
            "cpv_code": "48000000",
            "status": "closed",
            "awards": [],
        },
    ],
    "total": 2,
}

PROCURER_CONTRACTS = {
    "items": [
        {
            "_id": "c010",
            "title": "Road Construction",
            "procurer": {"ico": "12345678", "name": "Ministry of Finance"},
            "final_value": 8_000_000.0,
            "award_date": "2023-09-01",
            "cpv_code": "45000000",
            "status": "closed",
            "awards": [{"supplier_ico": "77777777", "supplier_name": "Build Co"}],
        }
    ],
    "total": 1,
}

DUAL_ROLE_ICO = "12345678"
SUPPLIER_ONLY_ICO = "87654321"
UNKNOWN_ICO = "00000000"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


# ------------------------------------------------------------------
# Helper: build a side_effect list for the 6 sequential call_tool
# calls issued by get_firma_profile for a supplier-only ICO:
#   1. find_supplier
#   2. find_procurer
#   3. search (top-5 as supplier)
#   4. _empty / search (top-5 as procurer) — skipped via _empty()
#   5. search (agg 100 as supplier)
#   6. _empty / search (agg 100 as procurer) — skipped via _empty()
# ------------------------------------------------------------------


def test_supplier_only_ico_returns_200(client):
    """A supplier-only ICO returns roles=['supplier'], primary_role='supplier'."""

    side_effects = [
        SUPPLIER_RESULT,       # find_supplier
        EMPTY_RESULT,          # find_procurer → not found
        SUPPLIER_CONTRACTS,    # top-5 as supplier
        SUPPLIER_CONTRACTS,    # agg-100 as supplier
    ]

    with patch("uvo_api.routers.firma.call_tool", new=AsyncMock(side_effect=side_effects)):
        response = client.get(f"/api/firma/{SUPPLIER_ONLY_ICO}")

    assert response.status_code == 200
    body = response.json()

    assert body["ico"] == SUPPLIER_ONLY_ICO
    assert body["name"] == "Tech Corp s.r.o."
    assert body["roles"] == ["supplier"]
    assert body["primary_role"] == "supplier"

    stats = body["stats"]
    assert stats["as_supplier"] is not None
    assert stats["as_procurer"] is None
    assert stats["as_supplier"]["contract_count"] == 10

    assert len(body["top_contracts"]) == 2
    assert body["top_contracts"][0]["role"] == "supplier"
    assert body["top_contracts"][0]["value"] == 2_000_000.0

    assert len(body["spend_by_year"]) >= 1
    years = [s["year"] for s in body["spend_by_year"]]
    assert 2023 in years


def test_dual_role_ico_returns_200(client):
    """An ICO appearing as both supplier and procurer has both roles in the response."""

    # For this test, DUAL_ROLE_ICO is a procurer; we invent it also being a supplier
    dual_supplier = {
        "items": [{"ico": DUAL_ROLE_ICO, "name": "Ministry of Finance", "contract_count": 5, "total_value": 1_000_000.0}],
        "total": 1,
    }
    dual_procurer = {
        "items": [{"ico": DUAL_ROLE_ICO, "name": "Ministry of Finance", "contract_count": 20, "total_value": 10_000_000.0}],
        "total": 1,
    }

    side_effects = [
        dual_supplier,          # find_supplier
        dual_procurer,          # find_procurer
        SUPPLIER_CONTRACTS,     # top-5 as supplier
        PROCURER_CONTRACTS,     # top-5 as procurer
        SUPPLIER_CONTRACTS,     # agg-100 as supplier
        PROCURER_CONTRACTS,     # agg-100 as procurer
    ]

    with patch("uvo_api.routers.firma.call_tool", new=AsyncMock(side_effect=side_effects)):
        response = client.get(f"/api/firma/{DUAL_ROLE_ICO}")

    assert response.status_code == 200
    body = response.json()

    assert set(body["roles"]) == {"supplier", "procurer"}
    # procurer has more contracts (20 > 5) → primary_role = procurer
    assert body["primary_role"] == "procurer"

    stats = body["stats"]
    assert stats["as_supplier"] is not None
    assert stats["as_procurer"] is not None
    assert stats["as_procurer"]["contract_count"] == 20

    # Top contracts come from both roles
    roles_in_top = {c["role"] for c in body["top_contracts"]}
    assert "supplier" in roles_in_top
    assert "procurer" in roles_in_top


def test_unknown_ico_returns_404(client):
    """An ICO unknown to both find_supplier and find_procurer returns 404."""

    side_effects = [
        EMPTY_RESULT,   # find_supplier
        EMPTY_RESULT,   # find_procurer
    ]

    with patch("uvo_api.routers.firma.call_tool", new=AsyncMock(side_effect=side_effects)):
        response = client.get(f"/api/firma/{UNKNOWN_ICO}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Firma nenájdená"
