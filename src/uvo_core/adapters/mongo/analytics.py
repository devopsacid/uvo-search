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

import asyncio
import logging

from uvo_core.adapters.mongo import entities
from uvo_core.cache import _make_key, async_ttl_cache

logger = logging.getLogger(__name__)

# final_value → estimated_value → 0  (matches _schema.contract_value)
_VALUE_EXPR = {"$ifNull": ["$final_value", {"$ifNull": ["$estimated_value", 0]}]}
# award_date → publication_date  (matches _schema.contract_date)
_DATE_EXPR = {"$ifNull": ["$award_date", "$publication_date"]}
# 4-char year prefix of the coalesced date string ("0000" when absent).
_YEAR_STR = {"$substrCP": [{"$ifNull": [_DATE_EXPR, "0000"]}, 0, 4]}


def clear_analytics_caches() -> None:
    """Drop all in-process analytics caches.

    Called by the API's ``notices:written`` invalidation subscriber so freshly
    ingested data surfaces without waiting for each query's TTL to lapse. Every
    ``async_ttl_cache``-wrapped aggregate in this module is listed in
    ``_CACHED_AGGREGATES`` (defined below the functions) so none can be missed.
    """
    for fn in _CACHED_AGGREGATES:
        fn.cache_clear()
    entities.clear_entity_caches()


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
        s_rows, p_rows = await asyncio.gather(
            db["notices"].aggregate(supplier_pipeline).to_list(None),
            db["notices"].aggregate(procurer_pipeline).to_list(None),
        )
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
    """Market-wide CPV distribution + per-CPV median contract value — cached 24 h.

    ``median`` is the robust baseline the market_deviation flag compares against
    (a few very large contracts can't drag a median the way they drag a mean). The
    ``$median`` accumulator needs MongoDB 7.0+ (Atlas Local ships it); the scoring
    layer falls back to ``total/count`` if a row lacks ``median``.
    """
    pipeline = [
        {"$match": {"cpv_code": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$cpv_code",
                "count": {"$sum": 1},
                "total": {"$sum": {"$ifNull": ["$final_value", 0]}},
                "median": {
                    "$median": {
                        "input": {"$ifNull": ["$final_value", 0]},
                        "method": "approximate",
                    }
                },
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
    """Full-corpus monthly count + spend for one year.

    The year window is expressed on the *raw* ``award_date`` / ``publication_date``
    fields in the leading ``$match`` (equivalent to coalescing ``award_date`` then
    ``publication_date``) so the planner can use indexes instead of computing a
    derived field for every document first.
    """
    window = {"$gte": f"{year}-", "$lt": f"{year + 1}-"}
    match = {
        **_dashboard_match(None, None),
        "$or": [
            {"award_date": window},
            {"award_date": None, "publication_date": window},
        ],
    }
    return [
        {"$match": match},
        {
            "$group": {
                "_id": {"$toInt": {"$substrCP": [_DATE_EXPR, 5, 2]}},
                "count": {"$sum": 1},
                "total": {"$sum": _VALUE_EXPR},
            }
        },
    ]


def build_award_timeline_pipelines(ico: str) -> tuple[list[dict], list[dict]]:
    """Per-award (date, counterparty_ico, value) rows for a company, both roles.

    Procurer side: the company issued the award → the awarded supplier is the
    counterparty. Supplier side: the company won the award → the procurer is the
    counterparty. The scoring engine groups the union by counterparty to detect
    short-window award bursts (contract-splitting signal).
    """
    as_procurer = [
        {"$match": {"notice_type": "contract_award", "procurer.ico": ico}},
        {"$unwind": "$awards"},
        {
            "$project": {
                "_id": 0,
                "date": _DATE_EXPR,
                "counterparty_ico": "$awards.supplier.ico",
                "value": _VALUE_EXPR,
                "cpv_code": "$cpv_code",
                "procedure_type": "$procedure_type",
            }
        },
    ]
    as_supplier = [
        {"$match": {"notice_type": "contract_award", "awards.supplier.ico": ico}},
        {
            "$project": {
                "_id": 0,
                "date": _DATE_EXPR,
                "counterparty_ico": "$procurer.ico",
                "value": _VALUE_EXPR,
                "cpv_code": "$cpv_code",
                "procedure_type": "$procedure_type",
            }
        },
    ]
    return as_procurer, as_supplier


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


# --- Cached dashboard aggregates -------------------------------------------------
# Each is a server-side full-corpus $group; the corpus only changes on ingestion,
# and clear_analytics_caches() (driven by notices:written) drops them early.


@async_ttl_cache(
    maxsize=256,
    ttl=900,
    key_from=lambda db, ico, entity_type: _make_key((ico, entity_type), {}),
)
async def _spend_by_year_agg(db, ico: str | None, entity_type: str | None) -> list[dict]:
    pipeline = build_spend_by_year_pipeline(ico, entity_type)
    return await db["notices"].aggregate(pipeline).to_list(None)


@async_ttl_cache(
    maxsize=256,
    ttl=900,
    key_from=lambda db, ico, entity_type, year_from, year_to: _make_key(
        (ico, entity_type, year_from, year_to), {}
    ),
)
async def _cpv_breakdown_agg(
    db, ico: str | None, entity_type: str | None, year_from: int | None, year_to: int | None
) -> list[dict]:
    pipeline = build_cpv_breakdown_pipeline(ico, entity_type, year_from, year_to)
    return await db["notices"].aggregate(pipeline).to_list(None)


@async_ttl_cache(maxsize=32, ttl=900, key_from=lambda db, year: _make_key((year,), {}))
async def _monthly_buckets_agg(db, year: int) -> list[dict]:
    pipeline = build_monthly_buckets_pipeline(year)
    return await db["notices"].aggregate(pipeline).to_list(None)


@async_ttl_cache(
    maxsize=64,
    ttl=1800,
    key_from=lambda db, field, unwind, n: _make_key((field, unwind, n), {}),
)
async def _top_entities_agg(db, field: str, unwind: bool, n: int) -> list[dict]:
    pipeline = build_top_entities_pipeline(field, unwind=unwind, n=n)
    return await db["notices"].aggregate(pipeline).to_list(n)


@async_ttl_cache(maxsize=500, ttl=1800, key_from=lambda db, ico: _make_key((ico,), {}))
async def _award_timeline_agg(db, ico: str) -> list[dict]:
    as_procurer, as_supplier = build_award_timeline_pipelines(ico)
    proc_rows, supp_rows = await asyncio.gather(
        db["notices"].aggregate(as_procurer).to_list(None),
        db["notices"].aggregate(as_supplier).to_list(None),
    )
    return proc_rows + supp_rows


# --- Entity (procurer / supplier) pages -------------------------------------------

_PROFILE_ROLES = {"procurer", "supplier"}
_MIN_YEAR, _MAX_YEAR = 1993, 2100
_TOP_CONTRACT_PROJECTION = {
    "title": 1,
    "procurer": 1,
    "awards": 1,
    "final_value": 1,
    "estimated_value": 1,
    "award_date": 1,
    "publication_date": 1,
    "cpv_code": 1,
    "status": 1,
}


async def top_contracts_by_value(db, ico: str, role: str, limit: int = 5) -> list[dict]:
    """Largest contracts (by ``final_value``) for a supplier or procurer.

    A dedicated sorted ``find`` rather than the Atlas ``$search`` path: that path
    orders by publication date, which made "top contracts" show the newest ones.
    Records without a ``final_value`` sort last.
    """
    field = "awards.supplier.ico" if role == "supplier" else "procurer.ico"
    query = {"notice_type": "contract_award", field: ico}
    docs = (
        await db["notices"]
        .find(query, _TOP_CONTRACT_PROJECTION)
        .sort("final_value", -1)
        .limit(limit)
        .to_list(limit)
    )
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


def build_entity_profile_pipeline(ico: str, role: str, top_n: int = 10) -> list[dict]:
    """Full-population stats for one procurer/supplier in a single ``$facet`` pass.

    * ``years``: spend + count per year (spend_by_year, years_active, totals).
    * ``partners``: top-N counterparties by value.
    * ``concentration``: ``sum(v)`` and ``sum(v^2)`` over *all* counterparties,
      from which HHI is derived without shipping every counterparty to Python.

    For a procurer the counterparty is the supplier of the first award (the whole
    contract value is attributed to it, matching the previous per-row logic);
    for a supplier it is the procuring authority.
    """
    if role == "procurer":
        prep: list[dict] = [{"$addFields": {"_cp": {"$arrayElemAt": ["$awards.supplier", 0]}}}]
    else:
        prep = [{"$addFields": {"_cp": "$procurer"}}]
    prep.append({"$match": {"_cp.ico": {"$nin": [None, ""]}}})
    per_partner = {
        "$group": {
            "_id": "$_cp.ico",
            "name": {"$first": "$_cp.name"},
            "count": {"$sum": 1},
            "total": {"$sum": _VALUE_EXPR},
        }
    }
    return [
        {"$match": _dashboard_match(ico, role)},
        {
            "$facet": {
                "years": [
                    {
                        "$group": {
                            "_id": _YEAR_STR,
                            "total": {"$sum": _VALUE_EXPR},
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
                "partners": [*prep, per_partner, {"$sort": {"total": -1}}, {"$limit": top_n}],
                "concentration": [
                    *prep,
                    per_partner,
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": "$total"},
                            "sumsq": {"$sum": {"$multiply": ["$total", "$total"]}},
                            "partner_count": {"$sum": 1},
                        }
                    },
                ],
            }
        },
    ]


def shape_entity_profile(raw: dict) -> dict:
    """Turn the raw ``$facet`` output into the plain dict the routers consume."""
    spend_by_year: list[dict] = []
    contract_count = 0
    total_value = 0.0
    for row in raw.get("years") or []:
        contract_count += int(row.get("count") or 0)
        total_value += float(row.get("total") or 0.0)
        try:
            year = int(row.get("_id") or 0)
        except (TypeError, ValueError):
            continue
        if _MIN_YEAR <= year <= _MAX_YEAR:
            spend_by_year.append({"year": year, "total_value": float(row.get("total") or 0.0)})

    conc = (raw.get("concentration") or [{}])[0]
    partner_total = float(conc.get("total") or 0.0)
    hhi = 10_000.0 * float(conc.get("sumsq") or 0.0) / (partner_total**2) if partner_total else 0.0
    return {
        "contract_count": contract_count,
        "total_value": total_value,
        "spend_by_year": spend_by_year,
        "years_active": [y["year"] for y in spend_by_year],
        "partners": [
            {
                "ico": str(p["_id"]),
                "name": p.get("name") or "",
                "contract_count": int(p.get("count") or 0),
                "total_value": float(p.get("total") or 0.0),
            }
            for p in raw.get("partners") or []
        ],
        "partner_total_value": partner_total,
        "partner_count": int(conc.get("partner_count") or 0),
        "hhi": hhi,
    }


@async_ttl_cache(
    maxsize=500,
    ttl=1800,
    key_from=lambda db, ico, role, top_n=10: _make_key((ico, role, top_n), {}),
)
async def entity_profile(db, ico: str, role: str, top_n: int = 10) -> dict:
    """Full-population summary (counts, spend by year, top partners, HHI) for an entity."""
    if role not in _PROFILE_ROLES:
        raise ValueError(f"role must be one of {sorted(_PROFILE_ROLES)}, got {role!r}")
    pipeline = build_entity_profile_pipeline(ico, role, top_n)
    result = await db["notices"].aggregate(pipeline).to_list(1)
    return shape_entity_profile(result[0] if result else {})


_CACHED_AGGREGATES = (
    _firma_core_agg,
    _firma_partners_agg,
    _market_cpv_agg,
    _spend_by_year_agg,
    _cpv_breakdown_agg,
    _monthly_buckets_agg,
    _top_entities_agg,
    _award_timeline_agg,
    entity_profile,
)


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
        return await _top_entities_agg(self._db, "awards.supplier.ico", True, n)

    async def top_procurers(self, n: int = 10) -> list[dict]:
        return await _top_entities_agg(self._db, "procurer.ico", False, n)

    async def spend_by_year(
        self, ico: str | None = None, entity_type: str | None = None
    ) -> list[dict]:
        return await _spend_by_year_agg(self._db, ico, entity_type)

    async def cpv_breakdown(
        self,
        ico: str | None = None,
        entity_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict]:
        return await _cpv_breakdown_agg(self._db, ico, entity_type, year_from, year_to)

    async def monthly_buckets(self, year: int) -> list[dict]:
        return await _monthly_buckets_agg(self._db, year)

    async def award_timeline(self, ico: str) -> list[dict]:
        return await _award_timeline_agg(self._db, ico)
