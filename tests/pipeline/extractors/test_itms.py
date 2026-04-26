"""Tests for the ITMS2014+ extractor (new shape: list stub → detail + contracts + subject)."""

import httpx
import pytest
import respx

from uvo_pipeline.extractors.itms import fetch_procurements
from uvo_pipeline.utils.rate_limiter import RateLimiter

BASE = "https://opendata.itms2014.sk"

# List endpoint returns reference stubs only
STUB_1 = {
    "id": 2,
    "kod": "VO66152197",
    "predpokladanaHodnotaZakazky": 328405,
    "stav": "Ukončené",
    "obstaravatelSubjekt": {"subjekt": {"href": "/v2/subjekty/100184", "id": 100184}},
}
STUB_2 = {
    "id": 4,
    "kod": "VO36674224",
    "predpokladanaHodnotaZakazky": 18795312.9,
    "stav": "Ukončené",
    "obstaravatelSubjekt": {"subjekt": {"href": "/v2/subjekty/100076", "id": 100076}},
}

# Singular detail response adds title, date, CPV, zadavatel(ico)
DETAIL_1 = {
    **STUB_1,
    "nazov": "Rozšírenie kapacity ČOV Lozorno",
    "datumZverejneniaVoVestniku": "2014-02-25T00:00:00Z",
    "hlavnyPredmetHlavnySlovnik": {"ciselnikKod": 1049, "id": 6902},
    "zadavatel": {"subjekt": {"id": 100184, "ico": "00304905", "dic": "2020643669"}},
}

SUBJECT_100184 = {
    "id": 100184,
    "nazov": "Obec Lozorno",
    "ico": "00304905",
    "dic": "2020643669",
}
SUBJECT_100076 = {
    "id": 100076,
    "nazov": "Ministerstvo dopravy SR",
    "ico": "30416094",
}

CONTRACT_1 = {
    "id": 1001,
    "hlavnyDodavatelDodavatelObstaravatel": {
        "href": "/v2/dodavatelia/200",
        "ico": "12345678",
        "id": 200,
    },
    "celkovaSumaZmluvy": 14500.0,
}
SUPPLIER_200 = {"id": 200, "nazov": "Office supplies s.r.o.", "ico": "12345678"}


def _list_side_effect(*pages):
    pages_list = list(pages)
    count = [0]

    def side_effect(request):
        i = count[0]
        count[0] += 1
        return httpx.Response(200, json=pages_list[i] if i < len(pages_list) else [])

    return side_effect


@pytest.mark.asyncio
async def test_fetch_enriches_with_detail_contracts_and_subject():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(side_effect=_list_side_effect([STUB_1]))
        mock.get(f"/v2/verejneObstaravania/{STUB_1['id']}").mock(
            return_value=httpx.Response(200, json=DETAIL_1)
        )
        mock.get(f"/v2/verejneObstaravania/{STUB_1['id']}/zmluvyVerejneObstaravanie").mock(
            return_value=httpx.Response(200, json=[CONTRACT_1])
        )
        mock.get(f"/v2/subjekty/{SUBJECT_100184['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100184)
        )
        mock.get(f"/v2/dodavatelia/{SUPPLIER_200['id']}").mock(
            return_value=httpx.Response(200, json=SUPPLIER_200)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]

    assert len(results) == 1
    r = results[0]
    assert r["nazov"] == "Rozšírenie kapacity ČOV Lozorno"
    assert r["_subject"]["nazov"] == "Obec Lozorno"
    assert r["_subject"]["ico"] == "00304905"
    # Supplier name enrichment
    assert r["_contracts"][0]["_supplier"]["nazov"] == "Office supplies s.r.o."
    assert r["_contracts"][0]["_supplier"]["ico"] == "12345678"


