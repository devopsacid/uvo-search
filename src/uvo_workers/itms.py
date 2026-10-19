"""ITMS2014+ extractor worker."""

import asyncio
from typing import Literal

import httpx

from uvo_pipeline.cache import MemoryCache, RedisCache
from uvo_pipeline.extractors.itms import fetch_procurements as fetch_itms_procurements
from uvo_pipeline.transformers.itms import transform_procurement as transform_itms
from uvo_pipeline.utils.rate_limiter import RateLimiter
from uvo_workers.extract import Cycle, MinIdCheckpoint, SourceSpec, run_source
from uvo_workers.settings import ExtractorSettings, settings_factory


class ItmsSettings(ExtractorSettings):
    itms_interval_seconds: int = 3600
    itms_cache_backend: Literal["redis", "memory"] = "redis"
    itms_cache_ttl_seconds: int = 86400
    health_port: int = 8094

    @property
    def interval_seconds(self) -> int:
        return self.itms_interval_seconds


get_settings = settings_factory(ItmsSettings)


async def _fetch(cycle: Cycle):
    pipeline = cycle.pipeline
    if cycle.settings.itms_cache_backend == "redis":
        cache_backend = RedisCache(cycle.redis, prefix="")
    else:
        cache_backend = MemoryCache()

    rate_limiter = RateLimiter(rate=int(pipeline.itms_rate_limit), per=1.0)
    async with httpx.AsyncClient(
        base_url=pipeline.itms_base_url, timeout=pipeline.request_timeout
    ) as client:
        async for raw in fetch_itms_procurements(
            client,
            rate_limiter,
            min_id=cycle.cursor,
            cache_backend=cache_backend,
            cache_ttl_seconds=cycle.settings.itms_cache_ttl_seconds,
        ):
            yield raw


SPEC = SourceSpec(
    name="itms",
    settings=get_settings,
    fetch=_fetch,
    transform=transform_itms,
    checkpoint=MinIdCheckpoint("itms_min_id"),
)


async def main() -> None:
    await run_source(SPEC)


if __name__ == "__main__":
    asyncio.run(main())
