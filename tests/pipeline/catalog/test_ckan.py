"""Tests for CKAN catalog discovery."""

import httpx
import pytest
import respx
from datetime import date

from uvo_pipeline.catalog.ckan import discover_vestnik_packages, extract_zip_urls

CKAN_PAGE = {
    "success": True,
    "result": {
        "count": 2,
        "results": [
            {
                "id": "pkg-1",
                "name": "vestnik-1-2025",
                "metadata_modified": "2025-01-15T10:00:00",
                "resources": [{"url": "https://example.com/vestnik_01.zip", "format": "ZIP"}],
            },
            {
                "id": "pkg-2",
                "name": "vestnik-2-2025",
                "metadata_modified": "2025-02-01T10:00:00",
                "resources": [{"url": "https://example.com/vestnik_02.zip", "format": "ZIP"}],
            },
        ],
    },
}


@pytest.mark.asyncio
async def test_discover_yields_packages():
    with respx.mock(base_url="https://data.gov.sk") as mock:
        mock.get("/api/3/action/package_search").mock(
            return_value=httpx.Response(200, json=CKAN_PAGE)
        )
        async with httpx.AsyncClient(base_url="https://data.gov.sk") as client:
            packages = [p async for p in discover_vestnik_packages(client)]
    assert len(packages) == 2
    assert packages[0]["id"] == "pkg-1"


@pytest.mark.asyncio
async def test_discover_handles_error_gracefully():
    with respx.mock(base_url="https://data.gov.sk") as mock:
        mock.get("/api/3/action/package_search").mock(
            return_value=httpx.Response(500)
        )
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
