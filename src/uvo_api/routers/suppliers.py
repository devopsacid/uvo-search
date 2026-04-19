# src/uvo_api/routers/suppliers.py
"""Suppliers endpoints."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import contract_date, contract_value, map_contract_row, year_from_date
from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    ContractRow,
    PaginationMeta,
    ProcurerRelation,
    SpendByYear,
    SupplierCard,
    SupplierDetail,
    SupplierListResponse,
    SupplierSummary,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    q: str | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SupplierListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if q:
        args["name_query"] = q
    if ico:
        args["ico"] = ico

    result = await call_tool("find_supplier", args)
    items = result.get("items", [])
    total = int(result.get("total") or len(items))

    cards = [
        SupplierCard(
            ico=str(s.get("ico") or ""),
            name=s.get("name") or "",
            contract_count=int(s.get("contract_count") or 0),
            total_value=float(s.get("total_value") or 0),
        )
        for s in items
    ]
    return SupplierListResponse(
        data=cards,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


async def _fetch_supplier_and_contracts(ico: str) -> tuple[dict, list[dict]]:
    supplier_result = await call_tool("find_supplier", {"ico": ico, "limit": 1})
    suppliers = supplier_result.get("items", [])
    if not suppliers:
        raise HTTPException(status_code=404, detail=f"Supplier {ico} not found")
    supplier = suppliers[0]

    contracts_result = await call_tool(
        "search_completed_procurements", {"supplier_ico": ico, "limit": 100}
    )
    contracts = contracts_result.get("items", [])
    return supplier, contracts


@router.get("/{ico}/summary", response_model=SupplierSummary)
async def get_supplier_summary(ico: str) -> SupplierSummary:
    supplier, contracts = await _fetch_supplier_and_contracts(ico)

    spend_by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = year_from_date(contract_date(c))
        spend_by_year[year] += contract_value(c)

    total_value = float(supplier.get("total_value") or sum(spend_by_year.values()))
    count = int(supplier.get("contract_count") or len(contracts))

    return SupplierSummary(
        ico=str(supplier.get("ico") or ico),
        name=supplier.get("name") or "",
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        spend_by_year=[
            SpendByYear(year=y, total_value=v) for y, v in sorted(spend_by_year.items()) if y > 0
        ],
    )


@router.get("/{ico}", response_model=SupplierDetail)
async def get_supplier_detail(ico: str) -> SupplierDetail:
    supplier, contracts = await _fetch_supplier_and_contracts(ico)

    procurer_totals: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "value": 0.0})
    years: set[int] = set()
    rows: list[ContractRow] = []

    for c in contracts:
        row = map_contract_row(c)
        rows.append(row)
        years.add(row.year)
        if row.procurer_ico:
            p = procurer_totals[row.procurer_ico]
            p["name"] = row.procurer_name
            p["count"] += 1
            p["value"] += row.value

    top_procurers = sorted(
        [
            ProcurerRelation(
                ico=k, name=v["name"], contract_count=v["count"], total_value=v["value"]
            )
            for k, v in procurer_totals.items()
        ],
        key=lambda x: x.total_value,
        reverse=True,
    )[:10]

    total_value = float(supplier.get("total_value") or sum(r.value for r in rows))
    count = int(supplier.get("contract_count") or len(rows))

    return SupplierDetail(
        ico=str(supplier.get("ico") or ico),
        name=supplier.get("name") or "",
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        years_active=sorted(y for y in years if y > 0),
        top_procurers=top_procurers,
        contracts=rows,
    )
