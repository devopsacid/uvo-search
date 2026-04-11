"""Pipeline orchestrator — coordinates all ETL steps."""

import logging
import math
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Literal

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from neo4j import AsyncGraphDatabase

from uvo_pipeline.catalog.ckan import discover_vestnik_packages, extract_zip_urls
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.extractors.vestnik_xml import parse_xml_file
from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch
from uvo_pipeline.loaders.neo4j import ensure_constraints, merge_notice_batch
from uvo_pipeline.models import PipelineReport
from uvo_pipeline.transformers.vestnik import transform_notice as transform_vestnik_notice
from uvo_pipeline.utils.checkpoint import get_checkpoint, save_checkpoint
from uvo_pipeline.utils.zip_handler import download_zip, extract_xml_files

logger = logging.getLogger(__name__)


async def _run_cross_source_dedup(db: AsyncIOMotorDatabase, run_id: str) -> int:
    """
    Find notices from different sources that likely refer to the same real-world event.

    Pass 1: Match by (procurer.ico, cpv_code) across sources.
    Pass 2: For notices without ICO, match by (title_slug, publication_date ±7 days) across sources.

    For each group of matches:
    1. Assign a shared canonical_id (MongoDB _id of oldest notice as string)
    2. Update all notices with that canonical_id
    3. Write a record to cross_source_matches collection

    Returns total number of cross-source match groups found.
    """
    match_count = 0

    # --- Pass 1: procurer.ico + cpv_code ---
    pipeline_pass1 = [
        {"$match": {
            "procurer.ico": {"$ne": None, "$exists": True},
            "cpv_code": {"$ne": None, "$exists": True},
            "pipeline_run_id": run_id,
        }},
        {"$group": {
            "_id": {"procurer_ico": "$procurer.ico", "cpv_code": "$cpv_code"},
            "notices": {"$push": {"id": "$_id", "source": "$source", "pub_date": "$publication_date"}},
            "sources": {"$addToSet": "$source"},
        }},
        {"$match": {"sources.1": {"$exists": True}}},
    ]

    groups = await db.notices.aggregate(pipeline_pass1).to_list(length=None)

    for group in groups:
        notices_in_group = group["notices"]
        notices_in_group.sort(key=lambda x: x.get("pub_date") or "")
        canonical_id = str(notices_in_group[0]["id"])
        notice_ids = [str(n["id"]) for n in notices_in_group]

        await db.notices.update_many(
            {"_id": {"$in": [ObjectId(nid) for nid in notice_ids]}},
            {"$set": {"canonical_id": canonical_id}},
        )
        await db.cross_source_matches.update_one(
            {"canonical_id": canonical_id},
            {"$set": {
                "canonical_id": canonical_id,
                "notice_ids": notice_ids,
                "sources": group["sources"],
                "procurer_ico": group["_id"]["procurer_ico"],
                "cpv_code": group["_id"]["cpv_code"],
                "match_type": "ico_cpv",
            }},
            upsert=True,
        )
        match_count += 1

    # --- Pass 2: title_slug + publication_date ±7 days (for notices without ICO) ---
    # Fetch ICO-less notices from this run that have a title_slug and no canonical_id yet
    ico_less = await db.notices.find({
        "pipeline_run_id": run_id,
        "title_slug": {"$ne": None, "$exists": True},
        "canonical_id": None,
        "$or": [
            {"procurer.ico": None},
            {"procurer.ico": {"$exists": False}},
        ],
    }).to_list(length=None)

    # Group by title_slug
    from collections import defaultdict
    by_slug: dict[str, list] = defaultdict(list)
    for n in ico_less:
        slug = n.get("title_slug")
        if slug:
            by_slug[slug].append(n)

    for slug, slug_notices in by_slug.items():
        if len(slug_notices) < 2:
            continue

        # Find clusters within ±7 days of each other, across different sources
        slug_notices.sort(key=lambda x: x.get("publication_date") or "")

        processed: set[str] = set()
        for i, anchor in enumerate(slug_notices):
            if str(anchor["_id"]) in processed:
                continue

            anchor_date_str = anchor.get("publication_date")
            if not anchor_date_str:
                continue

            try:
                from datetime import date as date_type
                anchor_date = date_type.fromisoformat(str(anchor_date_str))
            except (ValueError, TypeError):
                continue

            cluster = [anchor]
            cluster_sources = {anchor["source"]}

            for other in slug_notices[i + 1:]:
                if str(other["_id"]) in processed:
                    continue
                if other["source"] == anchor["source"]:
                    continue
                other_date_str = other.get("publication_date")
                if not other_date_str:
                    continue
                try:
                    other_date = date_type.fromisoformat(str(other_date_str))
                except (ValueError, TypeError):
                    continue
                if abs((other_date - anchor_date).days) <= 7:
                    cluster.append(other)
                    cluster_sources.add(other["source"])

            if len(cluster_sources) < 2:
                continue  # Same source duplicates — not cross-source

            cluster.sort(key=lambda x: x.get("publication_date") or "")
            canonical_id = str(cluster[0]["_id"])
            notice_ids = [str(n["_id"]) for n in cluster]

            await db.notices.update_many(
                {"_id": {"$in": [ObjectId(nid) for nid in notice_ids]}},
                {"$set": {"canonical_id": canonical_id}},
            )
            await db.cross_source_matches.update_one(
                {"canonical_id": canonical_id},
                {"$set": {
                    "canonical_id": canonical_id,
                    "notice_ids": notice_ids,
                    "sources": list(cluster_sources),
                    "title_slug": slug,
                    "match_type": "title_slug_date",
                }},
                upsert=True,
            )
            for n in cluster:
                processed.add(str(n["_id"]))
            match_count += 1

    return match_count


