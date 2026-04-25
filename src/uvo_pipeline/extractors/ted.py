"""TED (Tenders Electronic Daily) extractor.

Fetches Slovak procurement notices from the TED API v3:
  POST https://api.ted.europa.eu/v3/notices/search

API v3 changes from v2:
  - Query syntax: use `buyer-country = SVK` (not `CY=[SVK]`)
  - Fields: use descriptive kebab-case names (not old abbreviated codes like ND, PD, CY)
  - Response: `totalNoticeCount` (not `total`)
"""

import logging
from datetime import date
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

_SEARCH_PATH = "/v3/notices/search"
_FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-country",
    "buyer-name",
    "classification-cpv",
    "contract-nature",
    "tender-value",
    "tender-value-cur",
    "notice-type",
    "winner-name",
    "winner-identifier",
    "winner-country",
    "winner-size",
    "winner-decision-date",
    "result-value-lot",
    "result-value-cur-lot",
    "result-value-notice",
    "result-value-cur-notice",
    "contract-conclusion-date",
    "contract-identifier",
    "organisation-name-tenderer",
    "organisation-identifier-tenderer",
    "ojs-number",
]


# TED Contract-Award-Notice types — only these carry winner/supplier data.
_CAN_NOTICE_TYPES = ("can-standard", "can-modif", "can-social", "can-desg", "can-tran")


def _build_query(
    date_from: date | None,
    date_to: date | None,
    awards_only: bool = False,
) -> str:
    """Build TED v3 search query string for Slovak notices."""
    base = "buyer-country = SVK"
    if awards_only:
        can_clause = " OR ".join(f'notice-type="{t}"' for t in _CAN_NOTICE_TYPES)
        base += f" AND ({can_clause})"
    if date_from is not None:
        base += f" AND publication-date >= {date_from.strftime('%Y%m%d')}"
    if date_to is not None:
        base += f" AND publication-date <= {date_to.strftime('%Y%m%d')}"
    return base


async def search_sk_notices(
    client: httpx.AsyncClient,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    page_size: int = 100,
    awards_only: bool = False,
) -> AsyncIterator[dict]:
    """Yield raw TED notice dicts for Slovak procurement notices.

    When awards_only=True, the query is narrowed to Contract-Award-Notice
    types (can-*) — these are the ones that carry winner/supplier data.
    Paginates through all result pages. On HTTP error, logs and stops.
    """
    query = _build_query(date_from, date_to, awards_only=awards_only)
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
        total: int = data.get("totalNoticeCount", 0)

        logger.debug("TED page %d: %d notices (total=%d)", page, len(notices), total)

        for notice in notices:
            yield notice

        if not notices or page * page_size >= total:
            break

        page += 1
