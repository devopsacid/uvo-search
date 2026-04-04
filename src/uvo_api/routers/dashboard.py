# src/uvo_api/routers/dashboard.py
"""Dashboard aggregation endpoints."""

import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    CpvShare,
    DashboardDelta,
    DashboardSummary,
    RecentContract,
    SpendByYear,
    TopProcurer,
    TopSupplier,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_CPV_LABELS: dict[str, dict[str, str]] = {}


def _load_cpv_labels() -> dict[str, dict[str, str]]:
    global _CPV_LABELS
    if not _CPV_LABELS:
        path = Path(__file__).parent.parent / "data" / "cpv_labels.json"
        _CPV_LABELS = json.loads(path.read_text())
    return _CPV_LABELS


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _cpv_prefix(code: str | None) -> str:
    """Normalize CPV code to 8-digit prefix for label lookup."""
    if not code:
        return "00000000"
    digits = code.replace("-", "").replace(" ", "")[:8]
    return digits.ljust(8, "0")


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> DashboardSummary:
    contract_args: dict = {"limit": 100}
    if ico and entity_type == "supplier":
        contract_args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        contract_args["procurer_id"] = ico

    contracts_result = await call_tool("search_completed_procurements", contract_args)
    contracts = contracts_result.get("data", [])
    total = contracts_result.get("total", len(contracts))

    total_value = sum(float(c.get("hodnota_zmluvy") or 0) for c in contracts)
    avg_value = total_value / len(contracts) if contracts else 0

    suppliers_result = await call_tool("find_supplier", {"limit": 1})
    active_suppliers = suppliers_result.get("total", 0)

    return DashboardSummary(
        total_value=total_value,
        contract_count=total,
        avg_value=avg_value,
        active_suppliers=active_suppliers,
        deltas={
            "total_value": DashboardDelta(value=0),
            "contract_count": DashboardDelta(value=0),
        },
    )


@router.get("/spend-by-year", response_model=list[SpendByYear])
async def spend_by_year(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[SpendByYear]:
    args: dict = {"limit": 100}
    if ico and entity_type == "supplier":
        args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        args["procurer_id"] = ico

    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("data", [])

    by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = _year_from_date(c.get("datum_zverejnenia"))
        if year > 0:
            by_year[year] += float(c.get("hodnota_zmluvy") or 0)

    return [SpendByYear(year=y, total_value=v) for y, v in sorted(by_year.items())]


@router.get("/top-suppliers", response_model=list[TopSupplier])
async def top_suppliers(
    n: int = Query(5, ge=1, le=20),
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[TopSupplier]:
    result = await call_tool("find_supplier", {"limit": n * 2})
    items = result.get("data", [])

    suppliers = [
        TopSupplier(
            ico=str(s.get("ico", "")),
            name=s.get("nazov", ""),
            total_value=float(s.get("celkova_hodnota") or 0),
            contract_count=int(s.get("pocet_zakaziek") or 0),
        )
        for s in items
    ]
    return sorted(suppliers, key=lambda x: x.total_value, reverse=True)[:n]


@router.get("/top-procurers", response_model=list[TopProcurer])
async def top_procurers(
    n: int = Query(5, ge=1, le=20),
) -> list[TopProcurer]:
    result = await call_tool("find_procurer", {"limit": n * 2})
    items = result.get("data", [])

    procurers = [
        TopProcurer(
            ico=str(p.get("ico", "")),
            name=p.get("nazov", ""),
            total_spend=float(p.get("celkova_hodnota") or 0),
            contract_count=int(p.get("pocet_zakaziek") or 0),
        )
        for p in items
    ]
    return sorted(procurers, key=lambda x: x.total_spend, reverse=True)[:n]


@router.get("/by-cpv", response_model=list[CpvShare])
async def by_cpv(
    ico: str | None = Query(None),
    entity_type: str | None = Query(None),
) -> list[CpvShare]:
    args: dict = {"limit": 100}
    if ico and entity_type == "supplier":
        args["supplier_ico"] = ico
    elif ico and entity_type == "procurer":
        args["procurer_id"] = ico

    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("data", [])
    labels = _load_cpv_labels()

    by_cpv: dict[str, float] = defaultdict(float)
    for c in contracts:
        prefix = _cpv_prefix(c.get("cpv_kod"))
        by_cpv[prefix] += float(c.get("hodnota_zmluvy") or 0)

    total = sum(by_cpv.values()) or 1
    shares = []
    for code, value in sorted(by_cpv.items(), key=lambda x: x[1], reverse=True):
        label = labels.get(code, {"sk": code, "en": code})
        shares.append(CpvShare(
            cpv_code=code,
            label_sk=label.get("sk", code),
            label_en=label.get("en", code),
            total_value=value,
            percentage=round(value / total * 100, 1),
        ))
    return shares


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

    result = await call_tool("search_completed_procurements", args)
    contracts = result.get("data", [])

    return [
        RecentContract(
            id=str(c.get("id", "")),
            title=c.get("nazov", ""),
            procurer_name=(c.get("obstaravatel") or {}).get("nazov", ""),
            procurer_ico=(c.get("obstaravatel") or {}).get("ico", ""),
            value=float(c.get("hodnota_zmluvy") or 0),
            year=_year_from_date(c.get("datum_zverejnenia")),
            status=_status_from_year(_year_from_date(c.get("datum_zverejnenia"))),
        )
        for c in contracts
    ]
