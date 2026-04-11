I cannot write files — I'm in read-only planning mode. I'll output the plan directly as my response, per the instructions.

---

# UVO.gov.sk Scraper Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an HTML scraper for uvo.gov.sk that paginates listing pages, optionally fetches detail pages, transforms rows to `CanonicalNotice`, and wires the step into the existing pipeline orchestrator after TED.

**Architecture:** A new async-generator extractor (`extractors/uvo.py`) fetches and parses HTML with BeautifulSoup, yielding raw dicts. A new transformer (`transformers/uvo.py`) maps those dicts to `CanonicalNotice`. Four config fields and a one-word Literal extension gate the feature; the orchestrator gains a single extraction block after the TED block.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup4 + lxml (already installed), respx (test mocks), pytest-asyncio, pydantic-settings, python-slugify

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `pyproject.toml` | Add `beautifulsoup4` dependency |
| Modify | `src/uvo_pipeline/config.py` | 4 new UVO settings |
| Modify | `src/uvo_pipeline/models.py` | Add `"uvo"` to `source` Literal |
| Create | `src/uvo_pipeline/extractors/uvo.py` | HTML listing/detail extractor |
| Create | `src/uvo_pipeline/transformers/uvo.py` | Raw dict → CanonicalNotice |
| Modify | `src/uvo_pipeline/orchestrator.py` | Wire in UVO extraction step |
| Create | `tests/pipeline/extractors/test_uvo.py` | Extractor tests |
| Create | `tests/pipeline/transformers/test_uvo.py` | Transformer tests |

---

### Task 1: Add beautifulsoup4 dependency

**Files:**
- Modify: `pyproject.toml`

Note: `lxml>=5.0` is already present in `pyproject.toml`. `beautifulsoup4` is already installed in the venv (version 4.12.3) but is not declared as a project dependency. This task fixes that.

- [ ] **Step 1: Add beautifulsoup4 to pyproject.toml dependencies**

In `pyproject.toml`, inside the `dependencies = [` list (around line 8), add:
```
"beautifulsoup4>=4.12",
```
The block should read:
```toml
dependencies = [
    "mcp[cli]>=1.0.0",
    "nicegui>=3.9.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "cachetools>=5.0.0",
    "fastapi[standard]>=0.115.0",
    "motor>=3.4",
    "neo4j>=5.0",
    "lxml>=5.0",
    "beautifulsoup4>=4.12",
    "aiofiles>=23.0",
    "python-slugify>=8.0"
]
```

- [ ] **Step 2: Sync the lockfile**

Run:
```bash
uv sync
```
Expected: `uv.lock` updated, no errors.

- [ ] **Step 3: Verify import works**

Run:
```bash
uv run python -c "from bs4 import BeautifulSoup; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: declare beautifulsoup4 as explicit dependency"
```

---

### Task 2: Config additions

**Files:**
- Modify: `src/uvo_pipeline/config.py`
- Create: `tests/pipeline/test_config_uvo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_config_uvo.py`:
```python
"""Tests for UVO config fields."""
from uvo_pipeline.config import PipelineSettings


def test_uvo_defaults():
    s = PipelineSettings()
    assert s.uvo_base_url == "https://www.uvo.gov.sk"
    assert s.uvo_rate_limit == 1.0
    assert s.uvo_request_delay == 0.5
    assert s.uvo_fetch_details is True


def test_uvo_env_override(monkeypatch):
    monkeypatch.setenv("UVO_BASE_URL", "https://test.uvo.gov.sk")
    monkeypatch.setenv("UVO_RATE_LIMIT", "2.5")
    monkeypatch.setenv("UVO_REQUEST_DELAY", "0.1")
    monkeypatch.setenv("UVO_FETCH_DETAILS", "false")
    s = PipelineSettings()
    assert s.uvo_base_url == "https://test.uvo.gov.sk"
    assert s.uvo_rate_limit == 2.5
    assert s.uvo_request_delay == 0.1
    assert s.uvo_fetch_details is False
```

- [ ] **Step 2: Run the test to see it fail**

Run:
```bash
uv run pytest tests/pipeline/test_config_uvo.py -v
```
Expected: `AttributeError: 'PipelineSettings' object has no attribute 'uvo_base_url'`

- [ ] **Step 3: Add the 4 fields to config.py**

In `src/uvo_pipeline/config.py`, add after the `crz_rate_limit` line (line 29):
```python
    crz_rate_limit: int = 55
    uvo_base_url: str = "https://www.uvo.gov.sk"
    uvo_rate_limit: float = 1.0
    uvo_request_delay: float = 0.5
    uvo_fetch_details: bool = True
    request_timeout: float = 60.0
```

