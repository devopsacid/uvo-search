"""Tests for subject (procurer and supplier) MCP tools."""

import pytest

from uvo_mcp.tools.subjects import find_procurer, find_supplier


class TestFindProcurer:
    @pytest.mark.asyncio
    async def test_no_mongo_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await find_procurer(ctx)

        assert "error" in result
        assert result["status_code"] == 503
        assert "MongoDB" in result["error"]

    @pytest.mark.asyncio
    async def test_no_mongo_with_params_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await find_procurer(ctx, name_query="Ministry", ico="00151742")

        assert "error" in result
        assert result["status_code"] == 503


class TestFindSupplier:
    @pytest.mark.asyncio
    async def test_no_mongo_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await find_supplier(ctx)

        assert "error" in result
        assert result["status_code"] == 503
        assert "MongoDB" in result["error"]

    @pytest.mark.asyncio
    async def test_no_mongo_with_params_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await find_supplier(ctx, name_query="Tech", ico="87654321")

        assert "error" in result
        assert result["status_code"] == 503
