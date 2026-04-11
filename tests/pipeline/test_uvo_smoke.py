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
    # notice_type is derived from status: "awarded" → "contract_award"
    assert n1.notice_type == "contract_award"
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