The full `config.py` should now read:
```python
"""Pipeline configuration settings."""

from typing import Literal
from pydantic_settings import BaseSettings


class PipelineSettings(BaseSettings):
    # Source APIs
    ekosystem_base_url: str = "https://datahub.ekosystem.slovensko.digital"
    ekosystem_api_token: str = ""
    ted_base_url: str = "https://api.ted.europa.eu"
    ckan_base_url: str = "https://data.slovensko.sk"

    # Databases (required for pipeline)
    mongodb_uri: str = "mongodb://uvo:changeme@mongo:27017"
    mongodb_database: str = "uvo_search"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Pipeline behaviour
    pipeline_mode: Literal["recent", "historical"] = "recent"
    recent_days: int = 365
    historical_from_year: int = 2014
    cache_dir: str = "/app/cache"
    batch_size: int = 500
    neo4j_batch_size: int = 100
    crz_rate_limit: int = 55
    uvo_base_url: str = "https://www.uvo.gov.sk"
    uvo_rate_limit: float = 1.0
    uvo_request_delay: float = 0.5
    uvo_fetch_details: bool = True
    request_timeout: float = 60.0

    model_config = {"env_file": ".env", "extra": "ignore"}
```

- [ ] **Step 4: Run the tests to see them pass**

Run:
```bash
uv run pytest tests/pipeline/test_config_uvo.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/config.py tests/pipeline/test_config_uvo.py
git commit -m "feat: add UVO config fields to PipelineSettings"
```

---

### Task 3: Models update

**Files:**
- Modify: `src/uvo_pipeline/models.py:51`
- Create: `tests/pipeline/test_models_uvo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_models_uvo.py`:
```python
"""Tests for the uvo source Literal in CanonicalNotice."""
import pytest
from pydantic import ValidationError
from uvo_pipeline.models import CanonicalNotice


def test_source_accepts_uvo():
    notice = CanonicalNotice(
        source="uvo",
        source_id="12345",
        notice_type="contract_notice",
        title="Test",
    )
    assert notice.source == "uvo"


def test_source_rejects_unknown():
    with pytest.raises(ValidationError):
        CanonicalNotice(
            source="unknown_source",
            source_id="1",
            notice_type="other",
            title="x",
        )
```

- [ ] **Step 2: Run the test to see it fail**

Run:
```bash
uv run pytest tests/pipeline/test_models_uvo.py::test_source_accepts_uvo -v
```
Expected: `ValidationError` — `uvo` is not in the Literal.

- [ ] **Step 3: Add "uvo" to the source Literal**

In `src/uvo_pipeline/models.py`, line 51, change:
```python
    source: Literal["vestnik", "crz", "ted"]
```
to:
```python
    source: Literal["vestnik", "crz", "ted", "uvo"]
```

- [ ] **Step 4: Run the tests to see them pass**

Run:
```bash
uv run pytest tests/pipeline/test_models_uvo.py -v
```
Expected: 2 passed

- [ ] **Step 5: Confirm existing tests still pass**

Run:
```bash
uv run pytest tests/pipeline/ -v --tb=short
```
Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_pipeline/models.py tests/pipeline/test_models_uvo.py
git commit -m "feat: add 'uvo' to CanonicalNotice source Literal"
```

---

### Task 4: Extractor HTML parsing helpers

**Files:**
- Create: `src/uvo_pipeline/extractors/uvo.py` (partial — helpers only)
- Create: `tests/pipeline/extractors/test_uvo.py` (partial — helper tests only)

Note: Before writing fixtures, you must verify the actual HTML structure of a live uvo.gov.sk page. The spec uses educated guesses. Run:
```bash
curl -A "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0" \
  "https://www.uvo.gov.sk/vyhladavanie/vyhladavanie-zakaziek?limit=5&page=1" \
  -o /tmp/uvo_listing_sample.html
```
Open `/tmp/uvo_listing_sample.html` and inspect the actual table class names, row structure, and field positions. Then adjust the fixture strings and the parsing code below to match reality. The structure in the plan is the best available approximation — update it once you see the real HTML.

- [ ] **Step 1: Write failing tests for _parse_listing_row and _parse_detail_page**

Create `tests/pipeline/extractors/test_uvo.py`:
```python
"""Tests for the UVO extractor."""
import httpx
import pytest
import respx
from datetime import date

from uvo_pipeline.extractors.uvo import _parse_listing_row, _parse_detail_page, fetch_notices
from uvo_pipeline.utils.rate_limiter import RateLimiter

# Minimal realistic listing HTML with two notice rows.
# IMPORTANT: Verify this against real uvo.gov.sk HTML before implementation.
LISTING_HTML_TWO_ROWS = """
<html><body>
<table class="results-table">
  <tbody>
    <tr>
      <td><a href="/vestnik-a-registre/vestnik/oznamenie/detail/12345?cHash=abc123">Stavebné práce na moste</a></td>
      <td>Ministerstvo vnútra SR<br/><small>ICO: 00151866</small></td>
      <td>45221000-2</td>
      <td>15.03.2024</td>
      <td>Ukončené</td>
      <td>500 000,00 EUR</td>
    </tr>
    <tr>
      <td><a href="/vestnik-a-registre/vestnik/oznamenie/detail/99999?cHash=def456">IT systémy</a></td>
      <td>Ministerstvo financií SR<br/><small>ICO: 00151742</small></td>
      <td>72000000-5</td>
      <td>10.01.2024</td>
      <td>Prebiehajúce</td>
      <td>1 200 000,00 EUR</td>
    </tr>
  </tbody>
</table>
</body></html>
"""

LISTING_HTML_EMPTY = """
<html><body>
<table class="results-table"><tbody></tbody></table>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<div class="notice-detail">
  <div class="field-label">Dodávateľ</div>
  <div class="field-value">Stavby s.r.o.<br/>ICO: 44556677</div>
  <div class="field-label">Finálna cena</div>
  <div class="field-value">480 000,00 EUR</div>
  <div class="field-label">Dátum uzavretia zmluvy</div>
  <div class="field-value">01.06.2024</div>
</div>
</body></html>
"""


