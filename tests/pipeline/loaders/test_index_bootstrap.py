"""Index bootstrap coverage for the dashboard / firma query paths (B7, B8)."""

from unittest.mock import AsyncMock, MagicMock

from mongomock_motor import AsyncMongoMockClient

from uvo_core.adapters.mongo.loaders import ensure_indexes
from uvo_core.adapters.neo4j.loader import ensure_constraints


async def _index_keys(coll) -> set[tuple]:
    info = await coll.index_information()
    return {tuple(spec["key"]) for spec in info.values()}


async def test_notices_compound_indexes_created():
    db = AsyncMongoMockClient()["idx_notices"]
    await ensure_indexes(db)
    keys = await _index_keys(db.notices)
    assert (("notice_type", 1), ("publication_date", -1)) in keys
    assert (("procurer.ico", 1), ("notice_type", 1)) in keys
    assert (("awards.supplier.ico", 1), ("notice_type", 1)) in keys


async def test_ingestion_log_component_ts_index_created():
    db = AsyncMongoMockClient()["idx_log"]
    await ensure_indexes(db)
    assert (("component", 1), ("ts", -1)) in await _index_keys(db.ingestion_log)


async def test_ensure_indexes_is_idempotent():
    db = AsyncMongoMockClient()["idx_twice"]
    await ensure_indexes(db)
    await ensure_indexes(db)


async def test_neo4j_bootstrap_creates_notice_cpv_index():
    session = MagicMock()
    session.run = AsyncMock()
    await ensure_constraints(session)
    statements = [c.args[0] for c in session.run.call_args_list]
    assert any("notice_cpv" in s and "n.cpv_code" in s for s in statements)
