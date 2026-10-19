# tests/api/test_graph.py
"""Tests for graph endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.api._deps import deps
from uvo_api.app import create_app
from uvo_api.db import require_neo4j_driver

SAMPLE_EGO = {
    "nodes": [
        {"id": "12345678", "label": "Ministry", "type": "procurer", "value": 5},
        {"id": "87654321", "label": "Tech Corp", "type": "supplier", "value": 3},
    ],
    "edges": [
        {"from": "12345678", "to": "87654321", "label": "3 zmlúv", "value": 900000.0},
    ],
}

SAMPLE_CPV = {
    "nodes": [
        {"id": "P1", "label": "Procurer A", "type": "procurer"},
        {"id": "S1", "label": "Supplier B", "type": "supplier"},
    ],
    "edges": [
        {"from": "P1", "to": "S1", "label": "2 zmlúv", "value": 400000.0},
    ],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return TestClient(create_app())


@pytest.fixture
def neo4j(client):
    """A connected (mock) Neo4j driver for the graph routes."""
    with deps(client, require_neo4j_driver, MagicMock(name="neo4j_driver")):
        yield


def test_ego_graph_happy_path(client, neo4j):
    with patch("uvo_api.routers.graph.ego_network", new=AsyncMock(return_value=SAMPLE_EGO)) as ego:
        response = client.get("/api/graph/ego/12345678?hops=2")
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    node_ids = {n["data"]["id"] for n in body["nodes"]}
    assert "12345678" in node_ids
    assert "87654321" in node_ids
    edge = body["edges"][0]
    assert edge["data"]["source"] == "12345678"
    assert edge["data"]["target"] == "87654321"
    assert edge["data"]["value"] == 900000.0
    assert ego.await_args.args[1:] == ("12345678", 2)


def test_ego_graph_not_found(client, neo4j):
    with patch(
        "uvo_api.routers.graph.ego_network", new=AsyncMock(return_value={"nodes": [], "edges": []})
    ):
        response = client.get("/api/graph/ego/00000000")
    assert response.status_code == 404


def test_ego_graph_hops_validation(client, neo4j):
    response = client.get("/api/graph/ego/12345678?hops=5")
    assert response.status_code == 422


def test_cpv_graph_happy_path(client, neo4j):
    with patch("uvo_api.routers.graph.cpv_network", new=AsyncMock(return_value=SAMPLE_CPV)) as cpv:
        response = client.get("/api/graph/cpv/72000000?year=2024")
    assert response.status_code == 200
    assert cpv.await_args.args[1:] == ("72000000", 2024)
    body = response.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["data"]["source"] == "P1"
    assert body["edges"][0]["data"]["target"] == "S1"


def test_cpv_graph_missing_year(client, neo4j):
    response = client.get("/api/graph/cpv/72000000")
    assert response.status_code == 422


def test_graph_503_on_neo4j_down(client):
    """No Neo4j driver configured: typed BackendUnavailable -> 503, not an empty 200."""
    response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503
    response = client.get("/api/graph/cpv/72000000?year=2024")
    assert response.status_code == 503
