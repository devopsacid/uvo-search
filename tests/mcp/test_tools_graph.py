"""Tests for graph MCP tools."""

from unittest.mock import MagicMock

import pytest

from uvo_mcp.tools.graph import (
    find_related_organisations,
    find_supplier_concentration,
    get_procurement_network,
)


def make_ctx(neo4j_driver=None):
    from uvo_mcp.config import Settings
    from uvo_mcp.server import AppContext

    settings = Settings(storage_secret="test")
    ctx = MagicMock()
    ctx.request_context.lifespan_context = AppContext(
        http_client=MagicMock(),
        settings=settings,
        neo4j_driver=neo4j_driver,
    )
    return ctx


@pytest.mark.asyncio
async def test_find_supplier_concentration_no_neo4j():
    ctx = make_ctx(neo4j_driver=None)
    result = await find_supplier_concentration(ctx, procurer_ico="12345678")
    assert result["status_code"] == 503


@pytest.mark.asyncio
async def test_find_related_organisations_no_neo4j():
    ctx = make_ctx(neo4j_driver=None)
    result = await find_related_organisations(ctx, ico="12345678")
    assert result["status_code"] == 503


@pytest.mark.asyncio
async def test_get_procurement_network_no_neo4j():
    ctx = make_ctx(neo4j_driver=None)
    result = await get_procurement_network(ctx, cpv_code="72000000-5", year=2024)
    assert result["status_code"] == 503
