"""One-shot: backfill title_slug on notices where it's null but title is present.

No transformer ever set title_slug directly (see uvo_pipeline.models.CanonicalNotice,
which now derives it via a model validator for all *new* writes). Dedup pass 2
(title_slug + publication_date ±7 days, see uvo_pipeline.dedup) depends on it, so
the ~480k pre-existing notices need a one-time backfill to catch up.

content_hash does not include title_slug, so this backfill is a plain $set and
does not need to touch content_hash or re-run through upsert_batch.

Safe to re-run — only touches notices where title_slug is currently null.

Usage:
  python -m scripts.backfill_title_slug [--batch-size N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
from slugify import slugify

from uvo_pipeline.config import PipelineSettings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("backfill_title_slug")


def _target_query() -> dict:
    # Mongo matches missing-or-null fields with {"field": None}.
    return {"title_slug": None, "title": {"$ne": None, "$exists": True}}


async def main(batch_size: int, dry_run: bool) -> int:
    settings = PipelineSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]

    query = _target_query()
    total = await db.notices.count_documents(query)
    logger.info("Found %d notices with null title_slug and a non-null title", total)

    if not total:
        client.close()
        return 0

    processed = 0
    updated = 0
    ops: list[UpdateOne] = []

    cursor = db.notices.find(query, {"_id": 1, "title": 1})
    async for doc in cursor:
        title = doc.get("title")
        if not title:
            continue
        slug = slugify(title)
        processed += 1

        if dry_run:
            if processed <= 10:
                logger.info("  dry-run preview: %r -> %r", title, slug)
            continue

        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"title_slug": slug}}))
        if len(ops) >= batch_size:
            result = await db.notices.bulk_write(ops, ordered=False)
            updated += result.modified_count
            logger.info("progress: %d/%d processed, %d updated", processed, total, updated)
            ops.clear()

    if ops:
        result = await db.notices.bulk_write(ops, ordered=False)
        updated += result.modified_count

    logger.info(
        "Done: %d processed, %d updated (dry_run=%s)", processed, updated, dry_run,
    )

    client.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch-size", type=int, default=1000, help="Bulk-write batch size")
    p.add_argument("--dry-run", action="store_true", help="Count + preview only, no writes")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.batch_size, args.dry_run)))
