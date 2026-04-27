"""ITMS2014+ extractor worker."""

import asyncio
import logging
import uuid
from typing import Literal

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_pipeline.cache import MemoryCache, RedisCache
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.itms import fetch_procurements as fetch_itms_procurements
from uvo_pipeline.redis_client import RedisSettings
from uvo_pipeline.streams import xadd_notice
from uvo_pipeline.transformers.itms import transform_procurement as transform_itms
from uvo_pipeline.utils.checkpoint import get_checkpoint, save_checkpoint
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

    model_config = {"env_file": ".env", "extra": "ignore"}


async def _extract(redis_client: redis.asyncio.Redis, state: dict) -> int:
    settings = ItmsSettings()
    pipeline_settings = PipelineSettings()
    run_id = uuid.uuid4().hex

    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]

    try:
        checkpoint = await get_checkpoint(db, "itms")
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
                        await xadd_notice(
                            redis_client,
                            "itms",
                            n.model_dump(mode="json"),
                            content_hash=n.content_hash,
                            run_id=run_id,
                            maxlen=settings.stream_maxlen_approx,
                        )
                        count += 1
                    buffer.clear()
                    # Checkpoint after each flush so a crash only loses the partial buffer
                    new_min_id = str(itms_max_seen + 1)
                    await save_checkpoint(db, "itms", {"itms_min_id": new_min_id})
                    state["itms_min_id"] = new_min_id

        for n in buffer:
            await xadd_notice(
                redis_client,
                "itms",
                n.model_dump(mode="json"),
                content_hash=n.content_hash,
                run_id=run_id,
                maxlen=settings.stream_maxlen_approx,
            )
            count += 1
        buffer.clear()

        new_min_id = str(itms_max_seen + 1)
        await save_checkpoint(db, "itms", {"itms_min_id": new_min_id})
        state["itms_min_id"] = new_min_id

    finally:
        mongo_client.close()

    return count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = ItmsSettings()
    redis_settings = RedisSettings()
    await run_extractor_loop(
        source="itms",
        interval_seconds=settings.itms_interval_seconds,
        extract=_extract,
        redis_settings=redis_settings,
        health_port=settings.health_port,
    )


if __name__ == "__main__":
    asyncio.run(main())
