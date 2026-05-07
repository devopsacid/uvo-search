# tests/api/test_unified_search.py
"""Tests for GET /api/search/unified."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SUPPLIER_RESULT = {
    "items": [
        {"ico": "11223344", "name": "Acme Corp", "contract_count": 5, "total_value": 100000.0},
    ],
    "total": 1,
}

PROCURER_RESULT = {
    "items": [
        {"ico": "99887766", "name": "City Hall", "contract_count": 12, "total_value": 500000.0},
    ],
    "total": 1,
}

OVERLAP_PROCURER_RESULT = {
    "items": [
        # same ICO as SUPPLIER_RESULT — should be merged into one FirmaHit
        {"ico": "11223344", "name": "Acme Corp", "contract_count": 5, "total_value": 100000.0},
    ],
    "total": 1,
}

CONTRACT_RESULT = {
    "items": [
        {
            "_id": "abc123",
            "title": "Road repair works",
            "procurer": {"ico": "99887766", "name": "City Hall"},
            "final_value": 75000.0,
            "award_date": "2023-04-10",
        }
    ],
    "total": 1,
}

EMPTY_RESULT: dict = {"items": [], "total": 0}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def _make_call_tool_side_effect(*results):
    """Return an AsyncMock that yields results in order across multiple calls."""
    mock = AsyncMock(side_effect=list(results))
    return mock


# ---------------------------------------------------------------------------
# Normal text query
# ---------------------------------------------------------------------------


def test_unified_returns_grouped_shape(client):
    with patch(
        "uvo_api.routers.search.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_RESULT, PROCURER_RESULT, CONTRACT_RESULT]),
    ):
        response = client.get("/api/search/unified?q=acme")
    assert response.status_code == 200
    body = response.json()
    assert body["q"] == "acme"
    assert "firmy" in body
    assert "zakazky" in body


def test_unified_firmy_shape(client):
    with patch(
        "uvo_api.routers.search.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_RESULT, PROCURER_RESULT, CONTRACT_RESULT]),
    ):
        response = client.get("/api/search/unified?q=acme")
    firmy = response.json()["firmy"]
    assert len(firmy) >= 1
    firma = firmy[0]
    assert "ico" in firma
    assert "name" in firma
    assert "roles" in firma
    assert isinstance(firma["roles"], list)
    assert "contract_count" in firma


def test_unified_zakazky_shape(client):
    with patch(
        "uvo_api.routers.search.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_RESULT, PROCURER_RESULT, CONTRACT_RESULT]),
    ):
        response = client.get("/api/search/unified?q=road")
    zakazky = response.json()["zakazky"]
    assert len(zakazky) == 1
    z = zakazky[0]
    assert z["id"] == "abc123"
    assert z["title"] == "Road repair works"
    assert z["procurer_name"] == "City Hall"
    assert z["value"] == 75000.0
    assert z["year"] == 2023


def test_unified_firmy_deduplication(client):
    """Supplier + procurer with same ICO → single FirmaHit with both roles."""
    with patch(
        "uvo_api.routers.search.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_RESULT, OVERLAP_PROCURER_RESULT, CONTRACT_RESULT]),
    ):
        response = client.get("/api/search/unified?q=acme")
    firmy = response.json()["firmy"]
    matched = [f for f in firmy if f["ico"] == "11223344"]
    assert len(matched) == 1
    assert set(matched[0]["roles"]) == {"supplier", "procurer"}


# ---------------------------------------------------------------------------
# ICO lookup (8-digit numeric)
# ---------------------------------------------------------------------------


def test_unified_ico_query_returns_only_firmy(client):
    with patch(
        "uvo_api.routers.search.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_RESULT, EMPTY_RESULT]),
    ):
        response = client.get("/api/search/unified?q=11223344")
    assert response.status_code == 200
    body = response.json()
    assert body["zakazky"] == []
    assert len(body["firmy"]) >= 1


def test_unified_ico_query_does_not_call_contract_search(client):
    mock = AsyncMock(side_effect=[SUPPLIER_RESULT, EMPTY_RESULT])
    with patch("uvo_api.routers.search.call_tool", new=mock):
        client.get("/api/search/unified?q=11223344")
    tool_names = [call.args[0] for call in mock.call_args_list]
    assert "search_completed_procurements" not in tool_names


# ---------------------------------------------------------------------------
# Short query — early return, no MCP calls
# ---------------------------------------------------------------------------


def test_unified_short_query_returns_empty(client):
    mock = AsyncMock(return_value=EMPTY_RESULT)
    with patch("uvo_api.routers.search.call_tool", new=mock):
        response = client.get("/api/search/unified?q=a")
    assert response.status_code == 200
    body = response.json()
    assert body["firmy"] == []
    assert body["zakazky"] == []
    mock.assert_not_called()


def test_unified_empty_query_returns_empty(client):
    mock = AsyncMock(return_value=EMPTY_RESULT)
    with patch("uvo_api.routers.search.call_tool", new=mock):
        response = client.get("/api/search/unified?q=")
    assert response.status_code == 200
    body = response.json()
    assert body["firmy"] == []
    assert body["zakazky"] == []
    mock.assert_not_called()


# ---------------------------------------------------------------------------
# Limit param
# ---------------------------------------------------------------------------


def test_unified_respects_limit(client):
    many_suppliers = {
        "items": [
            {"ico": f"1000000{i}", "name": f"Firm {i}", "contract_count": i, "total_value": 0.0}
            for i in range(15)
        ],
        "total": 15,
    }
    with patch(
        "uvo_api.routers.search.call_tool",
        new=AsyncMock(side_effect=[many_suppliers, EMPTY_RESULT, EMPTY_RESULT]),
    ):
        response = client.get("/api/search/unified?q=firm&limit=5")
    assert response.status_code == 200
    assert len(response.json()["firmy"]) <= 5
