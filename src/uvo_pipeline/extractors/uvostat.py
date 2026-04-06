"""UVOstat API extractor — async paginating generators."""

import logging
from datetime import date
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

_MAX_BATCH_SIZE = 100


async def fetch_all_procurements(
    client: httpx.AsyncClient,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    batch_size: int = 100,
) -> AsyncIterator[dict]:
    """Paginate GET /api/ukoncene_obstaravania; yield one raw dict per item."""
    async for item in _paginate(
        client,
        endpoint="/api/ukoncene_obstaravania",
        date_from=date_from,
        date_to=date_to,
        batch_size=batch_size,
    ):
        yield item


async def fetch_announced_procurements(
    client: httpx.AsyncClient,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    batch_size: int = 100,
) -> AsyncIterator[dict]:
    """Paginate GET /api/vyhlasene_obstaravania; yield one raw dict per item."""
    async for item in _paginate(
        client,
        endpoint="/api/vyhlasene_obstaravania",
        date_from=date_from,
        date_to=date_to,
        batch_size=batch_size,
    ):
        yield item


async def _paginate(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    date_from: date | None,
    date_to: date | None,
    batch_size: int,
) -> AsyncIterator[dict]:
    """Shared paginator for UVOstat list endpoints."""
    limit = min(batch_size, _MAX_BATCH_SIZE)
    offset = 0
    total: int | None = None

    while True:
        params: dict = {"limit": limit, "offset": offset}
        if date_from is not None:
            params["datum_zverejnenia_od"] = date_from.strftime("%Y-%m-%d")
        if date_to is not None:
            params["datum_zverejnenia_do"] = date_to.strftime("%Y-%m-%d")

        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error fetching %s (offset=%d): %s %s",
                endpoint,
                offset,
                exc.response.status_code,
                exc.response.text,
            )
            return
        except httpx.HTTPError as exc:
            logger.error("Connection error fetching %s (offset=%d): %s", endpoint, offset, exc)
            return

        payload = response.json()
        items: list[dict] = payload.get("data", [])
        if total is None:
            total = payload.get("summary", {}).get("total_records", 0)

        logger.info(
            "Fetched %s offset=%d limit=%d — got %d items (total=%d)",
            endpoint,
            offset,
            limit,
            len(items),
            total,
        )

        for item in items:
            yield item

        offset += limit
        if not items or offset >= total:
            break
