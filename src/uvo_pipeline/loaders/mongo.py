"""MongoDB loader — upsert canonical notices, procurers, and suppliers."""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalSupplier

logger = logging.getLogger(__name__)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all required indexes and unique constraints."""
    # notices: unique on (source, source_id)
    await db.notices.create_index(
        [("source", 1), ("source_id", 1)], unique=True, name="source_source_id_unique"
    )
    await db.notices.create_index([("publication_date", -1)], name="publication_date_desc")
    await db.notices.create_index([("procurer.ico", 1)], name="procurer_ico")
    await db.notices.create_index([("cpv_code", 1)], name="cpv_code")
    await db.notices.create_index([("awards.supplier.ico", 1)], name="supplier_ico")
    await db.notices.create_index([("canonical_id", 1)], name="canonical_id", sparse=True)
    await db.notices.create_index(
        [("title", "text"), ("description", "text")],
        name="text_search",
        default_language="none",
    )

    # procurers: unique on ico (sparse) and name_slug
    await db.procurers.create_index(
        [("ico", 1)], unique=True, sparse=True, name="ico_unique"
    )
    await db.procurers.create_index(
        [("name_slug", 1)], unique=True, name="name_slug_unique"
    )
    await db.procurers.create_index([("name", "text")], name="text_search")

    # suppliers: same as procurers
    await db.suppliers.create_index(
        [("ico", 1)], unique=True, sparse=True, name="ico_unique"
    )
    await db.suppliers.create_index(
        [("name_slug", 1)], unique=True, name="name_slug_unique"
    )
    await db.suppliers.create_index([("name", "text")], name="text_search")

    # pipeline_state: unique on source
    await db.pipeline_state.create_index(
        [("source", 1)], unique=True, name="source_unique"
    )

    # ckan_packages: unique on package_id
    await db.ckan_packages.create_index(
        [("package_id", 1)], unique=True, name="package_id_unique"
    )
    await db.ckan_packages.create_index([("last_modified", -1)], name="last_modified_desc")

    logger.info("MongoDB indexes ensured")


async def upsert_notice(db: AsyncIOMotorDatabase, notice: CanonicalNotice) -> str:
    """Upsert a single notice. Returns the MongoDB _id as string."""
    doc = notice.model_dump(mode="json")
    result = await db.notices.find_one_and_update(
        {"source": notice.source, "source_id": notice.source_id},
        {
            "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
            "$setOnInsert": {"ingested_at": doc["ingested_at"]},
        },
        upsert=True,
        return_document=True,
    )
    return str(result["_id"])


async def upsert_procurer(db: AsyncIOMotorDatabase, procurer: CanonicalProcurer) -> str:
    """Upsert a procurer by ico (preferred) or name_slug fallback."""
    doc = procurer.model_dump(mode="json")
    if procurer.ico:
        filter_: dict[str, Any] = {"ico": procurer.ico}
    else:
        filter_ = {"name_slug": procurer.name_slug}
    result = await db.procurers.find_one_and_update(
        filter_,
        {"$set": doc, "$addToSet": {"sources": {"$each": procurer.sources}}},
        upsert=True,
        return_document=True,
    )
    return str(result["_id"])


async def upsert_supplier(db: AsyncIOMotorDatabase, supplier: CanonicalSupplier) -> str:
    """Upsert a supplier by ico (preferred) or name_slug fallback."""
    doc = supplier.model_dump(mode="json")
    if supplier.ico:
        filter_: dict[str, Any] = {"ico": supplier.ico}
    else:
        filter_ = {"name_slug": supplier.name_slug}
    result = await db.suppliers.find_one_and_update(
        filter_,
        {"$set": doc, "$addToSet": {"sources": {"$each": supplier.sources}}},
        upsert=True,
        return_document=True,
    )
    return str(result["_id"])


async def upsert_batch(
    db: AsyncIOMotorDatabase,
    notices: list[CanonicalNotice],
    *,
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk upsert a list of notices. Returns {inserted, updated, errors}."""
    inserted = updated = errors = 0
    for i in range(0, len(notices), batch_size):
        batch = notices[i : i + batch_size]
        for notice in batch:
            try:
                doc = notice.model_dump(mode="json")
                result = await db.notices.update_one(
                    {"source": notice.source, "source_id": notice.source_id},
                    {
                        "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                        "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                    },
                    upsert=True,
                )
                if result.upserted_id:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                logger.error("Failed to upsert notice %s/%s: %s", notice.source, notice.source_id, exc)
                errors += 1

        # Also upsert entities from this batch
        for notice in batch:
            if notice.procurer:
                try:
                    await upsert_procurer(db, notice.procurer)
                except Exception as exc:
                    logger.warning("Failed to upsert procurer: %s", exc)
            for award in notice.awards:
                try:
                    await upsert_supplier(db, award.supplier)
                except Exception as exc:
                    logger.warning("Failed to upsert supplier: %s", exc)

    logger.info("Batch upsert: %d inserted, %d updated, %d errors", inserted, updated, errors)
    return {"inserted": inserted, "updated": updated, "errors": errors}
