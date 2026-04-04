"""CKAN catalog discovery — finds Vestník XML packages on data.gov.sk."""

import logging
from collections.abc import AsyncIterator
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_SEARCH_PATH = "/api/3/action/package_search"
_QUERY = "vestnik+verejneho+obstaravania"
_PAGE_SIZE = 50


async def discover_vestnik_packages(
    client: httpx.AsyncClient,
    *,
    from_date: date | None = None,
    max_packages: int = 500,
) -> AsyncIterator[dict]:
    """Yield CKAN dataset dicts for Vestník packages from data.gov.sk.

    Paginates using start/rows. Filters by metadata_modified >= from_date if given.
    Stops when results are exhausted or max_packages is reached.
    """
    yielded = 0
    start = 0

    while yielded < max_packages:
        params = {
            "q": _QUERY,
            "sort": "metadata_modified desc",
            "rows": _PAGE_SIZE,
            "start": start,
        }

        try:
            response = await client.get(_SEARCH_PATH, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("CKAN API error at start=%d: %s", start, exc)
            return

        data = response.json()
        if not data.get("success"):
            logger.error("CKAN API returned success=false: %s", data)
            return

        results = data.get("result", {}).get("results", [])
        if not results:
            logger.debug("CKAN: no more results at start=%d", start)
            return

        for package in results:
            if yielded >= max_packages:
                return

            if from_date is not None:
                modified_str = package.get("metadata_modified", "")
                if modified_str:
                    try:
                        modified_date = date.fromisoformat(modified_str[:10])
                        if modified_date < from_date:
                            logger.debug(
                                "CKAN: package %s modified %s before from_date %s, stopping",
                                package.get("name"),
                                modified_date,
                                from_date,
                            )
                            return
                    except (ValueError, TypeError):
                        pass

            yield package
            yielded += 1

        start += _PAGE_SIZE

        # If we got fewer results than a full page, we've exhausted the catalog
        if len(results) < _PAGE_SIZE:
            return


async def extract_zip_urls(ckan_dataset: dict) -> list[str]:
    """Return download URLs for ZIP resources in a CKAN dataset."""
    urls = []
    for resource in ckan_dataset.get("resources", []):
        fmt = (resource.get("format") or "").upper()
        url = resource.get("url") or ""
        if fmt == "ZIP" or url.lower().endswith(".zip"):
            urls.append(url)
    return urls
