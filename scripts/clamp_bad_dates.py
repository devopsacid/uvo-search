# scripts/clamp_bad_dates.py
# One-shot backfill: null out implausible date years in `notices`.
# Run: uv run python scripts/clamp_bad_dates.py --dry-run
"""One-shot: scan `notices` for implausible date years and null them out.

Mirrors the runtime validation rule. Use --dry-run first.
Logs each clamp to `ingestion_log` with event=notice_invalid_date
component=backfill so the UI surfaces them just like live events.
"""

import argparse
import asyncio
from datetime import date

from motor.motor_asyncio import AsyncIOMotorClient

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.ingestion_log import ensure_log_indexes, log_event
from uvo_pipeline.utils.date_validation import MIN_YEAR, max_year


DATE_FIELDS = ["publication_date", "deadline_date", "award_date"]


async def main(dry_run: bool, limit: int | None) -> None:
    settings = PipelineSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]
    await ensure_log_indexes(db)

    lo, hi = MIN_YEAR, max_year()
    query = {
        "$or": [
            {f: {"$lt": f"{lo:04d}-01-01"}} for f in DATE_FIELDS
        ] + [
            {f: {"$gt": f"{hi:04d}-12-31"}} for f in DATE_FIELDS
        ]
    }

    cursor = db.notices.find(query)
    if limit:
        cursor = cursor.limit(limit)

    fixed = 0
    async for doc in cursor:
        unsets = {}
        details_per_field = []
        for f in DATE_FIELDS:
            v = doc.get(f)
            if isinstance(v, str) and len(v) >= 4:
                try:
                    y = int(v[:4])
                except ValueError:
                    continue
                if y < lo or y > hi:
                    unsets[f] = ""
                    details_per_field.append({"field": f, "year": y})
            elif isinstance(v, date):
                if v.year < lo or v.year > hi:
                    unsets[f] = ""
                    details_per_field.append({"field": f, "year": v.year})

        if not unsets:
            continue

        if not dry_run:
            await db.notices.update_one(
                {"_id": doc["_id"]},
                {"$unset": unsets},
            )
            for d in details_per_field:
                await log_event(
                    db,
                    level="warning",
                    event="notice_invalid_date",
                    component="backfill",
                    source=doc.get("source"),
                    source_id=doc.get("source_id"),
                    message=f"backfill: {d['field']} year {d['year']} clamped",
                    details={**d, "reason": "year_out_of_range"},
                )
        fixed += 1

    print(f"{'DRY RUN — ' if dry_run else ''}clamped {fixed} notices")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
