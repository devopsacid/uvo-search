"""Value filtering must happen in the query, not after pagination.

Adapted from the Phase 2 plan's MCP-era test: contracts.py no longer calls
call_tool, it calls get_notice_repo().search(...) directly (uvo_core.services
in-process). Investigation found this defect was already fixed as part of the
architecture refactor — search_procurements() (uvo_core/adapters/mongo/
procurements.py) applies value_min/value_max inside the $match stage and
returns `total` from a $facet count over the filtered set, not the page
length. This test pins that behaviour against regression.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from uvo_api.app import create_app

RESPONSE = {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.fixture
def client():
    return TestClient(create_app())


def _mock_repo(search_return: dict) -> MagicMock:
    repo = MagicMock()
    repo.search = AsyncMock(return_value=search_return)
    return repo


def test_value_bounds_are_forwarded_to_the_query(client):
    repo = _mock_repo(RESPONSE)
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        client.get("/api/contracts", params={"value_min": 1000, "value_max": 5000})
    kwargs = repo.search.await_args.kwargs
    assert kwargs["value_min"] == 1000
    assert kwargs["value_max"] == 5000


def test_total_comes_from_the_query_not_the_page(client):
    """total must reflect the full filtered result set, not the current page."""
    repo = _mock_repo({"items": [], "total": 4321, "limit": 20, "offset": 0})
    with patch("uvo_api.routers.contracts.get_notice_repo", return_value=repo):
        response = client.get("/api/contracts", params={"value_min": 1000})
    assert response.json()["pagination"]["total"] == 4321
