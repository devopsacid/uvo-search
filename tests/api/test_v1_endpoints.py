"""Public /v1 endpoint behavior (auth + redis stubbed, MCP/Mongo mocked)."""

from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

ACTIVE_KEY = {"_id": "key_pro", "plan": "pro", "owner_email": "a@b.sk", "active": True}
AUTH_HEADERS = {"X-API-Key": "raw"}

SUPPLIER_RESULT = {
    "items": [{"ico": "87654321", "name": "Tech Corp", "contract_count": 10, "total_value": 5_000_000.0}],
    "total": 1,
}
PROCURER_RESULT = {
    "items": [{"ico": "12345678", "name": "Ministry", "contract_count": 20, "total_value": 9_000_000.0}],
    "total": 1,
}
EMPTY = {"items": [], "total": 0}

CONTRACT_ITEM = {
    "_id": "c001",
    "title": "IT Infrastructure",
    "procurer": {"ico": "12345678", "name": "Ministry"},
    "awards": [{"supplier_ico": "87654321", "supplier_name": "Tech Corp"}],
    "final_value": 150000.0,
    "publication_date": "2024-01-15",
    "award_date": "2024-01-20",
    "cpv_code": "72000000",
    "status": "active",
}

CORE_AGG = {
    "as_supplier": [{"count": 10, "total": 5_000_000.0, "last": "2023-06-15"}],
    "as_procurer": [],
    "cpv": [
        {"_id": "72000000", "count": 8, "total": 4_000_000.0},
        {"_id": "48000000", "count": 2, "total": 1_000_000.0},
    ],
    "spend_by_year": [{"_id": "2023", "total": 5_000_000.0}],
}

PARTNERS_AGG = {
    "total": 1,
    "items": [
        {
            "ico": "12345678",
            "name": "Ministry",
            "role": "procurer",
            "contract_count": 10,
            "total_value": 5_000_000.0,
            "last_contract_at": "2023-06-15",
        }
    ],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setattr(
        "uvo_api.ratelimit.get_redis",
        AsyncMock(return_value=fakeredis.aioredis.FakeRedis(decode_responses=True)),
    )
    monkeypatch.setattr("uvo_api.auth._lookup_key", AsyncMock(return_value=ACTIVE_KEY))
    app = create_app()
    return TestClient(app)


def test_search_companies_merges_and_envelopes(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies.run_query",
        AsyncMock(side_effect=[SUPPLIER_RESULT, PROCURER_RESULT]),
    )
    resp = client.get("/v1/companies?q=tech&limit=10", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    icos = {c["ico"] for c in body["data"]}
    assert icos == {"87654321", "12345678"}
    assert body["pagination"]["next_cursor"] is None


def test_get_company_record(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies.run_query",
        AsyncMock(side_effect=[SUPPLIER_RESULT, EMPTY]),
    )
    resp = client.get("/v1/companies/87654321", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ico"] == "87654321"
    assert data["roles"] == ["supplier"]


def test_get_company_record_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies.run_query",
        AsyncMock(side_effect=[EMPTY, EMPTY]),
    )
    resp = client.get("/v1/companies/00000000", headers=AUTH_HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "company_not_found"


def test_company_profile(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies.run_query",
        AsyncMock(side_effect=[SUPPLIER_RESULT, EMPTY]),
    )
    monkeypatch.setattr("uvo_api.routers.v1.companies.get_db", lambda: MagicMock())
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies._firma_core_agg", AsyncMock(return_value=CORE_AGG)
    )
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies._firma_partners_agg", AsyncMock(return_value=PARTNERS_AGG)
    )
    resp = client.get("/v1/companies/87654321/profile", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contract_count"] == 10
    assert data["total_value"] == 5_000_000.0
    assert data["spend_by_year"] == [{"year": 2023, "total_value": 5_000_000.0}]
    assert data["top_procurers"][0]["ico"] == "12345678"
    assert data["top_suppliers"] == []
    # HHI over shares 0.8/0.2 => 0.64 + 0.04 = 0.68
    assert data["cpv_concentration"] == pytest.approx(0.68, abs=0.01)
    assert data["cpv_breakdown"][0]["code"] == "72000000"


def test_search_contracts(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.contracts.run_query",
        AsyncMock(return_value={"items": [CONTRACT_ITEM], "total": 1}),
    )
    resp = client.get("/v1/contracts?q=IT&limit=20", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    row = body["data"][0]
    assert row["id"] == "c001"
    assert row["title"] == "IT Infrastructure"
    assert row["value"] == 150000.0
    assert row["year"] == 2024
    assert body["pagination"]["next_cursor"] is None


def test_search_contracts_min_value_filter(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.contracts.run_query",
        AsyncMock(return_value={"items": [CONTRACT_ITEM], "total": 1}),
    )
    resp = client.get("/v1/contracts?min_value=200000", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_get_contract_detail(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.contracts.run_query",
        AsyncMock(return_value=CONTRACT_ITEM),
    )
    resp = client.get("/v1/contracts/c001", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == "c001"
    assert data["all_suppliers"][0]["supplier_ico"] == "87654321"
    assert data["publication_date"] == "2024-01-15"


def test_get_contract_detail_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.contracts.run_query",
        AsyncMock(return_value={"error": "not found", "status_code": 404}),
    )
    resp = client.get("/v1/contracts/9999", headers=AUTH_HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "contract_not_found"


def test_invalid_cursor_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies.run_query",
        AsyncMock(side_effect=[EMPTY, EMPTY]),
    )
    resp = client.get("/v1/companies?cursor=!!!notbase64", headers=AUTH_HEADERS)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_cursor"


def test_v1_openapi_excludes_internal_routes(client):
    schema = client.get("/v1/openapi.json").json()
    paths = schema["paths"].keys()
    assert any(p.startswith("/companies") for p in paths)
    assert not any(p.startswith("/api/") for p in paths)
