# src/uvo_api/routers/dashboard.py
"""Dashboard aggregation endpoints."""

import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Query

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.db import get_db
from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    CpvShare,
    DashboardDelta,
    DashboardSummary,
    MonthBucket,
    RecentContract,
    SpendByYear,
    TopProcurer,
    TopSupplier,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# MCP search tools cap results at 100 per call; fetch a larger slice for
# aggregations by paging through the cap.
_AGG_PAGE = 100
_AGG_PAGES = 5

_CPV_LABELS: dict[str, dict[str, str]] = {}


def _load_cpv_labels() -> dict[str, dict[str, str]]:
    global _CPV_LABELS
    if not _CPV_LABELS:
        path = Path(__file__).parent.parent / "data" / "cpv_labels.json"
        _CPV_LABELS = json.loads(path.read_text(encoding="utf-8"))
    return _CPV_LABELS


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _cpv_prefix(code: str | None) -> str:
    if not code:
        return "00000000"
    digits = code.replace("-", "").replace(" ", "")[:8]
    return digits.ljust(8, "0")


async def _fetch_contracts_sample(ico_filter: dict) -> tuple[list[dict], int]:
    """Fetch up to _AGG_PAGES * _AGG_PAGE contracts, plus the reported total."""
    collected: list[dict] = []
    total = 0
    for page in range(_AGG_PAGES):
        args = {"limit": _AGG_PAGE, "offset": page * _AGG_PAGE, **ico_filter}
        result = await call_tool("search_completed_procurements", args)
        items = result.get("items", [])
        total = max(total, int(result.get("total") or 0))
        if not items:
            break
        collected.extend(items)
        if len(items) < _AGG_PAGE:
            break
    return collected, total or len(collected)


def _ico_filter(ico: str | None, entity_type: str | None) -> dict:
    if not ico:
        return {}
    if entity_type == "supplier":
        return {"supplier_ico": ico}
    if entity_type == "procurer":
        return {"procurer_id": ico}
    return {}


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> DashboardSummary:
    flt = _ico_filter(ico, entity_type)
    contracts, total = await _fetch_contracts_sample(flt)

    values = [contract_value(c) for c in contracts]
    total_value = sum(values)
    avg_value = total_value / len(values) if values else 0.0

    suppliers_result = await call_tool("find_supplier", {"limit": 1})
    active_suppliers = int(suppliers_result.get("total") or 0)
    procurers_result = await call_tool("find_procurer", {"limit": 1})
    active_procurers = int(procurers_result.get("total") or 0)

    # Per-year comparison against the previous year (within the sampled slice).
    by_year: dict[int, list[float]] = defaultdict(list)
    for c, v in zip(contracts, values):
        y = year_from_date(contract_date(c))
        if y > 0:
            by_year[y].append(v)

    years_sorted = sorted(by_year.keys())
    deltas: dict[str, DashboardDelta] = {
        "total_value": DashboardDelta(value=0, pct=None),
        "contract_count": DashboardDelta(value=0, pct=None),
        "avg_value": DashboardDelta(value=0, pct=None),
        "active_suppliers": DashboardDelta(value=0, pct=None),
    }
    if len(years_sorted) >= 2:
        last, prev = years_sorted[-1], years_sorted[-2]
        cur_vals, prev_vals = by_year[last], by_year[prev]
        cur_sum, prev_sum = sum(cur_vals), sum(prev_vals)
        if prev_sum:
            deltas["total_value"] = DashboardDelta(
                value=cur_sum - prev_sum, pct=round((cur_sum - prev_sum) / prev_sum * 100, 1)
            )
        if len(prev_vals):
            deltas["contract_count"] = DashboardDelta(
                value=len(cur_vals) - len(prev_vals),
                pct=round((len(cur_vals) - len(prev_vals)) / len(prev_vals) * 100, 1),
            )
            cur_avg = cur_sum / len(cur_vals) if cur_vals else 0
            prev_avg = prev_sum / len(prev_vals) if prev_vals else 0
            if prev_avg:
                deltas["avg_value"] = DashboardDelta(
                    value=cur_avg - prev_avg,
                    pct=round((cur_avg - prev_avg) / prev_avg * 100, 1),
                )

    return DashboardSummary(
        total_value=total_value,
        contract_count=total,
        avg_value=avg_value,
        active_suppliers=active_suppliers or active_procurers,
        deltas=deltas,
    )