def test_parse_listing_row_returns_dict():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(LISTING_HTML_TWO_ROWS, "lxml")
    rows = soup.select("table.results-table tbody tr")
    assert len(rows) == 2
    result = _parse_listing_row(rows[0])
    assert result is not None
    assert result["id"] == "12345"
    assert result["title"] == "Stavebné práce na moste"
    assert result["procurer_name"] == "Ministerstvo vnútra SR"
    assert result["procurer_ico"] == "00151866"
    assert result["cpv"] == "45221000-2"
    assert result["published_date"] == "2024-03-15"
    assert result["status"] == "Ukončené"
    assert result["estimated_value"] == 500000.0
    assert result["detail_url"] == "/vestnik-a-registre/vestnik/oznamenie/detail/12345?cHash=abc123"


def test_parse_listing_row_second_row():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(LISTING_HTML_TWO_ROWS, "lxml")
    rows = soup.select("table.results-table tbody tr")
    result = _parse_listing_row(rows[1])
    assert result is not None
    assert result["id"] == "99999"
    assert result["estimated_value"] == 1200000.0
    assert result["published_date"] == "2024-01-10"


def test_parse_listing_row_returns_none_on_bad_html():
    from bs4 import Tag
    # Pass a completely empty tag that won't have expected children
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<tr></tr>", "lxml")
    row = soup.find("tr")
    result = _parse_listing_row(row)
    assert result is None


def test_parse_detail_page_extracts_supplier():
    result = _parse_detail_page(DETAIL_HTML)
    assert result["supplier_name"] == "Stavby s.r.o."
    assert result["supplier_ico"] == "44556677"
    assert result["final_value"] == 480000.0
    assert result["currency"] == "EUR"
    assert result["award_date"] == "2024-06-01"


def test_parse_detail_page_missing_supplier_returns_nones():
    html = "<html><body><div class='notice-detail'></div></body></html>"
    result = _parse_detail_page(html)
    assert result["supplier_name"] is None
    assert result["supplier_ico"] is None
    assert result["final_value"] is None
    assert result["award_date"] is None
```

- [ ] **Step 2: Run the tests to see them fail**

Run:
```bash
uv run pytest tests/pipeline/extractors/test_uvo.py::test_parse_listing_row_returns_dict -v
```
Expected: `ImportError: cannot import name '_parse_listing_row' from 'uvo_pipeline.extractors.uvo'`

- [ ] **Step 3: Create the extractor file with helpers only**

Create `src/uvo_pipeline/extractors/uvo.py`:
```python
"""UVO.gov.sk HTML scraper extractor.

Paginates the procurement listing at /vyhladavanie/vyhladavanie-zakaziek
and optionally fetches individual detail pages.

IMPORTANT: The HTML selectors here are based on educated guesses from the spec.
Before finalising, fetch a real listing page and verify:
  curl -A "Mozilla/5.0 ..." "https://www.uvo.gov.sk/vyhladavanie/vyhladavanie-zakaziek?limit=5&page=1"
Adjust _TABLE_SELECTOR, _ROW_SELECTOR, and the column index constants below to match.
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
            "notice_type_raw": None,  # refined from detail page
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
        "notice_type_raw": None,
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

        await rate_limiter.acquire()
        try:
            response = await client.get(
                _LISTING_PATH,
                params=params,
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (429, 503):
                logger.warning(
                    "UVO: HTTP %s on page %d, backing off",
                    exc.response.status_code, page,
                )
                await asyncio.sleep(30)
                continue
            logger.error("UVO: HTTP %s on listing page %d", exc.response.status_code, page)
            return
        except httpx.RequestError as exc:
            logger.error("UVO: request error on listing page %d: %s", page, exc)
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
        await asyncio.sleep(request_delay)
```

- [ ] **Step 4: Run the helper tests**

Run:
```bash
uv run pytest tests/pipeline/extractors/test_uvo.py::test_parse_listing_row_returns_dict \
             tests/pipeline/extractors/test_uvo.py::test_parse_listing_row_second_row \
             tests/pipeline/extractors/test_uvo.py::test_parse_listing_row_returns_none_on_bad_html \
             tests/pipeline/extractors/test_uvo.py::test_parse_detail_page_extracts_supplier \
             tests/pipeline/extractors/test_uvo.py::test_parse_detail_page_missing_supplier_returns_nones \
             -v
```
Expected: 5 passed. If any fail because real HTML differs from the fixture, adjust `_COL_*` constants and the `field-label`/`field-value` selectors to match what you observed from the live page.

- [ ] **Step 5: Commit**

```bash
git add src/uvo_pipeline/extractors/uvo.py tests/pipeline/extractors/test_uvo.py
git commit -m "feat: add UVO extractor HTML helpers with tests"
```

---

### Task 5: Extractor fetch_notices — pagination, date stop, detail fetch

**Files:**
- Modify: `src/uvo_pipeline/extractors/uvo.py` (already created — `fetch_notices` is already in the file from Task 4; this task adds integration-level tests for it)
- Modify: `tests/pipeline/extractors/test_uvo.py`

- [ ] **Step 1: Add fetch_notices tests to the existing test file**

Append to `tests/pipeline/extractors/test_uvo.py` (after the existing tests):
```python

# ---- fetch_notices integration tests ----

LISTING_HTML_ONE_ROW = """
<html><body>
<table class="results-table">
  <tbody>
    <tr>
      <td><a href="/vestnik-a-registre/vestnik/oznamenie/detail/12345?cHash=abc123">Stavebné práce na moste</a></td>
      <td>Ministerstvo vnútra SR<br/><small>ICO: 00151866</small></td>
      <td>45221000-2</td>
      <td>15.03.2024</td>
      <td>Ukončené</td>
      <td>500 000,00 EUR</td>
    </tr>
  </tbody>
