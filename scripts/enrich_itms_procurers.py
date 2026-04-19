"""One-shot: backfill procurer name/ICO + title/date/CPV on ITMS notices that
were ingested with the old (reference-only) shape.

Walks all notices where source=='itms' and procurer.name is empty, fetches
the singular procurement detail + resolved subject from the ITMS API,
rebuilds the notice via the transformer, and writes it back to Mongo + Neo4j.

Subject lookups are cached across the run. Rate-limited via RateLimiter.
Safe to re-run — idempotent (content_hash recomputed each pass).

Usage:
  python -m scripts.enrich_itms_procurers [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase

from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.itms import _fetch_subject
from uvo_pipeline.loaders.mongo import upsert_batch
from uvo_pipeline.loaders.neo4j import merge_notice_batch
from uvo_pipeline.transformers.itms import transform_procurement
from uvo_pipeline.utils.hashing import compute_notice_hash
from uvo_pipeline.utils.rate_limiter import RateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("enrich_itms")


async def _fetch_detail(client: httpx.AsyncClient, rate_limiter: RateLimiter, pid: int) -> dict | None:
    await rate_limiter.acquire()
    try:
        resp = await client.get(f"/v2/verejneObstaravania/{pid}")
    except httpx.RequestError as exc:
        logger.warning("ITMS detail %s fetch failed: %s", pid, exc)
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


async def _fetch_contracts(client: httpx.AsyncClient, rate_limiter: RateLimiter, pid: int) -> list:
    await rate_limiter.acquire()
    try:
        resp = await client.get(f"/v2/verejneObstaravania/{pid}/zmluvyVerejneObstaravanie")
    except httpx.RequestError:
        return []
    return resp.json() if resp.status_code == 200 else []


async def _process_one(
    source_id: str,
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    subject_cache: dict,
) -> dict[str, Any] | None:
    pid = int(source_id)
    raw = await _fetch_detail(client, rate_limiter, pid)
    if raw is None:
        return None
    raw["_contracts"] = await _fetch_contracts(client, rate_limiter, pid)
    subj_ref = (raw.get("obstaravatelSubjekt") or {}).get("subjekt") or {}
    sid = subj_ref.get("id")
    if sid is not None:
        subject = await _fetch_subject(client, rate_limiter, int(sid), subject_cache)
        if subject:
            raw["_subject"] = subject

    notice = transform_procurement(raw)
    notice.content_hash = compute_notice_hash(notice)
    return notice


async def main(limit: int | None, dry_run: bool) -> int:
    settings = PipelineSettings()

    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_database]
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    # Find target source_ids
    cursor = db.notices.find(
        {"source": "itms", "procurer.name": ""},
        {"source_id": 1, "_id": 0},
    )
    if limit:
        cursor = cursor.limit(limit)
    source_ids = [doc["source_id"] async for doc in cursor]
    logger.info("Found %d ITMS notices needing enrichment", len(source_ids))

    if not source_ids:
        await mongo_client.close()
        await neo4j_driver.close()
        return 0

    rate_limiter = RateLimiter(rate=int(settings.itms_rate_limit), per=1.0)
    subject_cache: dict[int, dict] = {}

    batch: list = []
    batch_size = 500
    processed = 0
    updated = 0
    failed = 0

    async with httpx.AsyncClient(
        base_url=settings.itms_base_url,
        timeout=settings.request_timeout,
    ) as client:
        for sid in source_ids:
            try:
                notice = await _process_one(sid, client, rate_limiter, subject_cache)
            except Exception as exc:
                logger.warning("enrich %s failed: %s", sid, exc)
                failed += 1
                processed += 1
                continue
            if notice is None:
                failed += 1
            else:
                batch.append(notice)
            processed += 1

            if len(batch) >= batch_size:
                if not dry_run:
                    result = await upsert_batch(db, batch, batch_size=batch_size)
                    updated += result["updated"] + result["inserted"]
                    async with neo4j_driver.session() as s:
                        await merge_notice_batch(s, batch)
                logger.info(
                    "progress: %d/%d processed, %d upserted, %d failed, %d subjects cached",
                    processed, len(source_ids), updated, failed, len(subject_cache),
                )
                batch.clear()

        if batch and not dry_run:
            result = await upsert_batch(db, batch, batch_size=batch_size)
            updated += result["updated"] + result["inserted"]
            async with neo4j_driver.session() as s:
                await merge_notice_batch(s, batch)

    logger.info(
        "Done: %d processed, %d upserted (dry_run=%s), %d failed, %d unique subjects",
        processed, updated, dry_run, failed, len(subject_cache),
    )

    mongo_client.close()
    await neo4j_driver.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="Cap number of notices to process")
    p.add_argument("--dry-run", action="store_true", help="Fetch + transform but skip writes")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.limit, args.dry_run)))
