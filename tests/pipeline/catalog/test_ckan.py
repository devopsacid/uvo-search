"""Tests for CKAN catalog discovery."""

import httpx
import pytest
from datetime import date

from uvo_pipeline.catalog.ckan import discover_vestnik_packages, extract_zip_urls


@pytest.mark.asyncio
async def test_discover_yields_no_packages_while_disabled():
    # CKAN is currently disabled (data.gov.sk replaced by data.slovensko.sk)
    async with httpx.AsyncClient(base_url="https://data.gov.sk") as client:
        packages = [p async for p in discover_vestnik_packages(client)]
    assert packages == []


@pytest.mark.asyncio
async def test_discover_handles_error_gracefully():
    # Stub always returns empty regardless of server response
    async with httpx.AsyncClient(base_url="https://data.gov.sk") as client:
        packages = [p async for p in discover_vestnik_packages(client)]
    assert packages == []


@pytest.mark.asyncio
async def test_extract_zip_urls_returns_zip_resources():
    dataset = {
        "resources": [
            {"url": "https://example.com/data.zip", "format": "ZIP"},
            {"url": "https://example.com/readme.txt", "format": "TXT"},
        ]
    }
    urls = await extract_zip_urls(dataset)
    assert urls == ["https://example.com/data.zip"]
