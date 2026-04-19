"""SPARQL discovery for Vestník bulletins on data.slovensko.sk."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

_SPARQL_TEMPLATE = """\
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
SELECT ?dataset ?title ?issued ?modified ?url WHERE {{
  ?dataset a dcat:Dataset ;
           dct:publisher <{publisher_uri}> ;
           dct:title ?title ;
           dcat:distribution ?dist .
  ?dist dcat:accessURL ?url .
  OPTIONAL {{ ?dataset dct:issued   ?issued }}
  OPTIONAL {{ ?dataset dct:modified ?modified }}
  FILTER (lang(?title) = "sk")
  {since_filter}
}} ORDER BY ?modified LIMIT {page_size} OFFSET {offset}"""


@dataclass
class VestnikDataset:
    uri: str
    title: str
    publish_date: date | None
    modified: datetime | None
    download_url: str


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except (ValueError, TypeError):
        return None


async def discover_vestnik_datasets(
    client: httpx.AsyncClient,
    *,
    publisher_uri: str,
    sparql_url: str,
    since: date | None = None,
    page_size: int = 200,
) -> AsyncIterator[VestnikDataset]:
    since_filter = (
        f'FILTER (?modified >= "{since.isoformat()}T00:00:00"^^xsd:dateTime)'
        if since
        else ""
    )
    offset = 0

    while True:
        query = _SPARQL_TEMPLATE.format(
            publisher_uri=publisher_uri,
            since_filter=since_filter,
            page_size=page_size,
            offset=offset,
        )
        try:
            response = await client.post(
                sparql_url,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "NKOD SPARQL HTTP %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return
        except httpx.RequestError as exc:
            logger.warning("NKOD SPARQL request failed: %s", exc)
            return

        bindings = response.json().get("results", {}).get("bindings", [])
        if not bindings:
            break

        for row in bindings:
            modified_dt = _parse_dt(row.get("modified", {}).get("value"))
            issued_dt = _parse_dt(row.get("issued", {}).get("value"))
            pub_date = issued_dt.date() if issued_dt else None
            yield VestnikDataset(
                uri=row["dataset"]["value"],
                title=row["title"]["value"],
                publish_date=pub_date,
                modified=modified_dt,
                download_url=row["url"]["value"],
            )

        offset += page_size
