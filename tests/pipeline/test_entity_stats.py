"""Tests for denormalized entity-stats recompute (loaders.mongo)."""

import json
from unittest.mock import AsyncMock, MagicMock

from pymongo import UpdateOne

from uvo_pipeline.loaders.mongo import _entity_stats_pipeline, recompute_entity_stats


def _has(pipeline, token: str) -> bool:
    return token in json.dumps(pipeline)


def test_procurer_pipeline_groups_by_scalar_ico_without_setunion():
    pipeline = _entity_stats_pipeline("procurers")
    assert pipeline[0]["$match"] == {"procurer.ico": {"$nin": [None, ""]}}
    assert pipeline[-1]["$group"]["_id"] == "$procurer.ico"
    # Scalar field — no notice-level array dedup needed.
    assert not _has(pipeline, "$setUnion")
    assert not _has(pipeline, "$unwind")


def test_supplier_pipeline_dedups_awards_per_notice_via_setunion():
    pipeline = _entity_stats_pipeline("suppliers")
    # $setUnion collapses multiple awards to the same supplier within one notice
    # so a notice is counted once (matches the old $lookup notice-level count).
    assert _has(pipeline, "$setUnion")
    assert pipeline[-1]["$group"]["_id"] == "$_icos"


def _fake_db(procurer_rows, supplier_rows):
    def aiter(rows):
        async def gen():
            for r in rows:
                yield r

        cur = MagicMock()
        cur.__aiter__ = lambda self: gen()
        return cur

    notices = MagicMock()
    notices.aggregate = MagicMock(side_effect=[aiter(procurer_rows), aiter(supplier_rows)])

    collections = {
        "procurers": MagicMock(bulk_write=AsyncMock(return_value=MagicMock(modified_count=len(procurer_rows)))),
        "suppliers": MagicMock(bulk_write=AsyncMock(return_value=MagicMock(modified_count=len(supplier_rows)))),
    }
    db = MagicMock()
    db.notices = notices
    db.__getitem__ = lambda self, k: collections[k]
    return db, collections


async def test_recompute_writes_ico_keyed_updates_and_counts():
    db, colls = _fake_db(
        procurer_rows=[{"_id": "111", "contract_count": 3, "total_value": 900.0}],
        supplier_rows=[
            {"_id": "222", "contract_count": 2, "total_value": 500.0},
            {"_id": "333", "contract_count": 1, "total_value": 0},
        ],
    )
    out = await recompute_entity_stats(db)

    assert out == {
        "procurers_matched": 1,
        "procurers_updated": 1,
        "suppliers_matched": 2,
        "suppliers_updated": 2,
    }
    (ops, ), kwargs = colls["procurers"].bulk_write.call_args
    assert isinstance(ops[0], UpdateOne)
    assert ops[0]._filter == {"ico": "111"}
    assert ops[0]._doc == {"$set": {"contract_count": 3, "total_value": 900.0}}


async def test_recompute_dry_run_does_not_write():
    db, colls = _fake_db(
        procurer_rows=[{"_id": "111", "contract_count": 3, "total_value": 900.0}],
        supplier_rows=[{"_id": "222", "contract_count": 2, "total_value": 500.0}],
    )
    out = await recompute_entity_stats(db, dry_run=True)

    colls["procurers"].bulk_write.assert_not_called()
    colls["suppliers"].bulk_write.assert_not_called()
    assert out["procurers_matched"] == 1
    assert out["suppliers_matched"] == 1
    assert out["procurers_updated"] == 0
    assert out["suppliers_updated"] == 0
