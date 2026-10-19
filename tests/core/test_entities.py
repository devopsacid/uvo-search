"""Point-lookup identity helpers (B11, B12/B17)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from uvo_core.adapters.mongo import entities


@pytest.fixture(autouse=True)
def _fresh():
    entities.clear_entity_caches()
    yield
    entities.clear_entity_caches()


async def test_get_entity_by_ico_finds_both_roles_and_projects():
    db = AsyncMongoMockClient()["ent_both"]
    await db.suppliers.insert_one({"ico": "1", "name": "Dual", "embedding": [0.1] * 4})
    await db.procurers.insert_one({"ico": "1", "name": "Dual", "contract_count": 4})
    ent = await entities.get_entity_by_ico(db, "1")
    assert ent["supplier"] == {"ico": "1", "name": "Dual"}
    assert ent["procurer"]["contract_count"] == 4
    assert entities.entity_roles(ent) == ["supplier", "procurer"]
    assert entities.entity_name(ent) == "Dual"


async def test_get_entity_by_ico_unknown():
    db = AsyncMongoMockClient()["ent_none"]
    ent = await entities.get_entity_by_ico(db, "404")
    assert ent == {"supplier": None, "procurer": None}
    assert entities.entity_roles(ent) == []
    assert entities.entity_name(ent) == ""


async def test_get_entity_by_ico_is_cached():
    suppliers, procurers = MagicMock(), MagicMock()
    suppliers.find_one = AsyncMock(return_value={"ico": "1", "name": "S"})
    procurers.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.__getitem__.side_effect = lambda n: {"suppliers": suppliers, "procurers": procurers}[n]
    await entities.get_entity_by_ico(db, "1")
    await entities.get_entity_by_ico(db, "1")
    assert suppliers.find_one.await_count == 1


async def test_entity_totals_uses_estimated_count_and_caches():
    suppliers, procurers = MagicMock(), MagicMock()
    suppliers.estimated_document_count = AsyncMock(return_value=7)
    procurers.estimated_document_count = AsyncMock(return_value=3)
    db = MagicMock()
    db.__getitem__.side_effect = lambda n: {"suppliers": suppliers, "procurers": procurers}[n]
    assert await entities.entity_totals(db) == {"suppliers": 7, "procurers": 3}
    await entities.entity_totals(db)
    assert suppliers.estimated_document_count.await_count == 1
