"""Tests for the FastAPI application factory."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.api._deps import deps
from uvo_api.app import create_app
from uvo_api.db import get_db, get_index_probe


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


def _probe(ready: bool) -> MagicMock:
    probe = MagicMock()
    probe.ready = AsyncMock(return_value=ready)
    return probe


def test_readyz_ok_when_mongo_answers_and_indexes_present(client, monkeypatch):
    monkeypatch.setattr("uvo_api.app.mongo_ready", AsyncMock(return_value=True))
    with deps(client, get_db, MagicMock()), deps(client, get_index_probe, _probe(True)):
        response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readyz_503_when_mongo_down_but_health_still_ok(client, monkeypatch):
    monkeypatch.setattr("uvo_api.app.mongo_ready", AsyncMock(return_value=False))
    with deps(client, get_db, MagicMock()), deps(client, get_index_probe, _probe(True)):
        assert client.get("/readyz").status_code == 503
    # liveness is unconditional
    assert client.get("/health").status_code == 200


def test_readyz_503_when_required_search_indexes_missing(client, monkeypatch):
    monkeypatch.setattr("uvo_api.app.mongo_ready", AsyncMock(return_value=True))
    with deps(client, get_db, MagicMock()), deps(client, get_index_probe, _probe(False)):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert client.get("/health").status_code == 200