@pytest.mark.asyncio
async def test_fetch_paginates_across_two_pages():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(side_effect=_list_side_effect([STUB_1], [STUB_2]))
        for sid in (STUB_1["id"], STUB_2["id"]):
            mock.get(f"/v2/verejneObstaravania/{sid}").mock(
                return_value=httpx.Response(200, json={"id": sid, "stav": "Prebieha"})
            )
            mock.get(f"/v2/verejneObstaravania/{sid}/zmluvyVerejneObstaravanie").mock(
                return_value=httpx.Response(200, json=[])
            )
        mock.get(f"/v2/subjekty/{SUBJECT_100184['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100184)
        )
        mock.get(f"/v2/subjekty/{SUBJECT_100076['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100076)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]

    assert [r["id"] for r in results] == [STUB_1["id"], STUB_2["id"]]


@pytest.mark.asyncio
async def test_fetch_empty_first_page_yields_nothing():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(return_value=httpx.Response(200, json=[]))
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
            [r async for r in fetch_procurements(client, rate_limiter, min_id=500)]
    assert "500" in str(list_route.calls.last.request.url)


@pytest.mark.asyncio
async def test_fetch_contracts_404_gives_empty_list():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(side_effect=_list_side_effect([STUB_1]))
        mock.get(f"/v2/verejneObstaravania/{STUB_1['id']}").mock(
            return_value=httpx.Response(200, json=DETAIL_1)
        )
        mock.get(f"/v2/verejneObstaravania/{STUB_1['id']}/zmluvyVerejneObstaravanie").mock(
            return_value=httpx.Response(404)
        )
        mock.get(f"/v2/subjekty/{SUBJECT_100184['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100184)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]
    assert results[0]["_contracts"] == []


@pytest.mark.asyncio
async def test_fetch_list_http_error_yields_nothing():
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/v2/verejneObstaravania").mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [r async for r in fetch_procurements(client, rate_limiter)]
    assert results == []


@pytest.mark.asyncio
async def test_fetch_stops_when_max_items_reached():
    """max_items caps yields and prevents an extra list page request."""
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        list_route = mock.get("/v2/verejneObstaravania").mock(
            side_effect=_list_side_effect([STUB_1, STUB_2])
        )
        for sid in (STUB_1["id"], STUB_2["id"]):
            mock.get(f"/v2/verejneObstaravania/{sid}").mock(
                return_value=httpx.Response(200, json={"id": sid, "stav": "Prebieha"})
            )
            mock.get(f"/v2/verejneObstaravania/{sid}/zmluvyVerejneObstaravanie").mock(
                return_value=httpx.Response(200, json=[])
            )
        mock.get(f"/v2/subjekty/{SUBJECT_100184['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100184)
        )
        mock.get(f"/v2/subjekty/{SUBJECT_100076['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100076)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            results = [
                r async for r in fetch_procurements(client, rate_limiter, max_items=1)
            ]

    assert len(results) == 1
    assert results[0]["id"] == STUB_1["id"]
    # Only the first list page should have been fetched.
    assert list_route.call_count == 1


@pytest.mark.asyncio
async def test_subject_cache_avoids_repeat_fetches():
    """Two procurements sharing a procurer should trigger only one subject fetch."""
    rate_limiter = RateLimiter(rate=10000)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        shared = {**STUB_2, "obstaravatelSubjekt": STUB_1["obstaravatelSubjekt"]}
        mock.get("/v2/verejneObstaravania").mock(side_effect=_list_side_effect([STUB_1, shared]))
        for sid in (STUB_1["id"], shared["id"]):
            mock.get(f"/v2/verejneObstaravania/{sid}").mock(
                return_value=httpx.Response(200, json={"stav": "Prebieha", **STUB_1, "id": sid})
            )
            mock.get(f"/v2/verejneObstaravania/{sid}/zmluvyVerejneObstaravanie").mock(
                return_value=httpx.Response(200, json=[])
            )
        subj_route = mock.get(f"/v2/subjekty/{SUBJECT_100184['id']}").mock(
            return_value=httpx.Response(200, json=SUBJECT_100184)
        )
        async with httpx.AsyncClient(base_url=BASE) as client:
            _ = [r async for r in fetch_procurements(client, rate_limiter)]

    assert subj_route.call_count == 1
