"""Tests for the FastAPI application factory."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    app = create_app()
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "uvo-api"}


def test_cors_header_present(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5174"})
    assert "access-control-allow-origin" in response.headers


def test_readyz_ok_when_mongo_answers(client, monkeypatch):
    monkeypatch.setattr("uvo_api.app.mongo_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("uvo_api.app.get_db", MagicMock())
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readyz_503_when_mongo_down_but_health_still_ok(client, monkeypatch):
    monkeypatch.setattr("uvo_api.app.mongo_ready", AsyncMock(return_value=False))
    monkeypatch.setattr("uvo_api.app.get_db", MagicMock())
    assert client.get("/readyz").status_code == 503
    # liveness is unconditional
    assert client.get("/health").status_code == 200
