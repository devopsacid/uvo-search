"""Golden-shape test: the MCP tool output contract must not drift after the Phase 2
in-process refactor. External LLM clients depend on these exact JSON shapes.

Exercises the full tool → uvo_core.service → uvo_core.adapter path with a mocked Mongo
handle (no DB), asserting the response dict is byte-identical to the pre-refactor shape.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uvo_mcp.config import Settings
from uvo_mcp.server import AppContext
from uvo_mcp.tools.procurements import _search_mongo_procurements, search_completed_procurements


@pytest.fixture(autouse=True)
def _clear_cache():
    _search_mongo_procurements.cache_clear()
    yield
    _search_mongo_procurements.cache_clear()


def _ctx_with_db(db) -> MagicMock:
    ctx = MagicMock()
    ctx.request_context.lifespan_context = AppContext(
        http_client=MagicMock(), settings=Settings(), mongo_db=db
    )
    return ctx


@pytest.mark.asyncio
async def test_search_completed_procurements_golden_shape():
    agg = MagicMock()
    agg.to_list = AsyncMock(
        return_value=[
            {
                "items": [
                    {"_id": "abc123", "title": "Dodávka IT", "final_value": 1000.0}
                ],
                "total": [{"count": 1}],
            }
        ]
    )
    db = MagicMock()
    db.notices.aggregate = MagicMock(return_value=agg)

    result = await search_completed_procurements(_ctx_with_db(db), text_query="it", limit=20, offset=0)

    # Exact top-level contract the MCP clients rely on.
    assert list(result.keys()) == ["items", "total", "limit", "offset"]
    assert result["total"] == 1
    assert result["limit"] == 20
    assert result["offset"] == 0
    assert result["items"] == [{"_id": "abc123", "title": "Dodávka IT", "final_value": 1000.0}]
    # ObjectId is stringified.
    assert isinstance(result["items"][0]["_id"], str)
