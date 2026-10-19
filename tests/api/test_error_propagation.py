"""A backend outage must surface as 503, never as an empty 200 or a leaked message.

Routers call uvo_core services in-process, so failures arrive as exceptions: the typed
``BackendUnavailable`` (a dependency known to be unavailable, e.g. Neo4j not configured)
or the driver's own exception (Mongo/Neo4j unreachable). One exception handler maps
them all to a generic 503.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError

from tests.api._deps import deps
from uvo_api.app import create_app
from uvo_api.db import Resources, install_resources, require_neo4j_driver
from uvo_core.errors import BackendUnavailable

LEAKY = "mongodb://uvo:s3cret@mongo:27017 refused"


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_missing_neo4j_is_a_503_not_an_empty_200(client):
    response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503
    assert response.json() == {"detail": "Backend temporarily unavailable"}


def test_backend_unavailable_detail_does_not_leak_the_raw_message(client):
    response = client.get("/api/graph/ego/12345678")
    assert "Neo4j not connected" not in response.text


@pytest.mark.parametrize(
    "error",
    [
        BackendUnavailable(LEAKY),
        ServerSelectionTimeoutError(LEAKY),
        AutoReconnect(LEAKY),
        ServiceUnavailable(LEAKY),
        RuntimeError(LEAKY),
    ],
    ids=lambda e: type(e).__name__,
)
def test_backend_errors_become_503_without_leaking(client, error):
    with deps(client, require_neo4j_driver, MagicMock()):
        with patch("uvo_api.routers.graph.ego_network", new=AsyncMock(side_effect=error)):
            response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503
    assert "s3cret" not in response.text


def test_mongo_outage_on_a_list_endpoint_is_503_not_an_empty_list(client):
    outage = ServerSelectionTimeoutError(LEAKY)
    with patch("uvo_api.routers.suppliers.find_suppliers", new=AsyncMock(side_effect=outage)):
        response = client.get("/api/suppliers")
    assert response.status_code == 503
    assert "data" not in response.json()
    assert "s3cret" not in response.text


def test_mongo_outage_on_repository_route_is_503(client):
    repo = MagicMock()
    repo.search = AsyncMock(side_effect=AutoReconnect(LEAKY))
    from uvo_api.db import get_notice_repo

    with deps(client, get_notice_repo, repo):
        response = client.get("/api/contracts")
    assert response.status_code == 503


def test_v1_backend_outage_uses_public_error_envelope(client):
    install_resources(
        client.app,
        Resources(
            mongo_client=MagicMock(),
            db=MagicMock(),
            redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        ),
    )
    active_key = {"_id": "k1", "plan": "pro", "active": True}
    with (
        patch("uvo_api.auth._lookup_key", new=AsyncMock(return_value=active_key)),
        patch(
            "uvo_api.routers.v1.companies.find_suppliers",
            new=AsyncMock(side_effect=ServerSelectionTimeoutError(LEAKY)),
        ),
    ):
        response = client.get("/v1/companies?q=x", headers={"X-API-Key": "raw"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "backend_unavailable"
    assert "s3cret" not in response.text


def test_unhandled_exception_becomes_503_not_empty_200(client):
    with deps(client, require_neo4j_driver, MagicMock()):
        with patch(
            "uvo_api.routers.graph.ego_network", new=AsyncMock(side_effect=RuntimeError(LEAKY))
        ):
            response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503
