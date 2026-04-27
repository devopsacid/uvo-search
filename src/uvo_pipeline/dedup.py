"""Cross-source deduplication — assigns shared canonical_id to matching notices."""

from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def run_cross_source_dedup(
    db: AsyncIOMotorDatabase,
    *,
    run_id: str | None = None,
    window_days: int = 30,
) -> int:
    """Find cross-source duplicate notices and assign them a shared canonical_id.

    Filter predicate:
      - canonical_id is null (or absent)
      - ingested_at >= now - window_days
      - if run_id is given, ALSO restrict to pipeline_run_id == run_id (legacy mode)
    """
    if run_id is not None:
        base_filter: dict = {"pipeline_run_id": run_id}
    else:
        cutoff = (datetime.utcnow() - timedelta(days=window_days)).isoformat()
        base_filter = {"ingested_at": {"$gte": cutoff}}

    match_count = 0

    # --- Pass 1: procurer.ico + cpv_code ---
    pass1_match = {
        **base_filter,
        "procurer.ico": {"$ne": None, "$exists": True},
        "cpv_code": {"$ne": None, "$exists": True},
    }

    pipeline_pass1 = [
        {"$match": pass1_match},
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
    pass2_filter = {
        **base_filter,
        "title_slug": {"$ne": None, "$exists": True},
        "canonical_id": None,
        "$or": [
            {"procurer.ico": None},
            {"procurer.ico": {"$exists": False}},
        ],
    }

    ico_less = await db.notices.find(pass2_filter).to_list(length=None)

    by_slug: dict[str, list] = defaultdict(list)
    for n in ico_less:
        slug = n.get("title_slug")
        if slug:
            by_slug[slug].append(n)

    for slug, slug_notices in by_slug.items():
        if len(slug_notices) < 2:
            continue

        slug_notices.sort(key=lambda x: x.get("publication_date") or "")

        processed: set[str] = set()
        for i, anchor in enumerate(slug_notices):
            if str(anchor["_id"]) in processed:
                continue

            anchor_date_str = anchor.get("publication_date")
            if not anchor_date_str:
                continue

            try:
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
                continue

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
