"""TED extractor worker."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import httpx
import redis.asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings

from uvo_core.adapters.mongo.checkpoints import MongoCheckpointStore
from uvo_core.adapters.redis.notice_stream import RedisNoticeStream
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.ted import search_sk_notices
from uvo_pipeline.redis_client import RedisSettings
from uvo_pipeline.transformers.ted import transform_ted_notice
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

    # Reuse the runner's long-lived Motor client/checkpoint store when running
    # inside run_extractor_loop; only open a fresh (short-lived) client when
    # _extract is invoked directly, e.g. in unit tests (plan §1.3.5).
    checkpoint_store = state.get("_checkpoint_store")
    mongo_client: AsyncIOMotorClient | None = None
    if checkpoint_store is None:
        mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
        checkpoint_store = MongoCheckpointStore(mongo_client[pipeline_settings.mongodb_database])

    notice_stream = RedisNoticeStream(redis_client, "ted", maxlen=settings.stream_maxlen_approx)

    try:
        checkpoint = await checkpoint_store.get("ted")
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
                        await notice_stream.xadd_notice(n.model_dump(mode="json"))
                        count += 1
                    buffer.clear()

        for n in buffer:
            await notice_stream.xadd_notice(n.model_dump(mode="json"))
            count += 1
        buffer.clear()

        await checkpoint_store.save("ted", {"ted_since": datetime.utcnow().isoformat()})

    finally:
        if mongo_client is not None:
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
