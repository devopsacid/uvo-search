"""Public /v1 company endpoints — search, core record, procurement profile."""

import asyncio

from fastapi import APIRouter, Query

from uvo_api.db import get_db
from uvo_api.mcp_client import call_tool
from uvo_api.routers._agg import _firma_core_agg, _firma_partners_agg
from uvo_api.routers.dashboard import _cpv_prefix, _load_cpv_labels
from uvo_api.routers.v1._common import decode_cursor, next_pagination
from uvo_api.routers.v1.models import (
    CompanyCard,
    CompanyListResponse,
    CompanyProfile,
    CompanyProfileResponse,
    CompanyRecord,
    CompanyRecordResponse,
    Counterparty,
    CpvBreakdownRow,
    Pagination,
    SpendYear,
)
from uvo_api.v1_errors import ApiV1Error

router = APIRouter(prefix="/companies", tags=["companies"])

# find_supplier / find_procurer cap at 100 rows; we merge + slice a page from that.
_MERGE_FETCH = 100

_EMPTY: dict = {"items": []}


async def _empty() -> dict:
    return _EMPTY


def _merge_companies(suppliers: list[dict], procurers: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in suppliers:
        ico = item.get("ico") or ""
        if not ico:
            continue
        merged[ico] = {
            "ico": ico,
            "name": item.get("name") or "",
            "roles": ["supplier"],
            "contract_count": int(item.get("contract_count") or 0),
            "total_value": float(item.get("total_value") or 0.0),
        }
    for item in procurers:
        ico = item.get("ico") or ""
        if not ico:
            continue
        if ico in merged:
            merged[ico]["roles"].append("procurer")
            merged[ico]["contract_count"] += int(item.get("contract_count") or 0)
            merged[ico]["total_value"] += float(item.get("total_value") or 0.0)
        else:
            merged[ico] = {
                "ico": ico,
                "name": item.get("name") or "",
                "roles": ["procurer"],
                "contract_count": int(item.get("contract_count") or 0),
                "total_value": float(item.get("total_value") or 0.0),
            }
    return sorted(merged.values(), key=lambda x: x["contract_count"], reverse=True)


@router.get("", response_model=CompanyListResponse)
async def search_companies(
    q: str | None = Query(None, description="Company name fragment."),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> CompanyListResponse:
    """Search suppliers and procurers by name, merged into a single company view."""
    offset = decode_cursor(cursor)
    args: dict = {"limit": _MERGE_FETCH}
    if q:
        args["name_query"] = q

    supplier_result, procurer_result = await asyncio.gather(
        call_tool("find_supplier", args),
        call_tool("find_procurer", args),
    )
    merged = _merge_companies(
        supplier_result.get("items", []),
        procurer_result.get("items", []),
    )
    total = len(merged)
    page = merged[offset : offset + limit]

    return CompanyListResponse(
        data=[CompanyCard(**c) for c in page],
        pagination=next_pagination(offset, limit, len(page), total),
    )


@router.get("/{ico}", response_model=CompanyRecordResponse)
async def get_company(ico: str) -> CompanyRecordResponse:
    """Core identity record for a company by ICO."""
    supplier_result, procurer_result = await asyncio.gather(
        call_tool("find_supplier", {"ico": ico, "limit": 1}),
        call_tool("find_procurer", {"ico": ico, "limit": 1}),
    )
    supplier_items = supplier_result.get("items", [])
    procurer_items = procurer_result.get("items", [])
    if not supplier_items and not procurer_items:
        raise ApiV1Error(404, "company_not_found", f"No company found for ICO {ico}.")

    roles: list[str] = []
    if supplier_items:
        roles.append("supplier")
    if procurer_items:
        roles.append("procurer")
    name = (supplier_items or procurer_items)[0].get("name") or ""

    return CompanyRecordResponse(data=CompanyRecord(ico=ico, name=name, roles=roles))


def _cpv_breakdown(rows: list[dict]) -> tuple[list[CpvBreakdownRow], float]:
    labels = _load_cpv_labels()
    total = sum(float(r.get("total") or 0.0) for r in rows) or 1.0
    breakdown: list[CpvBreakdownRow] = []
    hhi = 0.0
    for r in rows:
        code = _cpv_prefix(r.get("_id"))
        value = float(r.get("total") or 0.0)
        share = value / total
        hhi += share * share
        breakdown.append(
            CpvBreakdownRow(
                code=code,
                label=labels.get(code, {}).get("sk") or code,
                contract_count=int(r.get("count") or 0),
                total_value=value,
                share=round(share * 100, 1),
            )
        )
    return breakdown, round(hhi, 4)


@router.get("/{ico}/profile", response_model=CompanyProfileResponse)
async def get_company_profile(ico: str) -> CompanyProfileResponse:
    """Flagship procurement profile: totals, spend by year, counterparties, CPV mix."""
    db = get_db()
    supplier_result, procurer_result, core, partners = await asyncio.gather(
        call_tool("find_supplier", {"ico": ico, "limit": 1}),
        call_tool("find_procurer", {"ico": ico, "limit": 1}),
        _firma_core_agg(db, ico),
        _firma_partners_agg(db, ico, "all", "value", 10, 0),
    )

    supplier_items = supplier_result.get("items", [])
    procurer_items = procurer_result.get("items", [])
    if not supplier_items and not procurer_items:
        raise ApiV1Error(404, "company_not_found", f"No company found for ICO {ico}.")

    roles: list[str] = []
    if supplier_items:
        roles.append("supplier")
    if procurer_items:
        roles.append("procurer")
    name = (supplier_items or procurer_items)[0].get("name") or ""

    def _agg_block(key: str) -> dict:
        rows = core.get(key) or []
        return rows[0] if rows else {}

    as_supplier = _agg_block("as_supplier")
    as_procurer = _agg_block("as_procurer")
    contract_count = int(as_supplier.get("count") or 0) + int(as_procurer.get("count") or 0)
    total_value = float(as_supplier.get("total") or 0.0) + float(as_procurer.get("total") or 0.0)

    spend_by_year: list[SpendYear] = []
    for r in core.get("spend_by_year") or []:
        try:
            year = int(r.get("_id") or 0)
        except (ValueError, TypeError):
            continue
        if year < 1993 or year > 2100:
            continue
        spend_by_year.append(SpendYear(year=year, total_value=float(r.get("total") or 0.0)))

    counterparties = [
        Counterparty(
            ico=p.get("ico"),
            name=p.get("name"),
            role=p.get("role"),
            contract_count=int(p.get("contract_count") or 0),
            total_value=float(p.get("total_value") or 0.0),
        )
        for p in partners.get("items", [])
    ]
    top_procurers = [c for c in counterparties if c.role == "procurer"]
    top_suppliers = [c for c in counterparties if c.role == "supplier"]

    cpv_breakdown, cpv_concentration = _cpv_breakdown(core.get("cpv") or [])

    profile = CompanyProfile(
        ico=ico,
        name=name,
        roles=roles,
        contract_count=contract_count,
        total_value=total_value,
        spend_by_year=spend_by_year,
        top_procurers=top_procurers,
        top_suppliers=top_suppliers,
        cpv_breakdown=cpv_breakdown,
        cpv_concentration=cpv_concentration,
    )
    return CompanyProfileResponse(data=profile, pagination=Pagination())
