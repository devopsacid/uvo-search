# tests/api/test_firma_extensions.py
"""Tests for the three firma extension endpoints: partneri, cpv-profile, firmy."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

ICO = "12345678"

EMPTY = {"items": [], "total": 0}

# Contracts where ICO=12345678 was the supplier; counterparty (procurer) is "11111111"
SUPPLIER_CONTRACTS = {
    "items": [
        {
            "_id": "s1",
            "title": "IT Services",
            "procurer": {"ico": "11111111", "name": "Ministry A"},
            "final_value": 1_000_000.0,
            "award_date": "2023-05-01",
            "cpv_code": "72000000",
            "awards": [],
        },
        {
            "_id": "s2",
            "title": "Software",
            "procurer": {"ico": "11111111", "name": "Ministry A"},
            "final_value": 500_000.0,
            "award_date": "2022-01-10",
            "cpv_code": "48000000",
            "awards": [],
        },
    ],
    "total": 2,
}

# Contracts where ICO=12345678 was the procurer; counterparty (supplier) is "22222222"
PROCURER_CONTRACTS = {
    "items": [
        {
            "_id": "p1",
            "title": "Construction",
            "procurer": {"ico": ICO, "name": "Ministry of Finance"},
            "final_value": 3_000_000.0,
            "award_date": "2023-09-15",
            "cpv_code": "45000000",
            "awards": [{"supplier_ico": "22222222", "supplier_name": "Build Co"}],
        }
    ],
    "total": 1,
}

MARKET_CONTRACTS = {
    "items": [
        {
            "_id": "m1",
            "title": "Market IT",
            "procurer": {"ico": "99999999", "name": "Other Gov"},
            "final_value": 200_000.0,
            "award_date": "2023-03-01",
            "cpv_code": "72000000",
            "awards": [],
        },
        {
            "_id": "m2",
            "title": "Market Construction",
            "procurer": {"ico": "88888888", "name": "Roads Dept"},
            "final_value": 800_000.0,
            "award_date": "2022-11-20",
            "cpv_code": "45000000",
            "awards": [],
        },
    ],
    "total": 2,
}

SUPPLIER_FIND_RESULT = {
    "items": [
        {"ico": "AAA00001", "name": "Alpha Corp", "contract_count": 10, "total_value": 2_000_000.0},
        {"ico": "BBB00002", "name": "Beta Ltd", "contract_count": 5, "total_value": 800_000.0},
    ],
    "total": 2,
}

PROCURER_FIND_RESULT = {
    "items": [
        {"ico": "AAA00001", "name": "Alpha Corp", "contract_count": 3, "total_value": 500_000.0},
        {"ico": "CCC00003", "name": "Gamma s.r.o.", "contract_count": 7, "total_value": 1_200_000.0},
    ],
    "total": 2,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# TASK-05: /api/firma/{ico}/partneri
# ---------------------------------------------------------------------------

# _fetch_contracts_sample calls search_completed_procurements in pages.
# With the mock returning < 100 items each page stops after first call.
# Two parallel calls are made: one with supplier_ico=ico, one with procurer_id=ico.

def _partneri_side_effects(supplier_result, procurer_result):
    """Returns a side_effect list for _fetch_contracts_sample calls.

    _fetch_contracts_sample issues search_completed_procurements calls.
    The two asyncio.gather calls happen in parallel but mock is sequential,
    so we provide both pages interleaved the way asyncio.gather resolves them:
    gather fires both coroutines, which each call call_tool once (small result).
    """
    # supplier fetch (page 0) → procurer fetch (page 0)
    return [supplier_result, procurer_result]


def test_partneri_returns_correct_shape(client):
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/partneri")

    assert response.status_code == 200
    body = response.json()
    assert "total" in body
    assert "items" in body
    assert body["total"] > 0

    item = body["items"][0]
    for field in ("ico", "name", "role", "contract_count", "total_value", "last_contract_at"):
        assert field in item


def test_partneri_role_filter_supplier(client):
    """role=supplier returns only counterparties that acted as suppliers."""
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/partneri?role=supplier")

    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert item["role"] == "supplier"


def test_partneri_role_filter_procurer(client):
    """role=procurer returns only counterparties that acted as procurers."""
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/partneri?role=procurer")

    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert item["role"] == "procurer"


def test_partneri_all_has_both_roles(client):
    """role=all (default) returns counterparties from both sides."""
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/partneri")

    body = response.json()
    roles = {item["role"] for item in body["items"]}
    assert "supplier" in roles
    assert "procurer" in roles


def test_partneri_sort_by_count(client):
    """sort=count orders by contract_count desc."""
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/partneri?sort=count")

    body = response.json()
    counts = [item["contract_count"] for item in body["items"]]
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# TASK-06: /api/firma/{ico}/cpv-profile
# ---------------------------------------------------------------------------

def test_cpv_profile_shape(client):
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
            (MARKET_CONTRACTS["items"], 2),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/cpv-profile")

    assert response.status_code == 200
    body = response.json()
    assert "for_company" in body
    assert "market_baseline" in body

    assert len(body["for_company"]) > 0
    row = body["for_company"][0]
    for field in ("code", "label", "total_value", "contract_count", "percentage"):
        assert field in row


def test_cpv_profile_percentages_sum_to_100(client):
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
            (MARKET_CONTRACTS["items"], 2),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/cpv-profile")

    body = response.json()
    company_pct_sum = sum(r["percentage"] for r in body["for_company"])
    # rounding means sum is close but not exact; allow ±1%
    assert abs(company_pct_sum - 100.0) <= 1.0


def test_cpv_profile_market_only_has_matching_codes(client):
    """market_baseline only contains CPV codes present in for_company."""
    with patch(
        "uvo_api.routers.firma._fetch_contracts_sample",
        new=AsyncMock(side_effect=[
            (SUPPLIER_CONTRACTS["items"], 2),
            (PROCURER_CONTRACTS["items"], 1),
            (MARKET_CONTRACTS["items"], 2),
        ]),
    ):
        response = client.get(f"/api/firma/{ICO}/cpv-profile")

    body = response.json()
    company_codes = {r["code"] for r in body["for_company"]}
    for mrow in body["market_baseline"]:
        assert mrow["code"] in company_codes


# ---------------------------------------------------------------------------
# TASK-07: /api/firmy
# ---------------------------------------------------------------------------

def test_firmy_returns_merged_list(client):
    with patch(
        "uvo_api.routers.firma.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_FIND_RESULT, PROCURER_FIND_RESULT]),
    ):
        response = client.get("/api/firmy")

    assert response.status_code == 200
    body = response.json()
    assert "total" in body
    assert "items" in body
    assert body["total"] > 0

    item = body["items"][0]
    for field in ("ico", "name", "roles", "contract_count", "total_value"):
        assert field in item


def test_firmy_merges_dual_role_ico(client):
    """AAA00001 appears in both supplier and procurer results — must be merged."""
    with patch(
        "uvo_api.routers.firma.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_FIND_RESULT, PROCURER_FIND_RESULT]),
    ):
        response = client.get("/api/firmy")

    body = response.json()
    merged = next((i for i in body["items"] if i["ico"] == "AAA00001"), None)
    assert merged is not None
    assert set(merged["roles"]) == {"supplier", "procurer"}
    # contract_count summed: 10 + 3 = 13
    assert merged["contract_count"] == 13


def test_firmy_role_filter_supplier_only(client):
    with patch(
        "uvo_api.routers.firma.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_FIND_RESULT]),
    ):
        response = client.get("/api/firmy?role=supplier")

    body = response.json()
    for item in body["items"]:
        assert "supplier" in item["roles"]


def test_firmy_role_filter_procurer_only(client):
    with patch(
        "uvo_api.routers.firma.call_tool",
        new=AsyncMock(side_effect=[PROCURER_FIND_RESULT]),
    ):
        response = client.get("/api/firmy?role=procurer")

    body = response.json()
    for item in body["items"]:
        assert "procurer" in item["roles"]


def test_firmy_sorted_by_contract_count_desc(client):
    with patch(
        "uvo_api.routers.firma.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_FIND_RESULT, PROCURER_FIND_RESULT]),
    ):
        response = client.get("/api/firmy")

    body = response.json()
    counts = [i["contract_count"] for i in body["items"]]
    assert counts == sorted(counts, reverse=True)


def test_firmy_pagination(client):
    with patch(
        "uvo_api.routers.firma.call_tool",
        new=AsyncMock(side_effect=[SUPPLIER_FIND_RESULT, PROCURER_FIND_RESULT]),
    ):
        response = client.get("/api/firmy?limit=1&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    # total reflects the full merged set, not just this page
    assert body["total"] > 1
