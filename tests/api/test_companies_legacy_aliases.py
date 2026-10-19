# tests/api/test_companies_legacy_aliases.py
"""The deprecated /api/firma* and /api/firmy paths still answer and stay out of OpenAPI."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

ICO = "12345678"

CORE_AGG = {
    "as_supplier": [{"count": 2, "total": 100.0, "last": "2023-06-15"}],
    "as_procurer": [],
    "cpv": [{"_id": "72000000", "count": 2, "total": 100.0}],
    "spend_by_year": [{"_id": "2023", "total": 100.0}],
}
ENTITY = {"supplier": {"ico": ICO, "name": "Tech Corp s.r.o."}, "procurer": None}
PARTNERS = {
    "total": 1,
    "items": [
        {
            "ico": "11111111",
            "name": "Ministry A",
            "role": "procurer",
            "contract_count": 2,
            "total_value": 100.0,
            "last_contract_at": "2023-06-15",
        }
    ],
}
MARKET = [{"_id": "72000000", "count": 5, "total": 500.0}]
FIND = {
    "items": [{"ico": "AAA00001", "name": "Alpha Corp", "contract_count": 3, "total_value": 9.0}],
    "total": 1,
}


async def _top(db, ico, role, limit=5):
    return []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


@pytest.fixture
def patched():
    base = "uvo_api.routers.companies"
    with (
        patch(f"{base}.get_entity_by_ico", new=AsyncMock(return_value=ENTITY)),
        patch(f"{base}.top_contracts_by_value", new=_top),
        patch(f"{base}._company_core_agg", new=AsyncMock(return_value=CORE_AGG)),
        patch(f"{base}._company_partners_agg", new=AsyncMock(return_value=PARTNERS)),
        patch(f"{base}._market_cpv_agg", new=AsyncMock(return_value=MARKET)),
        patch(f"{base}.find_suppliers", new=AsyncMock(return_value=FIND)),
        patch(f"{base}.find_procurers", new=AsyncMock(return_value={"items": []})),
    ):
        yield


ALIAS_PAIRS = [
    (f"/api/firma/{ICO}", f"/api/companies/{ICO}"),
    (f"/api/firma/{ICO}/partneri", f"/api/companies/{ICO}/partners"),
    (
        f"/api/firma/{ICO}/partneri?role=supplier&limit=5",
        f"/api/companies/{ICO}/partners?role=supplier&limit=5",
    ),
    (f"/api/firma/{ICO}/cpv-profile", f"/api/companies/{ICO}/cpv-profile"),
    ("/api/firmy", "/api/companies"),
    ("/api/firmy?q=alpha&limit=1", "/api/companies?q=alpha&limit=1"),
]


@pytest.mark.parametrize(("legacy", "canonical"), ALIAS_PAIRS)
def test_legacy_alias_matches_canonical_body(client, patched, legacy, canonical):
    old = client.get(legacy)
    new = client.get(canonical)
    assert new.status_code == 200
    assert old.status_code == 200
    assert old.json() == new.json()


def test_legacy_aliases_absent_from_openapi(monkeypatch):
    # /openapi.json is disabled by default (docs_enabled), so build the schema directly.
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    paths = create_app().openapi()["paths"]
    assert "/api/companies" in paths
    assert "/api/companies/{ico}" in paths
    assert "/api/companies/{ico}/partners" in paths
    assert "/api/companies/{ico}/cpv-profile" in paths
    leaked = [p for p in paths if "firma" in p or "firmy" in p]
    assert leaked == []


def test_legacy_alias_unknown_company_is_404(client):
    with (
        patch(
            "uvo_api.routers.companies.get_entity_by_ico",
            new=AsyncMock(return_value={"supplier": None, "procurer": None}),
        ),
        patch("uvo_api.routers.companies.top_contracts_by_value", new=_top),
        patch("uvo_api.routers.companies._company_core_agg", new=AsyncMock(return_value={})),
    ):
        response = client.get("/api/firma/00000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "Company not found"
