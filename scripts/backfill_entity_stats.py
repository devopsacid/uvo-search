"""Backfill denormalized contract_count / total_value onto procurers & suppliers.

Entity search (adapters/mongo/subjects.py) used to compute contract_count /
total_value with a per-row $lookup that scanned `notices` for every result row
(plan §1.3.3). Those two fields are now denormalized onto the procurer/supplier
documents; this script populates them for the existing corpus, and the same
`recompute_entity_stats` routine keeps them fresh going forward.

Design decision — recompute, do NOT increment inline
-----------------------------------------------------
The obvious alternative — $inc the counters inside the loader's per-notice
upsert — is NOT idempotent under this pipeline:

  * The loader skips unchanged notices via the content-hash registry
    (loaders.mongo.upsert_batch), so a re-ingested notice must not be counted
    again — but an inline $inc on the entity upsert (which runs for every notice
    in the batch, skipped or not) would double-count on every re-run.
  * On a *changed* notice the final_value may differ from last time, so an
    increment can't know the delta without reading the previous value.

Recompute derives the counts from the current corpus in one aggregation, so it
is correct regardless of how many times a notice was ingested. It is O(notices),
but so is the cross-source dedup that already runs periodically; the dedup worker
calls `recompute_entity_stats` at the end of its debounced cycle
(uvo_workers/dedup.py) so the fields stay fresh without a separate cron. This
script is the manual/backfill entry point (and a safe way to force a refresh).

Semantics match the old $lookup exactly: counts are at the *notice* level (a
notice with several awards to the same supplier counts once) and total_value
sums `final_value` once per notice. Only ICO-bearing entities are maintained.

Safe to re-run — idempotent.

Usage:
  python -m scripts.backfill_entity_stats [--batch-size N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from uvo_pipeline.config import get_pipeline_settings
from uvo_pipeline.loaders.mongo import recompute_entity_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("backfill_entity_stats")


async def main(batch_size: int, dry_run: bool) -> int:
    settings = get_pipeline_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]
    try:
        stats = await recompute_entity_stats(db, batch_size=batch_size, dry_run=dry_run)
    finally:
        client.close()

    logger.info(
        "Done (dry_run=%s): procurers matched=%d updated=%d | suppliers matched=%d updated=%d",
        dry_run,
        stats.get("procurers_matched", 0),
        stats.get("procurers_updated", 0),
        stats.get("suppliers_matched", 0),
        stats.get("suppliers_updated", 0),
    )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch-size", type=int, default=1000, help="Bulk-write batch size")
    p.add_argument("--dry-run", action="store_true", help="Count only, no writes")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.batch_size, args.dry_run)))
