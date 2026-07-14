"""One-shot: repair CRZ notices whose publication_date was corrupted upstream.

Upstream CRZ occasionally sends a corrupted signed_on year (transposed
digits, e.g. "3202-03-02" for "2023-03-02", or "1024-10-24" for
"2024-10-24"), which previously propagated straight into publication_date
and awards[].signing_date. uvo_pipeline.transformers.crz now rejects
implausible years (<2000 or >current+1) and falls back to
published_at -> effective_from (see _resolve_signing_date), but that fix
only applies to newly-ingested contracts — this script repairs the ~114
already-written notices with a bad or missing publication_date.

Finds source=='crz' notices with publication_date null, <2000-01-01, or
>2100-01-01 (ISO date strings sort lexicographically, so plain string
comparison works), re-fetches each contract from the CRZ API by source_id,
re-transforms it with the fixed transformer, and bulk-writes the corrected
publication_date + awards[0].signing_date.

Safe to re-run — idempotent (re-fetches + re-transforms every time).

Usage:
  python -m scripts.repair_crz_dates [--dry-run] [--batch-size N]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.crz import fetch_contract_by_id
from uvo_pipeline.transformers.crz import transform_contract
from uvo_pipeline.utils.rate_limiter import RateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("repair_crz_dates")

_MIN_DATE = "2000-01-01"
_MAX_DATE = "2100-01-01"


def _corrupted_date_query() -> dict:
    return {
        "source": "crz",
        "$or": [
            {"publication_date": None},
            {"publication_date": {"$lt": _MIN_DATE}},
            {"publication_date": {"$gt": _MAX_DATE}},
        ],
    }


async def main(batch_size: int, dry_run: bool) -> int:
    settings = PipelineSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]

    docs = await db.notices.find(
        _corrupted_date_query(), {"source_id": 1, "publication_date": 1}
    ).to_list(length=None)
    logger.info("Found %d CRZ notices with corrupted/missing publication_date", len(docs))

    if not docs:
        client.close()
        return 0

    rate_limiter = RateLimiter(rate=int(settings.crz_rate_limit), per=60.0)
    processed = 0
    updated = 0
    unresolved = 0
    failed = 0
    ops: list[UpdateOne] = []

    async with httpx.AsyncClient(
        base_url=settings.ekosystem_base_url,
        timeout=settings.request_timeout,
    ) as client_http:
        for doc in docs:
            processed += 1
            source_id = doc["source_id"]

            raw = await fetch_contract_by_id(
                client_http, rate_limiter, source_id, api_token=settings.ekosystem_api_token,
            )
            if raw is None:
                logger.warning("CRZ %s: re-fetch failed, skipping", source_id)
                failed += 1
                continue

            try:
                notice = transform_contract(raw)
            except Exception as exc:
                logger.warning("CRZ %s: transform failed: %s", source_id, exc)
                failed += 1
                continue

            new_pub_date = notice.publication_date.isoformat() if notice.publication_date else None
            if new_pub_date is None:
                # All three of signed_on/published_at/effective_from were
                # missing or implausible upstream — nothing to correct to.
                logger.warning("CRZ %s: no plausible date found upstream either", source_id)
                unresolved += 1
                continue

            update: dict = {"publication_date": new_pub_date}
            if notice.awards:
                signing_date = notice.awards[0].signing_date
                update["awards.0.signing_date"] = signing_date.isoformat() if signing_date else None

            logger.info(
                "CRZ %s: publication_date %r -> %r",
                source_id, doc.get("publication_date"), new_pub_date,
            )

            if not dry_run:
                ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": update}))
                updated += 1

            if len(ops) >= batch_size:
                await db.notices.bulk_write(ops, ordered=False)
                ops.clear()

        if ops:
            await db.notices.bulk_write(ops, ordered=False)

    logger.info(
        "Done: %d processed, %d updated (dry_run=%s), %d unresolved, %d failed",
        processed, updated, dry_run, unresolved, failed,
    )

    client.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch-size", type=int, default=50, help="Bulk-write batch size")
    p.add_argument("--dry-run", action="store_true", help="Fetch + transform but skip writes")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.batch_size, args.dry_run)))
