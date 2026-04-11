"""Tests for the TED extractor."""

import httpx
import pytest
import respx
from datetime import date

from uvo_pipeline.extractors.ted import search_sk_notices

TED_RESPONSE = {
    "notices": [
        {
            "publication-number": "25",
            "publication-date": "20240615",
            "notice-title": "IT services",
            "classification-cpv": ["72000000"],
            "buyer-name": "Ministry",
            "tender-value": 50000,
            "tender-value-cur": "EUR",
        },
    ],
    "page": 1,
    "totalNoticeCount": 1,
}


@pytest.mark.asyncio
async def test_search_sk_notices_yields_items():
    with respx.mock(base_url="https://api.ted.europa.eu") as mock:
        mock.post("/v3/notices/search").mock(
            return_value=httpx.Response(200, json=TED_RESPONSE)
        )
        async with httpx.AsyncClient(base_url="https://api.ted.europa.eu") as client:
            results = [r async for r in search_sk_notices(client)]

    assert len(results) == 1
    assert results[0]["notice-title"] == "IT services"


@pytest.mark.asyncio
async def test_search_handles_error():
    with respx.mock(base_url="https://api.ted.europa.eu") as mock:
        mock.post("/v3/notices/search").mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient(base_url="https://api.ted.europa.eu") as client:
            results = [r async for r in search_sk_notices(client)]

    assert results == []


@pytest.mark.asyncio
async def test_search_paginates():
    """With total > page_size, a second request should be made."""
    page1 = {
        "notices": [{"publication-number": "24", "publication-date": "20240101", "notice-title": "Notice 1"}],
        "page": 1,
        "totalNoticeCount": 2,
    }
    page2 = {
        "notices": [{"publication-number": "24", "publication-date": "20240102", "notice-title": "Notice 2"}],
        "page": 2,
        "totalNoticeCount": 2,
    }
    with respx.mock(base_url="https://api.ted.europa.eu") as mock:
        mock.post("/v3/notices/search").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        async with httpx.AsyncClient(base_url="https://api.ted.europa.eu") as client:
            results = [r async for r in search_sk_notices(client, page_size=1)]

    assert len(results) == 2
    assert results[0]["notice-title"] == "Notice 1"
    assert results[1]["notice-title"] == "Notice 2"


@pytest.mark.asyncio
async def test_search_date_filter_included_in_query():
    """date_from should be encoded into the query string sent to TED."""
    captured_bodies: list[dict] = []

    async def capture(request: httpx.Request, *args, **kwargs) -> httpx.Response:
        import json
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"notices": [], "page": 1, "total": 0})

    with respx.mock(base_url="https://api.ted.europa.eu") as mock:
        mock.post("/v3/notices/search").mock(side_effect=capture)
        async with httpx.AsyncClient(base_url="https://api.ted.europa.eu") as client:
            results = [
                r
                async for r in search_sk_notices(
                    client, date_from=date(2024, 1, 1), date_to=date(2024, 12, 31)
                )
            ]

    assert results == []
    assert len(captured_bodies) == 1
    query = captured_bodies[0]["query"]
    assert "20240101" in query
    assert "20241231" in query