async def run(
    mode: Literal["recent", "historical"],
    *,
    settings: PipelineSettings,
    dry_run: bool = False,
) -> PipelineReport:
    """Orchestrate the full ETL pipeline."""
    run_id = str(uuid.uuid4())
    started_at = datetime.utcnow()
    report = PipelineReport(run_id=run_id, mode=mode, started_at=started_at)

    from_date: date
    if mode == "recent":
        from_date = (datetime.utcnow() - timedelta(days=settings.recent_days)).date()
    else:
        from_date = date(settings.historical_from_year, 1, 1)

    logger.info("Pipeline run %s starting (mode=%s, from=%s, dry_run=%s)", run_id, mode, from_date, dry_run)

    if dry_run:
        logger.info("Dry run — skipping DB connections")
        report.finished_at = datetime.utcnow()
        return report

    # Connect to databases
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_database]
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    try:
        # Ensure indexes/constraints exist
        await ensure_indexes(db)
        async with neo4j_driver.session() as neo4j_session:
            await ensure_constraints(neo4j_session)

        # Load checkpoint — advance from_date if a more recent run is recorded
        checkpoint = await get_checkpoint(db, "pipeline")
        last_run = checkpoint.get("last_run_at")
        if last_run and mode == "recent":
            try:
                checkpoint_date = datetime.fromisoformat(str(last_run)).date()
                if checkpoint_date > from_date:
                    from_date = checkpoint_date
                    logger.info("Using checkpoint date: %s", from_date)
            except Exception:
                pass

        # Collect notices from all active sources
        all_notices = []

        # Step 6: Vestník XML extractor
        logger.info("Extracting from Vestník XML via CKAN catalog...")
        cache_dir = Path(settings.cache_dir)
        vestnik_count = 0
        async with httpx.AsyncClient(
            base_url=settings.ckan_base_url,
            timeout=settings.request_timeout,
        ) as ckan_client:
            async with httpx.AsyncClient(timeout=settings.request_timeout) as dl_client:
                async for package in discover_vestnik_packages(ckan_client, from_date=from_date):
                    for zip_url in await extract_zip_urls(package):
                        try:
                            zip_path = await download_zip(zip_url, dl_client, cache_dir)
                            extract_dir = cache_dir / zip_path.stem
                            xml_files = extract_xml_files(zip_path, extract_dir)
                            for xml_path in xml_files:
                                for raw in parse_xml_file(xml_path):
                                    try:
                                        notice = transform_vestnik_notice(raw)
                                        notice.pipeline_run_id = run_id
                                        all_notices.append(notice)
                                        vestnik_count += 1
                                    except Exception as exc:
                                        logger.warning("Vestník transform error: %s", exc)
                        except Exception as exc:
                            logger.error("Vestník ZIP error for %s: %s", zip_url, exc)
                            report.errors.append(f"Vestník ZIP {zip_url}: {exc}")

        report.source_counts["vestnik"] = vestnik_count
        logger.info("Vestník: %d notices extracted", vestnik_count)

        # Step 7: CRZ extractor
        from uvo_pipeline.extractors.crz import fetch_contracts_since
        from uvo_pipeline.transformers.crz import transform_contract
        from uvo_pipeline.utils.rate_limiter import RateLimiter

        logger.info("Extracting from CRZ (since=%s)...", from_date)
        crz_rate_limiter = RateLimiter(rate=settings.crz_rate_limit, per=60.0)
        crz_count = 0
        async with httpx.AsyncClient(
            base_url=settings.ekosystem_base_url,
            timeout=settings.request_timeout,
        ) as crz_client:
            async for raw in fetch_contracts_since(
                crz_client,
                crz_rate_limiter,
                since=from_date,
                api_token=settings.ekosystem_api_token,
            ):
                try:
                    notice = transform_contract(raw)
                    notice.pipeline_run_id = run_id
                    all_notices.append(notice)
                    crz_count += 1
                except Exception as exc:
                    logger.warning("CRZ transform error: %s", exc)

        report.source_counts["crz"] = crz_count
        logger.info("CRZ: %d contracts extracted", crz_count)

        # Step 8: TED extractor
        from uvo_pipeline.extractors.ted import search_sk_notices
        from uvo_pipeline.transformers.ted import transform_ted_notice

        logger.info("Extracting from TED EU (from=%s)...", from_date)
        ted_count = 0
        async with httpx.AsyncClient(
            base_url=settings.ted_base_url,
            timeout=settings.request_timeout,
        ) as ted_client:
            async for raw in search_sk_notices(ted_client, date_from=from_date):
                try:
                    notice = transform_ted_notice(raw)
                    notice.pipeline_run_id = run_id
                    all_notices.append(notice)
                    ted_count += 1
                except Exception as exc:
                    logger.warning("TED transform error: %s", exc)

        report.source_counts["ted"] = ted_count
        logger.info("TED: %d notices extracted", ted_count)

        # Step 9: UVO.gov.sk extractor
        from uvo_pipeline.extractors.uvo import fetch_notices as fetch_uvo_notices
        from uvo_pipeline.transformers.uvo import transform_notice as transform_uvo_notice

        logger.info("Extracting from UVO.gov.sk (from=%s)...", from_date)
        uvo_rate_limiter = RateLimiter(rate=max(1, math.ceil(settings.uvo_rate_limit)), per=1.0)
        uvo_count = 0
        uvo_to_date = datetime.utcnow().date()

        async with httpx.AsyncClient(
            base_url=settings.uvo_base_url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"},
            timeout=settings.request_timeout,
        ) as uvo_client:
            if mode == "historical":
                # Year-by-year to avoid huge in-memory batches
                from_year = settings.historical_from_year
                current_year = uvo_to_date.year
                for year in range(from_year, current_year + 1):
                    year_from = date(year, 1, 1)
                    year_to = date(year, 12, 31)
                    async for raw in fetch_uvo_notices(
                        uvo_client,
                        uvo_rate_limiter,
                        from_date=year_from,
                        to_date=year_to,
                        fetch_details=settings.uvo_fetch_details,
                        request_delay=settings.uvo_request_delay,
                    ):
                        try:
                            notice = transform_uvo_notice(raw)
                            notice.pipeline_run_id = run_id
                            all_notices.append(notice)
                            uvo_count += 1
                        except Exception as exc:
                            logger.warning("UVO transform error: %s", exc)
            else:
                async for raw in fetch_uvo_notices(
                    uvo_client,
                    uvo_rate_limiter,
                    from_date=from_date,
                    to_date=uvo_to_date,
                    fetch_details=settings.uvo_fetch_details,
                    request_delay=settings.uvo_request_delay,
                ):
                    try:
                        notice = transform_uvo_notice(raw)
                        notice.pipeline_run_id = run_id
                        all_notices.append(notice)
                        uvo_count += 1
                    except Exception as exc:
                        logger.warning("UVO transform error: %s", exc)

        report.source_counts["uvo"] = uvo_count
        logger.info("UVO: %d notices extracted", uvo_count)

        if all_notices:
            # Compute content hashes before writing
            from uvo_pipeline.utils.hashing import compute_notice_hash
            for notice in all_notices:
                notice.content_hash = compute_notice_hash(notice)

            # Write to MongoDB
            mongo_result = await upsert_batch(db, all_notices, batch_size=settings.batch_size)
            report.notices_inserted = mongo_result["inserted"]
            report.notices_updated = mongo_result["updated"]
            report.notices_skipped = mongo_result["skipped"]
            if mongo_result["errors"]:
                report.errors.append(f"MongoDB: {mongo_result['errors']} upsert errors")

            # Write to Neo4j
            async with neo4j_driver.session() as neo4j_session:
                neo4j_result = await merge_notice_batch(neo4j_session, all_notices)
                if neo4j_result["errors"]:
                    report.errors.append(f"Neo4j: {neo4j_result['errors']} merge errors")

            # Save checkpoint
            await save_checkpoint(db, "pipeline", {
                "last_mode": mode,
                "from_date": from_date.isoformat(),
                "notices_processed": len(all_notices),
            })

            # Cross-source deduplication
            logger.info("Running cross-source deduplication...")
            match_groups = await _run_cross_source_dedup(db, run_id)
            logger.info("Cross-source dedup found %d match groups", match_groups)
            report.source_counts["cross_source_matches"] = match_groups

        logger.info(
            "Pipeline run %s complete: %d inserted, %d updated, %d skipped",
            run_id, report.notices_inserted, report.notices_updated, report.notices_skipped,
        )

    except Exception as exc:
        logger.exception("Pipeline run %s failed", run_id)
        report.errors.append(str(exc))
    finally:
        mongo_client.close()
        await neo4j_driver.close()

    report.finished_at = datetime.utcnow()
    return report
