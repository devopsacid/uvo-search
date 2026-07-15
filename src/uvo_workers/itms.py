"""ITMS2014+ extractor worker."""

import asyncio
import logging
import uuid
from functools import lru_cache
from typing import Literal

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore
from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_pipeline.cache import MemoryCache, RedisCache
from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.extractors.itms import fetch_procurements as fetch_itms_procurements
from uvo_pipeline.redis_client import get_redis_settings
from uvo_pipeline.transformers.itms import transform_procurement as transform_itms
from uvo_pipeline.utils.hashing import compute_notice_hash
from uvo_pipeline.utils.rate_limiter import RateLimiter
from uvo_workers.runner import run_extractor_loop

logger = logging.getLogger(__name__)

FLUSH_BATCH = 500


class ItmsSettings(BaseSettings):
    itms_interval_seconds: int = 3600
    itms_cache_backend: Literal["redis", "memory"] = "redis"
    itms_cache_ttl_seconds: int = 86400
    stream_maxlen_approx: int = 100_000
    health_port: int = 8094

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


@lru_cache
def get_settings() -> ItmsSettings:
    """One ItmsSettings construction per process (cached factory idiom)."""
    return ItmsSettings()


async def _extract(redis_client: redis.asyncio.Redis, state: dict) -> int:
    settings = get_settings()
    pipeline_settings = get_pipeline_settings()
    run_id = uuid.uuid4().hex

    # Reuse the runner's long-lived Motor client/checkpoint store when running
    # inside run_extractor_loop; only open a fresh (short-lived) client when
    # _extract is invoked directly, e.g. in unit tests (plan §1.3.5).
    checkpoint_store = state.get("_checkpoint_store")
    mongo_client: AsyncIOMotorClient | None = None
    if checkpoint_store is None:
        mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
        checkpoint_store = MongoCheckpointStore(mongo_client[pipeline_settings.mongodb_database])

    notice_stream = RedisNoticeStream(redis_client, "itms", maxlen=settings.stream_maxlen_approx)

    try:
        checkpoint = await checkpoint_store.get("itms")
        itms_min_id = int(checkpoint.get("itms_min_id") or state.get("itms_min_id") or 0)
        logger.info("itms: extracting min_id=%d", itms_min_id)

        if settings.itms_cache_backend == "redis":
            cache_backend = RedisCache(redis_client, prefix="")
        else:
            cache_backend = MemoryCache()

        rate_limiter = RateLimiter(rate=int(pipeline_settings.itms_rate_limit), per=1.0)
        count = 0
        buffer: list = []
        itms_max_seen = itms_min_id - 1

        async with httpx.AsyncClient(
            base_url=pipeline_settings.itms_base_url,
            timeout=pipeline_settings.request_timeout,
        ) as client:
            async for raw in fetch_itms_procurements(
                client,
                rate_limiter,
                min_id=itms_min_id,
                cache_backend=cache_backend,
                cache_ttl_seconds=settings.itms_cache_ttl_seconds,
            ):
                try:
                    notice = transform_itms(raw)
                    notice.pipeline_run_id = run_id
                    notice.content_hash = compute_notice_hash(notice)
                    buffer.append(notice)
                    itms_max_seen = max(itms_max_seen, int(raw["id"]))
                except Exception as exc:
                    logger.warning("itms transform error: %s", exc)

                if len(buffer) >= FLUSH_BATCH:
                    for n in buffer:
                        await notice_stream.xadd_notice(n.model_dump(mode="json"))
                        count += 1
                    buffer.clear()
                    # Checkpoint after each flush so a crash only loses the partial buffer
                    new_min_id = str(itms_max_seen + 1)
                    await checkpoint_store.save("itms", {"itms_min_id": new_min_id})
                    state["itms_min_id"] = new_min_id

        for n in buffer:
            await notice_stream.xadd_notice(n.model_dump(mode="json"))
            count += 1
        buffer.clear()

        new_min_id = str(itms_max_seen + 1)
        await checkpoint_store.save("itms", {"itms_min_id": new_min_id})
        state["itms_min_id"] = new_min_id

    finally:
        if mongo_client is not None:
            mongo_client.close()

    return count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    redis_settings = get_redis_settings()
    await run_extractor_loop(
        source="itms",
        interval_seconds=settings.itms_interval_seconds,
        extract=_extract,
        redis_settings=redis_settings,
        health_port=settings.health_port,
    )


if __name__ == "__main__":
    asyncio.run(main())
