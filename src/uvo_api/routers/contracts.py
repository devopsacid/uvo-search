# src/uvo_api/routers/contracts.py
"""Contracts endpoints — list and detail."""

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import map_contract_detail, map_contract_row
from uvo_api.mcp_client import call_tool
from uvo_api.models import ContractDetail, ContractListResponse, PaginationMeta

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    q: str | None = Query(None),
    cpv: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    value_min: float | None = Query(None),
    value_max: float | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ContractListResponse:
    args: dict = {"limit": limit, "offset": offset}
    if q:
        args["text_query"] = q
    if cpv:
        args["cpv_codes"] = [cpv]
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    if ico:
        args["supplier_ico"] = ico

    result = await call_tool("search_completed_procurements", args)

    items = result.get("items", [])
    total = result.get("total", len(items))

    rows = [map_contract_row(i) for i in items]
    if value_min is not None:
        rows = [r for r in rows if r.value >= value_min]
    if value_max is not None:
        rows = [r for r in rows if r.value <= value_max]
    if value_min is not None or value_max is not None:
        total = len(rows)

    return ContractListResponse(
        data=rows,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(contract_id: str) -> ContractDetail:
    result = await call_tool("get_procurement_detail", {"procurement_id": contract_id})
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])

    return map_contract_detail(result)
