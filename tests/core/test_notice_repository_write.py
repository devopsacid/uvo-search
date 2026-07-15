"""MongoNoticeRepository write methods (Phase 5) — thin delegation to the
loader/dedup implementations, exercised through the port so routers/workers
that depend on NoticeRepository rather than the free functions stay covered.
"""

from mongomock_motor import AsyncMongoMockClient

from uvo_core.adapters.mongo.repositories import MongoNoticeRepository
from uvo_pipeline.loaders.mongo import ensure_indexes


def _notice(source_id: str, title: str = "Test notice") -> dict:
    return {
        "source": "vestnik",
        "source_id": source_id,
        "notice_type": "contract_award",
        "title": title,
        "procurer": {"ico": "12345678", "name": "Test Procurer", "name_slug": "test-procurer"},
    }


async def test_upsert_batch_delegates_and_returns_counts():
    db = AsyncMongoMockClient()["upsert_batch_test"]
    await ensure_indexes(db)
    repo = MongoNoticeRepository(db)

    result = await repo.upsert_batch([_notice("W-1"), _notice("W-2")])

    assert result["inserted"] == 2
    assert result["updated"] == 0
    assert result["errors"] == 0
    assert await db.notices.count_documents({}) == 2


async def test_upsert_batch_idempotent_via_port():
    db = AsyncMongoMockClient()["upsert_batch_test2"]
    await ensure_indexes(db)
    repo = MongoNoticeRepository(db)

    await repo.upsert_batch([_notice("W-3")])
    result2 = await repo.upsert_batch([_notice("W-3")])

    assert result2["inserted"] == 0
    assert result2["skipped"] == 1


async def test_persist_match_groups_delegates():
    db = AsyncMongoMockClient()["persist_groups_test"]
    n1 = await db.notices.insert_one({"source": "crz", "source_id": "P-1", "canonical_id": None})
    n2 = await db.notices.insert_one(
        {"source": "vestnik", "source_id": "P-2", "canonical_id": None}
    )
    repo = MongoNoticeRepository(db)

    group = {
        "canonical_id": str(n1.inserted_id),
        "notice_ids": [str(n1.inserted_id), str(n2.inserted_id)],
        "sources": ["crz", "vestnik"],
        "match_type": "ico_cpv",
    }
    written = await repo.persist_match_groups([group])

    assert written == 1
    doc1 = await db.notices.find_one({"_id": n1.inserted_id})
    doc2 = await db.notices.find_one({"_id": n2.inserted_id})
    assert doc1["canonical_id"] == doc2["canonical_id"] == str(n1.inserted_id)
    csm = await db.cross_source_matches.find_one({"canonical_id": str(n1.inserted_id)})
    assert csm["match_type"] == "ico_cpv"
