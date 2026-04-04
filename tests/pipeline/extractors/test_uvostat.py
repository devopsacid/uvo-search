"""Tests for the UVOstat API extractor."""

import pytest
import httpx
import respx
from datetime import date

from uvo_pipeline.extractors.uvostat import fetch_all_procurements, fetch_announced_procurements

PROCUREMENT_FIXTURE = {
    "data": [
        {
            "id": "1",
            "nazov": "Test procurement",
            "obstaravatel": {"id": "10", "nazov": "Ministry", "ico": "12345678"},
            "dodavatelia": [{"id": "20", "nazov": "Acme", "ico": "87654321"}],
            "hodnota_zmluvy": 50000.0,
            "mena": "EUR",
            "datum_zverejnenia": "2024-06-01",
            "cpv": "72000000-5",
        },
        {
            "id": "2",
            "nazov": "Another one",
            "obstaravatel": {"id": "10", "nazov": "Ministry", "ico": "12345678"},
            "dodavatelia": [],
            "hodnota_zmluvy": None,
            "mena": "EUR",
            "datum_zverejnenia": "2024-06-02",
            "cpv": None,
        },
    ],
    "total": 2,
    "limit": 100,
    "offset": 0,
}


@pytest.mark.asyncio
async def test_fetch_all_procurements_yields_items():
    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(200, json=PROCUREMENT_FIXTURE)
        )
        async with httpx.AsyncClient(
            base_url="https://www.uvostat.sk", headers={"ApiToken": "test"}
        ) as client:
            results = [r async for r in fetch_all_procurements(client)]
    assert len(results) == 2
    assert results[0]["id"] == "1"


@pytest.mark.asyncio
async def test_fetch_all_procurements_with_date_filter():
    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        route = mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(
                200, json={**PROCUREMENT_FIXTURE, "data": [], "total": 0}
            )
        )
        async with httpx.AsyncClient(
            base_url="https://www.uvostat.sk", headers={"ApiToken": "test"}
        ) as client:
            results = [
                r
                async for r in fetch_all_procurements(client, date_from=date(2024, 1, 1))
            ]
    assert results == []
    assert "datum_zverejnenia_od=2024-01-01" in str(route.calls[0].request.url)


@pytest.mark.asyncio
async def test_fetch_handles_http_error_gracefully():
    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        mock.get("/api/ukoncene_obstaravania").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        async with httpx.AsyncClient(
            base_url="https://www.uvostat.sk", headers={"ApiToken": "bad"}
        ) as client:
            results = [r async for r in fetch_all_procurements(client)]
    assert results == []  # error logged, no raise


@pytest.mark.asyncio
async def test_fetch_announced_procurements_yields_items():
    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        mock.get("/api/vyhlasene_obstaravania").mock(
            return_value=httpx.Response(200, json=PROCUREMENT_FIXTURE)
        )
        async with httpx.AsyncClient(
            base_url="https://www.uvostat.sk", headers={"ApiToken": "test"}
        ) as client:
            results = [r async for r in fetch_announced_procurements(client)]
    assert len(results) == 2
    assert results[1]["id"] == "2"


@pytest.mark.asyncio
async def test_fetch_paginates_multiple_pages():
    """Verify that a second page is fetched when offset < total."""
    page1 = {
        "data": [{"id": "1", "nazov": "First"}],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }
    page2 = {
        "data": [{"id": "2", "nazov": "Second"}],
        "total": 2,
        "limit": 1,
        "offset": 1,
    }

    call_count = 0

    def response_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json=page1)
        return httpx.Response(200, json=page2)

    with respx.mock(base_url="https://www.uvostat.sk") as mock:
        mock.get("/api/ukoncene_obstaravania").mock(side_effect=response_handler)
        async with httpx.AsyncClient(
            base_url="https://www.uvostat.sk", headers={"ApiToken": "test"}
        ) as client:
            results = [r async for r in fetch_all_procurements(client, batch_size=1)]

    assert len(results) == 2
    assert call_count == 2
