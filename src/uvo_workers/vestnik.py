"""Vestník NKOD extractor worker."""

import asyncio
from pathlib import Path
from typing import Literal

import httpx

from uvo_pipeline.catalog.nkod import discover_vestnik_datasets
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.transformers.vestnik_nkod import transform_notice as transform_vestnik_notice
from uvo_pipeline.utils.rate_limiter import RateLimiter
from uvo_workers.extract import Cycle, MaxModifiedCheckpoint, SourceSpec, run_source
from uvo_workers.settings import ExtractorSettings, settings_factory


class VestnikSettings(ExtractorSettings):
    vestnik_interval_seconds: int = 3600
    vestnik_mode: Literal["recent", "historical"] = "recent"
    health_port: int = 8091

    @property
    def interval_seconds(self) -> int:
        return self.vestnik_interval_seconds


get_settings = settings_factory(VestnikSettings)


async def _fetch(cycle: Cycle):
    pipeline = cycle.pipeline
    rate_limiter = RateLimiter(rate=max(1, int(pipeline.vestnik_rate_limit)), per=1.0)
    cache_dir = Path(pipeline.cache_dir)

    async with httpx.AsyncClient(timeout=pipeline.request_timeout) as sparql_client:
        async with httpx.AsyncClient(
            timeout=pipeline.request_timeout, follow_redirects=True
        ) as dl_client:
            async for ds in discover_vestnik_datasets(
                sparql_client,
                publisher_uri=pipeline.uvo_publisher_uri,
                sparql_url=pipeline.nkod_sparql_url,
                since=cycle.cursor,
            ):
                MaxModifiedCheckpoint.observe(cycle, ds.modified)
                async for raw in fetch_bulletin(dl_client, rate_limiter, ds, cache_dir=cache_dir):
                    yield raw


SPEC = SourceSpec(
    name="vestnik",
    settings=get_settings,
    fetch=_fetch,
    transform=transform_vestnik_notice,
    checkpoint=MaxModifiedCheckpoint(
        "vestnik_last_modified", historical=lambda s: s.vestnik_mode == "historical"
    ),
)


async def main() -> None:
    await run_source(SPEC)


if __name__ == "__main__":
    asyncio.run(main())
