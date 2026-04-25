"""One-shot: backfill awards[] on TED notices that were ingested before
winner fields were wired up in the v3 transformer.

Re-runs the TED SK search from historical_from_year with the updated
extractor (which now requests winner/result fields) and re-transforms
each notice via the updated transformer. Upserts into Mongo + Neo4j.

Idempotent — (source, source_id) is the upsert key; content_hash is
recomputed each pass.

Usage:
  python -m scripts.enrich_ted_awards [--from-year 2014] [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.ted import search_sk_notices
from uvo_pipeline.loaders.mongo import upsert_batch
from uvo_pipeline.loaders.neo4j import merge_notice_batch
from uvo_pipeline.transformers.ted import transform_ted_notice
from uvo_pipeline.utils.hashing import compute_notice_hash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("enrich_ted")


async def main(from_year: int, limit: int | None, dry_run: bool) -> int:
    settings = PipelineSettings()

    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_database]
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    batch: list = []
    batch_size = 200
    processed = 0
    upserted = 0
    failed = 0
    current_year = date.today().year

    async def flush() -> None:
        nonlocal upserted
        if batch and not dry_run:
            result = await upsert_batch(db, batch, batch_size=batch_size)
            upserted += result["inserted"] + result["updated"]
            async with neo4j_driver.session() as s:
                await merge_notice_batch(s, batch)
        batch.clear()

    async with httpx.AsyncClient(
        base_url=settings.ted_base_url,
        timeout=settings.request_timeout,
    ) as client:
        # TED v3 caps pagination at 15,000 per query. Segment by year so each
        # yearly slice fits the window, and narrow to CAN types (the ones
        # that actually carry winner/supplier data).
        for year in range(from_year, current_year + 1):
            year_from = date(year, 1, 1)
            year_to = date(year, 12, 31)
            logger.info("TED CAN backfill: year=%d", year)
            async for raw in search_sk_notices(
                client,
                date_from=year_from,
                date_to=year_to,
                awards_only=True,
            ):
                try:
                    notice = transform_ted_notice(raw)
                    notice.content_hash = compute_notice_hash(notice)
                    batch.append(notice)
                except Exception as exc:
                    logger.warning("TED transform error: %s", exc)
                    failed += 1
                processed += 1

                if limit and processed >= limit:
                    break

                if len(batch) >= batch_size:
                    await flush()
                    logger.info(
                        "progress: year=%d, %d processed, %d upserted, %d failed",
                        year, processed, upserted, failed,
                    )

            if limit and processed >= limit:
                break

        await flush()

    logger.info(
        "Done: %d processed, %d upserted (dry_run=%s), %d failed",
        processed, upserted, dry_run, failed,
    )

    mongo_client.close()
    await neo4j_driver.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from-year", type=int, default=2014)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args.from_year, args.limit, args.dry_run)))
