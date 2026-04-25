"""MongoDB loader — upsert canonical notices, procurers, and suppliers."""

import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalSupplier
from uvo_pipeline.utils.hashing import compute_notice_hash

logger = logging.getLogger(__name__)


async def _ensure_index(collection: AsyncIOMotorCollection, keys: Any, **kwargs: Any) -> None:
    """create_index, but if a same-named index exists with a different spec, drop and recreate."""
    name = kwargs.get("name")
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        if exc.code == 86 and name:  # IndexKeySpecsConflict
            logger.warning(
                "Index %s.%s spec changed; dropping and recreating", collection.name, name
            )
            await collection.drop_index(name)
            await collection.create_index(keys, **kwargs)
        else:
            raise


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all required indexes and unique constraints."""
    # notices: unique on (source, source_id)
    await _ensure_index(
        db.notices,
        [("source", 1), ("source_id", 1)], unique=True, name="source_source_id_unique"
    )
    await _ensure_index(db.notices, [("publication_date", -1)], name="publication_date_desc")
    await _ensure_index(db.notices, [("procurer.ico", 1)], name="procurer_ico")
    await _ensure_index(db.notices, [("cpv_code", 1)], name="cpv_code")
    await _ensure_index(db.notices, [("awards.supplier.ico", 1)], name="supplier_ico")
    await _ensure_index(db.notices, [("canonical_id", 1)], name="canonical_id", sparse=True)
    await _ensure_index(
        db.notices,
        [("title", "text"), ("description", "text")],
        name="text_search",
        default_language="none",
    )

    # procurers: unique on ico (string-typed only) and name_slug
    await _ensure_index(
        db.procurers,
        [("ico", 1)],
        unique=True,
        partialFilterExpression={"ico": {"$type": "string"}},
        name="ico_unique",
    )
    # name_slug is non-unique: historical data has dupes from a prior pipeline
    # version that did not enforce uniqueness; ICO is the real identity.
    await _ensure_index(
        db.procurers, [("name_slug", 1)], name="name_slug_unique"
    )
    await _ensure_index(db.procurers, [("name", "text")], name="text_search")

    # suppliers: same as procurers
    await _ensure_index(
        db.suppliers,
        [("ico", 1)],
        unique=True,
        partialFilterExpression={"ico": {"$type": "string"}},
        name="ico_unique",
    )
    await _ensure_index(
        db.suppliers, [("name_slug", 1)], name="name_slug_unique"
    )
    await _ensure_index(db.suppliers, [("name", "text")], name="text_search")

    # pipeline_state: unique on source
    await _ensure_index(
        db.pipeline_state, [("source", 1)], unique=True, name="source_unique"
    )

    # ckan_packages: unique on package_id
    await _ensure_index(
        db.ckan_packages, [("package_id", 1)], unique=True, name="package_id_unique"
    )
    await _ensure_index(db.ckan_packages, [("last_modified", -1)], name="last_modified_desc")

    # ingested_docs: fast lookup + audit trail
    await _ensure_index(
        db.ingested_docs,
        [("source", 1), ("source_id", 1)], unique=True, name="source_source_id_unique"
    )
    await _ensure_index(db.ingested_docs, [("pipeline_run_id", 1)], name="pipeline_run_id")
    await _ensure_index(
        db.ingested_docs,
        [("source", 1), ("ingested_at", -1)], name="source_ingested_at_desc"
    )
    await _ensure_index(db.ingested_docs, [("ingested_at", -1)], name="ingested_at_desc")

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
    sources = doc.pop("sources", []) or []
    if procurer.ico:
        filter_: dict[str, Any] = {"ico": procurer.ico}
    else:
        filter_ = {"name_slug": procurer.name_slug}
    result = await db.procurers.find_one_and_update(
        filter_,
        {"$set": doc, "$addToSet": {"sources": {"$each": sources}}},
        upsert=True,
        return_document=True,
    )
    return str(result["_id"])


async def upsert_supplier(db: AsyncIOMotorDatabase, supplier: CanonicalSupplier) -> str:
    """Upsert a supplier by ico (preferred) or name_slug fallback."""
    doc = supplier.model_dump(mode="json")
    sources = doc.pop("sources", []) or []
    if supplier.ico:
        filter_: dict[str, Any] = {"ico": supplier.ico}
    else:
        filter_ = {"name_slug": supplier.name_slug}
    result = await db.suppliers.find_one_and_update(
        filter_,
        {"$set": doc, "$addToSet": {"sources": {"$each": sources}}},
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
    """Bulk upsert notices with pre-ingestion skip via ingested_docs registry.

    Returns {inserted, updated, skipped, errors}.
    """
    inserted = updated = skipped = errors = 0

    for i in range(0, len(notices), batch_size):
        batch = notices[i : i + batch_size]

        # Compute hashes for all notices in this batch
        for notice in batch:
            if notice.content_hash is None:
                notice.content_hash = compute_notice_hash(notice)

        # Bulk-fetch existing registry entries for this batch
        keys = [{"source": n.source, "source_id": n.source_id} for n in batch]
        existing_docs = await db.ingested_docs.find({"$or": keys}).to_list(length=None)
        registry = {
            (doc["source"], doc["source_id"]): doc
            for doc in existing_docs
        }

        now = datetime.now(timezone.utc).isoformat()

        for notice in batch:
            key = (notice.source, notice.source_id)
            reg_entry = registry.get(key)

            try:
                if reg_entry is None:
                    # New notice — upsert into notices, insert registry entry
                    doc = notice.model_dump(mode="json")
                    result = await db.notices.update_one(
                        {"source": notice.source, "source_id": notice.source_id},
                        {
                            "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                            "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                        },
                        upsert=True,
                    )
                    await db.ingested_docs.insert_one({
                        "source": notice.source,
                        "source_id": notice.source_id,
                        "content_hash": notice.content_hash,
                        "ingested_at": now,
                        "last_seen_at": now,
                        "pipeline_run_id": notice.pipeline_run_id,
                        "skipped_count": 0,
                    })
                    if result.upserted_id is not None:
                        inserted += 1
                    else:
                        updated += 1

                elif reg_entry["content_hash"] == notice.content_hash:
                    # Unchanged — skip upsert, update registry metadata
                    await db.ingested_docs.update_one(
                        {"source": notice.source, "source_id": notice.source_id},
                        {
                            "$set": {"last_seen_at": now},
                            "$inc": {"skipped_count": 1},
                        },
                    )
                    skipped += 1

                else:
                    # Changed — upsert notice, update registry hash
                    doc = notice.model_dump(mode="json")
                    await db.notices.update_one(
                        {"source": notice.source, "source_id": notice.source_id},
                        {
                            "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                            "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                        },
                        upsert=True,
                    )
                    await db.ingested_docs.update_one(
                        {"source": notice.source, "source_id": notice.source_id},
                        {"$set": {
                            "content_hash": notice.content_hash,
                            "last_seen_at": now,
                            "pipeline_run_id": notice.pipeline_run_id,
                        }},
                    )
                    updated += 1

            except Exception as exc:
                logger.error(
                    "Failed to upsert notice %s/%s: %s", notice.source, notice.source_id, exc
                )
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

    logger.info(
        "Batch upsert: %d inserted, %d updated, %d skipped, %d errors",
        inserted, updated, skipped, errors,
    )
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}
