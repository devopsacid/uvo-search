"""Offset must be bounded — an unbounded $skip is a cheap DoS primitive.

Mongo walks and discards every skipped document, so an anonymous request with
$skip: 50_000_000 costs a full collection scan.
"""

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app
from uvo_api.config import get_settings

PAGINATED_PATHS = ["/api/contracts", "/api/suppliers", "/api/procurers"]

MAX_OFFSET = 10_000


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_MONGODB_URI", "mongodb://test:test@localhost:27017")
    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


@pytest.mark.parametrize("path", PAGINATED_PATHS)
def test_excessive_offset_is_rejected(client, path):
    response = client.get(path, params={"offset": 50_000_000})
    assert response.status_code == 422


@pytest.mark.parametrize("path", PAGINATED_PATHS)
def test_offset_just_above_limit_is_rejected(client, path):
    response = client.get(path, params={"offset": MAX_OFFSET + 1})
    assert response.status_code == 422


@pytest.mark.parametrize("path", PAGINATED_PATHS)
def test_negative_offset_is_rejected(client, path):
    response = client.get(path, params={"offset": -1})
    assert response.status_code == 422
