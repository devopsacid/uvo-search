from unittest.mock import AsyncMock, MagicMock

from uvo_mcp.tools.autocomplete import _run_autocomplete


async def test_autocomplete_parallel_across_collections():
    def make_coll(rows):
        coll = MagicMock()
        agg = MagicMock()
        agg.to_list = AsyncMock(return_value=rows)
        coll.aggregate = MagicMock(return_value=agg)
        return coll

    db = {
        "procurers": make_coll([{"_id": "p1", "ico": "111", "name": "Fakulta A"}]),
        "suppliers": make_coll([{"_id": "s1", "ico": "222", "name": "Firma B"}]),
        "notices":   make_coll([{"_id": "n1", "source_id": "N1", "title": "Dodávka"}]),
    }

    out = await _run_autocomplete(db, "fak", types=["procurer", "supplier", "notice"], limit=5)
    types = {r["type"] for r in out["results"]}
    assert types == {"procurer", "supplier", "notice"}
    procurer = next(r for r in out["results"] if r["type"] == "procurer")
    assert procurer["label"] == "Fakulta A"
    assert procurer["sublabel"] == "IČO 111"


async def test_autocomplete_empty_query_returns_empty():
    out = await _run_autocomplete({}, "", types=["procurer"], limit=5)
    assert out == {"results": []}
