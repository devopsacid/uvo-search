"""ITMS2014+ extractor — cursor-paginated async generator."""
import logging
from typing import AsyncIterator
import httpx
from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
_LIST_PATH = "/v2/verejneObstaravania"


async def fetch_procurements(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    min_id: int = 0,
) -> AsyncIterator[dict]:
    cursor = min_id
    while True:
        await rate_limiter.acquire()
        try:
            response = await client.get(_LIST_PATH, params={"minId": cursor, "limit": 100})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("ITMS list HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return
        except httpx.RequestError as exc:
            logger.error("ITMS list request failed: %s", exc)
            return
        items = response.json()
        if not items:
            break
        for item in items:
            await rate_limiter.acquire()
            detail_url = f"{_LIST_PATH}/{item['id']}/zmluvyVerejneObstaravanie"
            try:
                contracts_resp = await client.get(detail_url)
                item["_contracts"] = contracts_resp.json() if contracts_resp.status_code == 200 else []
            except httpx.RequestError as exc:
                logger.warning("ITMS contract detail failed id=%s: %s", item["id"], exc)
                item["_contracts"] = []
            yield item
        cursor = max(item["id"] for item in items) + 1