</table>
</body></html>
"""

LISTING_HTML_OLD_ROW = """
<html><body>
<table class="results-table">
  <tbody>
    <tr>
      <td><a href="/vestnik-a-registre/vestnik/oznamenie/detail/99901?cHash=zzz">Staré dielo</a></td>
      <td>Starý úrad<br/><small>ICO: 00000001</small></td>
      <td>45000000-7</td>
      <td>01.01.2010</td>
      <td>Ukončené</td>
      <td>100 000,00 EUR</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


@pytest.mark.asyncio
async def test_fetch_listing_yields_notices():
    rate_limiter = RateLimiter(rate=100)
    with respx.mock(base_url="https://www.uvo.gov.sk") as mock:
        mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            side_effect=[
                httpx.Response(200, text=LISTING_HTML_TWO_ROWS),
                httpx.Response(200, text=LISTING_HTML_EMPTY),
            ]
        )
        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            results = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    to_date=date(2024, 12, 31),
                    fetch_details=False,
                    request_delay=0,
                )
            ]
    assert len(results) == 2
    assert results[0]["id"] == "12345"
    assert results[1]["id"] == "99999"


@pytest.mark.asyncio
async def test_fetch_stops_at_from_date():
    """A page with a notice older than from_date should stop pagination."""
    rate_limiter = RateLimiter(rate=100)
    with respx.mock(base_url="https://www.uvo.gov.sk") as mock:
        mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            return_value=httpx.Response(200, text=LISTING_HTML_OLD_ROW)
        )
        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            results = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    fetch_details=False,
                    request_delay=0,
                )
            ]
    # The old notice (2010) is below from_date so it is skipped
    assert results == []


@pytest.mark.asyncio
async def test_pagination_stops_on_empty_page():
    rate_limiter = RateLimiter(rate=100)
    with respx.mock(base_url="https://www.uvo.gov.sk") as mock:
        mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            side_effect=[
                httpx.Response(200, text=LISTING_HTML_ONE_ROW),
                httpx.Response(200, text=LISTING_HTML_EMPTY),
            ]
        )
        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            results = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    fetch_details=False,
                    request_delay=0,
                )
            ]
    assert len(results) == 1


@pytest.mark.asyncio
async def test_fetch_detail_extracts_supplier():
    rate_limiter = RateLimiter(rate=100)
    with respx.mock(base_url="https://www.uvo.gov.sk") as mock:
        mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            side_effect=[
                httpx.Response(200, text=LISTING_HTML_ONE_ROW),
                httpx.Response(200, text=LISTING_HTML_EMPTY),
            ]
        )
        mock.get(
            "/vestnik-a-registre/vestnik/oznamenie/detail/12345",
            params={"cHash": "abc123"},
        ).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            results = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    fetch_details=True,
                    request_delay=0,
                )
            ]
    assert len(results) == 1
    assert results[0]["supplier_name"] == "Stavby s.r.o."
    assert results[0]["supplier_ico"] == "44556677"
    assert results[0]["final_value"] == 480000.0


@pytest.mark.asyncio
async def test_fetch_listing_only_makes_no_detail_calls():
    rate_limiter = RateLimiter(rate=100)
    with respx.mock(base_url="https://www.uvo.gov.sk", assert_all_called=False) as mock:
        listing_route = mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            side_effect=[
                httpx.Response(200, text=LISTING_HTML_ONE_ROW),
                httpx.Response(200, text=LISTING_HTML_EMPTY),
            ]
        )
        detail_route = mock.get(
            "/vestnik-a-registre/vestnik/oznamenie/detail/12345"
        ).mock(return_value=httpx.Response(200, text=DETAIL_HTML))

        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            results = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    fetch_details=False,
                    request_delay=0,
                )
            ]
    assert len(results) == 1
    assert detail_route.called is False


@pytest.mark.asyncio
async def test_fetch_max_pages_limits_results():
    rate_limiter = RateLimiter(rate=100)
    with respx.mock(base_url="https://www.uvo.gov.sk") as mock:
        mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            return_value=httpx.Response(200, text=LISTING_HTML_TWO_ROWS)
        )
        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            results = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    fetch_details=False,
                    max_pages=1,
                    request_delay=0,
                )
            ]
    assert len(results) == 2  # both rows from the one allowed page
