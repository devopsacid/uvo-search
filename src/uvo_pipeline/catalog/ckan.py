"""CKAN catalog discovery — finds Vestník XML packages on the Slovak open data portal.

NOTE: data.gov.sk has been replaced by a React SPA at data.slovensko.sk that no longer
exposes a CKAN API. All requests to the CKAN endpoint will return HTML, so this module
currently yields nothing and logs a warning. The extractor is kept in place for when
an alternative API is identified.
"""

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
    """Yield CKAN dataset dicts for Vestník packages.

    Currently disabled: data.gov.sk has been replaced by a React SPA that no longer
    exposes a CKAN API. Logs a warning and yields nothing until a replacement is found.
    """
    logger.warning(
        "CKAN Vestník source is unavailable: data.gov.sk has been replaced by "
        "data.slovensko.sk which no longer exposes a CKAN API endpoint. "
        "Skipping Vestník XML extraction."
    )
    return
    yield  # make this an async generator


async def extract_zip_urls(ckan_dataset: dict) -> list[str]:
    """Return download URLs for ZIP resources in a CKAN dataset."""
    urls = []
    for resource in ckan_dataset.get("resources", []):
        fmt = (resource.get("format") or "").upper()
        url = resource.get("url") or ""
        if fmt == "ZIP" or url.lower().endswith(".zip"):
            urls.append(url)
    return urls
