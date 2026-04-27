"""Pipeline orchestrator — coordinates all ETL steps."""

import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from neo4j import AsyncGraphDatabase

from uvo_pipeline.catalog.nkod import discover_vestnik_datasets
from uvo_pipeline.config import PipelineSettings
from uvo_pipeline.dedup import run_cross_source_dedup
from uvo_pipeline.extractors.vestnik_nkod import fetch_bulletin
from uvo_pipeline.loaders.mongo import ensure_indexes, upsert_batch
from uvo_pipeline.loaders.neo4j import ensure_constraints, merge_notice_batch
from uvo_pipeline.models import CanonicalNotice, PipelineReport
from uvo_pipeline.transformers.vestnik_nkod import transform_notice as transform_vestnik_notice
from uvo_pipeline.utils.checkpoint import get_checkpoint, save_checkpoint
from uvo_pipeline.utils.hashing import compute_notice_hash

logger = logging.getLogger(__name__)


async def _run_cross_source_dedup(db, run_id: str) -> int:
    return await run_cross_source_dedup(db, run_id=run_id)


async def _persist_source(
    db: AsyncIOMotorDatabase,
    neo4j_driver: "AsyncGraphDatabase",  # type: ignore[name-defined]
    source_name: str,
    notices: list[CanonicalNotice],
    *,
    settings: PipelineSettings,
    report: PipelineReport,
) -> None:
    """Compute hashes, write notices to Mongo + Neo4j, accumulate report counters.

    Called once per source so that a long run (or a crash mid-run) doesn't lose
    the work of already-extracted sources. Mongo upsert is idempotent on
    (source, source_id), so a re-run of a partially-completed source is safe.
    """
    if not notices:
        logger.info("%s: nothing to persist", source_name)
        return

    for notice in notices:
        notice.content_hash = compute_notice_hash(notice)

    mongo_result = await upsert_batch(db, notices, batch_size=settings.batch_size)
    report.notices_inserted += mongo_result["inserted"]
    report.notices_updated += mongo_result["updated"]
    report.notices_skipped += mongo_result["skipped"]
    if mongo_result["errors"]:
        report.errors.append(
            f"MongoDB ({source_name}): {mongo_result['errors']} upsert errors"
        )

    async with neo4j_driver.session() as neo4j_session:
        neo4j_result = await merge_notice_batch(neo4j_session, notices)
        if neo4j_result["errors"]:
            report.errors.append(
                f"Neo4j ({source_name}): {neo4j_result['errors']} merge errors"
            )

    logger.info(
        "%s: persisted %d notices (inserted=%d updated=%d skipped=%d)",
        source_name,
        len(notices),
        mongo_result["inserted"],
        mongo_result["updated"],
        mongo_result["skipped"],
    )


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

        from uvo_pipeline.utils.rate_limiter import RateLimiter

        total_persisted = 0

        # Step 6: Vestník NKOD extractor (SPARQL discovery + bulletin download)
        vestnik_checkpoint = checkpoint.get("vestnik_last_modified")
        vestnik_since: date | None
        if mode == "historical":
            vestnik_since = None
        elif vestnik_checkpoint:
            try:
                vestnik_since = datetime.fromisoformat(str(vestnik_checkpoint)).date()
            except (ValueError, TypeError):
                vestnik_since = from_date
        else:
            vestnik_since = from_date

        logger.info("Extracting from Vestník NKOD (since=%s)...", vestnik_since)
        cache_dir = Path(settings.cache_dir)
        vestnik_rate_limiter = RateLimiter(rate=max(1, int(settings.vestnik_rate_limit)), per=1.0)
        vestnik_notices: list[CanonicalNotice] = []
        vestnik_max_modified: datetime | None = None
        async with httpx.AsyncClient(timeout=settings.request_timeout) as sparql_client:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout,
                follow_redirects=True,
            ) as dl_client:
                async for ds in discover_vestnik_datasets(
                    sparql_client,
                    publisher_uri=settings.uvo_publisher_uri,
                    sparql_url=settings.nkod_sparql_url,
                    since=vestnik_since,
                ):
                    if ds.modified and (vestnik_max_modified is None or ds.modified > vestnik_max_modified):
                        vestnik_max_modified = ds.modified
                    async for raw in fetch_bulletin(
                        dl_client,
                        vestnik_rate_limiter,
                        ds,
                        cache_dir=cache_dir,
                    ):
                        try:
                            notice = transform_vestnik_notice(raw)
                            notice.pipeline_run_id = run_id
                            vestnik_notices.append(notice)
                        except Exception as exc:
                            logger.warning(
                                "Vestník transform error (item id=%s): %s",
                                raw.get("id"),
                                str(exc).splitlines()[0],
                            )

        report.source_counts["vestnik"] = len(vestnik_notices)
        logger.info("Vestník: %d notices extracted", len(vestnik_notices))
        await _persist_source(
            db, neo4j_driver, "vestnik", vestnik_notices,
            settings=settings, report=report,
        )
        total_persisted += len(vestnik_notices)
        if vestnik_max_modified is not None:
            await save_checkpoint(
                db, "pipeline",
                {"vestnik_last_modified": vestnik_max_modified.isoformat()},
            )

        # Step 7: CRZ extractor — stream-flushed: every batch_size notices land
        # in Mongo/Neo4j during extraction so the dashboard sees progress and
        # an interruption mid-CRZ doesn't lose hours of accumulated work.
        from uvo_pipeline.extractors.crz import fetch_contracts_since
        from uvo_pipeline.transformers.crz import transform_contract

        logger.info("Extracting from CRZ (since=%s)...", from_date)
        crz_rate_limiter = RateLimiter(rate=settings.crz_rate_limit, per=60.0)
        crz_buffer: list[CanonicalNotice] = []
        crz_total = 0
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
                    crz_buffer.append(notice)
                    crz_total += 1
                except Exception as exc:
                    logger.warning("CRZ transform error: %s", exc)
                if len(crz_buffer) >= settings.batch_size:
                    await _persist_source(
                        db, neo4j_driver, "crz", crz_buffer,
                        settings=settings, report=report,
                    )
                    crz_buffer.clear()

        if crz_buffer:
            await _persist_source(
                db, neo4j_driver, "crz", crz_buffer,
                settings=settings, report=report,
            )
            crz_buffer.clear()

        report.source_counts["crz"] = crz_total
        logger.info("CRZ: %d contracts extracted (streamed)", crz_total)
        total_persisted += crz_total

        # Step 8: TED extractor
        from uvo_pipeline.extractors.ted import search_sk_notices
        from uvo_pipeline.transformers.ted import transform_ted_notice

        logger.info("Extracting from TED EU (from=%s)...", from_date)
        ted_notices: list[CanonicalNotice] = []
        async with httpx.AsyncClient(
            base_url=settings.ted_base_url,
            timeout=settings.request_timeout,
        ) as ted_client:
            async for raw in search_sk_notices(ted_client, date_from=from_date):
                try:
                    notice = transform_ted_notice(raw)
                    notice.pipeline_run_id = run_id
                    ted_notices.append(notice)
                except Exception as exc:
                    logger.warning("TED transform error: %s", exc)

        report.source_counts["ted"] = len(ted_notices)
        logger.info("TED: %d notices extracted", len(ted_notices))
        await _persist_source(
            db, neo4j_driver, "ted", ted_notices,
            settings=settings, report=report,
        )
        total_persisted += len(ted_notices)

        # UVO.gov.sk has no public API — its listing endpoint moved behind
        # Oracle Access Manager SSO. UVO notices enter the pipeline via the
        # Vestník NKOD extractor instead (Vestník is UVO's official gazette
        # and the NKOD SPARQL feed is filtered on the UVO publisher URI).

        # Step N: ITMS2014+
        from uvo_pipeline.extractors.itms import fetch_procurements as fetch_itms_procurements
        from uvo_pipeline.transformers.itms import transform_procurement as transform_itms

        itms_min_id = int(checkpoint.get("itms_min_id") or 0)
        itms_max_items = settings.itms_max_items_per_run
        logger.info(
            "Extracting from ITMS2014+ (min_id=%d, max_items_per_run=%s)...",
            itms_min_id,
            itms_max_items if itms_max_items > 0 else "unbounded",
        )
        itms_rate_limiter = RateLimiter(rate=int(settings.itms_rate_limit), per=1.0)
        itms_buffer: list[CanonicalNotice] = []
        itms_total = 0
        itms_max_seen = itms_min_id - 1  # track highest id yielded for checkpoint
        # ITMS is the slowest source (~3 req/item with detail+contracts+subject
        # lookups) so stream-flush every batch_size items AND advance the
        # min_id checkpoint after each flush — that way an interruption only
        # loses the partial buffer, not the whole run.
        async with httpx.AsyncClient(
            base_url=settings.itms_base_url,
            timeout=settings.request_timeout,
        ) as itms_client:
            async for raw in fetch_itms_procurements(
                itms_client,
                itms_rate_limiter,
                min_id=itms_min_id,
                max_items=itms_max_items if itms_max_items > 0 else None,
            ):
                try:
                    notice = transform_itms(raw)
                    notice.pipeline_run_id = run_id
                    itms_buffer.append(notice)
                    itms_total += 1
                    itms_max_seen = max(itms_max_seen, int(raw["id"]))
                except Exception as exc:
                    logger.warning("ITMS transform error: %s", exc)
                if len(itms_buffer) >= settings.batch_size:
                    await _persist_source(
                        db, neo4j_driver, "itms", itms_buffer,
                        settings=settings, report=report,
                    )
                    itms_buffer.clear()
                    await save_checkpoint(
                        db, "pipeline", {"itms_min_id": str(itms_max_seen + 1)},
                    )

        if itms_buffer:
            await _persist_source(
                db, neo4j_driver, "itms", itms_buffer,
                settings=settings, report=report,
            )
            itms_buffer.clear()
            await save_checkpoint(
                db, "pipeline", {"itms_min_id": str(itms_max_seen + 1)},
            )

        report.source_counts["itms"] = itms_total
        logger.info("ITMS: %d procurements extracted (streamed)", itms_total)
        total_persisted += itms_total

        # Final pipeline-wide checkpoint summary. `last_run_at` is stamped
        # ONLY here so a partially-completed prior run can't advance the
        # next run's `from_date` past data that was never actually fetched.
        await save_checkpoint(
            db, "pipeline",
            {
                "last_mode": mode,
                "from_date": from_date.isoformat(),
                "notices_processed": total_persisted,
                "last_run_at": datetime.utcnow(),
            },
        )

        # Cross-source deduplication runs once over everything written by this run
        if total_persisted:
            logger.info("Running cross-source deduplication...")
            match_groups = await run_cross_source_dedup(db, run_id=run_id, window_days=30)
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
