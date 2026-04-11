"""Shared fixtures for pipeline tests."""

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
from motor.motor_asyncio import AsyncIOMotorClient


@pytest_asyncio.fixture
async def mock_mongo_db():
    """In-memory MongoDB mock using mongomock-motor."""
    client = AsyncMongoMockClient()
    db = client["uvo_search_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def motor_db():
    """Real local MongoDB for integration tests (uvo_test_tmp database)."""
    client = AsyncIOMotorClient("mongodb://uvo:changeme@localhost:27017")
    db = client["uvo_test_tmp"]
    yield db
    # Clean up all collections after each test
    for name in await db.list_collection_names():
        await db.drop_collection(name)
    client.close()
