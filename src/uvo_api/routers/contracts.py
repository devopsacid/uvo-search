# src/uvo_api/routers/contracts.py
"""Contracts endpoints — list and detail."""

from fastapi import APIRouter, HTTPException, Query

from uvo_api.mcp_client import call_tool
from uvo_api.models import ContractDetail, ContractListResponse, ContractRow, PaginationMeta

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


def _year_from_date(date_str: str | None) -> int:
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return 0


def _status_from_year(year: int) -> str:
    return "active" if year >= 2024 else "closed"


def _map_row(item: dict) -> ContractRow:
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

    items = result.get("data", [])
    total = result.get("total", len(items))

    rows = [_map_row(i) for i in items]
    if value_min is not None:
        rows = [r for r in rows if r.value >= value_min]
    if value_max is not None:
        rows = [r for r in rows if r.value <= value_max]

    return ContractListResponse(
        data=rows,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(contract_id: str) -> ContractDetail:
    result = await call_tool("get_procurement_detail", {"procurement_id": contract_id})
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 404), detail=result["error"])

    suppliers = result.get("dodavatelia") or []
    first = suppliers[0] if suppliers else {}
    year = _year_from_date(result.get("datum_zverejnenia"))

    return ContractDetail(
        id=str(result.get("id", "")),
        title=result.get("nazov", ""),
        procurer_name=(result.get("obstaravatel") or {}).get("nazov", ""),
        procurer_ico=(result.get("obstaravatel") or {}).get("ico", ""),
        supplier_name=first.get("nazov"),
        supplier_ico=first.get("ico"),
        value=float(result.get("hodnota_zmluvy") or 0),
        cpv_code=result.get("cpv_kod"),
        year=year,
        status=_status_from_year(year),
        all_suppliers=suppliers,
        publication_date=result.get("datum_zverejnenia"),
    )
