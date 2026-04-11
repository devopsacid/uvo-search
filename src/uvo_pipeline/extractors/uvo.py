"""UVO.gov.sk HTML scraper extractor.

Paginates the procurement listing at /vyhladavanie/vyhladavanie-zakaziek
and optionally fetches individual detail pages.

The HTML selectors are based on the observed Slovak government portal structure.
Adjust _TABLE_SELECTOR, _ROW_SELECTOR, and the column index constants below
if the site structure changes.
"""

import asyncio
import logging
import re
from datetime import date
from typing import AsyncIterator

import httpx
from bs4 import BeautifulSoup, Tag

from uvo_pipeline.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
_LISTING_PATH = "/vyhladavanie/vyhladavanie-zakaziek"

# CSS selectors — adjust after verifying real HTML structure
_TABLE_SELECTOR = "table.results-table"
_ROW_SELECTOR = "table.results-table tbody tr"

# Column positions within each <tr> (0-indexed)
_COL_TITLE = 0       # contains <a href="...detail/{id}?cHash=...">title</a>
_COL_PROCURER = 1    # "Name<br/><small>ICO: 12345678</small>"
_COL_CPV = 2
_COL_DATE = 3        # DD.MM.YYYY
_COL_STATUS = 4
_COL_VALUE = 5       # "500 000,00 EUR"

# Regex to extract notice ID from detail href
_DETAIL_ID_RE = re.compile(r"/detail/(\d+)")
_ICO_RE = re.compile(r"ICO:\s*(\d+)")


def _parse_value(text: str | None) -> float | None:
    """Parse Slovak currency string '500 000,00 EUR' → 500000.0, or None."""
    if not text:
        return None
    # Remove currency code and whitespace, replace Slovak decimal comma
    cleaned = re.sub(r"[^\d,\s]", "", text).strip()
    # Remove thousands-separator spaces, convert comma decimal separator
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_sk_date(text: str | None) -> str | None:
    """Parse 'DD.MM.YYYY' → 'YYYY-MM-DD', or None on failure."""
    if not text:
        return None
    parts = text.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return None


def _parse_listing_row(row: Tag) -> dict | None:
    """Parse one <tr> from the listing table into a raw dict.

    Returns None if the row cannot be parsed (header row, missing data, etc.).
    """
    try:
        cells = row.find_all("td")
        if len(cells) < 6:
            return None

        # Title cell: contains the link
        title_cell = cells[_COL_TITLE]
        link = title_cell.find("a")
        if link is None:
            return None
        detail_url = link.get("href", "")
        id_match = _DETAIL_ID_RE.search(detail_url)
        if not id_match:
            return None
        notice_id = id_match.group(1)
        title = link.get_text(strip=True)

        # Procurer cell: "Name<br/><small>ICO: ...</small>"
        procurer_cell = cells[_COL_PROCURER]
        # Get text before the <br> or <small> tag as procurer name
        raw_text = procurer_cell.get_text(separator="|", strip=True)
        procurer_parts = raw_text.split("|")
        procurer_name = procurer_parts[0].strip() if procurer_parts else ""
        ico_match = _ICO_RE.search(procurer_cell.get_text())
        procurer_ico = ico_match.group(1) if ico_match else None

        cpv = cells[_COL_CPV].get_text(strip=True) or None
        published_date = _parse_sk_date(cells[_COL_DATE].get_text(strip=True))
        status = cells[_COL_STATUS].get_text(strip=True) or None
        estimated_value = _parse_value(cells[_COL_VALUE].get_text(strip=True))

        return {
            "id": notice_id,
            "title": title,
            "procurer_name": procurer_name,
            "procurer_ico": procurer_ico,
            "cpv": cpv,
            "published_date": published_date,
            "status": status,
            "estimated_value": estimated_value,
            "detail_url": detail_url,
        }
    except Exception as exc:
        logger.warning("UVO: failed to parse listing row: %s", exc)
        return None