```

- [ ] **Step 2: Run the fetch_notices tests to see them fail**

Run:
```bash
uv run pytest tests/pipeline/extractors/test_uvo.py::test_fetch_listing_yields_notices -v
```
Expected: The test either fails because respx can't route the mock (detail URLs differ) or because pagination calls don't match. Fix the `fetch_notices` implementation if needed.

Note: `respx.mock` matches on path+params. The detail URL `/vestnik-a-registre/vestnik/oznamenie/detail/12345?cHash=abc123` is a relative URL — when `client.get` is called with it, respx will match against the base_url's host. The detail mock in `test_fetch_detail_extracts_supplier` may need adjustment to use `params={"cHash": "abc123"}` separately. Adjust as needed after seeing the actual failure.

- [ ] **Step 3: Run all extractor tests**

Run:
```bash
uv run pytest tests/pipeline/extractors/test_uvo.py -v
```
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/pipeline/extractors/test_uvo.py src/uvo_pipeline/extractors/uvo.py
git commit -m "feat: add UVO fetch_notices with pagination and detail fetch"
```

---

### Task 6: Transformer

**Files:**
- Create: `src/uvo_pipeline/transformers/uvo.py`
- Create: `tests/pipeline/transformers/test_uvo.py`

- [ ] **Step 1: Write the failing transformer tests**

Create `tests/pipeline/transformers/test_uvo.py`:
```python
"""Tests for the UVO transformer."""
import pytest
from datetime import date
from uvo_pipeline.transformers.uvo import transform_notice

FULL_RAW = {
    "id": "12345",
    "title": "Stavebné práce na moste",
    "procurer_name": "Ministerstvo vnútra SR",
    "procurer_ico": "00151866",
    "cpv": "45221000-2",
    "published_date": "2024-03-15",
    "status": "Ukončené",
    "estimated_value": 500000.0,
    "detail_url": "/vestnik-a-registre/vestnik/oznamenie/detail/12345?cHash=abc123",
    "notice_type_raw": "Zákazka",
    "supplier_name": "Stavby s.r.o.",
    "supplier_ico": "44556677",
    "final_value": 480000.0,
    "award_date": "2024-06-01",
    "currency": "EUR",
}


def test_transform_maps_required_fields():
    notice = transform_notice(FULL_RAW)
    assert notice.source == "uvo"
    assert notice.source_id == "12345"
    assert notice.title == "Stavebné práce na moste"
    assert notice.publication_date == date(2024, 3, 15)
    assert notice.cpv_code == "45221000-2"
    assert notice.estimated_value == 500000.0
    assert notice.status == "awarded"
    assert notice.notice_type == "contract_notice"


def test_transform_maps_procurer():
    notice = transform_notice(FULL_RAW)
    assert notice.procurer is not None
    assert notice.procurer.name == "Ministerstvo vnútra SR"
    assert notice.procurer.ico == "00151866"
    assert notice.procurer.name_slug == "ministerstvo-vnutra-sr"
    assert "uvo" in notice.procurer.sources


def test_transform_maps_supplier_to_award():
    notice = transform_notice(FULL_RAW)
    assert len(notice.awards) == 1
    award = notice.awards[0]
    assert award.supplier.name == "Stavby s.r.o."
    assert award.supplier.ico == "44556677"
    assert award.value == 480000.0
    assert award.currency == "EUR"
    assert award.signing_date == date(2024, 6, 1)


def test_transform_handles_missing_supplier():
    raw = {k: v for k, v in FULL_RAW.items() if k not in ("supplier_name", "supplier_ico", "final_value")}
    notice = transform_notice(raw)
    assert notice.awards == []


def test_transform_missing_value_is_none():
    raw = {k: v for k, v in FULL_RAW.items() if k != "estimated_value"}
    notice = transform_notice(raw)
    assert notice.estimated_value is None


def test_transform_missing_date_is_none():
    raw = {**FULL_RAW, "published_date": None}
    notice = transform_notice(raw)
    assert notice.publication_date is None


@pytest.mark.parametrize("uvo_status,expected", [
    ("Ukončené", "awarded"),
    ("Zmluvne ukončené", "awarded"),
    ("Zrušené", "cancelled"),
    ("Prebiehajúce", "announced"),
    ("Vyhlásené", "announced"),
    ("Neznámy stav", "unknown"),
    (None, "unknown"),
])
def test_transform_status_mapping(uvo_status, expected):
    raw = {**FULL_RAW, "status": uvo_status}
    notice = transform_notice(raw)
    assert notice.status == expected


@pytest.mark.parametrize("type_raw,expected", [
    ("Zákazka", "contract_notice"),
    ("Verejná zákazka", "contract_notice"),
    ("Zmluva", "contract_award"),
    ("Výsledok", "contract_award"),
    ("Predbežné oznámenie", "prior_information"),
    ("Oprava", "other"),
    ("Niečo iné", "other"),
    (None, "other"),
])
def test_transform_notice_type_mapping(type_raw, expected):
    raw = {**FULL_RAW, "notice_type_raw": type_raw}
    notice = transform_notice(raw)
    assert notice.notice_type == expected


def test_transform_no_procurer_when_name_missing():
    raw = {**FULL_RAW, "procurer_name": None}
    notice = transform_notice(raw)
    assert notice.procurer is None


def test_transform_currency_defaults_to_eur():
    raw = {k: v for k, v in FULL_RAW.items() if k != "currency"}
    notice = transform_notice(raw)
    # Awards currency should default to EUR
    assert notice.awards[0].currency == "EUR"
```

