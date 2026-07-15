"""Shared fixtures for pipeline tests."""

import mongomock.collection as _mongomock_collection
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

# Compatibility shim: pymongo >=4.9 added a `sort` kwarg to UpdateOne, which
# BulkOperationBuilder._add_to_bulk now always forwards — but mongomock 4.3.0
# (the latest release on PyPI as of this writing) predates that pymongo
# addition and its add_update() has no `sort` parameter, so ANY bulk_write()
# containing an UpdateOne raises `TypeError: unexpected keyword argument
# 'sort'` against mongomock, regardless of the upsert flag. This only affects
# the mongomock test double — real MongoDB/Motor already supports it. Accept
# and discard the kwarg here so loaders/mongo.py's bulk_write-based upsert_batch
# (Phase 5) is testable without a live database.
_orig_add_update = _mongomock_collection.BulkOperationBuilder.add_update


def _add_update_compat(
    self,
    selector,
    doc,
    multi=False,
    upsert=False,
    collation=None,
    array_filters=None,
    hint=None,
    sort=None,
):
    return _orig_add_update(
        self,
        selector,
        doc,
        multi=multi,
        upsert=upsert,
        collation=collation,
        array_filters=array_filters,
        hint=hint,
    )


_mongomock_collection.BulkOperationBuilder.add_update = _add_update_compat


@pytest_asyncio.fixture
async def mock_mongo_db():
    """In-memory MongoDB mock using mongomock-motor."""
    client = AsyncMongoMockClient()
    db = client["uvo_search_test"]
    yield db
    client.close()
