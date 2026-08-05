"""Authentication for the API.

Two independent schemes live here:

* ``require_api_key`` — API-key auth for the public ``/v1`` API. Keys live in the
  Mongo ``api_keys`` collection, stored as the sha256 hex digest of the raw key
  (``key_hash``) alongside ``plan``, ``owner_email``, ``active`` and
  ``created_at``. Lookups are cached in-process for 60s to avoid a Mongo
  round-trip per request.
* ``require_ops_token`` — a single bearer token guarding the operational
  dashboard endpoints, which expose worker topology and instance identifiers.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass

from cachetools import TTLCache
from fastapi import Header, HTTPException, Request, status

from uvo_api.config import get_settings
from uvo_api.db import get_db
from uvo_api.v1_errors import ApiV1Error

logger = logging.getLogger(__name__)

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


async def require_ops_token(authorization: str = Header(default="")) -> None:
    """Reject requests without a valid operational bearer token.

    Uses a constant-time comparison so the token cannot be recovered by
    timing. When no token is configured the routes are refused outright
    rather than left open — failing closed is the safe default for
    endpoints that expose internal topology.
    """
    expected = get_settings().ops_token
    if not expected:
        logger.warning("Operational endpoint called but API_OPS_TOKEN is unset; refusing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operational endpoints are not configured",
        )

    scheme, _, token = authorization.partition(" ")
    # compare_digest raises TypeError on non-ASCII str, which would surface as a
    # 500; comparing encoded bytes keeps a hostile header a clean 401.
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
