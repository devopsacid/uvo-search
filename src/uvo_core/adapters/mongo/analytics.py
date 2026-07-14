"""MongoDB analytics aggregations for company profiles and dashboards.

Absorbs the former ``uvo_api/routers/_agg.py`` firma helpers and adds the
full-corpus dashboard aggregations that replace the old 500-doc sampled
endpoints (plan §1.3.2). All heavy lifting is a server-side ``$group`` — the
FastAPI routers only shape the returned rows into response models.

Value and date expressions mirror ``uvo_api._schema.contract_value`` /
``contract_date`` so the full-corpus numbers use the same field-precedence the
sampled Python code did (``final_value`` then ``estimated_value``; ``award_date``
then ``publication_date``).
"""

from __future__ import annotations

from uvo_core.cache import _make_key, async_ttl_cache

# final_value → estimated_value → 0  (matches _schema.contract_value)
_VALUE_EXPR = {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]}
# award_date → publication_date  (matches _schema.contract_date)
_DATE_EXPR = {"$ifNull": ["$award_date", "$publication_date"]}
# 4-char year prefix of the coalesced date string ("0000" when absent).
_YEAR_STR = {"$substrCP": [{"$ifNull": [_DATE_EXPR, "0000"]}, 0, 4]}


def _dashboard_match(ico: str | None, entity_type: str | None) -> dict:
    """Mongo match for the dashboard corpus, mirroring the old sample's filter.

    ``_fetch_contracts_sample`` paged ``search_completed_procurements`` which
    always constrained ``notice_type == contract_award`` and, when an ICO+role
    was given, ``awards.supplier.ico`` / ``procurer.ico``.
    """
    match: dict = {"notice_type": "contract_award"}
    if ico:
        if entity_type == "supplier":
            match["awards.supplier.ico"] = ico
        elif entity_type == "procurer":
            match["procurer.ico"] = ico
    return match


