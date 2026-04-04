"""TED (Tenders Electronic Daily) extractor.

Fetches Slovak procurement notices from the TED API v3:
  POST https://api.ted.europa.eu/v3/notices/search
"""

import logging
from datetime import date
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

_SEARCH_PATH = "/v3/notices/search"
_FIELDS = ["ND", "PD", "TI", "CY", "OC", "AC", "TV", "ON", "WIN", "ND_OJ"]


def _build_query(date_from: date | None, date_to: date | None) -> str:
    """Build TED search query string for Slovak notices."""
    base = "ND=[24,25] AND CY=[SVK]"
    if date_from is not None:
        # TED date format is YYYYMMDD
        base += f" AND PD>=[{date_from.strftime('%Y%m%d')}]"
    if date_to is not None:
        base += f" AND PD<=[{date_to.strftime('%Y%m%d')}]"
    return base


async def search_sk_notices(
    client: httpx.AsyncClient,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    page_size: int = 100,
) -> AsyncIterator[dict]:
    """Yield raw TED notice dicts for Slovak procurement notices.

    Paginates through all result pages.  On HTTP error, logs and stops.
    """
    query = _build_query(date_from, date_to)
    page = 1

    while True:
        payload = {
            "query": query,
            "page": page,
            "limit": page_size,
            "fields": _FIELDS,
        }

        try:
            response = await client.post(_SEARCH_PATH, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "TED search returned HTTP %s (page=%d): %s",
                exc.response.status_code,
                page,
                exc.response.text[:200],
            )
            return
        except httpx.RequestError as exc:
            logger.error("TED search request failed (page=%d): %s", page, exc)
            return

        data = response.json()
        notices: list[dict] = data.get("notices", [])
        total: int = data.get("total", 0)

        logger.debug("TED page %d: %d notices (total=%d)", page, len(notices), total)

        for notice in notices:
            yield notice

        if not notices or page * page_size >= total:
            break

        page += 1
