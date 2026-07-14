# src/uvo_api/routers/dashboard.py
"""Dashboard aggregation endpoints.

Summary / spend-by-year / by-cpv / by-month compute over the **full corpus** via
server-side Mongo aggregations (CompanyAnalytics port). They previously
aggregated a 500-doc MCP-paged sample, which silently truncated every number
(plan §1.3.2). Response shapes are unchanged — the React GUI depends on them.
"""

import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Query

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.db import get_analytics
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
from uvo_api.services import run_query

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

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


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> DashboardSummary:
    analytics = get_analytics()
    year_rows = await analytics.spend_by_year(ico, entity_type)

    total_value = sum(float(r.get("total") or 0.0) for r in year_rows)
    contract_count = sum(int(r.get("count") or 0) for r in year_rows)
    avg_value = total_value / contract_count if contract_count else 0.0

    suppliers_result = await run_query("find_supplier", {"limit": 1})
    active_suppliers = int(suppliers_result.get("total") or 0)
    procurers_result = await run_query("find_procurer", {"limit": 1})
    active_procurers = int(procurers_result.get("total") or 0)

    # Per-year comparison against the previous year, over the full corpus.
    valid = [(year_from_date(str(r.get("_id"))), r) for r in year_rows]
    valid = sorted((y, r) for y, r in valid if y > 0)

    deltas: dict[str, DashboardDelta] = {
        "total_value": DashboardDelta(value=0, pct=None),
        "contract_count": DashboardDelta(value=0, pct=None),
        "avg_value": DashboardDelta(value=0, pct=None),
        "active_suppliers": DashboardDelta(value=0, pct=None),
    }
    if len(valid) >= 2:
        (_, prev_r), (_, cur_r) = valid[-2], valid[-1]
        cur_sum, prev_sum = float(cur_r.get("total") or 0), float(prev_r.get("total") or 0)
        cur_cnt, prev_cnt = int(cur_r.get("count") or 0), int(prev_r.get("count") or 0)
        if prev_sum:
            deltas["total_value"] = DashboardDelta(
                value=cur_sum - prev_sum, pct=round((cur_sum - prev_sum) / prev_sum * 100, 1)
            )
        if prev_cnt:
            deltas["contract_count"] = DashboardDelta(
                value=cur_cnt - prev_cnt,
                pct=round((cur_cnt - prev_cnt) / prev_cnt * 100, 1),
            )
            cur_avg = cur_sum / cur_cnt if cur_cnt else 0
            prev_avg = prev_sum / prev_cnt if prev_cnt else 0
            if prev_avg:
                deltas["avg_value"] = DashboardDelta(
                    value=cur_avg - prev_avg,
                    pct=round((cur_avg - prev_avg) / prev_avg * 100, 1),
                )

    return DashboardSummary(
        total_value=total_value,
        contract_count=contract_count,
        avg_value=avg_value,
        active_suppliers=active_suppliers or active_procurers,
        deltas=deltas,
    )


@router.get("/spend-by-year", response_model=list[SpendByYear])
async def spend_by_year(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[SpendByYear]:
    rows = await get_analytics().spend_by_year(ico, entity_type)

    by_year: dict[int, float] = {}
    for r in rows:
        year = year_from_date(str(r.get("_id")))
        if year > 0:
            by_year[year] = by_year.get(year, 0.0) + float(r.get("total") or 0.0)

    return [SpendByYear(year=y, total_value=v) for y, v in sorted(by_year.items())]


@router.get("/top-suppliers", response_model=list[TopSupplier])
async def top_suppliers(
    n: int = Query(10, ge=1, le=20),
) -> list[TopSupplier]:
    rows = await get_analytics().top_suppliers(n)
    return [
        TopSupplier(
            ico=str(r["_id"]),
            name=str(r.get("name") or ""),
            total_value=float(r["total_value"]),
            contract_count=int(r["contract_count"]),
        )
        for r in rows
    ]


@router.get("/top-procurers", response_model=list[TopProcurer])
async def top_procurers(
    n: int = Query(10, ge=1, le=20),
) -> list[TopProcurer]:
    rows = await get_analytics().top_procurers(n)
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
    rows = await get_analytics().cpv_breakdown(ico, entity_type, year_from, year_to)
    labels = _load_cpv_labels()

    buckets: dict[str, float] = defaultdict(float)
    for r in rows:
        buckets[_cpv_prefix(r.get("_id"))] += float(r.get("total") or 0.0)

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
    """Monthly contract count + value for a given year, over the full corpus."""
    rows = await get_analytics().monthly_buckets(year)
    by_m = {int(r["_id"]): r for r in rows if r.get("_id") is not None}

    return [
        MonthBucket(
            month=m,
            contract_count=int(by_m.get(m, {}).get("count", 0)),
            total_value=float(by_m.get(m, {}).get("total", 0.0)),
        )
        for m in range(1, 13)
    ]


@router.get("/recent", response_model=list[RecentContract])
async def recent_contracts(
    limit: int = Query(10, ge=1, le=50),
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[RecentContract]:
    args: dict = {"limit": limit}
    if ico and entity_type == "supplier":
        args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        args["procurer_id"] = ico
    result = await run_query("search_completed_procurements", args)
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
