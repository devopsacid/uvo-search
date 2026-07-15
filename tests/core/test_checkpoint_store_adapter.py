"""MongoCheckpointStore — thin CheckpointStore port wrapper over pipeline_state."""

from mongomock_motor import AsyncMongoMockClient

from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore


async def test_get_returns_empty_dict_when_absent():
    db = AsyncMongoMockClient()["checkpoint_test"]
    store = MongoCheckpointStore(db)

    assert await store.get("vestnik") == {}


async def test_save_then_get_roundtrips():
    db = AsyncMongoMockClient()["checkpoint_test2"]
    store = MongoCheckpointStore(db)

    await store.save("crz", {"crz_since": "2026-01-01T00:00:00"})
    checkpoint = await store.get("crz")

    assert checkpoint["crz_since"] == "2026-01-01T00:00:00"
    assert checkpoint["source"] == "crz"


async def test_save_upserts_without_duplicating():
    db = AsyncMongoMockClient()["checkpoint_test3"]
    store = MongoCheckpointStore(db)

    await store.save("itms", {"itms_min_id": "1"})
    await store.save("itms", {"itms_min_id": "501"})

    assert await db.pipeline_state.count_documents({"source": "itms"}) == 1
    checkpoint = await store.get("itms")
    assert checkpoint["itms_min_id"] == "501"
