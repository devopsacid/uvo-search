"""Tests for Vestník NKOD bulletin extractor."""

import httpx
import json
import pytest
import respx
from datetime import date, datetime
from pathlib import Path

from uvo_pipeline.catalog.nkod import VestnikDataset
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.utils.rate_limiter import RateLimiter


NOTICE_A = {
    "id": 1397309,
    "name": "Oznámenie o výsledku verejného obstarávania (D24)",
    "components": [],
}

NOTICE_B = {
    "id": 1397310,
    "name": "Oznámenie o zmene verejného obstarávania (D25)",
    "components": [],
}

ENVELOPE = {
    "bulletinPublishDate": "2026-04-17T01:02:38",
    "year": 2026,
    "number": 76,
    "bulletinItemList": [
        {"itemData": json.dumps(NOTICE_A)},
        {"itemData": json.dumps(NOTICE_B)},
    ],
}

DATASET = VestnikDataset(
    uri="https://data.gov.sk/set/vestnik/V-76-2026",
    title="Vestník 76/2026",
    publish_date=date(2026, 4, 17),
    modified=datetime(2026, 4, 17, 1, 2, 38),
    download_url="https://data.slovensko.sk/download?id=abc-123",
)


@pytest.mark.asyncio
async def test_fetch_yields_enriched_items():
    """Downloaded envelope is decoded and items are enriched with bulletin metadata."""
    rate_limiter = RateLimiter(rate=10000)

    with respx.mock(assert_all_called=False) as mock:
        mock.get(DATASET.download_url).mock(
            return_value=httpx.Response(200, json=ENVELOPE)
        )
        async with httpx.AsyncClient(follow_redirects=True) as client:
            items = [item async for item in fetch_bulletin(
                client, rate_limiter, DATASET
            )]

    assert len(items) == 2
    assert items[0]["id"] == 1397309
    assert items[0]["_bulletin_year"] == 2026
    assert items[0]["_bulletin_number"] == 76
    assert items[0]["_bulletin_publish_date"] == "2026-04-17T01:02:38"
    assert items[0]["_dataset_uri"] == DATASET.uri
    assert items[0]["_dataset_title"] == DATASET.title

    assert items[1]["id"] == 1397310
    assert items[1]["_bulletin_year"] == 2026


@pytest.mark.asyncio
async def test_fetch_with_cache_dir(tmp_path):
    """Cache dir parameter is accepted and used (integration test)."""
    rate_limiter = RateLimiter(rate=10000)

    with respx.mock(assert_all_called=False) as mock:
        mock.get(DATASET.download_url).mock(
            return_value=httpx.Response(200, json=ENVELOPE)
        )
        async with httpx.AsyncClient(follow_redirects=True) as client:
            items = [item async for item in fetch_bulletin(
                client, rate_limiter, DATASET, cache_dir=tmp_path
            )]

    # Just verify the generator works with cache_dir parameter
    assert len(items) == 2
    assert items[0]["id"] == 1397309


@pytest.mark.asyncio
async def test_fetch_skips_bad_item_data(tmp_path):
    """Invalid JSON in itemData is logged and skipped; valid items are yielded."""
    rate_limiter = RateLimiter(rate=10000)

    bad_envelope = {
        "bulletinPublishDate": "2026-04-17T01:02:38",
        "year": 2026,
        "number": 76,
        "bulletinItemList": [
            {"itemData": json.dumps(NOTICE_A)},
            {"itemData": "NOT VALID JSON {"},  # Bad JSON
            {"itemData": json.dumps(NOTICE_B)},
        ],
    }

    with respx.mock(assert_all_called=False) as mock:
        mock.get(DATASET.download_url).mock(
            return_value=httpx.Response(200, json=bad_envelope)
        )
        async with httpx.AsyncClient(follow_redirects=True) as client:
            items = [item async for item in fetch_bulletin(
                client, rate_limiter, DATASET
            )]

    # Only the two valid items should be yielded
    assert len(items) == 2
    assert items[0]["id"] == 1397309
    assert items[1]["id"] == 1397310


@pytest.mark.asyncio
async def test_fetch_returns_on_http_error():
    """HTTP error on download returns empty iteration."""
    rate_limiter = RateLimiter(rate=10000)

    with respx.mock(assert_all_called=False) as mock:
        mock.get(DATASET.download_url).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient(follow_redirects=True) as client:
            items = [item async for item in fetch_bulletin(
                client, rate_limiter, DATASET
            )]

    assert items == []