- [ ] **Step 2: Run tests to see them fail**

Run:
```bash
uv run pytest tests/pipeline/transformers/test_uvo.py -v
```
Expected: `ImportError: cannot import name 'transform_notice' from 'uvo_pipeline.transformers.uvo'`

- [ ] **Step 3: Create the transformer**

Create `src/uvo_pipeline/transformers/uvo.py`:
```python
"""UVO transformer — map raw UVO HTML-scraped dicts to CanonicalNotice."""

import logging
from datetime import date
from typing import Literal

from slugify import slugify

from uvo_pipeline.models import (
    CanonicalAward,
    CanonicalNotice,
    CanonicalProcurer,
    CanonicalSupplier,
)

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, str] = {
    "ukončené": "awarded",
    "zmluvne ukončené": "awarded",
    "zrušené": "cancelled",
    "prebiehajúce": "announced",
    "vyhlásené": "announced",
}

_NOTICE_TYPE_MAP: dict[str, str] = {
    "zákazka": "contract_notice",
    "verejná zákazka": "contract_notice",
    "zmluva": "contract_award",
    "výsledok": "contract_award",
    "predbežné oznámenie": "prior_information",
}


def _parse_date(value: str | None) -> date | None:
    """Parse an ISO date string 'YYYY-MM-DD' to a date, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("UVO: could not parse date: %r", value)
        return None


def _map_status(raw_status: str | None) -> str:
    if not raw_status:
        return "unknown"
    return _STATUS_MAP.get(raw_status.strip().lower(), "unknown")


def _map_notice_type(raw_type: str | None) -> str:
    if not raw_type:
        return "other"
    return _NOTICE_TYPE_MAP.get(raw_type.strip().lower(), "other")


def _build_procurer(raw: dict) -> CanonicalProcurer | None:
    name = raw.get("procurer_name")
    if not name:
        return None
    return CanonicalProcurer(
        ico=raw.get("procurer_ico"),
        name=name,
        name_slug=slugify(name),
        sources=["uvo"],
    )


def _build_awards(raw: dict) -> list[CanonicalAward]:
    supplier_name = raw.get("supplier_name")
    if not supplier_name:
        return []
    supplier = CanonicalSupplier(
        ico=raw.get("supplier_ico"),
        name=supplier_name,
        name_slug=slugify(supplier_name),
        sources=["uvo"],
    )
    return [
        CanonicalAward(
            supplier=supplier,
            value=raw.get("final_value"),
            currency=raw.get("currency") or "EUR",
            signing_date=_parse_date(raw.get("award_date")),
        )
    ]


def transform_notice(raw: dict) -> CanonicalNotice:
    """Map a raw UVO dict → CanonicalNotice."""
    return CanonicalNotice(
        source="uvo",
        source_id=str(raw["id"]),
        notice_type=_map_notice_type(raw.get("notice_type_raw")),  # type: ignore[arg-type]
        status=_map_status(raw.get("status")),  # type: ignore[arg-type]
        title=raw.get("title") or "Unnamed notice",
        procurer=_build_procurer(raw),
        awards=_build_awards(raw),
        cpv_code=raw.get("cpv"),
        estimated_value=raw.get("estimated_value"),
        final_value=raw.get("final_value"),
        currency=raw.get("currency") or "EUR",
        publication_date=_parse_date(raw.get("published_date")),
        award_date=_parse_date(raw.get("award_date")),
    )
```

- [ ] **Step 4: Run transformer tests**

Run:
```bash
uv run pytest tests/pipeline/transformers/test_uvo.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Run all pipeline tests to confirm no regressions**

Run:
```bash
uv run pytest tests/pipeline/ -v --tb=short
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_pipeline/transformers/uvo.py tests/pipeline/transformers/test_uvo.py
git commit -m "feat: add UVO transformer with status/type mapping"
```

---

### Task 7: Orchestrator wiring

**Files:**
- Modify: `src/uvo_pipeline/orchestrator.py`
- Modify: `tests/pipeline/test_orchestrator.py`

- [ ] **Step 1: Add a test that dry_run still works after wiring**

Append to `tests/pipeline/test_orchestrator.py`:
```python

@pytest.mark.asyncio
async def test_dry_run_completes_without_uvo_error():
    """dry_run=True should return a report without touching any DB or HTTP."""
    from uvo_pipeline.orchestrator import run
    from uvo_pipeline.config import PipelineSettings

    settings = PipelineSettings(
        uvo_base_url="https://www.uvo.gov.sk",
        uvo_fetch_details=False,
    )
    report = await run("recent", settings=settings, dry_run=True)
    assert report.finished_at is not None
    assert report.errors == []
