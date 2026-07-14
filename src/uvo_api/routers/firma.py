# src/uvo_api/routers/firma.py
"""Unified company profile endpoint — handles any company regardless of role."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.db import get_db
from uvo_api.models import (
    CpvProfileResponse,
    CpvProfileRow,
    FirmaCard,
    FirmaListResponse,
    FirmaProfile,
    FirmaStats,
    FirmaStatsBlock,
    FirmaTopContract,
    FirmaTopCpv,
    PartnerListResponse,
    PartnerRow,
    SpendByYear,
)
from uvo_api.routers._agg import _firma_core_agg, _firma_partners_agg, _market_cpv_agg
from uvo_api.routers.dashboard import _cpv_prefix, _load_cpv_labels
from uvo_api.services import run_query
from uvo_core.domain.companies import merge_companies_by_ico, primary_role

router = APIRouter(prefix="/api/firma", tags=["firma"])
firmy_router = APIRouter(prefix="/api/firmy", tags=["firmy"])

_EMPTY: dict = {"items": []}


async def _empty() -> dict:
    return _EMPTY


def _first_award(item: dict) -> dict:
    awards = item.get("awards") or []
    return awards[0] if awards else {}


@router.get("/{ico}", response_model=FirmaProfile)
async def get_firma_profile(ico: str) -> FirmaProfile:
    db = get_db()

    # Identity + top contracts (still via MCP — cached at MCP layer)
    supplier_result, procurer_result, core = await asyncio.gather(
        run_query("find_supplier", {"ico": ico, "limit": 1}),
        run_query("find_procurer", {"ico": ico, "limit": 1}),
        _firma_core_agg(db, ico),
    )

    supplier_items = supplier_result.get("items", [])
    procurer_items = procurer_result.get("items", [])

    if not supplier_items and not procurer_items:
        raise HTTPException(status_code=404, detail="Firma nenájdená")

    supplier = supplier_items[0] if supplier_items else {}
    procurer = procurer_items[0] if procurer_items else {}
    name = supplier.get("name") or procurer.get("name") or ""

    roles: list[str] = []
    if supplier_items:
        roles.append("supplier")
    if procurer_items:
        roles.append("procurer")

    # Stats from aggregation
    def _block(facet_key: str) -> FirmaStatsBlock | None:
        rows = core.get(facet_key) or []
        if not rows:
            return None
        r = rows[0]
        return FirmaStatsBlock(
            contract_count=int(r.get("count") or 0),
            total_value=float(r.get("total") or 0.0),
            last_contract_at=r.get("last"),
        )

    as_supplier = _block("as_supplier") if supplier_items else None
    as_procurer = _block("as_procurer") if procurer_items else None

    primary = primary_role(
        is_supplier=bool(supplier_items),
        is_procurer=bool(procurer_items),
        supplier_count=as_supplier.contract_count if as_supplier else 0,
        procurer_count=as_procurer.contract_count if as_procurer else 0,
    )

    # Top contracts (still via MCP for sort-by-value)
    top_s_coro = (
        run_query(
            "search_completed_procurements",
            {"supplier_ico": ico, "limit": 5, "sort_by": "value_desc"},
        )
        if supplier_items
        else _empty()
    )
    top_p_coro = (
        run_query(
            "search_completed_procurements",
            {"procurer_id": ico, "limit": 5, "sort_by": "value_desc"},
        )
        if procurer_items
        else _empty()
    )
    top_s_result, top_p_result = await asyncio.gather(top_s_coro, top_p_coro)

    top_s_rows: list[FirmaTopContract] = []
    for c in top_s_result.get("items", []):
        procurer_info = c.get("procurer") or {}
        top_s_rows.append(
            FirmaTopContract(
                id=str(c.get("_id") or c.get("id") or ""),
                title=c.get("title") or "",
                value=contract_value(c) or None,
                year=year_from_date(contract_date(c)) or None,
                counterparty_name=procurer_info.get("name"),
                counterparty_ico=procurer_info.get("ico"),
                role="supplier",
            )
        )

    top_p_rows: list[FirmaTopContract] = []
    for c in top_p_result.get("items", []):
        award = _first_award(c)
        top_p_rows.append(
            FirmaTopContract(
                id=str(c.get("_id") or c.get("id") or ""),
                title=c.get("title") or "",
                value=contract_value(c) or None,
                year=year_from_date(contract_date(c)) or None,
                counterparty_name=award.get("supplier_name") or award.get("name"),
                counterparty_ico=award.get("supplier_ico") or award.get("ico"),
                role="procurer",
            )
        )

    top_contracts = sorted(top_s_rows + top_p_rows, key=lambda x: x.value or 0, reverse=True)[:5]

    # CPV from aggregation
    labels = _load_cpv_labels()
    top_cpvs: list[FirmaTopCpv] = []
    for r in core.get("cpv") or []:
        code = _cpv_prefix(r.get("_id"))
        top_cpvs.append(
            FirmaTopCpv(
                code=code,
                label=labels.get(code, {}).get("sk") or code,
                contract_count=int(r.get("count") or 0),
                total_value=float(r.get("total") or 0.0),
            )
        )

    # Spend by year from aggregation
    spend_by_year: list[SpendByYear] = []
    for r in core.get("spend_by_year") or []:
        try:
            year = int(r.get("_id") or 0)
        except (ValueError, TypeError):
            continue
        if year < 1993 or year > 2100:
            continue
        spend_by_year.append(SpendByYear(year=year, total_value=float(r.get("total") or 0.0)))

    return FirmaProfile(
        ico=ico,
        name=name,
        roles=roles,
        primary_role=primary,
        stats=FirmaStats(as_supplier=as_supplier, as_procurer=as_procurer),
        top_cpvs=top_cpvs,
        top_contracts=top_contracts,
        spend_by_year=spend_by_year,
    )


@router.get("/{ico}/partneri", response_model=PartnerListResponse)
async def get_firma_partneri(
    ico: str,
    role: str = Query("all"),
    sort: str = Query("value"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PartnerListResponse:
    db = get_db()
    result = await _firma_partners_agg(db, ico, role, sort, limit, offset)
    return PartnerListResponse(
        total=result["total"],
        items=[PartnerRow(**p) for p in result["items"]],
    )


@router.get("/{ico}/cpv-profile", response_model=CpvProfileResponse)
async def get_firma_cpv_profile(ico: str) -> CpvProfileResponse:
    db = get_db()
    core, market_rows = await asyncio.gather(
        _firma_core_agg(db, ico),
        _market_cpv_agg(db, limit=20),
    )

    labels = _load_cpv_labels()

    top_codes = [_cpv_prefix(r.get("_id")) for r in (core.get("cpv") or [])]
    top_codes_set = set(top_codes)

    company_total = sum(float(r.get("total") or 0) for r in (core.get("cpv") or [])) or 1.0
    for_company: list[CpvProfileRow] = [
        CpvProfileRow(
            code=_cpv_prefix(r.get("_id")),
            label=labels.get(_cpv_prefix(r.get("_id")), {}).get("sk") or _cpv_prefix(r.get("_id")),
            total_value=float(r.get("total") or 0),
            contract_count=int(r.get("count") or 0),
            percentage=round(float(r.get("total") or 0) / company_total * 100, 1),
        )
        for r in (core.get("cpv") or [])
    ]

    mkt_total = (
        sum(
            float(r.get("total") or 0)
            for r in market_rows
            if _cpv_prefix(r.get("_id")) in top_codes_set
        )
        or 1.0
    )
    market_baseline: list[CpvProfileRow] = [
        CpvProfileRow(
            code=_cpv_prefix(r.get("_id")),
            label=labels.get(_cpv_prefix(r.get("_id")), {}).get("sk") or _cpv_prefix(r.get("_id")),
            total_value=float(r.get("total") or 0),
            contract_count=int(r.get("count") or 0),
            percentage=round(float(r.get("total") or 0) / mkt_total * 100, 1),
        )
        for r in market_rows
        if _cpv_prefix(r.get("_id")) in top_codes_set
    ]

    return CpvProfileResponse(for_company=for_company, market_baseline=market_baseline)


@firmy_router.get("", response_model=FirmaListResponse)
async def list_firmy(
    q: str | None = Query(None),
    role: str = Query("all"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> FirmaListResponse:
    search_args: dict = {}
    if q:
        search_args["name_query"] = q

    supplier_coro = (
        run_query("find_supplier", {**search_args, "limit": 100})
        if role in ("supplier", "all")
        else _empty()
    )
    procurer_coro = (
        run_query("find_procurer", {**search_args, "limit": 100})
        if role in ("procurer", "all")
        else _empty()
    )

    supplier_result, procurer_result = await asyncio.gather(supplier_coro, procurer_coro)

    items = merge_companies_by_ico(
        supplier_result.get("items", []),
        procurer_result.get("items", []),
        accumulate=True,
        skip_empty_ico=True,
        sort_by_count=True,
    )
    total = len(items)
    page = items[offset : offset + limit]

    return FirmaListResponse(
        total=total,
        items=[FirmaCard(**f) for f in page],
    )
