# src/uvo_api/db.py
"""Lazy Motor client for the analytics API."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from uvo_api.config import ApiSettings

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the shared Motor database handle, creating the client on first call."""
    global _client
    settings = ApiSettings()
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client[settings.mongodb_database]
