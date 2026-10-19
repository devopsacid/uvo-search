"""Infrastructure client creation for the workers - the single place.

Every Mongo/Redis/Neo4j handle a worker process uses is built here and owned
by ``WorkerContext``. Switching to a shared factory module later means
changing only these three ``open_*`` functions. Tests inject ready-made fakes
through ``WorkerClients`` instead of patching module attributes.
"""

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis

from uvo_core.adapters.redis.client import RedisSettings, close_redis, get_redis
from uvo_pipeline.config import get_pipeline_settings


def open_mongo() -> tuple[AsyncIOMotorClient, AsyncIOMotorDatabase]:
    settings = get_pipeline_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    return client, client[settings.mongodb_database]


async def open_redis(redis_settings: RedisSettings) -> Redis:
    return await get_redis(
        url=redis_settings.redis_url,
        password=redis_settings.redis_password or None,
    )


def open_neo4j():
    settings = get_pipeline_settings()
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


@dataclass
class WorkerClients:
    """The handles one worker process owns; ``close`` releases all of them."""

    mongo: AsyncIOMotorClient
    db: AsyncIOMotorDatabase
    redis: Redis | None = None
    neo4j: object | None = None

    async def close(self) -> None:
        self.mongo.close()
        if self.neo4j is not None:
            await self.neo4j.close()
        if self.redis is not None:
            await close_redis(self.redis)
