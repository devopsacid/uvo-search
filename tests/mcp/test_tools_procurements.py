"""Tests for procurement MCP tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.tools.procurements import (
    _search_mongo_procurements,
    get_procurement_detail,
    search_completed_procurements,
)


@pytest.fixture(autouse=True)
def clear_procurements_cache():
    _search_mongo_procurements.cache_clear()
    yield
    _search_mongo_procurements.cache_clear()


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


async def test_pipeline_filters_inside_search_and_counts_via_search_meta():
    items = MagicMock()
    items.to_list = AsyncMock(return_value=[{"_id": "n1", "title": "X"}])
    meta = MagicMock()
    meta.to_list = AsyncMock(return_value=[{"count": {"total": 1}}])
    db = MagicMock()
    db.notices.aggregate = MagicMock(side_effect=[items, meta])

    out = await _search_mongo_procurements(db, text_query="fakulta", date_from="2024-01-01")
    assert out["total"] == 1
    pipeline = db.notices.aggregate.call_args_list[0].args[0]
    filters = pipeline[0]["$search"]["compound"]["filter"]
    assert {"equals": {"path": "notice_type", "value": "contract_award"}} in filters
    assert {"range": {"path": "publication_date", "gte": "2024-01-01"}} in filters
    assert not any("$facet" in s for s in pipeline)
    assert "$searchMeta" in db.notices.aggregate.call_args_list[1].args[0][0]


class TestGetProcurementDetail:
    @pytest.mark.asyncio
    async def test_no_mongo_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await get_procurement_detail(ctx, "1001")

        assert "error" in result
        assert result["status_code"] == 503
        assert "MongoDB" in result["error"]
