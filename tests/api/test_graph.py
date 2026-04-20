# tests/api/test_graph.py
"""Tests for graph endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

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


def test_ego_graph_happy_path(client):
    with patch("uvo_api.routers.graph.call_tool", new=AsyncMock(return_value=SAMPLE_EGO)):
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


def test_ego_graph_not_found(client):
    with patch("uvo_api.routers.graph.call_tool", new=AsyncMock(return_value={"nodes": [], "edges": []})):
        response = client.get("/api/graph/ego/00000000")
    assert response.status_code == 404


def test_ego_graph_hops_validation(client):
    response = client.get("/api/graph/ego/12345678?hops=5")
    assert response.status_code == 422


def test_cpv_graph_happy_path(client):
    with patch("uvo_api.routers.graph.call_tool", new=AsyncMock(return_value=SAMPLE_CPV)):
        response = client.get("/api/graph/cpv/72000000?year=2024")
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["data"]["source"] == "P1"
    assert body["edges"][0]["data"]["target"] == "S1"


def test_cpv_graph_missing_year(client):
    response = client.get("/api/graph/cpv/72000000")
    assert response.status_code == 422


def test_graph_503_on_neo4j_down(client):
    with patch(
        "uvo_api.routers.graph.call_tool",
        new=AsyncMock(return_value={"error": "Neo4j not connected", "status_code": 503}),
    ):
        response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503
