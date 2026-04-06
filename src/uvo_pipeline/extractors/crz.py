"""CRZ (Central Register of Contracts) extractor.

Fetches contracts from the Ekosystem CRZ API:
  - Sync endpoint:    GET /api/data/crz/contracts/sync?since=<ISO>  → paginated contract objects
  - Contract detail:  GET /api/data/crz/contracts/:id               → one contract dict

The sync endpoint returns full contract objects directly (not just IDs).
Pagination is cursor-based via the Link header (rel='next') or last_id param.
"""

import logging
import re
from datetime import date
from typing import AsyncIterator

import httpx

from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_SYNC_PATH = "/api/data/crz/contracts/sync"

_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel=["\']next["\']')


async def fetch_contracts_since(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    since: date | None = None,
    batch_size: int = 50,
    api_token: str = "",
) -> AsyncIterator[dict]:
    """Yield CRZ contract dicts for all contracts modified since *since*.

    Paginates the sync endpoint using Link header cursor.
    If the sync endpoint fails, logs the error and stops iteration.
    """
    params: dict = {}
    if since is not None:
        params["since"] = since.isoformat()
    if api_token:
        params["access_token"] = api_token

    url: str | None = _SYNC_PATH
    page = 0

    while url is not None:
        await rate_limiter.acquire()
        try:
            if page == 0:
                response = await client.get(url, params=params)
            else:
                # Subsequent pages: url is already the full next URL from Link header
                response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "CRZ sync endpoint returned HTTP %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return
        except httpx.RequestError as exc:
            logger.error("CRZ sync request failed: %s", exc)
            return

        contracts = response.json()
        if not isinstance(contracts, list):
            contracts = contracts.get("data", []) if isinstance(contracts, dict) else []

        logger.info("CRZ sync page %d: %d contracts", page, len(contracts))

        for contract in contracts:
            yield contract

        # Follow Link: <url>; rel='next' for pagination
        link_header = response.headers.get("Link", "")
        match = _LINK_NEXT_RE.search(link_header)
        url = match.group(1) if match else None
        page += 1

        if not contracts:
            break
