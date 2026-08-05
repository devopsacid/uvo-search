"""Operational endpoints require a bearer token; public endpoints do not.

/api/dashboard/{ingestion,ingestion-log,worker-status} expose worker topology,
instance UUIDs and error strings. They must not be anonymous.
"""

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app
from uvo_api.config import get_settings

OPS_PATHS = [
    "/api/dashboard/ingestion",
    "/api/dashboard/ingestion-log",
    "/api/dashboard/worker-status",
]


@pytest.fixture
def make_client(monkeypatch):
    """Build a TestClient with a controlled settings cache.

    ApiSettings is behind an lru_cache, so the cache must be cleared after the
    environment is patched, and again on teardown so later tests do not inherit
    this module's token.
    """

    def _build(ops_token: str | None = "test-ops-token"):
        monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
        if ops_token is None:
            monkeypatch.delenv("API_OPS_TOKEN", raising=False)
        else:
            monkeypatch.setenv("API_OPS_TOKEN", ops_token)
        get_settings.cache_clear()
        return TestClient(create_app())

    yield _build
    get_settings.cache_clear()


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.mark.parametrize("path", OPS_PATHS)
def test_ops_endpoint_rejects_anonymous(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", OPS_PATHS)
def test_ops_endpoint_rejects_wrong_token(client, path):
    response = client.get(path, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", OPS_PATHS)
def test_non_ascii_token_is_rejected_not_a_500(client, path):
    """secrets.compare_digest raises TypeError on non-ASCII str, which would
    turn a hostile header into a 500. It must stay a clean 401.

    Sent as raw bytes because that is what reaches the wire: httpx refuses to
    ASCII-encode a str header, but Starlette decodes incoming bytes as latin-1,
    so a non-ASCII token really can arrive at the dependency.
    """
    response = client.get(
        path, headers={"Authorization": "Bearer á-token".encode("latin-1")}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("path", OPS_PATHS)
def test_ops_endpoint_rejects_wrong_scheme(client, path):
    response = client.get(path, headers={"Authorization": "Basic test-ops-token"})
    assert response.status_code == 401


def test_guard_is_registered_on_exactly_the_ops_routes(client):
    """Introspect the route table rather than calling the handlers, which would
    need a live Mongo. Every ops route carries the guard; public ones do not."""
    from uvo_api.auth import require_ops_token

    def guarded(route) -> bool:
        return any(
            getattr(dep, "dependency", getattr(dep, "call", None)) is require_ops_token
            for dep in getattr(route, "dependencies", [])
        )

    routes = {r.path: r for r in client.app.routes if hasattr(r, "path")}
    for path in OPS_PATHS:
        assert path in routes, f"{path} is not registered"
        assert guarded(routes[path]), f"{path} is missing the ops-token guard"

    for public in ("/health", "/api/dashboard/summary"):
        if public in routes:
            assert not guarded(routes[public]), f"{public} must stay anonymous"


@pytest.mark.parametrize("path", OPS_PATHS)
def test_unconfigured_token_fails_closed(make_client, path):
    """With no token configured the routes are refused, not left open."""
    client = make_client(ops_token="")
    assert client.get(path).status_code == 503


def test_public_endpoint_still_anonymous(client):
    """A public route must not require the ops token."""
    assert client.get("/health").status_code == 200
