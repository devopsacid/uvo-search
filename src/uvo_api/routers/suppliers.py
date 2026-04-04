# src/uvo_api/routers/suppliers.py
"""Suppliers endpoints."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

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


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _map_contract_row(item: dict) -> ContractRow:
    suppliers = item.get("dodavatelia") or []
    first = suppliers[0] if suppliers else {}
    year = _year_from_date(item.get("datum_zverejnenia"))
    return ContractRow(
        id=str(item.get("id", "")),
        title=item.get("nazov", ""),
        procurer_name=(item.get("obstaravatel") or {}).get("nazov", ""),
        procurer_ico=(item.get("obstaravatel") or {}).get("ico", ""),
        supplier_name=first.get("nazov"),
        supplier_ico=first.get("ico"),
        value=float(item.get("hodnota_zmluvy") or 0),
        cpv_code=item.get("cpv_kod"),
        year=year,
        status=_status_from_year(year),
    )


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
    items = result.get("data", [])
    total = result.get("total", len(items))

    cards = [
        SupplierCard(
            ico=str(s.get("ico", "")),
            name=s.get("nazov", ""),
            contract_count=int(s.get("pocet_zakaziek") or 0),
            total_value=float(s.get("celkova_hodnota") or 0),
        )
        for s in items
    ]
    return SupplierListResponse(
        data=cards,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


async def _fetch_supplier_and_contracts(ico: str) -> tuple[dict, list[dict]]:
    supplier_result = await call_tool("find_supplier", {"ico": ico, "limit": 1})
    suppliers = supplier_result.get("data", [])
    if not suppliers:
        raise HTTPException(status_code=404, detail=f"Supplier {ico} not found")
    supplier = suppliers[0]

    contracts_result = await call_tool(
        "search_completed_procurements", {"supplier_ico": ico, "limit": 100}
    )
    contracts = contracts_result.get("data", [])
    return supplier, contracts


@router.get("/{ico}/summary", response_model=SupplierSummary)
async def get_supplier_summary(ico: str) -> SupplierSummary:
    supplier, contracts = await _fetch_supplier_and_contracts(ico)

    spend_by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = _year_from_date(c.get("datum_zverejnenia"))
        spend_by_year[year] += float(c.get("hodnota_zmluvy") or 0)

    total_value = float(supplier.get("celkova_hodnota") or sum(spend_by_year.values()))
    count = int(supplier.get("pocet_zakaziek") or len(contracts))

    return SupplierSummary(
        ico=str(supplier.get("ico", ico)),
        name=supplier.get("nazov", ""),
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        spend_by_year=[
            SpendByYear(year=y, total_value=v) for y, v in sorted(spend_by_year.items())
        ],
    )


@router.get("/{ico}", response_model=SupplierDetail)
async def get_supplier_detail(ico: str) -> SupplierDetail:
    supplier, contracts = await _fetch_supplier_and_contracts(ico)

    procurer_totals: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "value": 0.0})
    years: set[int] = set()
    rows: list[ContractRow] = []

    for c in contracts:
        row = _map_contract_row(c)
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

    total_value = float(supplier.get("celkova_hodnota") or sum(r.value for r in rows))
    count = int(supplier.get("pocet_zakaziek") or len(rows))

    return SupplierDetail(
        ico=str(supplier.get("ico", ico)),
        name=supplier.get("nazov", ""),
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        years_active=sorted(y for y in years if y > 0),
        top_procurers=top_procurers,
        contracts=rows,
    )
