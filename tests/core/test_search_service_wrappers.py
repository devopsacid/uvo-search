"""Typed entity lookups and the single page-clamp helper shared by API and MCP."""

from unittest.mock import AsyncMock

import pytest

from uvo_core.errors import BackendUnavailable
from uvo_core.services import search as search_service
from uvo_core.services.search import MAX_OFFSET, MAX_PAGE_SIZE, clamp_page


def test_clamp_page_bounds_limit_and_offset():
    assert clamp_page(1000, 50_000) == (MAX_PAGE_SIZE, MAX_OFFSET)
    assert clamp_page(20, -5) == (20, 0)
    assert clamp_page(20) == (20, 0)


def test_clamp_page_honours_a_caller_specific_max_limit():
    assert clamp_page(100, 0, max_limit=50) == (50, 0)


@pytest.mark.asyncio
async def test_find_suppliers_uses_supplier_lookup_and_clamps(monkeypatch):
    entity_search = AsyncMock(return_value={"items": [], "total": 0})
    monkeypatch.setattr(search_service, "entity_search", entity_search)

    await search_service.find_suppliers(object(), name_query="acme", limit=500, offset=-1)

    args, kwargs = entity_search.await_args
    assert args[1:] == ("suppliers", "awards.supplier.ico")
    assert kwargs == {
        "name_query": "acme",
        "ico": None,
        "sort_by": "name",
        "limit": MAX_PAGE_SIZE,
        "offset": 0,
    }


@pytest.mark.asyncio
async def test_find_procurers_uses_procurer_lookup(monkeypatch):
    entity_search = AsyncMock(return_value={"items": [], "total": 0})
    monkeypatch.setattr(search_service, "entity_search", entity_search)

    await search_service.find_procurers(object(), ico="12345678")

    args, kwargs = entity_search.await_args
    assert args[1:] == ("procurers", "procurer.ico")
    assert kwargs["ico"] == "12345678"


def test_backend_unavailable_keeps_a_reason_for_logs():
    err = BackendUnavailable("Neo4j not connected")
    assert err.reason == "Neo4j not connected"
    assert str(err) == "Neo4j not connected"
