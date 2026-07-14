"""Validate cross-source dedup pass 3 (supplier ICO + value window) against live data.

Builds the pass-3 match groups read-only, prints a summary + a sample of
matched pairs for eyeball plausibility, and — unless --dry-run is given —
persists the groups (canonical_id + cross_source_matches) exactly like
run_cross_source_dedup's pass 3 would.

Usage:
  uv run python scripts/preview_pass3_dedup.py --dry-run [--sample N]
  uv run python scripts/preview_pass3_dedup.py            # writes for real
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.dedup import (
    MAX_NOTICES_PER_SUPPLIER_ICO,
    build_ico_value_window_groups,
    persist_match_groups,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("preview_pass3_dedup")


async def _print_sample(db, groups: list[dict], sample_size: int) -> None:
    for group in groups[:sample_size]:
        docs = await db.notices.find(
            {"_id": {"$in": [ObjectId(nid) for nid in group["notice_ids"]]}},
            {"source": 1, "title": 1, "publication_date": 1, "awards": 1},
        ).to_list(length=None)
        print(f"\n--- supplier_ico={group['supplier_ico']} canonical_id={group['canonical_id']} ---")
        for d in docs:
            values = [a.get("value") for a in d.get("awards", []) if a.get("value") is not None]
            print(
                f"  [{d['source']:8s}] {d.get('publication_date')}  "
                f"value={values}  title={d.get('title', '')[:80]!r}"
            )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="preview only, do not write")
    parser.add_argument("--sample", type=int, default=10, help="number of matched groups to print")
    args = parser.parse_args()

    settings = PipelineSettings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]

    groups, skipped_high_freq = await build_ico_value_window_groups(db, base_filter={})

    total_notices = sum(len(g["notice_ids"]) for g in groups)
    print(f"candidate match groups: {len(groups)}")
    print(f"notices that would receive canonical_id: {total_notices}")
    print(
        f"supplier ICOs skipped as high-frequency "
        f"(>{MAX_NOTICES_PER_SUPPLIER_ICO} candidate notices): {skipped_high_freq}"
    )

    await _print_sample(db, groups, args.sample)

    if args.dry_run:
        print("\n--dry-run: no writes performed.")
        return

    written = await persist_match_groups(db, groups)
    print(f"\nwrote canonical_id for {total_notices} notices across {written} match groups.")


if __name__ == "__main__":
    asyncio.run(main())