```

- [ ] **Step 2: Run the test to verify it already passes (dry_run skips everything)**

Run:
```bash
uv run pytest tests/pipeline/test_orchestrator.py::test_dry_run_completes_without_uvo_error -v
```
Expected: PASS (the dry_run path returns early before any HTTP calls).

- [ ] **Step 3: Wire the UVO extraction step into orchestrator.py**

In `src/uvo_pipeline/orchestrator.py`, after the TED block (after line 222, after `report.source_counts["ted"] = ted_count`), add:

```python
        # Step 9: UVO.gov.sk extractor
        from uvo_pipeline.extractors.uvo import fetch_notices as fetch_uvo_notices
        from uvo_pipeline.transformers.uvo import transform_notice as transform_uvo_notice
        from uvo_pipeline.utils.rate_limiter import RateLimiter

        logger.info("Extracting from UVO.gov.sk (from=%s)...", from_date)
        uvo_rate_limiter = RateLimiter(rate=int(settings.uvo_rate_limit), per=1.0)
        uvo_count = 0
        uvo_to_date = datetime.utcnow().date()

        async with httpx.AsyncClient(
            base_url=settings.uvo_base_url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"},
            timeout=settings.request_timeout,
        ) as uvo_client:
            if mode == "historical":
                # Year-by-year to avoid huge in-memory batches
                from_year = settings.historical_from_year
                current_year = uvo_to_date.year
                for year in range(from_year, current_year + 1):
                    year_from = date(year, 1, 1)
                    year_to = date(year, 12, 31)
                    async for raw in fetch_uvo_notices(
                        uvo_client,
                        uvo_rate_limiter,
                        from_date=year_from,
                        to_date=year_to,
                        fetch_details=settings.uvo_fetch_details,
                        request_delay=settings.uvo_request_delay,
                    ):
                        try:
                            notice = transform_uvo_notice(raw)
                            notice.pipeline_run_id = run_id
                            all_notices.append(notice)
                            uvo_count += 1
                        except Exception as exc:
                            logger.warning("UVO transform error: %s", exc)
            else:
                async for raw in fetch_uvo_notices(
                    uvo_client,
                    uvo_rate_limiter,
                    from_date=from_date,
                    to_date=uvo_to_date,
                    fetch_details=settings.uvo_fetch_details,
                    request_delay=settings.uvo_request_delay,
                ):
                    try:
                        notice = transform_uvo_notice(raw)
                        notice.pipeline_run_id = run_id
                        all_notices.append(notice)
                        uvo_count += 1
                    except Exception as exc:
                        logger.warning("UVO transform error: %s", exc)

        report.source_counts["uvo"] = uvo_count
        logger.info("UVO: %d notices extracted", uvo_count)
```

- [ ] **Step 4: Run all orchestrator tests**

Run:
```bash
uv run pytest tests/pipeline/test_orchestrator.py -v --tb=short
```
Expected: all pass (dry_run path is unaffected by the new block).

- [ ] **Step 5: Run the full pipeline test suite**

Run:
```bash
uv run pytest tests/pipeline/ -v --tb=short
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/uvo_pipeline/orchestrator.py tests/pipeline/test_orchestrator.py
git commit -m "feat: wire UVO extractor into pipeline orchestrator"
```

---

### Task 8: End-to-end smoke test

**Files:**
- Create: `tests/pipeline/test_uvo_smoke.py`

This test verifies the entire path from config → extractor → transformer without hitting any real URLs.

- [ ] **Step 1: Write the smoke test**

Create `tests/pipeline/test_uvo_smoke.py`:
```python
"""End-to-end smoke test for the UVO pipeline path.

Mocks a single listing page (2 rows) + 2 detail pages, runs through
the extractor → transformer chain, and asserts canonical notices are produced.
"""
import httpx
import pytest
import respx
from datetime import date

from uvo_pipeline.extractors.uvo import fetch_notices
from uvo_pipeline.transformers.uvo import transform_notice
from uvo_pipeline.utils.rate_limiter import RateLimiter

LISTING_HTML = """
<html><body>
<table class="results-table">
  <tbody>
    <tr>
      <td><a href="/vestnik-a-registre/vestnik/oznamenie/detail/11111?cHash=aaa">Rekonštrukcia budovy</a></td>
      <td>Ministerstvo zdravotníctva SR<br/><small>ICO: 00165565</small></td>
      <td>45215000-7</td>
      <td>20.06.2024</td>
      <td>Ukončené</td>
      <td>750 000,00 EUR</td>
    </tr>
    <tr>
      <td><a href="/vestnik-a-registre/vestnik/oznamenie/detail/22222?cHash=bbb">Dodávka kancelárskych potrieb</a></td>
      <td>Ministerstvo školstva SR<br/><small>ICO: 00166188</small></td>
      <td>30192000-1</td>
      <td>15.05.2024</td>
      <td>Prebiehajúce</td>
      <td>50 000,00 EUR</td>
    </tr>
  </tbody>
</table>
</body></html>
"""

DETAIL_11111 = """
<html><body>
<div class="notice-detail">
  <div class="field-label">Dodávateľ</div>
  <div class="field-value">Stavebná firma s.r.o.<br/>ICO: 12345678</div>
  <div class="field-label">Finálna cena</div>
  <div class="field-value">720 000,00 EUR</div>
  <div class="field-label">Dátum uzavretia zmluvy</div>
  <div class="field-value">01.08.2024</div>
</div>
</body></html>
"""

DETAIL_22222 = """
<html><body>
<div class="notice-detail">
  <div class="field-label">Dodávateľ</div>
  <div class="field-value">Papier a.s.<br/>ICO: 87654321</div>
  <div class="field-label">Finálna cena</div>
  <div class="field-value">48 000,00 EUR</div>
</div>
</body></html>
"""

