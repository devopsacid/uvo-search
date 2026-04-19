# src/uvo_api/routers/procurers.py
"""Procurers endpoints."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import contract_date, contract_value, map_contract_row, year_from_date
from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    ContractRow,
    PaginationMeta,
    ProcurerCard,
    ProcurerDetail,
    ProcurerListResponse,
    ProcurerSummary,
    SpendByYear,
    SupplierRelation,
)

router = APIRouter(prefix="/api/procurers", tags=["procurers"])


@router.get("", response_model=ProcurerListResponse)
async def list_procurers(
    q: str | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ProcurerListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if q:
        args["name_query"] = q
    if ico:
        args["ico"] = ico

    result = await call_tool("find_procurer", args)
    items = result.get("items", [])
    total = int(result.get("total") or len(items))

    cards = [
        ProcurerCard(
            ico=str(p.get("ico") or ""),
            name=p.get("name") or "",
            contract_count=int(p.get("contract_count") or 0),
            total_spend=float(p.get("total_value") or 0),
        )
        for p in items
    ]
    return ProcurerListResponse(
        data=cards,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


async def _fetch_procurer_and_contracts(ico: str) -> tuple[dict, list[dict]]:
    procurer_result = await call_tool("find_procurer", {"ico": ico, "limit": 1})
    procurers = procurer_result.get("items", [])
    if not procurers:
        raise HTTPException(status_code=404, detail=f"Procurer {ico} not found")
    procurer = procurers[0]

    contracts_result = await call_tool(
        "search_completed_procurements", {"procurer_id": ico, "limit": 100}
    )
    contracts = contracts_result.get("items", [])
    return procurer, contracts


@router.get("/{ico}/summary", response_model=ProcurerSummary)
async def get_procurer_summary(ico: str) -> ProcurerSummary:
    procurer, contracts = await _fetch_procurer_and_contracts(ico)

    spend_by_year: dict[int, float] = defaultdict(float)
    for c in contracts:
        year = year_from_date(contract_date(c))
        spend_by_year[year] += contract_value(c)

    total_spend = float(procurer.get("total_value") or sum(spend_by_year.values()))
    count = int(procurer.get("contract_count") or len(contracts))

    return ProcurerSummary(
        ico=str(procurer.get("ico") or ico),
        name=procurer.get("name") or "",
        contract_count=count,
        total_spend=total_spend,
        avg_value=total_spend / count if count else 0,
        spend_by_year=[
            SpendByYear(year=y, total_value=v) for y, v in sorted(spend_by_year.items()) if y > 0
        ],
    )


@router.get("/{ico}", response_model=ProcurerDetail)
async def get_procurer_detail(ico: str) -> ProcurerDetail:
    procurer, contracts = await _fetch_procurer_and_contracts(ico)

    supplier_totals: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "value": 0.0})
    years: set[int] = set()
    rows: list[ContractRow] = []

    for c in contracts:
        row = map_contract_row(c)
        rows.append(row)
        years.add(row.year)
        if row.supplier_ico:
            s = supplier_totals[row.supplier_ico]
            s["name"] = row.supplier_name or ""
            s["count"] += 1
            s["value"] += row.value

    top_suppliers = sorted(
        [
            SupplierRelation(
                ico=k, name=v["name"], contract_count=v["count"], total_value=v["value"]
            )
            for k, v in supplier_totals.items()
        ],
        key=lambda x: x.total_value,
        reverse=True,
    )[:10]

    total_spend = float(procurer.get("total_value") or sum(r.value for r in rows))
    count = int(procurer.get("contract_count") or len(rows))

    return ProcurerDetail(
        ico=str(procurer.get("ico") or ico),
        name=procurer.get("name") or "",
        contract_count=count,
        total_spend=total_spend,
        avg_value=total_spend / count if count else 0,
        years_active=sorted(y for y in years if y > 0),
        top_suppliers=top_suppliers,
        contracts=rows,
    )
