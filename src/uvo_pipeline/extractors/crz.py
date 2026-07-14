"""CRZ (Central Register of Contracts) extractor.

Fetches contracts from the Ekosystem CRZ API:
  - Sync endpoint:    GET /api/data/crz/contracts/sync?since=<ISO>  → paginated contract objects
  - Contract detail:  GET /api/data/crz/contracts/:id               → one contract dict

The sync endpoint returns full contract objects directly (not just IDs).
Pagination is cursor-based via the Link header (rel='next') or last_id param.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from datetime import date

import httpx

from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_SYNC_PATH = "/api/data/crz/contracts/sync"

_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel=["\']next["\']')

_MAX_429_RETRIES = 8
_DEFAULT_RETRY_AFTER_SEC = 60


def _parse_retry_after(value: str | None) -> int:
    if not value:
        return _DEFAULT_RETRY_AFTER_SEC
    try:
        return max(1, int(value))
    except (ValueError, TypeError):
        return _DEFAULT_RETRY_AFTER_SEC


async def fetch_contracts_since(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    since: date | None = None,
    batch_size: int = 50,
    api_token: str = "",
) -> AsyncIterator[dict]:
    """Yield CRZ contract dicts for all contracts modified since *since*.

    Paginates the sync endpoint using Link header cursor. On HTTP 429 the
    request is retried after the server-supplied ``Retry-After`` interval
    (or 60s default), up to ``_MAX_429_RETRIES`` times before giving up.
    Other errors stop iteration.
    """
    params: dict = {}
    if since is not None:
        params["since"] = since.isoformat()
    if api_token:
        params["access_token"] = api_token

    url: str | None = _SYNC_PATH
    page = 0

    while url is not None:
        response: httpx.Response | None = None
        for attempt in range(_MAX_429_RETRIES + 1):
            await rate_limiter.acquire()
            try:
                if page == 0:
                    resp = await client.get(url, params=params)
                else:
                    # Subsequent pages: url is already the full next URL
                    resp = await client.get(url)
            except httpx.RequestError as exc:
                logger.error("CRZ sync request failed: %s", exc)
                return

            if resp.status_code == 429:
                wait = _parse_retry_after(resp.headers.get("Retry-After"))
                if attempt >= _MAX_429_RETRIES:
                    logger.error(
                        "CRZ sync: HTTP 429 after %d retries — giving up", attempt
                    )
                    return
                logger.warning(
                    "CRZ sync: HTTP 429 (page %d, attempt %d/%d) — sleeping %ds",
                    page, attempt + 1, _MAX_429_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "CRZ sync endpoint returned HTTP %s: %s",
                    exc.response.status_code,
                    exc.response.text[:200],
                )
                return

            response = resp
            break

        if response is None:
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


async def fetch_contract_by_id(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    contract_id: str | int,
    *,
    api_token: str = "",
) -> dict | None:
    """Fetch a single CRZ contract by id (GET /api/data/crz/contracts/:id).

    Used by the date-repair backfill to re-fetch contracts whose signed_on
    year was corrupted upstream, so the corrected sync-shaped fields
    (signed_on/published_at/effective_from) can be re-derived via the
    transformer. Retries on HTTP 429 like fetch_contracts_since.
    """
    params: dict = {}
    if api_token:
        params["access_token"] = api_token

    url = f"{_SYNC_PATH.rsplit('/sync', 1)[0]}/{contract_id}"

    for attempt in range(_MAX_429_RETRIES + 1):
        await rate_limiter.acquire()
        try:
            resp = await client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.error("CRZ detail %s fetch failed: %s", contract_id, exc)
            return None

        if resp.status_code == 429:
            wait = _parse_retry_after(resp.headers.get("Retry-After"))
            if attempt >= _MAX_429_RETRIES:
                logger.error(
                    "CRZ detail %s: HTTP 429 after %d retries — giving up",
                    contract_id, attempt,
                )
                return None
            logger.warning(
                "CRZ detail %s: HTTP 429 (attempt %d/%d) — sleeping %ds",
                contract_id, attempt + 1, _MAX_429_RETRIES, wait,
            )
            await asyncio.sleep(wait)
            continue

        if resp.status_code == 404:
            return None

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "CRZ detail %s returned HTTP %s: %s",
                contract_id, exc.response.status_code, exc.response.text[:200],
            )
            return None

        data = resp.json()
        return data if isinstance(data, dict) else None

    return None