EMPTY_PAGE = """
<html><body>
<table class="results-table"><tbody></tbody></table>
</body></html>
"""


@pytest.mark.asyncio
async def test_uvo_smoke_extractor_to_transformer():
    rate_limiter = RateLimiter(rate=100)

    with respx.mock(base_url="https://www.uvo.gov.sk", assert_all_called=False) as mock:
        mock.get("/vyhladavanie/vyhladavanie-zakaziek").mock(
            side_effect=[
                httpx.Response(200, text=LISTING_HTML),
                httpx.Response(200, text=EMPTY_PAGE),
            ]
        )
        mock.get(
            "/vestnik-a-registre/vestnik/oznamenie/detail/11111",
            params={"cHash": "aaa"},
        ).mock(return_value=httpx.Response(200, text=DETAIL_11111))
        mock.get(
            "/vestnik-a-registre/vestnik/oznamenie/detail/22222",
            params={"cHash": "bbb"},
        ).mock(return_value=httpx.Response(200, text=DETAIL_22222))

        async with httpx.AsyncClient(base_url="https://www.uvo.gov.sk") as client:
            raws = [
                r async for r in fetch_notices(
                    client,
                    rate_limiter,
                    from_date=date(2024, 1, 1),
                    to_date=date(2024, 12, 31),
                    fetch_details=True,
                    request_delay=0,
                )
            ]

    assert len(raws) == 2

    notices = [transform_notice(r) for r in raws]

    n1 = notices[0]
    assert n1.source == "uvo"
    assert n1.source_id == "11111"
    assert n1.title == "Rekonštrukcia budovy"
    assert n1.status == "awarded"
    assert n1.notice_type == "contract_notice"
    assert n1.procurer is not None
    assert n1.procurer.ico == "00165565"
    assert len(n1.awards) == 1
    assert n1.awards[0].supplier.name == "Stavebná firma s.r.o."
    assert n1.awards[0].value == 720000.0
    assert n1.awards[0].signing_date is not None

    n2 = notices[1]
    assert n2.source == "uvo"
    assert n2.source_id == "22222"
    assert n2.status == "announced"
    assert n2.awards[0].supplier.ico == "87654321"
```

- [ ] **Step 2: Run the smoke test**

Run:
```bash
uv run pytest tests/pipeline/test_uvo_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 3: Run the complete test suite**

Run:
```bash
uv run pytest tests/ -v --tb=short -m "not e2e and not integration"
```
Expected: all pass, no new failures.

- [ ] **Step 4: Commit**

```bash
git add tests/pipeline/test_uvo_smoke.py
git commit -m "test: add UVO end-to-end smoke test"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| `beautifulsoup4` + `lxml` deps | Task 1 |
| 4 config fields | Task 2 |
| `"uvo"` in source Literal | Task 3 |
| `_parse_listing_row` helper | Task 4 |
| `_parse_detail_page` helper | Task 4 |
| `fetch_notices` async generator | Task 4 (implementation) + Task 5 (tests) |
| Pagination stops on empty page | Task 5 test `test_pagination_stops_on_empty_page` |
| Date boundary stop | Task 5 test `test_fetch_stops_at_from_date` |
| Detail fetch, `fetch_details=False` | Task 5 tests |
| `max_pages` guard | Task 5 test `test_fetch_max_pages_limits_results` |
| `transform_notice` | Task 6 |
| Status mapping (all 5 branches) | Task 6 parametrized test |
| Notice type mapping (all 5 branches) | Task 6 parametrized test |
| Missing supplier → `awards=[]` | Task 6 test |
| Orchestrator step after TED | Task 7 |
| Historical year-by-year loop | Task 7 implementation |
| `dry_run=True` still works | Task 7 test |
| Full extractor→transformer smoke | Task 8 |

**Placeholder scan:** None found. All steps contain exact code.

**Type consistency check:**
- `fetch_notices` signature uses `RateLimiter` from `uvo_pipeline.utils.rate_limiter` — consistent across Tasks 4, 5, 7, 8.
- `transform_notice` function name used in Task 6 implementation and Task 7 import: both `transform_uvo_notice` alias at the orchestrator call site. Consistent.
- `_parse_listing_row(row: Tag) -> dict | None` — used in Task 4 tests with `rows[0]` from BeautifulSoup, consistent.
- `_parse_detail_page(html: str) -> dict` — used in Task 4 tests with HTML strings, consistent.
- `CanonicalNotice.source` Literal updated in Task 3 before transformer (Task 6) sets `source="uvo"`. Correct order.

---

### Critical Files for Implementation

- `/home/max/Documents/src/uvo-search/src/uvo_pipeline/extractors/uvo.py`
- `/home/max/Documents/src/uvo-search/src/uvo_pipeline/transformers/uvo.py`
- `/home/max/Documents/src/uvo-search/src/uvo_pipeline/orchestrator.py`
- `/home/max/Documents/src/uvo-search/src/uvo_pipeline/models.py`
- `/home/max/Documents/src/uvo-search/src/uvo_pipeline/config.py`

---

The plan is complete. Note that it cannot be saved to `docs/superpowers/plans/2026-04-11-uvo-scraper.md` from this read-only planning session — the plan is returned here as output for the parent agent to save.

Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
