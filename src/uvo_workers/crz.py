"""CRZ extractor worker."""

import asyncio

import httpx

from uvo_pipeline.extractors.crz import fetch_contracts_since
from uvo_pipeline.transformers.crz import transform_contract
from uvo_pipeline.utils.rate_limiter import RateLimiter
from uvo_workers.extract import Cycle, SourceSpec, WallClockCheckpoint, run_source
from uvo_workers.settings import ExtractorSettings, settings_factory


class CrzSettings(ExtractorSettings):
    crz_interval_seconds: int = 3600
    health_port: int = 8092

    @property
    def interval_seconds(self) -> int:
        return self.crz_interval_seconds


get_settings = settings_factory(CrzSettings)


async def _fetch(cycle: Cycle):
    pipeline = cycle.pipeline
    rate_limiter = RateLimiter(rate=pipeline.crz_rate_limit, per=60.0)
    async with httpx.AsyncClient(
        base_url=pipeline.ekosystem_base_url, timeout=pipeline.request_timeout
    ) as client:
        async for raw in fetch_contracts_since(
            client, rate_limiter, since=cycle.cursor, api_token=pipeline.ekosystem_api_token
        ):
            yield raw


SPEC = SourceSpec(
    name="crz",
    settings=get_settings,
    fetch=_fetch,
    transform=transform_contract,
    checkpoint=WallClockCheckpoint("crz_since"),
)


async def main() -> None:
    await run_source(SPEC)


if __name__ == "__main__":
    asyncio.run(main())
