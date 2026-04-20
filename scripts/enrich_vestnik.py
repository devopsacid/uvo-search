"""One-shot: full Vestník NKOD backfill.

Discovers every Vestník dataset published by UVO (publisher IČO 31797903)
via the NKOD SPARQL endpoint, downloads each bulletin, transforms and
upserts into Mongo + Neo4j. Runs independently of the full pipeline so
it can be kicked off while other sources are ingesting.

Idempotent on (source, source_id) via upsert_batch.

Usage:
  python -m scripts.enrich_vestnik [--since YYYY-MM-DD] [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime
from pathlib import Path

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase

from uvo_pipeline.catalog.nkod import discover_vestnik_datasets
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.loaders.mongo import upsert_batch
from uvo_pipeline.loaders.neo4j import merge_notice_batch
from uvo_pipeline.transformers.vestnik_nkod import transform_notice
from uvo_pipeline.utils.hashing import compute_notice_hash
from uvo_pipeline.utils.rate_limiter import RateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("enrich_vestnik")


async def main(since: date | None, limit: int | None, dry_run: bool) -> int:
    settings = PipelineSettings()

    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_database]
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    batch: list = []
    batch_size = 500
    processed = 0
    upserted = 0
    skipped_xml = 0
    transform_failed = 0

    async def flush() -> None:
        nonlocal upserted
        if batch and not dry_run:
            result = await upsert_batch(db, batch, batch_size=batch_size)
            upserted += result["inserted"] + result["updated"]
            async with neo4j_driver.session() as s:
                await merge_notice_batch(s, batch)
        batch.clear()

    cache_dir = Path(settings.cache_dir)
    rate_limiter = RateLimiter(rate=max(1, int(settings.vestnik_rate_limit)), per=1.0)

    seen_uris: set[str] = set()

    async with httpx.AsyncClient(timeout=settings.request_timeout) as sparql_client, \
        httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as dl_client:
        dataset_count = 0
        async for ds in discover_vestnik_datasets(
            sparql_client,
            publisher_uri=settings.uvo_publisher_uri,
            sparql_url=settings.nkod_sparql_url,
            since=since,
        ):
            # Each dataset exposes multiple distributions (JSON, XML, XLSX…)
            # as separate SPARQL rows — content is identical, skip dupes.
            if ds.uri in seen_uris:
                continue
            seen_uris.add(ds.uri)
            dataset_count += 1
            before_count = processed
            async for raw in fetch_bulletin(dl_client, rate_limiter, ds, cache_dir=cache_dir):
                try:
                    notice = transform_notice(raw)
                    notice.content_hash = compute_notice_hash(notice)
                    batch.append(notice)
                except Exception as exc:
                    logger.warning(
                        "transform failed (dataset=%s, item=%s): %s",
                        ds.title, raw.get("id"), str(exc).splitlines()[0],
                    )
                    transform_failed += 1
                processed += 1

                if limit and processed >= limit:
                    break

                if len(batch) >= batch_size:
                    await flush()

            if before_count == processed:
                # fetch_bulletin yielded zero items — likely XML-era bulletin
                # that the JSON-only extractor can't parse.
                skipped_xml += 1

            if dataset_count % 20 == 0:
                logger.info(
                    "progress: %d datasets, %d notices processed, %d upserted, "
                    "%d skipped (XML-era), %d transform errors",
                    dataset_count, processed, upserted, skipped_xml, transform_failed,
                )

            if limit and processed >= limit:
                break

        await flush()

    logger.info(
        "Done: %d datasets visited, %d notices processed, %d upserted "
        "(dry_run=%s), %d XML-era bulletins skipped, %d transform errors",
        dataset_count, processed, upserted, dry_run, skipped_xml, transform_failed,
    )

    mongo_client.close()
    await neo4j_driver.close()
    return 0


def _parse_since(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=str, default=None, help="YYYY-MM-DD (default: all)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(_parse_since(args.since), args.limit, args.dry_run)))
