"""Tests for NKOD SPARQL discovery of Vestník datasets."""

import httpx
import pytest
import respx
from datetime import date, datetime

from uvo_pipeline.catalog.nkod import discover_vestnik_datasets, VestnikDataset

SPARQL_URL = "https://data.slovakiaplus.sk/sparql"
PUBLISHER_URI = "https://data.gov.sk/org/vestnik"


def _sparql_response(*bindings_list):
    """Build a SPARQL JSON response."""
    return {"results": {"bindings": list(bindings_list)}}


def _binding(dataset_uri, title, issued, modified, url):
    """Build a single SPARQL result binding."""
    return {
        "dataset": {"value": dataset_uri},
        "title": {"value": title},
        "issued": {"value": issued},
        "modified": {"value": modified},
        "url": {"value": url},
    }


@pytest.mark.asyncio
async def test_discover_yields_parsed_datasets():
    """One SPARQL row yields one VestnikDataset with fields correctly parsed."""
    row = _binding(
        dataset_uri="https://data.gov.sk/set/vestnik/V-76-2026",
        title="Vestník 76/2026",
        issued="2026-04-17T00:00:00",
        modified="2026-04-17T01:02:38",
        url="https://data.slovensko.sk/download?id=abc-123",
    )
    first_page = _sparql_response(row)
    second_page = _sparql_response()  # empty page stops iteration

    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(SPARQL_URL)
        route.side_effect = [
            httpx.Response(200, json=first_page),
            httpx.Response(200, json=second_page),
        ]
        async with httpx.AsyncClient() as client:
            datasets = [d async for d in discover_vestnik_datasets(
                client,
                publisher_uri=PUBLISHER_URI,
                sparql_url=SPARQL_URL,
            )]

    assert len(datasets) == 1
    ds = datasets[0]
    assert ds.uri == "https://data.gov.sk/set/vestnik/V-76-2026"
    assert ds.title == "Vestník 76/2026"
    assert ds.publish_date == date(2026, 4, 17)
    assert ds.modified == datetime(2026, 4, 17, 1, 2, 38)
    assert ds.download_url == "https://data.slovensko.sk/download?id=abc-123"


@pytest.mark.asyncio
async def test_discover_paginates_until_empty_page():
    """Pagination: first page has 2 rows, second page is empty."""
    row1 = _binding(
        "https://data.gov.sk/set/vestnik/V-75-2026",
        "Vestník 75/2026",
        "2026-04-16T00:00:00",
        "2026-04-16T10:00:00",
        "https://data.slovensko.sk/download?id=xyz-789",
    )
    row2 = _binding(
        "https://data.gov.sk/set/vestnik/V-76-2026",
        "Vestník 76/2026",
        "2026-04-17T00:00:00",
        "2026-04-17T01:02:38",
        "https://data.slovensko.sk/download?id=abc-123",
    )
    first_page = _sparql_response(row1, row2)
    second_page = _sparql_response()  # empty

    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(SPARQL_URL)
        route.side_effect = [
            httpx.Response(200, json=first_page),
            httpx.Response(200, json=second_page),
        ]
        async with httpx.AsyncClient() as client:
            datasets = [d async for d in discover_vestnik_datasets(
                client,
                publisher_uri=PUBLISHER_URI,
                sparql_url=SPARQL_URL,
            )]

    assert len(datasets) == 2
    assert datasets[0].uri == "https://data.gov.sk/set/vestnik/V-75-2026"
    assert datasets[1].uri == "https://data.gov.sk/set/vestnik/V-76-2026"
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_discover_uses_since_filter():
    """With since=date(2026, 1, 1), SPARQL query includes date filter."""
    row = _binding(
        "https://data.gov.sk/set/vestnik/V-1-2026",
        "Vestník 1/2026",
        "2026-01-02T00:00:00",
        "2026-01-02T08:00:00",
        "https://data.slovensko.sk/download?id=early",
    )
    first_page = _sparql_response(row)
    second_page = _sparql_response()

    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(SPARQL_URL)
        route.side_effect = [
            httpx.Response(200, json=first_page),
            httpx.Response(200, json=second_page),
        ]
        async with httpx.AsyncClient() as client:
            [d async for d in discover_vestnik_datasets(
                client,
                publisher_uri=PUBLISHER_URI,
                sparql_url=SPARQL_URL,
                since=date(2026, 1, 1),
            )]

    # Inspect the POST body for the FILTER clause (URL-encoded form data)
    request = route.calls[0].request
    body = request.content.decode()
    import urllib.parse
    decoded = urllib.parse.unquote(body)
    assert '2026-01-01T00:00:00' in decoded and 'FILTER' in decoded


@pytest.mark.asyncio
async def test_discover_stops_on_http_error():
    """HTTP 500 on first page yields nothing and stops iteration."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post(SPARQL_URL).mock(return_value=httpx.Response(500, text="Server error"))
        async with httpx.AsyncClient() as client:
            datasets = [d async for d in discover_vestnik_datasets(
                client,
                publisher_uri=PUBLISHER_URI,
                sparql_url=SPARQL_URL,
            )]

    assert datasets == []
