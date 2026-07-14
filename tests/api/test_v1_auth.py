"""Auth + rate limiting for the public /v1 API."""

from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

ACTIVE_FREE_KEY = {"_id": "key_free", "plan": "free", "owner_email": "a@b.sk", "active": True}
ACTIVE_PRO_KEY = {"_id": "key_pro", "plan": "pro", "owner_email": "a@b.sk", "active": True}
INACTIVE_KEY = {"_id": "key_x", "plan": "free", "owner_email": "a@b.sk", "active": False}

EMPTY_ENTITY = {"items": [], "total": 0}


@pytest.fixture
def fake_redis_server():
    return fakeredis.FakeServer()


@pytest.fixture
def fake_redis(fake_redis_server):
    return fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True)


@pytest.fixture
def client(monkeypatch, fake_redis):
    monkeypatch.setenv("API_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setattr("uvo_api.ratelimit.get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(
        "uvo_api.routers.v1.companies.run_query", AsyncMock(return_value=EMPTY_ENTITY)
    )
    app = create_app()
    return TestClient(app)


def _set_key(monkeypatch, doc):
    monkeypatch.setattr("uvo_api.auth._lookup_key", AsyncMock(return_value=doc))


def test_missing_api_key_returns_401(client, monkeypatch):
    _set_key(monkeypatch, None)
    resp = client.get("/v1/companies")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "missing_api_key"


def test_invalid_api_key_returns_401(client, monkeypatch):
    _set_key(monkeypatch, None)
    resp = client.get("/v1/companies", headers={"X-API-Key": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_api_key"


def test_inactive_api_key_returns_401(client, monkeypatch):
    _set_key(monkeypatch, INACTIVE_KEY)
    resp = client.get("/v1/companies", headers={"X-API-Key": "raw"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_api_key"


def test_valid_api_key_returns_200(client, monkeypatch):
    _set_key(monkeypatch, ACTIVE_PRO_KEY)
    resp = client.get("/v1/companies", headers={"X-API-Key": "raw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["pagination"]["next_cursor"] is None


def test_rate_limit_exceeded_returns_429(client, monkeypatch):
    _set_key(monkeypatch, ACTIVE_FREE_KEY)  # free = 30/min
    headers = {"X-API-Key": "raw"}
    for _ in range(30):
        assert client.get("/v1/companies", headers=headers).status_code == 200
    resp = client.get("/v1/companies", headers=headers)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limit_exceeded"
    assert "Retry-After" in resp.headers
    assert resp.json()["error"]["retry_after"] >= 0


def test_usage_metered_to_redis_stream(client, monkeypatch, fake_redis_server):
    _set_key(monkeypatch, ACTIVE_PRO_KEY)
    client.get("/v1/companies", headers={"X-API-Key": "raw"})
    reader = fakeredis.FakeStrictRedis(server=fake_redis_server, decode_responses=True)
    entries = reader.xrange("api:usage")
    assert len(entries) == 1
    fields = entries[0][1]
    assert fields["key_id"] == "key_pro"
    assert fields["endpoint"] == "/v1/companies"
    assert fields["status"] == "200"
