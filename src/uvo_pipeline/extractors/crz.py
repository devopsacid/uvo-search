"""CRZ (Central Register of Contracts) extractor.

Fetches contracts from the Ekosystem CRZ API:
  - Sync endpoint:    GET /api/datahub/crz/sync?since=<ISO>  → list of modified IDs
  - Contract detail:  GET /api/data/crz/contracts/:id        → one contract dict
"""

import logging
from datetime import date
from typing import AsyncIterator

import httpx

from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_SYNC_PATH = "/api/datahub/crz/sync"
_CONTRACT_PATH = "/api/data/crz/contracts/{id}"


async def fetch_contracts_since(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    since: date | None = None,
    batch_size: int = 50,
    api_token: str = "",
) -> AsyncIterator[dict]:
    """Yield CRZ contract dicts for all contracts modified since *since*.

    Steps:
      1. GET /api/datahub/crz/sync?since=<ISO> to obtain a list of modified IDs.
      2. For each ID, call GET /api/data/crz/contracts/:id (rate-limited).
      3. Yield the raw contract dict.

    If the sync endpoint fails, log the error and stop iteration.
    If a single contract fetch fails, log a warning and continue.
    """
    # --- Build sync request params ---
    params: dict = {}
    if since is not None:
        params["since"] = since.isoformat()
    if api_token:
        params["access_token"] = api_token

    try:
        response = await client.get(_SYNC_PATH, params=params)
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

    data = response.json()
    # The API returns either {"ids": [...]} or a plain list
    if isinstance(data, dict):
        ids: list = data.get("ids", [])
    else:
        ids = list(data)

    logger.info("CRZ sync returned %d contract IDs", len(ids))

    for contract_id in ids:
        detail_params: dict = {}
        if api_token:
            detail_params["access_token"] = api_token

        await rate_limiter.acquire()
        try:
            detail_response = await client.get(
                _CONTRACT_PATH.format(id=contract_id),
                params=detail_params if detail_params else None,
            )
            detail_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "CRZ contract %s returned HTTP %s — skipping",
                contract_id,
                exc.response.status_code,
            )
            continue
        except httpx.RequestError as exc:
            logger.warning("CRZ contract %s request failed: %s — skipping", contract_id, exc)
            continue

        yield detail_response.json()
