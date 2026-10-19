"""MongoDB aggregations behind the analytics dashboards (metric definition D1).

Everything is computed at query time over ``notices``; nothing is written.

Layout, top to bottom:

* ``build_*`` - pure pipeline builders (unit-tested by asserting stage shapes);
* ``shape_*`` - pure functions turning raw aggregate rows into the read-models
  the :class:`uvo_core.ports.DashboardAnalytics` port returns;
* ``_*_agg``  - ``async_ttl_cache``'d aggregate runners returning **raw rows**
  (cached 15 min, self-registered for ``clear_data_caches()``);
* :class:`MongoDashboardAnalytics` - the port adapter.

Raw rows are cached rather than shaped results so time-dependent fields (source
age) are computed fresh on every call.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from uvo_core.cache import _make_key, async_ttl_cache
from uvo_core.domain.analytics import (
    D1_NOTICE_TYPE,
    DATE_EXPR,
    NO_CPV,
    SOURCES,
    VALUE_EXPR,
    DashboardFilter,
    cpv_division,
    cpv_group,
    freshness_status,
    hhi_band,
    period_key,
    zero_filled_periods,
)
from uvo_core.domain.cpv import cpv_label_sk

logger = logging.getLogger(__name__)

_TTL_SECONDS = 900
_MAXSIZE = 512
_MAX_TIME_MS = 15_000

# Distinct, non-empty supplier ICOs of one notice ($setUnion, never a plain $unwind of
# awards: a notice with two lines for the same supplier still counts that supplier once).
_SUPPLIERS_EXPR: dict = {
    "$setDifference": [
        {"$setUnion": [{"$ifNull": ["$awards.supplier.ico", []]}, []]},
        [None, ""],
    ]
}
_NO_ICO = {"$nin": [None, ""]}

_TOP_DIMENSIONS = ("procurer", "supplier", "cpv_division")
_METRIC_FIELD = {"total_value": "total", "contract_count": "count"}
_SPLITS = ("source", "cpv_division")
_CONCENTRATION_TOP = 10
_COVERAGE_MONTHS = 24
_CADENCE_SECONDS: dict[str, int | None] = {
    "vestnik": 3600,
    "crz": 3600,
    "ted": 3600,
    "uvo": None,  # legacy: no running extractor
    "itms": 3600,
}
_NO_CPV_LABEL = "Bez CPV"
_OTHER_LABEL = "Ostatné"


# --------------------------------------------------------------------------- builders


def _cpv_bucket_expr(digits: int) -> dict:
    """First ``digits`` digits of ``cpv_code`` padded to an 8-digit code, ``00000000`` if absent."""
    code = {"$ifNull": ["$cpv_code", ""]}
    return {
        "$cond": [
            {"$gte": [{"$strLenCP": code}, digits]},
            {"$concat": [{"$substrCP": [code, 0, digits]}, "0" * (8 - digits)]},
            NO_CPV,
        ]
    }


def build_match(f: DashboardFilter) -> dict:
    """Index-friendly D1 ``$match``: award_date range, else publication_date range.

    Same shape as ``analytics.build_monthly_buckets_pipeline``; the first ``$or`` branch
    uses ``{notice_type, award_date}``, the second ``{notice_type, publication_date}``.
    """
    match: dict = {
        "notice_type": D1_NOTICE_TYPE,
        "$or": [
            {"award_date": {"$gte": f.date_from, "$lte": f.date_to}},
            {
                "award_date": None,
                "publication_date": {"$gte": f.date_from, "$lte": f.date_to},
            },
        ],
    }
    if f.cpv:
        match["cpv_code"] = {"$regex": f"^{f.cpv}"}
    if f.source:
        match["source"] = f.source
    if f.procurer_ico:
        match["procurer.ico"] = f.procurer_ico
    if f.supplier_ico:
        match["awards.supplier.ico"] = f.supplier_ico
    return match


def _lean_project() -> dict:
    """Project the few fields the facets need so later stages carry small documents."""
    return {
        "$project": {
            "_id": 0,
            "v": VALUE_EXPR,
            "pico": "$procurer.ico",
            "pname": "$procurer.name",
            "sup": _SUPPLIERS_EXPR,
            "cpv": _cpv_bucket_expr(2),
        }
    }


def _count_total_group() -> dict:
    return {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$v"}}}


def build_summary_pipeline(f: DashboardFilter) -> list[dict]:
    """Totals plus distinct procurer / supplier counts in one pass."""
    return [
        {"$match": build_match(f)},
        _lean_project(),
        {
            "$facet": {
                "totals": [_count_total_group()],
                "procurers": [
                    {"$match": {"pico": _NO_ICO}},
                    {"$group": {"_id": "$pico"}},
                    {"$count": "n"},
                ],
                "suppliers": [
                    {"$unwind": "$sup"},
                    {"$group": {"_id": "$sup"}},
                    {"$count": "n"},
                ],
            }
        },
    ]


def build_timeseries_pipeline(
    f: DashboardFilter, granularity: str, split_by: str | None, top: int
) -> list[dict]:
    """Per period (and optionally per split key) count and value.

    Groups by month (or year for ``year``); quarters are summed from months in
    :func:`shape_timeseries`. ``top`` is applied there too, since the number of
    (period, key) rows is small (periods x at most ~45 keys).
    """
    if split_by is not None and split_by not in _SPLITS:
        raise ValueError(f"split_by must be one of {_SPLITS}, got {split_by!r}")
    width = 4 if granularity == "year" else 7
    group_id: dict = {"period": {"$substrCP": [DATE_EXPR, 0, width]}}
    if split_by == "source":
        group_id["key"] = "$source"
    elif split_by == "cpv_division":
        group_id["key"] = _cpv_bucket_expr(2)
    return [
        {"$match": build_match(f)},
        {
            "$group": {
                "_id": group_id,
                "count": {"$sum": 1},
                "total": {"$sum": VALUE_EXPR},
            }
        },
    ]


def _name_lookup(dimension: str) -> list[dict]:
    """Attach the display name of a supplier ICO (procurer names ride along via $first)."""
    if dimension != "supplier":
        return []
    return [
        {
            "$lookup": {
                "from": "suppliers",
                "localField": "_id",
                "foreignField": "ico",
                "as": "_entity",
            }
        },
        {"$addFields": {"name": {"$first": "$_entity.name"}}},
        {"$project": {"_entity": 0}},
    ]


def _entity_group_stages(dimension: str) -> list[dict]:
    """Group the lean documents by entity: ``{_id, [name], count, total}``."""
    if dimension == "procurer":
        return [
            {"$match": {"pico": _NO_ICO}},
            {
                "$group": {
                    "_id": "$pico",
                    "name": {"$first": "$pname"},
                    "count": {"$sum": 1},
                    "total": {"$sum": "$v"},
                }
            },
        ]
    if dimension == "supplier":
        return [
            {"$unwind": "$sup"},
            {"$group": {"_id": "$sup", "count": {"$sum": 1}, "total": {"$sum": "$v"}}},
        ]
    if dimension == "cpv_division":
        return [{"$group": {"_id": "$cpv", "count": {"$sum": 1}, "total": {"$sum": "$v"}}}]
    raise ValueError(f"dimension must be one of {_TOP_DIMENSIONS}, got {dimension!r}")


def build_top_pipeline(f: DashboardFilter, dimension: str, metric: str, n: int) -> list[dict]:
    """Top-``n`` entities by ``metric`` plus the grand total of the filtered set."""
    if metric not in _METRIC_FIELD:
        raise ValueError(f"metric must be one of {tuple(_METRIC_FIELD)}, got {metric!r}")
    group_stages = _entity_group_stages(dimension)
    return [
        {"$match": build_match(f)},
        _lean_project(),
        {
            "$facet": {
                "total": [_count_total_group()],
                "items": [
                    *group_stages,
                    {"$sort": {_METRIC_FIELD[metric]: -1, "_id": 1}},
                    {"$limit": n},
                    *_name_lookup(dimension),
                ],
            }
        },
    ]


def build_concentration_pipeline(f: DashboardFilter, dimension: str) -> list[dict]:
    """Per-entity value, then ``$facet`` into HHI inputs (all entities) and the top 10."""
    if dimension not in ("supplier", "procurer"):
        raise ValueError(f"dimension must be supplier or procurer, got {dimension!r}")
    return [
        {"$match": build_match(f)},
        _lean_project(),
        *_entity_group_stages(dimension),
        {"$match": {"total": {"$gt": 0}}},
        {
            "$facet": {
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": "$total"},
                            "sumsq": {"$sum": {"$multiply": ["$total", "$total"]}},
                            "n": {"$sum": 1},
                        }
                    }
                ],
                "top": [
                    {"$sort": {"total": -1, "_id": 1}},
                    {"$limit": _CONCENTRATION_TOP},
                    *_name_lookup(dimension),
                ],
            }
        },
    ]


def build_cpv_pipeline(f: DashboardFilter, level: str) -> list[dict]:
    """Value and count per CPV division (2 digits) or group (3 digits)."""
    if level not in ("division", "group"):
        raise ValueError(f"level must be division or group, got {level!r}")
    bucket = _cpv_bucket_expr(2 if level == "division" else 3)
    return [
        {"$match": build_match(f)},
        {
            "$group": {
                "_id": bucket,
                "count": {"$sum": 1},
                "total": {"$sum": VALUE_EXPR},
            }
        },
    ]


def build_coverage_pipelines(since_month: str) -> dict[str, list[dict]]:
    """Per-source counts and quality, monthly publication counts, canonical-link count."""
    is_award = {"$eq": ["$notice_type", D1_NOTICE_TYPE]}

    def award_and(condition: dict) -> dict:
        return {"$sum": {"$cond": [{"$and": [is_award, condition]}, 1, 0]}}

    return {
        "sources": [
            {
                "$group": {
                    "_id": "$source",
                    "notices_total": {"$sum": 1},
                    "contract_awards": {"$sum": {"$cond": [is_award, 1, 0]}},
                    "last_publication": {"$max": "$publication_date"},
                    "last_ingested": {"$max": "$ingested_at"},
                    "with_value": award_and({"$gt": [VALUE_EXPR, 0]}),
                    "with_cpv": award_and(
                        {"$gt": [{"$strLenCP": {"$ifNull": ["$cpv_code", ""]}}, 0]}
                    ),
                    "with_supplier": award_and({"$gt": [{"$size": _SUPPLIERS_EXPR}, 0]}),
                    "with_procurer": award_and(
                        {"$gt": [{"$strLenCP": {"$ifNull": ["$procurer.ico", ""]}}, 0]}
                    ),
                }
            }
        ],
        "monthly": [
            {"$match": {"publication_date": {"$gte": since_month}}},
            {
                "$group": {
                    "_id": {
                        "period": {"$substrCP": [{"$ifNull": ["$publication_date", ""]}, 0, 7]},
                        "source": "$source",
                    },
                    "count": {"$sum": 1},
                }
            },
        ],
        "canonical": [
            {"$match": {"canonical_id": {"$exists": True, "$ne": None}}},
            {"$count": "n"},
        ],
    }


# ---------------------------------------------------------------------------- shaping


def _round1(value: float) -> float:
    return round(float(value), 1)


def _pct(part: float, whole: float) -> float:
    return _round1(part / whole * 100) if whole else 0.0


def _first(rows: list[dict], facet: str) -> dict:
    """First row of a ``$facet`` branch of the first output document, or ``{}``."""
    if not rows:
        return {}
    branch = rows[0].get(facet) or []
    return branch[0] if branch else {}


def _point(period: str, count: int, total: float) -> dict:
    return {
        "period": period,
        "contract_count": int(count),
        "total_value": float(total),
        "avg_value": float(total) / count if count else 0.0,
    }


def shape_summary(rows: list[dict], f: DashboardFilter) -> dict:
    """``Period`` read-model for one filter window."""
    totals = _first(rows, "totals")
    count = int(totals.get("count") or 0)
    total = float(totals.get("total") or 0.0)
    return {
        "date_from": f.date_from,
        "date_to": f.date_to,
        "contract_count": count,
        "total_value": total,
        "avg_value": total / count if count else 0.0,
        "procurer_count": int(_first(rows, "procurers").get("n") or 0),
        "supplier_count": int(_first(rows, "suppliers").get("n") or 0),
    }


def _split_label(split_by: str, key: str) -> str:
    if split_by == "source":
        return key
    return _NO_CPV_LABEL if key == NO_CPV else cpv_label_sk(key)


def shape_timeseries(
    rows: list[dict], f: DashboardFilter, granularity: str, split_by: str | None, top: int
) -> dict:
    """Zero-filled points (and split series) at the requested granularity."""
    periods = zero_filled_periods(f.date_from or "", f.date_to or "", granularity)
    # (key, period) -> [count, total]; key None is the grand total.
    cells: dict[tuple[str | None, str], list[float]] = {}
    key_value: dict[str, float] = {}
    for row in rows:
        rid = row["_id"]
        period = period_key(rid["period"], granularity)
        count, total = int(row.get("count") or 0), float(row.get("total") or 0.0)
        keys: list[str | None] = [None]
        if split_by is not None:
            key = rid.get("key") or (NO_CPV if split_by == "cpv_division" else "unknown")
            keys.append(key)
            key_value[key] = key_value.get(key, 0.0) + total
        for key in keys:
            cell = cells.setdefault((key, period), [0, 0.0])
            cell[0] += count
            cell[1] += total

    def points_for(key: str | None) -> list[dict]:
        return [_point(p, *(cells.get((key, p)) or (0, 0.0))) for p in periods]

    series = None
    if split_by is not None:
        ranked = sorted(key_value, key=lambda k: (-key_value[k], k))
        kept, folded = ranked[:top], ranked[top:]
        series = [
            {"key": k, "label": _split_label(split_by, k), "points": points_for(k)} for k in kept
        ]
        if folded:
            other_points = []
            for p in periods:
                count = sum(int((cells.get((k, p)) or (0, 0.0))[0]) for k in folded)
                total = sum(float((cells.get((k, p)) or (0, 0.0))[1]) for k in folded)
                other_points.append(_point(p, count, total))
            series.append({"key": "other", "label": _OTHER_LABEL, "points": other_points})
    return {"granularity": granularity, "points": points_for(None), "series": series}


def shape_top(rows: list[dict], dimension: str, metric: str, n: int) -> dict:
    """Ranked items with shares plus an ``other`` bucket for the remainder.

    ``share_pct`` is the share of the selected ``metric``. For ``supplier`` a notice
    with several distinct suppliers counts for each, so the items can exceed the
    total; ``other`` is clamped at zero in that case.
    """
    totals = _first(rows, "total")
    total_count = int(totals.get("count") or 0)
    total_value = float(totals.get("total") or 0.0)
    whole = total_value if metric == "total_value" else float(total_count)
    items = []
    for raw in (rows[0].get("items") or []) if rows else []:
        key = str(raw["_id"])
        value, count = float(raw.get("total") or 0.0), int(raw.get("count") or 0)
        if dimension == "cpv_division":
            label, ico = (_NO_CPV_LABEL if key == NO_CPV else cpv_label_sk(key)), None
        else:
            label, ico = (raw.get("name") or key), key
        items.append(
            {
                "key": key,
                "label": label,
                "ico": ico,
                "total_value": value,
                "contract_count": count,
                "share_pct": _pct(value if metric == "total_value" else count, whole),
            }
        )
    items = items[:n]
    other_value = max(total_value - sum(i["total_value"] for i in items), 0.0)
    other_count = max(total_count - sum(i["contract_count"] for i in items), 0)
    other_share = _round1(max(100.0 - sum(i["share_pct"] for i in items), 0.0)) if whole else 0.0
    return {
        "dimension": dimension,
        "metric": metric,
        "total": {"total_value": total_value, "contract_count": total_count},
        "items": items,
        "other": {
            "total_value": other_value,
            "contract_count": other_count,
            "share_pct": other_share,
        },
    }


def shape_concentration(rows: list[dict], dimension: str) -> dict:
    """HHI, concentration ratios and the cumulative top-10 curve."""
    totals = _first(rows, "totals")
    total = float(totals.get("total") or 0.0)
    sumsq = float(totals.get("sumsq") or 0.0)
    entity_count = int(totals.get("n") or 0)
    hhi_value = _round1(10_000.0 * sumsq / (total * total)) if total > 0 else 0.0

    top = []
    cumulative = 0.0
    top_values: list[float] = []
    for raw in (rows[0].get("top") or []) if rows else []:
        value = float(raw.get("total") or 0.0)
        cumulative += value
        top_values.append(value)
        ico = str(raw["_id"])
        top.append(
            {
                "ico": ico,
                "name": raw.get("name") or ico,
                "total_value": value,
                "share_pct": _pct(value, total),
                "cumulative_pct": _pct(cumulative, total),
            }
        )
    return {
        "dimension": dimension,
        "hhi": hhi_value,
        "hhi_band": hhi_band(hhi_value),
        "cr4_pct": _pct(sum(top_values[:4]), total),
        "cr10_pct": _pct(sum(top_values[:10]), total),
        "entity_count": entity_count,
        "total_value": total,
        "top": top,
    }


def shape_cpv(rows: list[dict], level: str) -> dict:
    """All CPV buckets sorted by value with shares."""
    total_value = sum(float(r.get("total") or 0.0) for r in rows)
    contract_count = sum(int(r.get("count") or 0) for r in rows)
    width = 2 if level == "division" else 3
    normalise = cpv_division if level == "division" else cpv_group
    items = []
    for raw in rows:
        code = normalise(str(raw["_id"]))
        value = float(raw.get("total") or 0.0)
        items.append(
            {
                "cpv_code": code,
                "prefix": code[:width],
                "label_sk": _NO_CPV_LABEL if code == NO_CPV else cpv_label_sk(code),
                "total_value": value,
                "contract_count": int(raw.get("count") or 0),
                "share_pct": _pct(value, total_value),
            }
        )
    items.sort(key=lambda i: (-i["total_value"], i["cpv_code"]))
    return {
        "level": level,
        "total_value": total_value,
        "contract_count": contract_count,
        "items": items,
    }


def coverage_since(now: datetime) -> str:
    """First ``YYYY-MM`` of the 24-month coverage window ending with ``now``'s month."""
    months = now.year * 12 + (now.month - 1) - (_COVERAGE_MONTHS - 1)
    return f"{months // 12:04d}-{months % 12 + 1:02d}"


