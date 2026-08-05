"""CORS and docs exposure hardening.

Interactive docs enumerate every route including the operational ones, and
credentialed CORS is pure risk on an API that uses no cookies or sessions.
"""

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app
from uvo_api.config import get_settings


@pytest.fixture
def env(monkeypatch):
    """Patch the environment and reset the cached settings factory.

    ApiSettings is behind an lru_cache, so without clearing it these tests
    would observe whatever the first test in the session constructed.
    """
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _client(env) -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_docs_disabled_by_default(env):
    client = _client(env)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_docs_enabled_when_flag_set(env):
    env.setenv("API_DOCS_ENABLED", "true")
    client = _client(env)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_cors_does_not_allow_credentials(env):
    client = _client(env)
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-credentials") is None


def test_cors_allows_only_get(env):
    client = _client(env)
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    allowed = response.headers.get("access-control-allow-methods", "")
    assert "DELETE" not in allowed
    assert "*" not in allowed
