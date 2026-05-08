"""Direct MongoDB aggregation helpers for firma endpoints."""

from __future__ import annotations

from uvo_mcp.cache import _make_key, async_ttl_cache


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
