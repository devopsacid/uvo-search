"""CRZ extractor worker."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from functools import lru_cache

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore
from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.extractors.crz import fetch_contracts_since
from uvo_pipeline.redis_client import get_redis_settings
from uvo_pipeline.transformers.crz import transform_contract
from uvo_pipeline.utils.hashing import compute_notice_hash
from uvo_pipeline.utils.rate_limiter import RateLimiter
from uvo_workers.checkpoints import next_checkpoint, resolve_since
from uvo_workers.flush import flush_notices
from uvo_workers.runner import run_extractor_loop

logger = logging.getLogger(__name__)

FLUSH_BATCH = 500


class CrzSettings(BaseSettings):
    crz_interval_seconds: int = 3600
    # MAXLEN is only a memory safety net; backpressure (stream_high_water)
    # keeps the consumer-group backlog far below it so unread entries are
    # never trimmed.
    stream_maxlen_approx: int = 1_000_000
    stream_high_water: int = 50_000
    # Re-fetch this much history on every cycle so late-published or
    # still-propagating records are not skipped (ingestion is idempotent).
    checkpoint_overlap_seconds: int = 86_400
    health_port: int = 8092

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


@lru_cache
def get_settings() -> CrzSettings:
    """One CrzSettings construction per process (cached factory idiom)."""
    return CrzSettings()


async def _extract(redis_client: redis.asyncio.Redis, state: dict) -> int:
    settings = get_settings()
    pipeline_settings = get_pipeline_settings()
    run_id = uuid.uuid4().hex
    cycle_start = datetime.now(UTC)

    # Reuse the runner's long-lived Motor client/checkpoint store when running
    # inside run_extractor_loop; only open a fresh (short-lived) client when
    # _extract is invoked directly, e.g. in unit tests (plan §1.3.5).
    checkpoint_store = state.get("_checkpoint_store")
    mongo_client: AsyncIOMotorClient | None = None
    if checkpoint_store is None:
        mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
        checkpoint_store = MongoCheckpointStore(mongo_client[pipeline_settings.mongodb_database])

    notice_stream = RedisNoticeStream(redis_client, "crz", maxlen=settings.stream_maxlen_approx)

    try:
        checkpoint = await checkpoint_store.get("crz")
        since = resolve_since(
            checkpoint.get("crz_since"),
            recent_days=pipeline_settings.recent_days,
            now=cycle_start,
        )

        logger.info("crz: extracting since=%s", since)

        rate_limiter = RateLimiter(rate=pipeline_settings.crz_rate_limit, per=60.0)
        count = 0
        buffer: list = []

        async with httpx.AsyncClient(
            base_url=pipeline_settings.ekosystem_base_url,
            timeout=pipeline_settings.request_timeout,
        ) as client:
            async for raw in fetch_contracts_since(
                client,
                rate_limiter,
                since=since,
                api_token=pipeline_settings.ekosystem_api_token,
            ):
                try:
                    notice = transform_contract(raw)
                    notice.pipeline_run_id = run_id
                    notice.content_hash = compute_notice_hash(notice)
                    buffer.append(notice)
                except Exception as exc:
                    logger.warning("crz transform error: %s", exc)

                if len(buffer) >= FLUSH_BATCH:
                    count += await flush_notices(
                        notice_stream, buffer, high_water=settings.stream_high_water
                    )
                    buffer.clear()

        count += await flush_notices(notice_stream, buffer, high_water=settings.stream_high_water)
        buffer.clear()

        await checkpoint_store.save(
            "crz",
            {
                "crz_since": next_checkpoint(
                    cycle_start, overlap_seconds=settings.checkpoint_overlap_seconds
                )
            },
        )

    finally:
        if mongo_client is not None:
            mongo_client.close()

    return count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    redis_settings = get_redis_settings()
    await run_extractor_loop(
        source="crz",
        interval_seconds=settings.crz_interval_seconds,
        extract=_extract,
        redis_settings=redis_settings,
        health_port=settings.health_port,
    )


if __name__ == "__main__":
    asyncio.run(main())
