"""Redis-backed rate limiting and usage metering for the public /v1 API."""

import logging
import time

import redis.asyncio as aioredis
from fastapi import Depends

from uvo_api.auth import ApiKeyContext, require_api_key
from uvo_api.config import get_settings
from uvo_api.v1_errors import ApiV1Error

logger = logging.getLogger(__name__)

# Requests per minute per API key, by plan.
PLAN_LIMITS: dict[str, int] = {"free": 30, "pro": 300, "business": 1000}

USAGE_STREAM = "api:usage"
USAGE_STREAM_MAXLEN = 100_000

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            password=settings.redis_password or None,
            decode_responses=True,
        )
    return _redis_client


async def enforce_rate_limit(
    ctx: ApiKeyContext = Depends(require_api_key),
) -> ApiKeyContext:
    """Fixed-window (per minute) rate limit via Redis INCR + EXPIRE."""
    limit = PLAN_LIMITS.get(ctx.plan, PLAN_LIMITS["free"])
    now = time.time()
    window = int(now // 60)
    key = f"api:ratelimit:{ctx.key_id}:{window}"

    redis = await get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)

    if count > limit:
        retry_after = 60 - int(now % 60)
        raise ApiV1Error(
            429,
            "rate_limit_exceeded",
            f"Rate limit of {limit} requests/min exceeded for plan '{ctx.plan}'.",
            headers={"Retry-After": str(retry_after)},
            extra={"retry_after": retry_after},
        )
    return ctx


async def record_usage(key_id: str, endpoint: str, status: int) -> None:
    """Append one usage event to the ``api:usage`` Redis stream (best-effort)."""
    try:
        redis = await get_redis()
        await redis.xadd(
            USAGE_STREAM,
            {"key_id": key_id, "endpoint": endpoint, "status": str(status), "ts": str(time.time())},
            maxlen=USAGE_STREAM_MAXLEN,
            approximate=True,
        )
    except Exception:  # metering must never break the request
        logger.warning("usage metering failed for key %s on %s", key_id, endpoint, exc_info=True)
