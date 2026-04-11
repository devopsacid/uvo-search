"""Shared fixtures for pipeline tests."""

import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def mock_mongo_db():
    """In-memory MongoDB mock using mongomock-motor."""
    client = AsyncMongoMockClient()
    db = client["uvo_search_test"]
    yield db
    client.close()