@router.get("/spend-by-year", response_model=list[SpendByYear])
async def spend_by_year(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[SpendByYear]:
    flt = _ico_filter(ico, entity_type)
    contracts, _ = await _fetch_contracts_sample(flt)

    by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = year_from_date(contract_date(c))
        if year > 0:
            by_year[year] += contract_value(c)

    return [SpendByYear(year=y, total_value=v) for y, v in sorted(by_year.items())]


@router.get("/top-suppliers", response_model=list[TopSupplier])
async def top_suppliers(
    n: int = Query(10, ge=1, le=20),
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[TopSupplier]:
    # Prefer the entity tool when available; fall back to aggregation over contracts.
    result = await call_tool("find_supplier", {"limit": n * 2})
    items = result.get("items", [])
    if items:
        suppliers = [
            TopSupplier(
                ico=str(s.get("ico") or ""),
                name=s.get("name") or "",
                total_value=float(s.get("total_value") or 0),
                contract_count=int(s.get("contract_count") or 0),
            )
            for s in items
        ]
        return sorted(suppliers, key=lambda x: x.total_value, reverse=True)[:n]

    # Fallback: aggregate by first supplier in awards from contract sample.
    contracts, _ = await _fetch_contracts_sample(_ico_filter(ico, entity_type))
    agg: dict[str, dict] = defaultdict(lambda: {"name": "", "value": 0.0, "count": 0})
    for c in contracts:
        awards = c.get("awards") or []
        if not awards:
            continue
        a = awards[0]
        key = str(a.get("supplier_ico") or a.get("ico") or "")
        if not key:
            continue
        agg[key]["name"] = a.get("supplier_name") or a.get("name") or agg[key]["name"]
        agg[key]["value"] += contract_value(c)
        agg[key]["count"] += 1
    items2 = sorted(
        [
            TopSupplier(ico=k, name=v["name"], total_value=v["value"], contract_count=v["count"])
            for k, v in agg.items()
        ],
        key=lambda x: x.total_value,
        reverse=True,
    )[:n]
    return items2


@router.get("/top-procurers", response_model=list[TopProcurer])
async def top_procurers(
    n: int = Query(10, ge=1, le=20),
) -> list[TopProcurer]:
    db = get_db()
    pipeline = [
        {"$match": {"procurer.ico": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$procurer.ico",
                "total_value": {"$sum": {"$ifNull": ["$final_value", 0]}},
                "contract_count": {"$sum": 1},
                "name": {"$first": "$procurer.name"},
            }
        },
        {"$sort": {"total_value": -1}},
        {"$limit": n},
    ]
    rows = await db["notices"].aggregate(pipeline).to_list(n)
    return [
        TopProcurer(
            ico=str(r["_id"]),
            name=str(r.get("name") or ""),
            total_spend=float(r["total_value"]),
            contract_count=int(r["contract_count"]),
        )
        for r in rows
    ]


@router.get("/by-cpv", response_model=list[CpvShare])
async def by_cpv(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
) -> list[CpvShare]:
    contracts, _ = await _fetch_contracts_sample(_ico_filter(ico, entity_type))
    labels = _load_cpv_labels()

    buckets: dict[str, float] = defaultdict(float)
    for c in contracts:
        if year_from is not None or year_to is not None:
            year = year_from_date(contract_date(c))
            if year_from is not None and year < year_from:
                continue
            if year_to is not None and year > year_to:
                continue
        prefix = _cpv_prefix(c.get("cpv_code"))
        buckets[prefix] += contract_value(c)

    total = sum(buckets.values()) or 1
    shares = []
    for code, value in sorted(buckets.items(), key=lambda x: x[1], reverse=True):
        label = labels.get(code, {"sk": code, "en": code})
        shares.append(
            CpvShare(
                cpv_code=code,
                label_sk=label.get("sk", code),
                label_en=label.get("en", code),
                total_value=value,
                percentage=round(value / total * 100, 1),
            )
        )
    return shares


@router.get("/by-month", response_model=list[MonthBucket])
async def by_month(
    year: int = Query(..., ge=2010, le=2100),
) -> list[MonthBucket]:
    """Monthly contract count + value for a given year."""
    contracts, _ = await _fetch_contracts_sample({})

    counts: dict[int, int] = defaultdict(int)
    values: dict[int, float] = defaultdict(float)

    for c in contracts:
        date_str = contract_date(c)
        if not date_str or len(date_str) < 7:
            continue
        try:
            c_year = int(date_str[:4])
            c_month = int(date_str[5:7])
        except ValueError:
            continue
        if c_year != year:
            continue
        counts[c_month] += 1
        values[c_month] += contract_value(c)

    return [
        MonthBucket(month=m, contract_count=counts.get(m, 0), total_value=values.get(m, 0.0))
        for m in range(1, 13)
    ]


@router.get("/recent", response_model=list[RecentContract])
async def recent_contracts(
    limit: int = Query(10, ge=1, le=50),
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[RecentContract]:
    args: dict = {"limit": limit, **_ico_filter(ico, entity_type)}
    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("items", [])

    rows: list[RecentContract] = []
    for c in contracts:
        year = year_from_date(contract_date(c))
        procurer = c.get("procurer") or {}
        rows.append(
            RecentContract(
                id=str(c.get("_id") or c.get("id") or ""),
                title=c.get("title") or "",
                procurer_name=procurer.get("name") or "",
                procurer_ico=procurer.get("ico") or "",
                value=contract_value(c),
                year=year,
                status=c.get("status") or _status_from_year(year),
            )
        )
    return rows
