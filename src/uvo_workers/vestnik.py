"""Vestník NKOD extractor worker."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_pipeline.catalog.nkod import discover_vestnik_datasets
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.redis_client import RedisSettings
from uvo_pipeline.streams import xadd_notice
from uvo_pipeline.transformers.vestnik_nkod import transform_notice as transform_vestnik_notice
from uvo_pipeline.utils.checkpoint import get_checkpoint, save_checkpoint
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


async def _extract(redis_client: redis.asyncio.Redis, state: dict) -> int:
    settings = VestnikSettings()
    pipeline_settings = PipelineSettings()
    run_id = uuid.uuid4().hex

    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]

    try:
        checkpoint = await get_checkpoint(db, "vestnik")
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
                                await xadd_notice(
                                    redis_client,
                                    "vestnik",
                                    n.model_dump(mode="json"),
                                    content_hash=n.content_hash,
                                    run_id=run_id,
                                    maxlen=settings.stream_maxlen_approx,
                                )
                                count += 1
                            buffer.clear()

        for n in buffer:
            await xadd_notice(
                redis_client,
                "vestnik",
                n.model_dump(mode="json"),
                content_hash=n.content_hash,
                run_id=run_id,
                maxlen=settings.stream_maxlen_approx,
            )
            count += 1
        buffer.clear()

        checkpoint_state: dict = {}
        if vestnik_max_modified is not None:
            checkpoint_state["vestnik_last_modified"] = vestnik_max_modified.isoformat()
        elif vestnik_checkpoint:
            checkpoint_state["vestnik_last_modified"] = vestnik_checkpoint
        if checkpoint_state:
            await save_checkpoint(db, "vestnik", checkpoint_state)

    finally:
        mongo_client.close()

    return count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = VestnikSettings()
    redis_settings = RedisSettings()
    await run_extractor_loop(
        source="vestnik",
        interval_seconds=settings.vestnik_interval_seconds,
        extract=_extract,
        redis_settings=redis_settings,
        health_port=settings.health_port,
    )


if __name__ == "__main__":
    asyncio.run(main())
