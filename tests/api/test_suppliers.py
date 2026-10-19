# tests/api/test_suppliers.py
from contextlib import nullcontext
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_SUPPLIER_RESPONSE = {
    "items": [
        {
            "ico": "87654321",
            "name": "Tech Corp",
            "contract_count": 10,
            "total_value": 5000000.0,
        },
        {"ico": "11111111", "name": "Build Co", "contract_count": 5, "total_value": 2000000.0},
    ],
    "total": 2,
}

SAMPLE_CONTRACTS_FOR_SUPPLIER = {
    "items": [
        {
            "_id": "1001",
            "title": "IT Project",
            "procurer": {"ico": "12345678", "name": "Ministry"},
            "awards": [{"supplier_ico": "87654321", "supplier_name": "Tech Corp"}],
            "final_value": 500000.0,
            "publication_date": "2023-06-01",
            "cpv_code": "72000000",
        }
    ],
    "total": 1,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def test_list_suppliers(client):
    with patch(
        "uvo_api.routers.suppliers.find_suppliers",
        new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE),
    ):
        response = client.get("/api/suppliers")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["ico"] == "87654321"
    assert body["data"][0]["name"] == "Tech Corp"
    assert body["data"][0]["contract_count"] == 10
    assert body["pagination"]["total"] == 2


def test_list_suppliers_search_by_name(client):
    with patch(
        "uvo_api.routers.suppliers.find_suppliers",
        new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE),
    ) as mock:
        client.get("/api/suppliers?q=Tech")
    mock.assert_called_once()
    args = mock.call_args.kwargs
    assert args.get("name_query") == "Tech"


def test_list_suppliers_search_by_ico(client):
    with patch(
        "uvo_api.routers.suppliers.find_suppliers",
        new=AsyncMock(return_value=SAMPLE_SUPPLIER_RESPONSE),
    ) as mock:
        client.get("/api/suppliers?ico=87654321")
    args = mock.call_args.kwargs
    assert args.get("ico") == "87654321"


PROFILE = {
    "contract_count": 400,
    "total_value": 9_000_000.0,
    "spend_by_year": [
        {"year": 2021, "total_value": 4_000_000.0},
        {"year": 2023, "total_value": 5_000_000.0},
    ],
    "years_active": [2021, 2023],
    "partners": [
        {"ico": "12345678", "name": "Ministry", "contract_count": 300, "total_value": 7e6},
        {"ico": "99999999", "name": "Tax Office", "contract_count": 100, "total_value": 2e6},
    ],
    "partner_total_value": 9_000_000.0,
    "partner_count": 2,
    "hhi": 6500.0,
}

SUPPLIER_DOC = {
    "ico": "87654321",
    "name": "Tech Corp",
    "contract_count": 1,
    "total_value": 500000.0,
}


def _entity_patches(supplier):
    return (
        nullcontext(),  # db handle: inert resources from conftest
        patch(
            "uvo_api.routers.suppliers.get_entity_by_ico",
            new=AsyncMock(return_value={"supplier": supplier, "procurer": None}),
        ),
        patch("uvo_api.routers.suppliers.entity_profile", new=AsyncMock(return_value=PROFILE)),
    )


def test_get_supplier_detail(client):
    p1, p2, p3 = _entity_patches(SUPPLIER_DOC)
    with (
        p1,
        p2,
        p3,
        patch(
            "uvo_api.routers.suppliers.search_procurements",
            new=AsyncMock(return_value=SAMPLE_CONTRACTS_FOR_SUPPLIER),
        ),
    ):
        response = client.get("/api/suppliers/87654321")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert body["contract_count"] == 1
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["id"] == "1001"
    # counterparties / years come from the full-population aggregation
    assert [p["ico"] for p in body["top_procurers"]] == ["12345678", "99999999"]
    assert body["years_active"] == [2021, 2023]


def test_get_supplier_summary(client):
    p1, p2, p3 = _entity_patches(SUPPLIER_DOC)
    run = AsyncMock()
    with p1, p2, p3, patch("uvo_api.routers.suppliers.search_procurements", new=run):
        response = client.get("/api/suppliers/87654321/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["ico"] == "87654321"
    assert [y["year"] for y in body["spend_by_year"]] == [2021, 2023]
    run.assert_not_called()


def test_get_supplier_not_found(client):
    p1, p2, p3 = _entity_patches(None)
    with p1, p2, p3:
        response = client.get("/api/suppliers/00000000")
    assert response.status_code == 404
