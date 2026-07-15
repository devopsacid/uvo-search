"""MongoDB loader — upsert canonical notices, procurers, and suppliers."""

import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import InsertOne, UpdateOne
from pymongo.errors import BulkWriteError, OperationFailure

from uvo_core.domain.models import CanonicalNotice, CanonicalProcurer, CanonicalSupplier
from uvo_pipeline.utils.hashing import compute_notice_hash

logger = logging.getLogger(__name__)


async def _ensure_index(collection: AsyncIOMotorCollection, keys: Any, **kwargs: Any) -> None:
    """create_index, but if a same-named index exists with a different spec, drop and recreate.

    Handles both IndexKeySpecsConflict (86) and IndexOptionsConflict (85) so legacy
    indexes (e.g. the old sparse ico_unique) can be migrated to a new spec in place.
    """
    name = kwargs.get("name")
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        if exc.code in (85, 86) and name:
            logger.warning(
                "Index %s.%s spec/options changed; dropping and recreating",
                collection.name,
                name,
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
        await _ensure_index(
            coll,
            [("ico", 1)],
            unique=True,
            partialFilterExpression=ico_partial,
            name="ico_unique",
        )
        await _ensure_index(coll, [("name_slug", 1)], name="name_slug_unique")
        await _ensure_index(coll, [("name", "text")], name="text_search")

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

    # ingestion_log: TTL + query indexes
    from uvo_pipeline.ingestion_log import ensure_log_indexes
    await ensure_log_indexes(db)

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


def _entity_update(ico: str | None, name_slug: str, doc: dict[str, Any]) -> tuple[dict, dict]:
    """Build the (filter, update) pair shared by the single-doc and bulk entity upserts."""
    doc = dict(doc)
    sources = doc.pop("sources", []) or []
    return (
        _entity_filter(ico, name_slug),
        {"$set": doc, "$addToSet": {"sources": {"$each": sources}}},
    )


async def upsert_procurer(db: AsyncIOMotorDatabase, procurer: CanonicalProcurer) -> str:
    """Upsert a procurer by ico (preferred) or name_slug fallback."""
    filter_, update = _entity_update(procurer.ico, procurer.name_slug, procurer.model_dump(mode="json"))
    result = await db.procurers.find_one_and_update(
        filter_, update, upsert=True, return_document=True,
    )
    return str(result["_id"])


async def upsert_supplier(db: AsyncIOMotorDatabase, supplier: CanonicalSupplier) -> str:
    """Upsert a supplier by ico (preferred) or name_slug fallback."""
    filter_, update = _entity_update(supplier.ico, supplier.name_slug, supplier.model_dump(mode="json"))
    result = await db.suppliers.find_one_and_update(
        filter_, update, upsert=True, return_document=True,
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

        # Build one UpdateOne per notice that needs a notices-collection write
        # (new or changed; "unchanged" only touches the registry) plus one
        # registry op per notice, then execute each collection's ops as a
        # single bulk_write instead of ~2N round trips. notice_op_notices
        # mirrors notice_ops 1:1 so the bulk result's `upserted_ids` (which
        # notices were newly created vs. matched-and-updated) can be mapped
        # back to the same inserted/updated counts the old per-doc
        # `result.upserted_id is not None` check produced.
        notice_ops: list[UpdateOne] = []
        notice_op_notices: list[CanonicalNotice] = []
        registry_ops: list[InsertOne | UpdateOne] = []

        for notice in batch:
            key = (notice.source, notice.source_id)
            reg_entry = registry.get(key)

            if reg_entry is None:
                # New notice — upsert into notices, insert registry entry
                doc = notice.model_dump(mode="json")
                notice_ops.append(UpdateOne(
                    {"source": notice.source, "source_id": notice.source_id},
                    {
                        "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                        "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                    },
                    upsert=True,
                ))
                notice_op_notices.append(notice)
                registry_ops.append(InsertOne({
                    "source": notice.source,
                    "source_id": notice.source_id,
                    "content_hash": notice.content_hash,
                    "ingested_at": now,
                    "last_seen_at": now,
                    "pipeline_run_id": notice.pipeline_run_id,
                    "skipped_count": 0,
                }))

            elif reg_entry["content_hash"] == notice.content_hash:
                # Unchanged — skip upsert, update registry metadata
                registry_ops.append(UpdateOne(
                    {"source": notice.source, "source_id": notice.source_id},
                    {
                        "$set": {"last_seen_at": now},
                        "$inc": {"skipped_count": 1},
                    },
                ))
                skipped += 1

            else:
                # Changed — upsert notice, update registry hash
                doc = notice.model_dump(mode="json")
                notice_ops.append(UpdateOne(
                    {"source": notice.source, "source_id": notice.source_id},
                    {
                        "$set": {k: v for k, v in doc.items() if k != "ingested_at"},
                        "$setOnInsert": {"ingested_at": doc["ingested_at"]},
                    },
                    upsert=True,
                ))
                notice_op_notices.append(notice)
                registry_ops.append(UpdateOne(
                    {"source": notice.source, "source_id": notice.source_id},
                    {"$set": {
                        "content_hash": notice.content_hash,
                        "last_seen_at": now,
                        "pipeline_run_id": notice.pipeline_run_id,
                    }},
                ))

        failed_notice_idx: set[int] = set()
        if notice_ops:
            try:
                notice_result = await db.notices.bulk_write(notice_ops, ordered=False)
                upserted_idx = set(notice_result.upserted_ids or {})
            except BulkWriteError as exc:
                details = exc.details or {}
                upserted_idx = {u["index"] for u in details.get("upserted", [])}
                for werr in details.get("writeErrors", []):
                    idx = werr["index"]
                    failed_notice_idx.add(idx)
                    n = notice_op_notices[idx]
                    logger.error(
                        "Failed to upsert notice %s/%s: %s", n.source, n.source_id, werr.get("errmsg")
                    )
                    errors += 1

            for idx, notice in enumerate(notice_op_notices):
                if idx in failed_notice_idx:
                    continue
                if idx in upserted_idx:
                    inserted += 1
                else:
                    updated += 1

        if registry_ops:
            try:
                await db.ingested_docs.bulk_write(registry_ops, ordered=False)
            except BulkWriteError as exc:
                for werr in (exc.details or {}).get("writeErrors", []):
                    logger.error("Failed to update ingested_docs registry: %s", werr.get("errmsg"))

        # Also upsert entities from this batch — one bulk_write per collection
        # instead of one find_one_and_update per procurer/supplier occurrence.
        # Unordered is safe: multiple ops for the same (source, source_id) key
        # within a batch each still apply their own $set/$addToSet atomically.
        procurer_ops: list[UpdateOne] = []
        supplier_ops: list[UpdateOne] = []
        for notice in batch:
            if notice.procurer:
                filter_, update = _entity_update(
                    notice.procurer.ico, notice.procurer.name_slug, notice.procurer.model_dump(mode="json")
                )
                procurer_ops.append(UpdateOne(filter_, update, upsert=True))
            for award in notice.awards:
                filter_, update = _entity_update(
                    award.supplier.ico, award.supplier.name_slug, award.supplier.model_dump(mode="json")
                )
                supplier_ops.append(UpdateOne(filter_, update, upsert=True))

        if procurer_ops:
            try:
                await db.procurers.bulk_write(procurer_ops, ordered=False)
            except BulkWriteError as exc:
                logger.warning("Failed to upsert %d procurer(s): %s", len(exc.details.get("writeErrors", [])), exc)
        if supplier_ops:
            try:
                await db.suppliers.bulk_write(supplier_ops, ordered=False)
            except BulkWriteError as exc:
                logger.warning("Failed to upsert %d supplier(s): %s", len(exc.details.get("writeErrors", [])), exc)

    logger.info(
        "Batch upsert: %d inserted, %d updated, %d skipped, %d errors",
        inserted, updated, skipped, errors,
    )
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}


def _entity_stats_pipeline(kind: str) -> list[dict]:
    """Per-ICO (contract_count, total_value) grouped from ``notices``.

    Mirrors the old per-row ``$lookup`` in ``adapters/mongo/subjects.py``: counts
    at the *notice* level (each matching notice once, even if a supplier appears
    in several awards of that notice) and sums ``final_value`` once per notice —
    hence ``$setUnion`` to dedupe the supplier ICOs within a notice rather than
    ``$unwind``ing the awards array.
    """
    value = {"$sum": {"$ifNull": ["$final_value", 0]}}
    if kind == "procurers":
        return [
            {"$match": {"procurer.ico": {"$nin": [None, ""]}}},
            {"$group": {"_id": "$procurer.ico", "contract_count": {"$sum": 1}, "total_value": value}},
        ]
    return [
        {"$match": {"awards.supplier.ico": {"$nin": [None, ""]}}},
        {"$project": {"final_value": 1, "_icos": {"$setUnion": ["$awards.supplier.ico", []]}}},
        {"$unwind": "$_icos"},
        {"$match": {"_icos": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$_icos", "contract_count": {"$sum": 1}, "total_value": value}},
    ]


async def recompute_entity_stats(
    db: AsyncIOMotorDatabase,
    *,
    batch_size: int = 1000,
    dry_run: bool = False,
) -> dict[str, int]:
    """Recompute denormalized ``contract_count``/``total_value`` on entities.

    Full-corpus aggregation over ``notices`` → ``$set`` onto matching
    ``procurers``/``suppliers`` docs (keyed by ICO). Only ICO-bearing entities
    are maintained (the entity search's stats path only ever resolved ICOs).

    Idempotent by construction — it derives the counts from the current corpus
    rather than incrementing, so it is safe to re-run and safe under the
    loader's content-hash skip semantics. Returns per-collection matched/updated
    counts; ``dry_run`` computes and reports without writing.
    """
    result: dict[str, int] = {}
    for kind in ("procurers", "suppliers"):
        matched = updated = 0
        ops: list[UpdateOne] = []
        cursor = db.notices.aggregate(_entity_stats_pipeline(kind), allowDiskUse=True)
        async for row in cursor:
            matched += 1
            if dry_run:
                continue
            ops.append(UpdateOne(
                {"ico": row["_id"]},
                {"$set": {
                    "contract_count": int(row.get("contract_count") or 0),
                    "total_value": float(row.get("total_value") or 0.0),
                }},
            ))
            if len(ops) >= batch_size:
                res = await db[kind].bulk_write(ops, ordered=False)
                updated += res.modified_count
                ops.clear()
        if ops:
            res = await db[kind].bulk_write(ops, ordered=False)
            updated += res.modified_count
        result[f"{kind}_matched"] = matched
        result[f"{kind}_updated"] = updated
        logger.info("recompute_entity_stats: %s matched=%d updated=%d (dry_run=%s)",
                    kind, matched, updated, dry_run)
    return result
