"""API-key authentication for the public /v1 API.

Keys live in the Mongo ``api_keys`` collection, stored as the sha256 hex digest
of the raw key (``key_hash``) alongside ``plan``, ``owner_email``, ``active`` and
``created_at``. Lookups are cached in-process for 60s to avoid a Mongo round-trip
per request.
"""

import hashlib
from dataclasses import dataclass

from cachetools import TTLCache
from fastapi import Header, Request

from uvo_api.db import get_db
from uvo_api.v1_errors import ApiV1Error

# Cache both hits and misses; 60s TTL bounds the staleness window for newly
# issued or revoked keys.
_key_cache: TTLCache = TTLCache(maxsize=1024, ttl=60)


@dataclass
class ApiKeyContext:
    key_id: str
    plan: str
    owner_email: str | None


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _lookup_key(key_hash: str) -> dict | None:
    if key_hash in _key_cache:
        return _key_cache[key_hash]
    db = get_db()
    doc = await db["api_keys"].find_one({"key_hash": key_hash})
    _key_cache[key_hash] = doc
    return doc


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> ApiKeyContext:
    if not x_api_key:
        raise ApiV1Error(401, "missing_api_key", "Provide an API key in the X-API-Key header.")

    doc = await _lookup_key(hash_key(x_api_key))
    if not doc or not doc.get("active", False):
        raise ApiV1Error(401, "invalid_api_key", "The provided API key is invalid or inactive.")

    ctx = ApiKeyContext(
        key_id=str(doc["_id"]),
        plan=doc.get("plan", "free"),
        owner_email=doc.get("owner_email"),
    )
    request.state.api_key_ctx = ctx
    return ctx
