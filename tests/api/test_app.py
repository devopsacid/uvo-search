"""Tests for the FastAPI application factory."""

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
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" in response.headers
