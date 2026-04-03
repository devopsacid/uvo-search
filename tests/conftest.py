"""Shared test fixtures for UVO Search tests."""

from unittest.mock import MagicMock

import httpx
import pytest
import respx

from uvo_mcp.config import Settings
from uvo_mcp.server import AppContext


class MockResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data
        self.text = str(json_data)

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://test.example.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


@pytest.fixture
def mock_http_client():
    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        client = httpx.AsyncClient(
            base_url="https://www.uvostat.sk",
            headers={"ApiToken": "test-token"},
            timeout=30.0,
        )
        yield client, mock


@pytest.fixture
def mock_context(mock_http_client):
    client, mock = mock_http_client
    settings = Settings(
        uvostat_api_token="test-token",
        uvostat_base_url="https://www.uvostat.sk",
    )
    app_ctx = AppContext(http_client=client, settings=settings)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    return ctx, mock
