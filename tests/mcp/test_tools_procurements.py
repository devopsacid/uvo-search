"""Tests for procurement MCP tools."""

import pytest

from uvo_mcp.tools.procurements import get_procurement_detail, search_completed_procurements


class TestSearchCompletedProcurements:
    @pytest.mark.asyncio
    async def test_no_mongo_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await search_completed_procurements(ctx)

        assert "error" in result
        assert result["status_code"] == 503
        assert "MongoDB" in result["error"]

    @pytest.mark.asyncio
    async def test_no_mongo_with_params_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await search_completed_procurements(
            ctx,
            text_query="software",
            cpv_codes=["72000000-5"],
            date_from="2024-01-01",
            date_to="2024-12-31",
        )

        assert "error" in result
        assert result["status_code"] == 503


class TestGetProcurementDetail:
    @pytest.mark.asyncio
    async def test_no_mongo_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await get_procurement_detail(ctx, "1001")

        assert "error" in result
        assert result["status_code"] == 503
        assert "MongoDB" in result["error"]
