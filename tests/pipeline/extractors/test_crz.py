"""Tests for the CRZ extractor."""

import httpx
import pytest
import respx
from datetime import date

from uvo_pipeline.extractors.crz import fetch_contracts_since
from uvo_pipeline.utils.rate_limiter import RateLimiter

SYNC_RESPONSE = {"ids": ["crz-1", "crz-2"]}
CONTRACT_1 = {
    "id": "crz-1",
    "predmet": "Test contract",
    "objednavatel": {"nazov": "City", "ico": "11111111"},
    "dodavatel": {"nazov": "Supplier", "ico": "22222222"},
    "datum_podpisu": "2024-01-15",
    "celkova_hodnota": 50000.0,
    "mena": "EUR",
}
CONTRACT_2 = {
    "id": "crz-2",
    "predmet": "Another contract",
    "objednavatel": {"nazov": "Ministry", "ico": "33333333"},
    "dodavatel": {"nazov": "Other", "ico": "44444444"},
    "datum_podpisu": "2024-02-01",
    "celkova_hodnota": 25000.0,
    "mena": "EUR",
}


@pytest.mark.asyncio
async def test_fetch_contracts_yields_items():
    rate_limiter = RateLimiter(rate=55)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/datahub/crz/sync").mock(
            return_value=httpx.Response(200, json=SYNC_RESPONSE)
        )
        mock.get("/api/data/crz/contracts/crz-1").mock(
            return_value=httpx.Response(200, json=CONTRACT_1)
        )
        mock.get("/api/data/crz/contracts/crz-2").mock(
            return_value=httpx.Response(200, json=CONTRACT_2)
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert len(results) == 2
    assert results[0]["id"] == "crz-1"


@pytest.mark.asyncio
async def test_fetch_handles_sync_error():
    rate_limiter = RateLimiter(rate=55)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/datahub/crz/sync").mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_failed_contract():
    """A failing contract detail request should be skipped, not abort iteration."""
    rate_limiter = RateLimiter(rate=55)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/datahub/crz/sync").mock(
            return_value=httpx.Response(200, json=SYNC_RESPONSE)
        )
        mock.get("/api/data/crz/contracts/crz-1").mock(
            return_value=httpx.Response(404)
        )
        mock.get("/api/data/crz/contracts/crz-2").mock(
            return_value=httpx.Response(200, json=CONTRACT_2)
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert len(results) == 1
    assert results[0]["id"] == "crz-2"


@pytest.mark.asyncio
async def test_fetch_sends_since_param():
    """The `since` date should be forwarded as a query param."""
    rate_limiter = RateLimiter(rate=55)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        sync_route = mock.get("/api/datahub/crz/sync").mock(
            return_value=httpx.Response(200, json={"ids": []})
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [
                r
                async for r in fetch_contracts_since(
                    client, rate_limiter, since=date(2024, 1, 1)
                )
            ]

    assert results == []
    assert "since" in str(sync_route.calls.last.request.url)


@pytest.mark.asyncio
async def test_fetch_sends_api_token():
    """When api_token is set it should appear in query params."""
    rate_limiter = RateLimiter(rate=55)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        sync_route = mock.get("/api/datahub/crz/sync").mock(
            return_value=httpx.Response(200, json={"ids": []})
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [
                r
                async for r in fetch_contracts_since(
                    client, rate_limiter, api_token="secret-token"
                )
            ]

    assert results == []
    assert "access_token" in str(sync_route.calls.last.request.url)
