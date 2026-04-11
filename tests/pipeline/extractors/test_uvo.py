"""Tests for the UVO extractor."""
import httpx
import pytest
import respx
from datetime import date

from uvo_pipeline.extractors.uvo import _parse_listing_row, _parse_detail_page, fetch_notices
from uvo_pipeline.utils.rate_limiter import RateLimiter

# Minimal realistic listing HTML with two notice rows.
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
