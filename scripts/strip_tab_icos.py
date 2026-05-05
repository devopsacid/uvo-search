"""One-shot: strip leading/trailing whitespace from ICO fields in suppliers and notices.

Finds documents where ico or awards[].supplier.ico contains leading/trailing
whitespace (tabs, spaces, \\r, \\n) and updates them in-place.

Usage:
  uv run python scripts/strip_tab_icos.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip()
MONGO_URI = MONGO_URI.replace("@mongo:", "@localhost:")
if "?" in MONGO_URI:
    _base, _params = MONGO_URI.split("?", 1)
    MONGO_URI = _base.rstrip("/") + "/_placeholder?" + _params
MONGO_DB = os.getenv("MONGODB_DATABASE", "uvo_search").strip()


async def fix_suppliers(db, dry_run: bool) -> int:
    """Strip whitespace from suppliers.ico where it differs from ico.strip()."""
    dirty = await db["suppliers"].find(
        {"ico": {"$regex": r"^[\s]|[\s]$"}},
        {"ico": 1, "name": 1},
    ).to_list(1000)
    if not dirty:
        print("  suppliers: no dirty ICOs found")
        return 0
    fixed = 0
    skipped = 0
    for doc in dirty:
        old = doc["ico"]
        new = old.strip()
        print(f"  suppliers: {doc.get('name', '?')!r:50s}  {old!r} -> {new!r}")
        if not dry_run:
            try:
                await db["suppliers"].update_one({"_id": doc["_id"]}, {"$set": {"ico": new}})
                fixed += 1
            except DuplicateKeyError:
                print(f"    SKIP (clean ICO {new!r} already exists — duplicate supplier)")
                skipped += 1
        else:
            fixed += 1
    if skipped:
        print(f"  suppliers: {skipped} skipped (would create duplicate ICO)")
    return fixed


async def fix_notices(db, dry_run: bool) -> int:
    """Strip whitespace from notices.awards[].supplier.ico using arrayFilters."""
    dirty_cursor = db["notices"].find(
        {"awards.supplier.ico": {"$regex": r"^[\s]|[\s]$"}},
        {"_id": 1, "awards": 1, "source": 1},
    )
    dirty = await dirty_cursor.to_list(10000)
    if not dirty:
        print("  notices: no dirty supplier ICOs found")
        return 0
    fixed = 0
    for doc in dirty:
        for i, award in enumerate(doc.get("awards") or []):
            old = (award.get("supplier") or {}).get("ico") or ""
            if old != old.strip():
                new = old.strip()
                print(f"  notices[{doc['source']}]: awards[{i}].supplier.ico {old!r} -> {new!r}")
                if not dry_run:
                    await db["notices"].update_one(
                        {"_id": doc["_id"]},
                        {"$set": {f"awards.{i}.supplier.ico": new}},
                    )
                fixed += 1
    return fixed


async def main(dry_run: bool) -> None:
    uri = MONGO_URI.replace("/_placeholder?", f"/{MONGO_DB}?") if "/_placeholder?" in MONGO_URI else MONGO_URI
    client = AsyncIOMotorClient(uri, directConnection=True)
    db = client[MONGO_DB]
    try:
        print(f"{'DRY RUN — ' if dry_run else ''}Scanning for dirty ICOs...")
        s = await fix_suppliers(db, dry_run)
        n = await fix_notices(db, dry_run)
        print(f"\nTotal: {s} supplier docs, {n} notice awards {'would be ' if dry_run else ''}fixed.")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