def _parse_detail_page(html: str) -> dict:
    """Parse a detail page HTML string and return a dict with supplier/award fields.

    All fields default to None — callers must handle missing data gracefully.
    """
    result: dict = {
        "supplier_name": None,
        "supplier_ico": None,
        "final_value": None,
        "award_date": None,
        "currency": None,
    }
    try:
        soup = BeautifulSoup(html, "lxml")
        labels = soup.find_all(class_="field-label")
        for label in labels:
            label_text = label.get_text(strip=True).lower()
            value_tag = label.find_next_sibling(class_="field-value")
            if value_tag is None:
                continue
            value_text = value_tag.get_text(separator="|", strip=True)

            if "dodávateľ" in label_text or "dodavatel" in label_text:
                parts = value_text.split("|")
                result["supplier_name"] = parts[0].strip() if parts else None
                ico_match = _ICO_RE.search(value_tag.get_text())
                result["supplier_ico"] = ico_match.group(1) if ico_match else None

            elif "finálna cena" in label_text or "finalna cena" in label_text:
                raw_value = value_tag.get_text(strip=True)
                result["final_value"] = _parse_value(raw_value)
                # Extract currency from trailing uppercase letters
                cur_match = re.search(r"\b([A-Z]{3})\b", raw_value)
                result["currency"] = cur_match.group(1) if cur_match else "EUR"

            elif "dátum uzavretia" in label_text or "datum uzavretia" in label_text:
                result["award_date"] = _parse_sk_date(value_tag.get_text(strip=True))

    except Exception as exc:
        logger.warning("UVO: failed to parse detail page: %s", exc)
    return result


async def fetch_notices(
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    *,
    from_date: date,
    to_date: date | None = None,
    fetch_details: bool = True,
    max_pages: int | None = None,
    request_delay: float = 0.5,
) -> AsyncIterator[dict]:
    """Yield raw UVO notice dicts, paging through the listing.

    Stops when a page is empty or the oldest notice on a page is older than from_date.
    If fetch_details=True, each raw dict is enriched with detail page data.
    """
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break

        params: dict = {"limit": 100, "page": page}
        # Attempt date filter params — may not be honoured; client-side filtering
        # below is the authoritative stop condition.
        if to_date is not None:
            params["date_to"] = to_date.strftime("%d.%m.%Y")
        params["date_from"] = from_date.strftime("%d.%m.%Y")

        # Bounded retry with exponential backoff
        max_retries = 3
        last_exc = None
        response = None
        for attempt in range(max_retries):
            await rate_limiter.acquire()
            try:
                response = await client.get(
                    _LISTING_PATH,
                    params=params,
                    headers={"User-Agent": _USER_AGENT},
                )
                response.raise_for_status()
                last_exc = None
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 503):
                    backoff = 10 * (2 ** attempt)
                    logger.warning(
                        "UVO: HTTP %s on page %d (attempt %d/%d), backing off %ds",
                        exc.response.status_code, page, attempt + 1, max_retries, backoff,
                    )
                    await asyncio.sleep(backoff)
                    last_exc = exc
                else:
                    logger.error("UVO: HTTP %s on listing page %d", exc.response.status_code, page)
                    return
            except httpx.RequestError as exc:
                logger.error("UVO: request error on listing page %d: %s", page, exc)
                return

        if last_exc is not None:
            logger.error(
                "UVO: page %d still failing after %d retries, aborting", page, max_retries
            )
            return

        soup = BeautifulSoup(response.text, "lxml")
        rows = soup.select(_ROW_SELECTOR)

        if not rows:
            logger.info("UVO: empty page %d — stopping pagination", page)
            break

        stop_after_page = False
        for row in rows:
            raw = _parse_listing_row(row)
            if raw is None:
                continue

            pub_date_str = raw.get("published_date")
            if pub_date_str:
                try:
                    pub_date = date.fromisoformat(pub_date_str)
                    if pub_date < from_date:
                        stop_after_page = True
                        continue
                    if to_date is not None and pub_date > to_date:
                        continue
                except (ValueError, TypeError):
                    pass

            if fetch_details and raw.get("detail_url"):
                if request_delay > 0:
                    await asyncio.sleep(request_delay)
                await rate_limiter.acquire()
                try:
                    detail_resp = await client.get(
                        raw["detail_url"],
                        headers={"User-Agent": _USER_AGENT},
                    )
                    detail_resp.raise_for_status()
                    detail = _parse_detail_page(detail_resp.text)
                    raw.update(detail)
                except Exception as exc:
                    logger.warning("UVO: could not fetch detail %s: %s", raw["detail_url"], exc)

            yield raw

        if stop_after_page:
            logger.info("UVO: reached from_date boundary on page %d — stopping", page)
            break

        page += 1
        if request_delay > 0:
            await asyncio.sleep(request_delay)
