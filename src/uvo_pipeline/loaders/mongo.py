"""MongoDB loader — upsert canonical notices, procurers, and suppliers."""

import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalSupplier
from uvo_pipeline.utils.hashing import compute_notice_hash

logger = logging.getLogger(__name__)


async def _create_index_upgrading(
    collection: AsyncIOMotorCollection,
    keys: list,
    *,
    name: str,
    **options: Any,
) -> None:
    """create_index that drops and recreates when an index with the same name
    exists with different options. Needed to migrate the legacy sparse
    ico_unique index to a partialFilterExpression-based variant in place.
    """
    try:
        await collection.create_index(keys, name=name, **options)
    except OperationFailure as exc:
        # code 85 = IndexOptionsConflict, 86 = IndexKeySpecsConflict
        if exc.code not in (85, 86):
            raise
        logger.info("Dropping legacy index %s.%s and recreating", collection.name, name)
        await collection.drop_index(name)
        await collection.create_index(keys, name=name, **options)


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

    # procurers / suppliers:
    # - ico_unique uses partialFilterExpression rather than sparse. MongoDB
    #   "sparse" still indexes null-valued fields, so two records with ico=null
    #   violate uniqueness; partialFilterExpression only indexes docs whose
    #   ico is an actual string.
    # - name_slug is indexed for lookup but NOT unique: real procurement data
    #   contains distinct legal entities sharing a name (different ICOs), and
    #   also inconsistent ICO reporting across sources for the same name.
    #   Dedup is driven by ico when present; name_slug fallback in upserts
    #   finds the first matching doc, which is acceptable for null-ico cases.
    ico_partial = {"ico": {"$type": "string"}}
    for coll in (db.procurers, db.suppliers):
        await _create_index_upgrading(
            coll,
            [("ico", 1)],
            name="ico_unique",
            unique=True,
            partialFilterExpression=ico_partial,
        )
        await _create_index_upgrading(
            coll,
            [("name_slug", 1)],
            name="name_slug_unique",
        )
        await coll.create_index([("name", "text")], name="text_search")

    # pipeline_state: unique on source
    await db.pipeline_state.create_index(
        [("source", 1)], unique=True, name="source_unique"
    )

    # ckan_packages: unique on package_id
    await db.ckan_packages.create_index(
        [("package_id", 1)], unique=True, name="package_id_unique"
    )
    await db.ckan_packages.create_index([("last_modified", -1)], name="last_modified_desc")

    # ingested_docs: fast lookup + audit trail
    await db.ingested_docs.create_index(
        [("source", 1), ("source_id", 1)], unique=True, name="source_source_id_unique"
    )
    await db.ingested_docs.create_index([("pipeline_run_id", 1)], name="pipeline_run_id")
    await db.ingested_docs.create_index(
        [("source", 1), ("ingested_at", -1)], name="source_ingested_at_desc"
    )
    await db.ingested_docs.create_index([("ingested_at", -1)], name="ingested_at_desc")

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


def _entity_filter(ico: str | None, name_slug: str) -> dict[str, Any]:
    """Match key for procurer/supplier upsert.

    With ICO: uniquely keyed on the ICO itself.
    Without ICO: keyed on (name_slug, ico=None) — the ico=None clause prevents
    the null-ico upsert from clobbering an existing ICO-bearing doc that
    happens to share a name_slug (real data has multiple distinct legal
    entities with identical slugified names).
    """
    if ico:
        return {"ico": ico}
    return {"name_slug": name_slug, "ico": None}


async def upsert_procurer(db: AsyncIOMotorDatabase, procurer: CanonicalProcurer) -> str:
    """Upsert a procurer by ico (preferred) or name_slug fallback."""
    doc = procurer.model_dump(mode="json")
    sources = doc.pop("sources", []) or []
    result = await db.procurers.find_one_and_update(
        _entity_filter(procurer.ico, procurer.name_slug),
        {"$set": doc, "$addToSet": {"sources": {"$each": sources}}},
        upsert=True,
        return_document=True,
    )
    return str(result["_id"])


async def upsert_supplier(db: AsyncIOMotorDatabase, supplier: CanonicalSupplier) -> str:
    """Upsert a supplier by ico (preferred) or name_slug fallback."""
    doc = supplier.model_dump(mode="json")
    sources = doc.pop("sources", []) or []
    result = await db.suppliers.find_one_and_update(
        _entity_filter(supplier.ico, supplier.name_slug),
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
        raw_batch = notices[i : i + batch_size]

        # Dedupe within the batch on (source, source_id). Callers may emit the
        # same notice twice when a source exposes the same payload via multiple
        # distributions (e.g. Vestník datasets have several format rows in the
        # NKOD SPARQL result). Without this, the first occurrence inserts and
        # the second collides on the ingested_docs unique index.
        deduped: dict[tuple[str, str], CanonicalNotice] = {}
        for notice in raw_batch:
            deduped[(notice.source, notice.source_id)] = notice
        batch = list(deduped.values())

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
