"""A backend outage must surface as 5xx, never as an empty 200 or a leaked message.

Adapted from the Phase 2 plan's McpToolError-era test: the API no longer hops
through MCP (uvo_api.mcp_client / McpToolError are gone), so the two failure
shapes exercised here are the ones the current uvo_core.services architecture
can actually produce — an {"error": ...} envelope from run_query (e.g. Neo4j
down) and an unhandled exception from a query function (e.g. Mongo down).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

ERROR_ENVELOPE = {"error": "Neo4j not connected", "status_code": 503}


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_error_envelope_is_not_an_empty_200(client):
    with patch("uvo_api.routers.graph.run_query", new=AsyncMock(return_value=ERROR_ENVELOPE)):
        response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503


def test_error_envelope_detail_does_not_leak_the_raw_message(client):
    with patch("uvo_api.routers.graph.run_query", new=AsyncMock(return_value=ERROR_ENVELOPE)):
        response = client.get("/api/graph/ego/12345678")
    assert "Neo4j not connected" not in response.text


def test_unhandled_exception_becomes_503_not_empty_200(client):
    with patch(
        "uvo_api.routers.graph.run_query",
        new=AsyncMock(side_effect=RuntimeError("mongodb://uvo:s3cret@mongo:27017 refused")),
    ):
        response = client.get("/api/graph/ego/12345678")
    assert response.status_code == 503


def test_unhandled_exception_detail_does_not_leak_credentials(client):
    with patch(
        "uvo_api.routers.graph.run_query",
        new=AsyncMock(side_effect=RuntimeError("mongodb://uvo:s3cret@mongo:27017 refused")),
    ):
        response = client.get("/api/graph/ego/12345678")
    assert "s3cret" not in response.text
