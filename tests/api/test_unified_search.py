# tests/api/test_unified_search.py
"""Tests for GET /api/search/unified."""

from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.api._deps import deps
from uvo_api.app import create_app
from uvo_api.db import get_embedder

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
        # same ICO as SUPPLIER_RESULT — should be merged into one CompanyHit
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


_MODULE = "uvo_api.routers.search"


@contextmanager
def _search_patches(
    client,
    *,
    supplier=SUPPLIER_RESULT,
    procurer=PROCURER_RESULT,
    vector=EMPTY_RESULT,
    contracts=CONTRACT_RESULT,
    failing: frozenset[str] = frozenset(),
):
    """Patch the four typed search functions the router calls; yield them by name.

    ``failing`` names the branches (supplier/procurer/vector/contracts) that raise.
    """
    answers = {
        "supplier": ("find_suppliers", supplier),
        "procurer": ("find_procurers", procurer),
        "vector": ("vector_search_companies", vector),
        "contracts": ("search_procurements", contracts),
    }
    mocks: dict[str, AsyncMock] = {}
    with ExitStack() as stack:
        # A loaded embedder is required for the vector branch to run at all.
        stack.enter_context(deps(client, get_embedder, MagicMock(name="embedder")))
        for branch, (fn_name, answer) in answers.items():
            if branch in failing:
                mock = AsyncMock(side_effect=RuntimeError(f"{branch} exploded"))
            else:
                mock = AsyncMock(return_value=answer)
            mocks[branch] = mock
            stack.enter_context(patch(f"{_MODULE}.{fn_name}", new=mock))
        yield mocks


# ---------------------------------------------------------------------------
# Normal text query
# ---------------------------------------------------------------------------


def test_unified_returns_grouped_shape(client):
    with _search_patches(client):
        response = client.get("/api/search/unified?q=acme")
    assert response.status_code == 200
    body = response.json()
    assert body["q"] == "acme"
    assert "companies" in body
    assert "contracts" in body


def test_unified_calls_typed_functions_with_explicit_keywords(client):
    with _search_patches(client) as mocks:
        client.get("/api/search/unified?q=acme&limit=7")
    assert mocks["supplier"].await_args.kwargs == {"name_query": "acme", "limit": 7}
    assert mocks["procurer"].await_args.kwargs == {"name_query": "acme", "limit": 7}
    assert mocks["contracts"].await_args.kwargs == {"text_query": "acme", "limit": 7}
    assert mocks["vector"].await_args.args[2:] == ("acme", 7)


def test_unified_companies_shape(client):
    with _search_patches(client):
        response = client.get("/api/search/unified?q=acme")
    companies = response.json()["companies"]
    assert len(companies) >= 1
    company = companies[0]
    assert "ico" in company
    assert "name" in company
    assert "roles" in company
    assert isinstance(company["roles"], list)
    assert "contract_count" in company


def test_unified_contracts_shape(client):
    with _search_patches(client):
        response = client.get("/api/search/unified?q=road")
    contracts = response.json()["contracts"]
    assert len(contracts) == 1
    z = contracts[0]
    assert z["id"] == "abc123"
    assert z["title"] == "Road repair works"
    assert z["procurer_name"] == "City Hall"
    assert z["value"] == 75000.0
    assert z["year"] == 2023


def test_unified_companies_deduplication(client):
    """Supplier + procurer with same ICO → single CompanyHit with both roles."""
    with _search_patches(client, procurer=OVERLAP_PROCURER_RESULT):
        response = client.get("/api/search/unified?q=acme")
    companies = response.json()["companies"]
    matched = [f for f in companies if f["ico"] == "11223344"]
    assert len(matched) == 1
    assert set(matched[0]["roles"]) == {"supplier", "procurer"}


def test_unified_without_embedder_degrades_to_text_hits(client):
    """No FastEmbed model: vector branch is skipped, text branches still answer."""
    with _search_patches(client) as mocks, deps(client, get_embedder, None):
        response = client.get("/api/search/unified?q=acme")
    assert response.status_code == 200
    assert len(response.json()["companies"]) == 2
    mocks["vector"].assert_not_called()


# ---------------------------------------------------------------------------
# ICO lookup (8-digit numeric)
# ---------------------------------------------------------------------------


def test_unified_ico_query_returns_only_companies(client):
    with _search_patches(client, procurer=EMPTY_RESULT):
        response = client.get("/api/search/unified?q=11223344")
    assert response.status_code == 200
    body = response.json()
    assert body["contracts"] == []
    assert len(body["companies"]) >= 1


def test_unified_ico_query_does_not_call_contract_search(client):
    with _search_patches(client, procurer=EMPTY_RESULT) as mocks:
        client.get("/api/search/unified?q=11223344")
    mocks["contracts"].assert_not_called()
    mocks["vector"].assert_not_called()
    assert mocks["supplier"].await_args.kwargs == {"ico": "11223344", "limit": 8}


# ---------------------------------------------------------------------------
# Short query — early return, no backend calls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["a", ""])
def test_unified_short_query_returns_empty(client, query):
    with _search_patches(client) as mocks:
        response = client.get(f"/api/search/unified?q={query}")
    assert response.status_code == 200
    body = response.json()
    assert body["companies"] == []
    assert body["contracts"] == []
    for mock in mocks.values():
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
    with _search_patches(
        client, supplier=many_suppliers, procurer=EMPTY_RESULT, contracts=EMPTY_RESULT
    ):
        response = client.get("/api/search/unified?q=firm&limit=5")
    assert response.status_code == 200
    assert len(response.json()["companies"]) <= 5


# ---------------------------------------------------------------------------
# Per-branch failure isolation (B20)
# ---------------------------------------------------------------------------


def test_unified_contract_branch_failure_keeps_companies_and_logs(client, caplog):
    with _search_patches(client, failing=frozenset({"contracts"})):
        with caplog.at_level("WARNING", logger="uvo_api.routers.search"):
            response = client.get("/api/search/unified?q=acme")
    assert response.status_code == 200
    body = response.json()
    assert len(body["companies"]) == 2
    assert body["contracts"] == []
    record = next(r for r in caplog.records if "contracts" in r.getMessage())
    assert record.levelname == "WARNING"
    assert record.exc_info is not None


def test_unified_vector_branch_failure_keeps_contracts(client):
    with _search_patches(client, failing=frozenset({"vector"})):
        response = client.get("/api/search/unified?q=acme")
    assert response.status_code == 200
    body = response.json()
    assert len(body["companies"]) == 2
    assert len(body["contracts"]) >= 1


def test_unified_all_branches_failing_propagates(client):
    failing = frozenset({"supplier", "procurer", "vector", "contracts"})
    with _search_patches(client, failing=failing):
        with pytest.raises(RuntimeError, match="exploded"):
            client.get("/api/search/unified?q=acme")
