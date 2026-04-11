"""Tests for the ITMS2014+ extractor."""

import httpx
import pytest
import respx
from uvo_pipeline.extractors.itms import fetch_procurements
from uvo_pipeline.utils.rate_limiter import RateLimiter

BASE = "https://opendata.itms2014.sk"

PROCUREMENT_1 = {
    "id": 36674224, "kod": "VO36674224",
    "nazov": "Dodávka kancelárskeho materiálu",
    "predpokladanaHodnotaZakazky": 15000.0,
    "stav": "Ukoncene",
    "datumZverejneniaVoVestniku": "2023-06-15T00:00:00",
    "hlavnyPredmetHlavnySlovnik": {"id": 101, "kod": "30192000-1"},
    "obstaravatelSubjekt": {"id": 5, "nazov": "Ministerstvo financií SR", "ico": "00151742"},
}
PROCUREMENT_2 = {
    "id": 36674225, "kod": "VO36674225",
    "nazov": "Dodávka IT vybavenia",
    "predpokladanaHodnotaZakazky": 50000.0,
    "stav": "Prebieha",
    "datumZverejneniaVoVestniku": "2023-07-01T00:00:00",
    "hlavnyPredmetHlavnySlovnik": {"id": 102, "kod": "72000000-5"},
    "obstaravatelSubjekt": {"id": 6, "nazov": "Ministerstvo vnútra SR", "ico": "00151866"},
}
CONTRACT_1 = {
    "id": 1001,
    "dodavatel": {"id": 200, "nazov": "Office supplies s.r.o.", "ico": "12345678"},
    "celkovaHodnotaZmluvy": 14500.0, "mena": "EUR",
}


def _make_list_side_effect(*pages):
    """Return a side_effect that sequences through pages then returns empty."""
    pages_list = list(pages)
    call_count = [0]

    def side_effect(request):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(pages_list):
            return httpx.Response(200, json=pages_list[idx])
        return httpx.Response(200, json=[])

    return side_effect


@pytest.mark.asyncio
async def test_fetch_yields_one_procurement_with_contracts():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(
            side_effect=_make_list_side_effect([PROCUREMENT_1])
        )
        mock.get(f"/v2/verejneObstaravania/{PROCUREMENT_1['id']}/zmluvyVerejneObstaravanie").mock(
            return_value=httpx.Response(200, json=[CONTRACT_1])
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]
    assert len(results) == 1
    assert results[0]["_contracts"] == [CONTRACT_1]


@pytest.mark.asyncio
async def test_fetch_paginates_across_two_pages():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(
            side_effect=_make_list_side_effect([PROCUREMENT_1], [PROCUREMENT_2])
        )
        mock.get(f"/v2/verejneObstaravania/{PROCUREMENT_1['id']}/zmluvyVerejneObstaravanie").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.get(f"/v2/verejneObstaravania/{PROCUREMENT_2['id']}/zmluvyVerejneObstaravanie").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]

    assert len(results) == 2
    assert results[0]["id"] == PROCUREMENT_1["id"]
    assert results[1]["id"] == PROCUREMENT_2["id"]


@pytest.mark.asyncio
async def test_fetch_empty_first_page_yields_nothing():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]
    assert results == []


@pytest.mark.asyncio
async def test_fetch_respects_min_id_param():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        list_route = mock.get("/v2/verejneObstaravania").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter, min_id=500)]
    assert "500" in str(list_route.calls.last.request.url)


@pytest.mark.asyncio
async def test_fetch_contracts_404_gives_empty_list():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(
            side_effect=_make_list_side_effect([PROCUREMENT_1])
        )
        mock.get(f"/v2/verejneObstaravania/{PROCUREMENT_1['id']}/zmluvyVerejneObstaravanie").mock(
            return_value=httpx.Response(404)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]
    assert len(results) == 1
    assert results[0]["_contracts"] == []


@pytest.mark.asyncio
async def test_fetch_list_http_error_yields_nothing():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]
    assert results == []