def _parse_ts(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def shape_coverage(
    source_rows: list[dict],
    monthly_rows: list[dict],
    canonical_notices: int,
    match_groups: int,
    now: datetime,
) -> dict:
    """Per-source freshness/quality, a 24-month grid and the canonical-link totals.

    Quality percentages are over the source's ``contract_award`` notices, the rows
    the dashboards actually count.
    """
    by_source = {str(r["_id"]): r for r in source_rows}
    sources = []
    for source in SOURCES:
        raw = by_source.get(source, {})
        awards = int(raw.get("contract_awards") or 0)
        last_ingested = raw.get("last_ingested")
        parsed = _parse_ts(last_ingested)
        age = max((now - parsed).total_seconds(), 0.0) if parsed else None
        sources.append(
            {
                "source": source,
                "notices_total": int(raw.get("notices_total") or 0),
                "contract_awards": awards,
                "last_publication_date": raw.get("last_publication"),
                "last_ingested_at": last_ingested if parsed else None,
                "age_seconds": round(age, 1) if age is not None else None,
                "status": freshness_status(age, source),
                "expected_cadence_seconds": _CADENCE_SECONDS[source],
                "quality": {
                    "with_value_pct": _pct(raw.get("with_value") or 0, awards),
                    "with_cpv_pct": _pct(raw.get("with_cpv") or 0, awards),
                    "with_supplier_ico_pct": _pct(raw.get("with_supplier") or 0, awards),
                    "with_procurer_ico_pct": _pct(raw.get("with_procurer") or 0, awards),
                },
            }
        )

    counts: dict[tuple[str, str], int] = {}
    for row in monthly_rows:
        rid = row["_id"]
        counts[(rid["period"], rid["source"])] = int(row.get("count") or 0)
    start = coverage_since(now)
    first = int(start[:4]) * 12 + int(start[5:7]) - 1
    monthly = []
    for offset in range(_COVERAGE_MONTHS):
        idx = first + offset
        period = f"{idx // 12:04d}-{idx % 12 + 1:02d}"
        monthly.append({"period": period, **{s: counts.get((period, s), 0) for s in SOURCES}})

    return {
        "generated_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources,
        "monthly": monthly,
        "canonical": {
            "notices_with_canonical_id": int(canonical_notices),
            "match_groups": int(match_groups),
        },
    }


# ------------------------------------------------------------------ cached aggregates


async def _run(db, pipeline: list[dict]) -> list[dict]:
    cursor = db["notices"].aggregate(pipeline, maxTimeMS=_MAX_TIME_MS, allowDiskUse=True)
    return await cursor.to_list(None)


@async_ttl_cache(maxsize=_MAXSIZE, ttl=_TTL_SECONDS, key_from=lambda db, f: _make_key((f,), {}))
async def _summary_agg(db, f: DashboardFilter) -> list[dict]:
    return await _run(db, build_summary_pipeline(f))


@async_ttl_cache(
    maxsize=_MAXSIZE,
    ttl=_TTL_SECONDS,
    key_from=lambda db, f, granularity, split_by, top: _make_key(
        (f, granularity, split_by, top), {}
    ),
)
async def _timeseries_agg(
    db, f: DashboardFilter, granularity: str, split_by: str | None, top: int
) -> list[dict]:
    return await _run(db, build_timeseries_pipeline(f, granularity, split_by, top))


@async_ttl_cache(
    maxsize=_MAXSIZE,
    ttl=_TTL_SECONDS,
    key_from=lambda db, f, dimension, metric, n: _make_key((f, dimension, metric, n), {}),
)
async def _top_agg(db, f: DashboardFilter, dimension: str, metric: str, n: int) -> list[dict]:
    return await _run(db, build_top_pipeline(f, dimension, metric, n))


@async_ttl_cache(
    maxsize=_MAXSIZE,
    ttl=_TTL_SECONDS,
    key_from=lambda db, f, dimension: _make_key((f, dimension), {}),
)
async def _concentration_agg(db, f: DashboardFilter, dimension: str) -> list[dict]:
    return await _run(db, build_concentration_pipeline(f, dimension))


@async_ttl_cache(
    maxsize=_MAXSIZE, ttl=_TTL_SECONDS, key_from=lambda db, f, level: _make_key((f, level), {})
)
async def _cpv_agg(db, f: DashboardFilter, level: str) -> list[dict]:
    return await _run(db, build_cpv_pipeline(f, level))


@async_ttl_cache(maxsize=1, ttl=_TTL_SECONDS, key_from=lambda db: _make_key((), {}))
async def _coverage_agg(db) -> dict:
    """Raw coverage rows: per-source groups, monthly grid rows and canonical counts."""
    pipelines = build_coverage_pipelines(coverage_since(datetime.now(UTC)))
    sources, monthly, canonical, match_groups = await asyncio.gather(
        _run(db, pipelines["sources"]),
        _run(db, pipelines["monthly"]),
        _run(db, pipelines["canonical"]),
        db["cross_source_matches"].estimated_document_count(),
    )
    return {
        "sources": sources,
        "monthly": monthly,
        "canonical": int(canonical[0]["n"]) if canonical else 0,
        "match_groups": int(match_groups),
    }


class MongoDashboardAnalytics:
    """DashboardAnalytics port backed by MongoDB ``notices`` aggregations."""

    def __init__(self, db) -> None:
        self._db = db

    async def summary(self, f: DashboardFilter) -> dict:
        return shape_summary(await _summary_agg(self._db, f), f)

    async def timeseries(
        self, f: DashboardFilter, granularity: str, split_by: str | None, top: int
    ) -> dict:
        rows = await _timeseries_agg(self._db, f, granularity, split_by, top)
        return shape_timeseries(rows, f, granularity, split_by, top)

    async def top(self, f: DashboardFilter, dimension: str, metric: str, n: int) -> dict:
        return shape_top(await _top_agg(self._db, f, dimension, metric, n), dimension, metric, n)

    async def concentration(self, f: DashboardFilter, dimension: str) -> dict:
        return shape_concentration(await _concentration_agg(self._db, f, dimension), dimension)

    async def cpv(self, f: DashboardFilter, level: str) -> dict:
        return shape_cpv(await _cpv_agg(self._db, f, level), level)

    async def coverage(self) -> dict:
        raw = await _coverage_agg(self._db)
        return shape_coverage(
            raw["sources"], raw["monthly"], raw["canonical"], raw["match_groups"], datetime.now(UTC)
        )
