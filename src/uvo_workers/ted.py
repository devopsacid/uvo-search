"""TED extractor worker."""

import asyncio

import httpx

from uvo_pipeline.extractors.ted import search_sk_notices
from uvo_pipeline.transformers.ted import transform_ted_notice
from uvo_workers.extract import Cycle, SourceSpec, WallClockCheckpoint, run_source
from uvo_workers.settings import ExtractorSettings, settings_factory


class TedSettings(ExtractorSettings):
    ted_interval_seconds: int = 3600
    health_port: int = 8093

    @property
    def interval_seconds(self) -> int:
        return self.ted_interval_seconds


get_settings = settings_factory(TedSettings)


async def _fetch(cycle: Cycle):
    pipeline = cycle.pipeline
    async with httpx.AsyncClient(
        base_url=pipeline.ted_base_url, timeout=pipeline.request_timeout
    ) as client:
        async for raw in search_sk_notices(client, date_from=cycle.cursor):
            yield raw


SPEC = SourceSpec(
    name="ted",
    settings=get_settings,
    fetch=_fetch,
    transform=transform_ted_notice,
    checkpoint=WallClockCheckpoint("ted_since"),
)


async def main() -> None:
    await run_source(SPEC)


if __name__ == "__main__":
    asyncio.run(main())
