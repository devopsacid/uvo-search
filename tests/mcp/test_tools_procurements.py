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


from unittest.mock import AsyncMock, MagicMock


async def test_pipeline_has_search_match_and_facet():
    agg = MagicMock()
    agg.to_list = AsyncMock(
        return_value=[{"items": [{"_id": "n1", "title": "X"}], "total": [{"count": 1}]}]
    )
    db = MagicMock()
    db.notices.aggregate = MagicMock(return_value=agg)

    from uvo_mcp.tools.procurements import _search_mongo_procurements

    out = await _search_mongo_procurements(db, text_query="fakulta", date_from="2024-01-01")
    assert out["total"] == 1
    (pipeline,) = db.notices.aggregate.call_args.args
    assert "$search" in pipeline[0]
    assert pipeline[1]["$match"]["notice_type"] == "contract_award"
    assert pipeline[1]["$match"]["publication_date"] == {"$gte": "2024-01-01"}
    assert "$facet" in pipeline[2]


class TestGetProcurementDetail:
    @pytest.mark.asyncio
    async def test_no_mongo_returns_503(self, mock_context):
        ctx, _ = mock_context

        result = await get_procurement_detail(ctx, "1001")

        assert "error" in result
        assert result["status_code"] == 503
        assert "MongoDB" in result["error"]
