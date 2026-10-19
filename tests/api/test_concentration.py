# tests/api/test_concentration.py
"""Tests for procurer concentration endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

SAMPLE_PROCURER = {
    "ico": "12345678",
    "name": "Ministry of Finance",
    "contract_count": 3,
    "total_value": 1800000.0,
}

# Full-population profile as produced by uvo_core's entity_profile aggregation.
SAMPLE_PROFILE = {
    "contract_count": 3,
    "total_value": 1_800_000.0,
    "spend_by_year": [{"year": 2024, "total_value": 1_800_000.0}],
    "years_active": [2024],
    "partners": [
        {"ico": "AAA", "name": "Alpha", "contract_count": 2, "total_value": 1_500_000.0},
        {"ico": "BBB", "name": "Beta", "contract_count": 1, "total_value": 300_000.0},
    ],
    "partner_total_value": 1_800_000.0,
    "partner_count": 2,
    "hhi": 10_000 * (1_500_000**2 + 300_000**2) / 1_800_000**2,
}


def _patches(procurer, profile=None):
    return (
        patch("uvo_api.routers.procurers.get_db", return_value=MagicMock()),
        patch(
            "uvo_api.routers.procurers.get_entity_by_ico",
            new=AsyncMock(return_value={"supplier": None, "procurer": procurer}),
        ),
        patch(
            "uvo_api.routers.procurers.entity_profile",
            new=AsyncMock(return_value=profile or SAMPLE_PROFILE),
        ),
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


def test_concentration_happy_path(client):
    p1, p2, p3 = _patches(SAMPLE_PROCURER)
    with p1, p2, p3:
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
    # HHI = (83.33)^2 + (16.67)^2 ~= 7222
    assert body["hhi"] == pytest.approx(7222.2, abs=0.1)


def test_concentration_uses_full_population_profile(client):
    """HHI comes from the aggregated profile, not from a 100-row contract sample."""
    p1, p2, p3 = _patches(SAMPLE_PROCURER)
    with p1, p2, p3 as profile_mock:
        client.get("/api/procurers/12345678/concentration?top_n=5")
    args = profile_mock.call_args.args
    assert args[1:] == ("12345678", "procurer", 5)


def test_concentration_not_found(client):
    p1, p2, p3 = _patches(None)
    with p1, p2, p3:
        response = client.get("/api/procurers/00000000/concentration")
    assert response.status_code == 404


def test_concentration_no_spend(client):
    empty = {**SAMPLE_PROFILE, "partners": [], "partner_total_value": 0.0, "hhi": 0.0}
    p1, p2, p3 = _patches(SAMPLE_PROCURER, empty)
    with p1, p2, p3:
        response = client.get("/api/procurers/12345678/concentration")
    assert response.status_code == 200
    assert response.json()["hhi"] == 0.0
    assert response.json()["top_suppliers"] == []


def test_concentration_top_n_param(client):
    profile = {**SAMPLE_PROFILE, "partners": SAMPLE_PROFILE["partners"][:1]}
    p1, p2, p3 = _patches(SAMPLE_PROCURER, profile)
    with p1, p2, p3:
        response = client.get("/api/procurers/12345678/concentration?top_n=1")
    assert response.status_code == 200
    body = response.json()
    assert len(body["top_suppliers"]) == 1
    assert body["top_suppliers"][0]["ico"] == "AAA"
