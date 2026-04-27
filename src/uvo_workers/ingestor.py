"""Ingestor worker — reads Redis Streams and writes to Mongo + Neo4j."""

import asyncio
import logging
import signal
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from pydantic_settings import BaseSettings

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.loaders.mongo import upsert_batch
from uvo_pipeline.loaders.neo4j import merge_notice_batch
from uvo_pipeline.models import CanonicalNotice
from uvo_pipeline.pubsub import publish
from uvo_pipeline.redis_client import RedisSettings, close_redis, get_redis
from uvo_pipeline.streams import ack, decode_entry, ensure_consumer_group, read_group
from uvo_workers.health import serve_health

logger = logging.getLogger(__name__)

_SOURCES = ["vestnik", "crz", "ted", "itms"]
_STREAMS = [f"notices:{s}" for s in _SOURCES]


class IngestorSettings(BaseSettings):
    ingestor_batch_size: int = 100
    health_port: int = 8095

    model_config = {"env_file": ".env", "extra": "ignore"}


async def run_ingestor() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = IngestorSettings()
    pipeline_settings = PipelineSettings()
    redis_settings = RedisSettings()
    instance_id = uuid.uuid4().hex

    metrics: dict = {
        "instance_id": instance_id,
        "batches_processed": 0,
        "notices_written": 0,
        "last_error": None,
        "redis_connected": False,
    }

    try:
        redis_client = await get_redis(
            url=redis_settings.redis_url,
            password=redis_settings.redis_password or None,
        )
        await redis_client.ping()
        metrics["redis_connected"] = True
    except Exception as exc:
        logger.critical("Redis connection failed: %s", exc)
        raise SystemExit(1) from exc

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received, stopping ingestor")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            pass

    health_task = asyncio.create_task(
        serve_health(settings.health_port, lambda: dict(metrics)),
        name="health-ingestor",
    )

    # Ensure consumer groups exist for all source streams
    for stream in _STREAMS:
        await ensure_consumer_group(redis_client, stream, "ingestor")

    mongo_client = AsyncIOMotorClient(pipeline_settings.mongodb_uri)
    db = mongo_client[pipeline_settings.mongodb_database]
    neo4j_driver = AsyncGraphDatabase.driver(
        pipeline_settings.neo4j_uri,
        auth=(pipeline_settings.neo4j_user, pipeline_settings.neo4j_password),
    )

    try:
        while not stop_event.is_set():
            try:
                results = await read_group(
                    redis_client,
                    "ingestor",
                    instance_id,
                    _STREAMS,
                    count=settings.ingestor_batch_size,
                    block_ms=5000,
                )
            except Exception as exc:
                logger.error("read_group failed: %s", exc)
                metrics["last_error"] = str(exc)
                await asyncio.sleep(1)
                continue

            if not results:
                continue

            for stream_name, entries in results:
                notices: list[CanonicalNotice] = []
                entry_ids: list[bytes] = []

                for entry_id, fields in entries:
                    try:
                        decoded = decode_entry(fields)
                        notice = CanonicalNotice.model_validate(decoded["payload"])
                        notices.append(notice)
                        entry_ids.append(entry_id)
                    except Exception as exc:
                        logger.warning("Failed to decode entry from %s: %s", stream_name, exc)

                if not notices:
                    continue

                try:
                    await upsert_batch(db, notices)
                    async with neo4j_driver.session() as neo4j_session:
                        await merge_notice_batch(neo4j_session, notices)

                    source = stream_name.removeprefix("notices:")
                    await ack(redis_client, stream_name, "ingestor", entry_ids)
                    await publish(redis_client, "notices:written", {"source": source, "count": len(notices)})

                    metrics["batches_processed"] += 1
                    metrics["notices_written"] += len(notices)
                    logger.info("ingestor: wrote %d notices from %s", len(notices), stream_name)

                except Exception as exc:
                    msg = f"{type(exc).__name__}: {exc}"
                    logger.error("ingestor: write failed for %s, not acking: %s", stream_name, msg)
                    metrics["last_error"] = msg
                    await asyncio.sleep(1)

    finally:
        health_task.cancel()
        try:
            await health_task
        except (asyncio.CancelledError, Exception):
            pass
        mongo_client.close()
        await neo4j_driver.close()
        await close_redis(redis_client)
        logger.info("ingestor stopped")


if __name__ == "__main__":
    asyncio.run(run_ingestor())
