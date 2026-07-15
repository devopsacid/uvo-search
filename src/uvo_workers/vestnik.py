"""Vestník NKOD extractor worker."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore
from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_pipeline.catalog.nkod import discover_vestnik_datasets
from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.redis_client import get_redis_settings
from uvo_pipeline.transformers.vestnik_nkod import transform_notice as transform_vestnik_notice
from uvo_pipeline.utils.hashing import compute_notice_hash
from uvo_pipeline.utils.rate_limiter import RateLimiter
from uvo_workers.runner import run_extractor_loop

logger = logging.getLogger(__name__)

FLUSH_BATCH = 500


class VestnikSettings(BaseSettings):
    vestnik_interval_seconds: int = 3600
    vestnik_mode: Literal["recent", "historical"] = "recent"
    stream_maxlen_approx: int = 100_000
    health_port: int = 8091

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


@lru_cache
def get_settings() -> VestnikSettings:
    """One VestnikSettings construction per process (cached factory idiom)."""
    return VestnikSettings()


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

    notice_stream = RedisNoticeStream(redis_client, "vestnik", maxlen=settings.stream_maxlen_approx)

    try:
        checkpoint = await checkpoint_store.get("vestnik")
        vestnik_checkpoint = checkpoint.get("vestnik_last_modified")

        if settings.vestnik_mode == "historical":
            vestnik_since = None
        elif vestnik_checkpoint:
            try:
                vestnik_since = datetime.fromisoformat(str(vestnik_checkpoint)).date()
            except (ValueError, TypeError):
                vestnik_since = (datetime.utcnow() - timedelta(days=pipeline_settings.recent_days)).date()
        else:
            vestnik_since = (datetime.utcnow() - timedelta(days=pipeline_settings.recent_days)).date()

        logger.info("vestnik: extracting since=%s", vestnik_since)

        rate_limiter = RateLimiter(rate=max(1, int(pipeline_settings.vestnik_rate_limit)), per=1.0)
        cache_dir = Path(pipeline_settings.cache_dir)
        count = 0
        buffer: list = []
        vestnik_max_modified: datetime | None = None

        async with httpx.AsyncClient(timeout=pipeline_settings.request_timeout) as sparql_client:
            async with httpx.AsyncClient(
                timeout=pipeline_settings.request_timeout,
                follow_redirects=True,
            ) as dl_client:
                async for ds in discover_vestnik_datasets(
                    sparql_client,
                    publisher_uri=pipeline_settings.uvo_publisher_uri,
                    sparql_url=pipeline_settings.nkod_sparql_url,
                    since=vestnik_since,
                ):
                    if ds.modified and (vestnik_max_modified is None or ds.modified > vestnik_max_modified):
                        vestnik_max_modified = ds.modified
                    async for raw in fetch_bulletin(
                        dl_client,
                        rate_limiter,
                        ds,
                        cache_dir=cache_dir,
                    ):
                        try:
                            notice = transform_vestnik_notice(raw)
                            notice.pipeline_run_id = run_id
                            notice.content_hash = compute_notice_hash(notice)
                            buffer.append(notice)
                        except Exception as exc:
                            logger.warning("vestnik transform error (id=%s): %s", raw.get("id"), exc)

                        if len(buffer) >= FLUSH_BATCH:
                            for n in buffer:
                                await notice_stream.xadd_notice(n.model_dump(mode="json"))
                                count += 1
                            buffer.clear()

        for n in buffer:
            await notice_stream.xadd_notice(n.model_dump(mode="json"))
            count += 1
        buffer.clear()

        checkpoint_state: dict = {}
        if vestnik_max_modified is not None:
            checkpoint_state["vestnik_last_modified"] = vestnik_max_modified.isoformat()
        elif vestnik_checkpoint:
            checkpoint_state["vestnik_last_modified"] = vestnik_checkpoint
        if checkpoint_state:
            await checkpoint_store.save("vestnik", checkpoint_state)

    finally:
        if mongo_client is not None:
            mongo_client.close()

    return count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    redis_settings = get_redis_settings()
    await run_extractor_loop(
        source="vestnik",
        interval_seconds=settings.vestnik_interval_seconds,
        extract=_extract,
        redis_settings=redis_settings,
        health_port=settings.health_port,
    )


if __name__ == "__main__":
    asyncio.run(main())
