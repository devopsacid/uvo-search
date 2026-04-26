"""Tests for the CRZ extractor."""

from datetime import date

import httpx
import pytest
import respx

from uvo_pipeline.extractors.crz import fetch_contracts_since
from uvo_pipeline.utils.rate_limiter import RateLimiter

CONTRACT_1 = {
    "id": 5587100,
    "subject": "Test contract",
    "contracting_authority_name": "City",
    "contracting_authority_cin_raw": "11111111",
    "supplier_name": "Supplier",
    "supplier_cin_raw": "22222222",
    "signed_on": "2024-01-15",
    "contract_price_total_amount": "50000.0",
}
CONTRACT_2 = {
    "id": 5587200,
    "subject": "Another contract",
    "contracting_authority_name": "Ministry",
    "contracting_authority_cin_raw": "33333333",
    "supplier_name": "Other",
    "supplier_cin_raw": "44444444",
    "signed_on": "2024-02-01",
    "contract_price_total_amount": "25000.0",
}

# The sync endpoint returns full contract objects directly (no separate detail fetch)
SYNC_CONTRACTS = [CONTRACT_1, CONTRACT_2]


@pytest.mark.asyncio
async def test_fetch_contracts_yields_items():
    rate_limiter = RateLimiter(rate=30)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(
            return_value=httpx.Response(200, json=SYNC_CONTRACTS)
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert len(results) == 2
    assert results[0]["id"] == 5587100


@pytest.mark.asyncio
async def test_fetch_handles_sync_error():
    rate_limiter = RateLimiter(rate=30)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_empty_sync_response():
    """An empty list from the sync endpoint should yield no items."""
    rate_limiter = RateLimiter(rate=30)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(
            return_value=httpx.Response(200, json=[])
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_sends_since_param():
    """The `since` date should be forwarded as a query param."""
    rate_limiter = RateLimiter(rate=30)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        sync_route = mock.get("/api/data/crz/contracts/sync").mock(
            return_value=httpx.Response(200, json=[])
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
    rate_limiter = RateLimiter(rate=30)
    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        sync_route = mock.get("/api/data/crz/contracts/sync").mock(
            return_value=httpx.Response(200, json=[])
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


@pytest.mark.asyncio
async def test_fetch_retries_on_429(monkeypatch):
    """A single 429 response should trigger a sleep + retry, yielding the eventual success."""
    rate_limiter = RateLimiter(rate=30)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("uvo_pipeline.extractors.crz.asyncio.sleep", fake_sleep)

    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "3"}, json={"message": "rate limit"}),
                httpx.Response(200, json=SYNC_CONTRACTS),
            ]
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert len(results) == 2
    assert sleeps == [3]


@pytest.mark.asyncio
async def test_fetch_429_without_retry_after_uses_default(monkeypatch):
    """If no Retry-After header, fall back to 60 seconds."""
    rate_limiter = RateLimiter(rate=30)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("uvo_pipeline.extractors.crz.asyncio.sleep", fake_sleep)

    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(
            side_effect=[
                httpx.Response(429, json={"message": "rate limit"}),
                httpx.Response(200, json=[]),
            ]
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert results == []
    assert sleeps == [60]


@pytest.mark.asyncio
async def test_fetch_gives_up_after_repeated_429(monkeypatch):
    """After exhausting retries the extractor stops gracefully."""
    rate_limiter = RateLimiter(rate=30)

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("uvo_pipeline.extractors.crz.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("uvo_pipeline.extractors.crz._MAX_429_RETRIES", 2)

    with respx.mock(base_url="https://datahub.ekosystem.slovensko.digital") as mock:
        mock.get("/api/data/crz/contracts/sync").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "1"})
        )
        async with httpx.AsyncClient(
            base_url="https://datahub.ekosystem.slovensko.digital"
        ) as client:
            results = [r async for r in fetch_contracts_since(client, rate_limiter)]

    assert results == []
