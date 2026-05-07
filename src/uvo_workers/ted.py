"""TED extractor worker."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.ted import search_sk_notices
from uvo_pipeline.redis_client import RedisSettings
from uvo_pipeline.streams import xadd_notice
from uvo_pipeline.transformers.ted import transform_ted_notice
from uvo_pipeline.utils.checkpoint import get_checkpoint, save_checkpoint
from uvo_pipeline.utils.hashing import compute_notice_hash
from uvo_workers.runner import run_extractor_loop

logger = logging.getLogger(__name__)

FLUSH_BATCH = 500


class TedSettings(BaseSettings):
    ted_interval_seconds: int = 3600
    stream_maxlen_approx: int = 100_000
    health_port: int = 8093

    model_config = {"env_file": ".env", "secrets_dir": "/run/secrets", "extra": "ignore"}


async def _extract(redis_client: redis.asyncio.Redis, state: dict) -> int:
    settings = TedSettings()
    pipeline_settings = PipelineSettings()
    run_id = uuid.uuid4().hex

    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]

    try:
        checkpoint = await get_checkpoint(db, "ted")
        ted_checkpoint = checkpoint.get("ted_since")
        if ted_checkpoint:
            try:
                since = datetime.fromisoformat(str(ted_checkpoint)).date()
            except (ValueError, TypeError):
                since = (datetime.utcnow() - timedelta(days=pipeline_settings.recent_days)).date()
        else:
            since = (datetime.utcnow() - timedelta(days=pipeline_settings.recent_days)).date()

        logger.info("ted: extracting since=%s", since)

        count = 0
        buffer: list = []

        async with httpx.AsyncClient(
            base_url=pipeline_settings.ted_base_url,
            timeout=pipeline_settings.request_timeout,
        ) as client:
            async for raw in search_sk_notices(client, date_from=since):
                try:
                    notice = transform_ted_notice(raw)
                    notice.pipeline_run_id = run_id
                    notice.content_hash = compute_notice_hash(notice)
                    buffer.append(notice)
                except Exception as exc:
                    logger.warning("ted transform error: %s", exc)

                if len(buffer) >= FLUSH_BATCH:
                    for n in buffer:
                        await xadd_notice(
                            redis_client,
                            "ted",
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
                "ted",
                n.model_dump(mode="json"),
                content_hash=n.content_hash,
                run_id=run_id,
                maxlen=settings.stream_maxlen_approx,
            )
            count += 1
        buffer.clear()

        await save_checkpoint(db, "ted", {"ted_since": datetime.utcnow().isoformat()})

    finally:
        mongo_client.close()

    return count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = TedSettings()
    redis_settings = RedisSettings()
    await run_extractor_loop(
        source="ted",
        interval_seconds=settings.ted_interval_seconds,
        extract=_extract,
        redis_settings=redis_settings,
        health_port=settings.health_port,
    )


if __name__ == "__main__":
    asyncio.run(main())
