"""Cross-source deduplication — assigns shared canonical_id to matching notices."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

# Pass 3 (supplier ICO + value window) tuning — see build_ico_value_window_groups.
ICO_VALUE_WINDOW_DAYS = 14
# 1.5x, not the naively "safe-looking" 2x: live-data validation (see
# scripts/preview_pass3_dedup.py) surfaced a same-ICO pair at ratio ~1.79
# (6,863.40 vs 12,298.77 EUR) that was almost certainly two distinct
# mini-contracts under the same recurring DNS framework agreement, not one
# notice reported twice — a 2x bound would have merged them. Genuine
# cross-source duplicates observed in the same sample (VAT-in/out, rounding,
# partial vs. final value) topped out around 1.23x, so 1.5x keeps headroom
# for that while rejecting the observed false merge.
ICO_VALUE_RATIO_MAX = 1.5
MAX_NOTICES_PER_SUPPLIER_ICO = 20


def _values_compatible(values_a: list[float], values_b: list[float]) -> bool:
    """Value-proximity guard for pass 3.

    Both sides must have at least one known award value — an ICO match where
    either notice has no value at all can't be verified, so it's rejected
    rather than guessed at. Among the known values, any pair within
    ICO_VALUE_RATIO_MAX of each other counts as compatible; see that
    constant's comment for how the threshold was picked.
    """
    if not values_a or not values_b:
        return False
    for a in values_a:
        for b in values_b:
            if a <= 0 or b <= 0:
                continue
            if max(a, b) / min(a, b) <= ICO_VALUE_RATIO_MAX:
                return True
    return False


async def build_ico_value_window_groups(
    db: AsyncIOMotorDatabase, base_filter: dict
) -> tuple[list[dict], int]:
    """Build pass-3 match groups: shared award supplier ICO, publication dates
    within ICO_VALUE_WINDOW_DAYS, and a compatible award value on both sides.

    Read-only — does not write to Mongo. Returns (groups, skipped_high_freq_ico_count)
    where each group is a dict ready to be persisted via persist_match_groups(),
    and skipped_high_freq_ico_count counts supplier ICOs excluded because they
    appear in more than MAX_NOTICES_PER_SUPPLIER_ICO candidate notices — a
    high-volume framework supplier (e.g. stationery, cleaning) can have dozens
    of unrelated contracts across sources in a single window, which would
    otherwise produce a combinatorial cluster of false merges.
    """
    pass3_filter = {
        **base_filter,
        "canonical_id": None,
        # $elemMatch, not the dot-path "awards.supplier.ico": {"$ne": None} — the
        # latter matches against the flattened per-element values, so a notice
        # with a mix of awards (some with ico, some without) gets excluded
        # because *some* element is null, even though at least one has an ico.
        "awards": {"$elemMatch": {"supplier.ico": {"$ne": None, "$exists": True}}},
    }

    candidates = await db.notices.find(
        pass3_filter, {"source": 1, "publication_date": 1, "awards": 1}
    ).to_list(length=None)

    by_ico: dict[str, list[dict]] = defaultdict(list)
    for n in candidates:
        seen_icos: set[str] = set()
        for award in n.get("awards") or []:
            ico = (award.get("supplier") or {}).get("ico")
            if not ico or ico in seen_icos:
                continue
            seen_icos.add(ico)
            values = [
                a.get("value")
                for a in n["awards"]
                if (a.get("supplier") or {}).get("ico") == ico and a.get("value") is not None
            ]
            by_ico[ico].append({
                "notice_id": n["_id"],
                "source": n["source"],
                "pub_date": n.get("publication_date"),
                "values": values,
            })

    groups: list[dict] = []
    skipped_high_freq = 0

    for ico, entries in by_ico.items():
        if len(entries) > MAX_NOTICES_PER_SUPPLIER_ICO:
            skipped_high_freq += 1
            continue
        if len(entries) < 2:
            continue

        entries.sort(key=lambda e: e.get("pub_date") or "")

        processed: set = set()
        for i, anchor in enumerate(entries):
            if anchor["notice_id"] in processed:
                continue

            anchor_date_str = anchor.get("pub_date")
            if not anchor_date_str:
                continue
            try:
                anchor_date = date_type.fromisoformat(str(anchor_date_str))
            except (ValueError, TypeError):
                continue

            cluster = [anchor]
            cluster_sources = {anchor["source"]}

            for other in entries[i + 1:]:
                if other["notice_id"] in processed:
                    continue
                if other["source"] == anchor["source"]:
                    continue
                other_date_str = other.get("pub_date")
                if not other_date_str:
                    continue
                try:
                    other_date = date_type.fromisoformat(str(other_date_str))
                except (ValueError, TypeError):
                    continue
                if abs((other_date - anchor_date).days) > ICO_VALUE_WINDOW_DAYS:
                    continue
                # Check against every member already in the cluster, not just the
                # anchor — otherwise two genuinely unrelated notices can each be
                # within tolerance *of the anchor* but not of each other, chaining
                # together via a shared anchor (observed on live data: a DNS
                # framework supplier with two distinct mini-contracts both landing
                # within value-ratio of a third, unrelated anchor notice).
                if not all(_values_compatible(other["values"], member["values"]) for member in cluster):
                    continue
                cluster.append(other)
                cluster_sources.add(other["source"])

            if len(cluster_sources) < 2:
                continue

            cluster.sort(key=lambda x: x.get("pub_date") or "")
            canonical_id = str(cluster[0]["notice_id"])
            notice_ids = [str(n["notice_id"]) for n in cluster]

            groups.append({
                "canonical_id": canonical_id,
                "notice_ids": notice_ids,
                "sources": sorted(cluster_sources),
                "supplier_ico": ico,
                "match_type": "supplier_ico_value_window",
            })
            for n in cluster:
                processed.add(n["notice_id"])

    return groups, skipped_high_freq


async def persist_match_groups(db: AsyncIOMotorDatabase, groups: list[dict]) -> int:
    """Write pre-built match groups to notices.canonical_id + cross_source_matches.

    Shared by run_cross_source_dedup (pass 3) and ad-hoc validation scripts so
    the write path stays identical between a dry-run preview and a real run.
    """
    for group in groups:
        await db.notices.update_many(
            {"_id": {"$in": [ObjectId(nid) for nid in group["notice_ids"]]}},
            {"$set": {"canonical_id": group["canonical_id"]}},
        )
        await db.cross_source_matches.update_one(
            {"canonical_id": group["canonical_id"]},
            {"$set": group},
            upsert=True,
        )
    return len(groups)


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
        cutoff = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=window_days)).isoformat()
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

    ico_less = await db.notices.find(
        pass2_filter, {"source": 1, "publication_date": 1, "title_slug": 1}
    ).to_list(length=None)

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

    # --- Pass 3: shared award supplier ICO + publication_date ±14 days + value proximity ---
    pass3_groups, _skipped_high_freq = await build_ico_value_window_groups(db, base_filter)
    match_count += await persist_match_groups(db, pass3_groups)

    return match_count
