# src/uvo_api/routers/contracts.py
"""Contracts endpoints — list and detail."""

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import map_contract_detail, map_contract_row
from uvo_api.db import get_notice_repo
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
    supplier_ico: str | None = Query(None),
    procurer_ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ContractListResponse:
    # `ico` is legacy; prefer explicit supplier_ico / procurer_ico.
    eff_supplier = supplier_ico or ico
    result = await get_notice_repo().search(
        text_query=q or None,
        cpv_codes=[cpv] if cpv else None,
        procurer_id=procurer_ico,
        supplier_ico=eff_supplier,
        date_from=date_from,
        date_to=date_to,
        value_min=value_min,
        value_max=value_max,
        limit=limit,
        offset=offset,
    )

    items = result.get("items", [])
    total = result.get("total", len(items))
    rows = [map_contract_row(i) for i in items]

    return ContractListResponse(
        data=rows,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(contract_id: str) -> ContractDetail:
    result = await get_notice_repo().get_by_source_id(contract_id)
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])

    return map_contract_detail(result)
