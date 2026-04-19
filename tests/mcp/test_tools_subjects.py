"""Tests for subject (procurer and supplier) MCP tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.tools.subjects import _run_entity_search, find_procurer, find_supplier


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


async def test_ico_bypass_uses_find_not_aggregate():
    coll = MagicMock()
    coll.count_documents = AsyncMock(return_value=1)
    cursor = MagicMock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{"_id": "x", "ico": "123", "name": "Acme"}])
    coll.find = MagicMock(return_value=cursor)
    db = {"procurers": coll}

    out = await _run_entity_search(
        db, "procurers", "procurer.ico",
        name_query=None, ico="123", sort_by="name", limit=10, offset=0,
    )
    assert out["total"] == 1
    assert out["items"][0]["ico"] == "123"
    coll.find.assert_called_once_with({"ico": "123"})


async def test_name_query_builds_search_pipeline():
    agg = MagicMock()
    agg.to_list = AsyncMock(
        return_value=[{"items": [{"_id": "a", "name": "Fakulta"}], "total": [{"count": 1}]}]
    )
    coll = MagicMock()
    coll.aggregate = MagicMock(return_value=agg)
    db = {"procurers": coll}

    out = await _run_entity_search(
        db, "procurers", "procurer.ico",
        name_query="fakul", ico=None, sort_by="contract_count", limit=5, offset=0,
    )
    assert out["total"] == 1
    (pipeline,) = coll.aggregate.call_args.args
    assert "$search" in pipeline[0]
    assert any("$lookup" in s for s in pipeline)
    assert "$facet" in pipeline[-1]