@async_ttl_cache(
    maxsize=500,
    ttl=3600,
    key_from=lambda db, ico: _make_key((ico,), {}),
)
async def _firma_core_agg(db, ico: str) -> dict:
    """One-shot $facet pipeline: supplier/procurer stats + top CPVs + spend-by-year."""
    pipeline = [
        {"$match": {"$or": [{"awards.supplier.ico": ico}, {"procurer.ico": ico}]}},
        {
            "$facet": {
                "as_supplier": [
                    {"$match": {"awards.supplier.ico": ico}},
                    {
                        "$group": {
                            "_id": None,
                            "count": {"$sum": 1},
                            "total": {"$sum": {"$ifNull": ["$final_value", 0]}},
                            "last": {"$max": "$award_date"},
                        }
                    },
                ],
                "as_procurer": [
                    {"$match": {"procurer.ico": ico}},
                    {
                        "$group": {
                            "_id": None,
                            "count": {"$sum": 1},
                            "total": {"$sum": {"$ifNull": ["$final_value", 0]}},
                            "last": {"$max": "$award_date"},
                        }
                    },
                ],
                "cpv": [
                    {
                        "$group": {
                            "_id": "$cpv_code",
                            "count": {"$sum": 1},
                            "total": {"$sum": {"$ifNull": ["$final_value", 0]}},
                        }
                    },
                    {"$sort": {"total": -1}},
                    {"$limit": 5},
                ],
                "spend_by_year": [
                    {
                        "$group": {
                            "_id": {
                                "$substrCP": [
                                    {
                                        "$ifNull": [
                                            "$award_date",
                                            {"$ifNull": ["$publication_date", "0000"]},
                                        ]
                                    },
                                    0,
                                    4,
                                ]
                            },
                            "total": {"$sum": {"$ifNull": ["$final_value", 0]}},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
            }
        },
    ]
    result = await db["notices"].aggregate(pipeline).to_list(1)
    return result[0] if result else {}


@async_ttl_cache(
    maxsize=200,
    ttl=1800,
    key_from=lambda db, ico, role, sort_by, limit, offset: _make_key(
        (ico, role, sort_by, limit, offset), {}
    ),
)
async def _firma_partners_agg(
    db, ico: str, role: str, sort_by: str, limit: int, offset: int
) -> dict:
    """Paginated partner aggregation for a company."""
    sort_field = "contract_count" if sort_by == "count" else "total_value"

    # Supplier-side: ico was supplier → counterparties are procurers
    supplier_pipeline = [
        {"$match": {"awards.supplier.ico": ico}},
        {
            "$group": {
                "_id": "$procurer.ico",
                "name": {"$first": "$procurer.name"},
                "contract_count": {"$sum": 1},
                "total_value": {"$sum": {"$ifNull": ["$final_value", 0]}},
                "last_contract_at": {"$max": "$award_date"},
            }
        },
        {"$addFields": {"role": "procurer"}},
    ]

    # Procurer-side: ico was procurer → counterparties are suppliers
    procurer_pipeline = [
        {"$match": {"procurer.ico": ico}},
        {"$unwind": "$awards"},
        {"$match": {"awards.supplier.ico": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$awards.supplier.ico",
                "name": {"$first": "$awards.supplier.name"},
                "contract_count": {"$sum": 1},
                "total_value": {"$sum": {"$ifNull": ["$final_value", 0]}},
                "last_contract_at": {"$max": "$award_date"},
            }
        },
        {"$addFields": {"role": "supplier"}},
    ]

    if role == "supplier":
        rows = await db["notices"].aggregate(procurer_pipeline).to_list(None)
    elif role == "procurer":
        rows = await db["notices"].aggregate(supplier_pipeline).to_list(None)
    else:
        s_rows = await db["notices"].aggregate(supplier_pipeline).to_list(None)
        p_rows = await db["notices"].aggregate(procurer_pipeline).to_list(None)
        rows = s_rows + p_rows

    rows.sort(key=lambda r: r.get(sort_field) or 0, reverse=True)
    total = len(rows)
    page = rows[offset : offset + limit]

    return {
        "total": total,
        "items": [
            {
                "ico": r.get("_id"),
                "name": r.get("name"),
                "role": r.get("role"),
                "contract_count": int(r.get("contract_count") or 0),
                "total_value": float(r.get("total_value") or 0.0),
                "last_contract_at": r.get("last_contract_at"),
            }
            for r in page
        ],
    }


@async_ttl_cache(
    maxsize=1,
    ttl=86400,
    key_from=lambda db, limit=20: _make_key((limit,), {}),
)
async def _market_cpv_agg(db, limit: int = 20) -> list[dict]:
    """Market-wide CPV distribution — cached 24 h."""
    pipeline = [
        {"$match": {"cpv_code": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$cpv_code",
                "count": {"$sum": 1},
                "total": {"$sum": {"$ifNull": ["$final_value", 0]}},
            }
        },
        {"$sort": {"total": -1}},
        {"$limit": limit},
    ]
    return await db["notices"].aggregate(pipeline).to_list(limit)


def build_spend_by_year_pipeline(ico: str | None, entity_type: str | None) -> list[dict]:
    """Full-corpus spend + count grouped by year (dashboard summary + spend-by-year)."""
    return [
        {"$match": _dashboard_match(ico, entity_type)},
        {
            "$group": {
                "_id": _YEAR_STR,
                "total": {"$sum": _VALUE_EXPR},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]


def build_cpv_breakdown_pipeline(
    ico: str | None,
    entity_type: str | None,
    year_from: int | None,
    year_to: int | None,
) -> list[dict]:
    """Full-corpus spend + count grouped by raw CPV code, optionally year-bounded.

    Grouping stays on the raw ``cpv_code``; the router applies ``_cpv_prefix``
    and label lookup afterwards so the 8-digit bucketing logic is unchanged.
    """
    pipeline: list[dict] = [{"$match": _dashboard_match(ico, entity_type)}]
    if year_from is not None or year_to is not None:
        year_bound: dict = {}
        if year_from is not None:
            year_bound["$gte"] = year_from
        if year_to is not None:
            year_bound["$lte"] = year_to
        pipeline += [
            {"$addFields": {"_year": {"$toInt": _YEAR_STR}}},
            {"$match": {"_year": year_bound}},
        ]
    pipeline += [
        {
            "$group": {
                "_id": "$cpv_code",
                "total": {"$sum": _VALUE_EXPR},
                "count": {"$sum": 1},
            }
        },
    ]
    return pipeline


def build_monthly_buckets_pipeline(year: int) -> list[dict]:
    """Full-corpus monthly count + spend for one year."""
    return [
        {"$match": _dashboard_match(None, None)},
        {"$addFields": {"_d": {"$ifNull": [_DATE_EXPR, ""]}}},
        {"$match": {"_d": {"$gte": f"{year}-", "$lt": f"{year + 1}-"}}},
        {
            "$group": {
                "_id": {"$toInt": {"$substrCP": ["$_d", 5, 2]}},
                "count": {"$sum": 1},
                "total": {"$sum": _VALUE_EXPR},
            }
        },
    ]


def build_top_entities_pipeline(field: str, unwind: bool, n: int) -> list[dict]:
    """Top-N entities by awarded/spent value (top-suppliers / top-procurers)."""
    match = {field: {"$nin": [None, ""]}}
    pipeline: list[dict] = [{"$match": match}]
    if unwind:
        pipeline += [{"$unwind": "$awards"}, {"$match": match}]
    pipeline += [
        {
            "$group": {
                "_id": f"${field}",
                "total_value": {"$sum": {"$ifNull": ["$final_value", 0]}},
                "contract_count": {"$sum": 1},
                "name": {"$first": f"${field.rsplit('.', 1)[0]}.name"},
            }
        },
        {"$sort": {"total_value": -1}},
        {"$limit": n},
    ]
    return pipeline


class MongoCompanyAnalytics:
    """CompanyAnalytics port backed by MongoDB ``notices`` aggregations."""

    def __init__(self, db) -> None:
        self._db = db

    async def core_stats(self, ico: str) -> dict:
        return await _firma_core_agg(self._db, ico)

    async def partners(self, ico: str, role: str, sort_by: str, limit: int, offset: int) -> dict:
        return await _firma_partners_agg(self._db, ico, role, sort_by, limit, offset)

    async def market_cpv(self, limit: int = 20) -> list[dict]:
        return await _market_cpv_agg(self._db, limit)

    async def top_suppliers(self, n: int = 10) -> list[dict]:
        pipeline = build_top_entities_pipeline("awards.supplier.ico", unwind=True, n=n)
        return await self._db["notices"].aggregate(pipeline).to_list(n)

    async def top_procurers(self, n: int = 10) -> list[dict]:
        pipeline = build_top_entities_pipeline("procurer.ico", unwind=False, n=n)
        return await self._db["notices"].aggregate(pipeline).to_list(n)

    async def spend_by_year(
        self, ico: str | None = None, entity_type: str | None = None
    ) -> list[dict]:
        pipeline = build_spend_by_year_pipeline(ico, entity_type)
        return await self._db["notices"].aggregate(pipeline).to_list(None)

    async def cpv_breakdown(
        self,
        ico: str | None = None,
        entity_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict]:
        pipeline = build_cpv_breakdown_pipeline(ico, entity_type, year_from, year_to)
        return await self._db["notices"].aggregate(pipeline).to_list(None)

    async def monthly_buckets(self, year: int) -> list[dict]:
        pipeline = build_monthly_buckets_pipeline(year)
        return await self._db["notices"].aggregate(pipeline).to_list(None)
