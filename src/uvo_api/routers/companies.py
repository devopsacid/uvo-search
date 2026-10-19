# src/uvo_api/routers/companies.py
"""Unified company profile endpoint — handles any company regardless of role."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import award_supplier, contract_date, contract_value, year_from_date
from uvo_api.db import Db
from uvo_api.models import (
    CompanyCard,
    CompanyListResponse,
    CompanyProfile,
    CompanyStats,
    CompanyStatsBlock,
    CompanyTopContract,
    CompanyTopCpv,
    CpvProfileResponse,
    CpvProfileRow,
    PartnerListResponse,
    PartnerRow,
    SpendByYear,
)
from uvo_core.adapters.mongo.analytics import (
    _company_core_agg,
    _company_partners_agg,
    _market_cpv_agg,
    top_contracts_by_value,
)
from uvo_core.adapters.mongo.entities import entity_roles, get_entity_by_ico
from uvo_core.domain.companies import merge_companies_by_ico, primary_role
from uvo_core.domain.cpv import cpv_prefix as _cpv_prefix
from uvo_core.domain.cpv import load_cpv_labels as _load_cpv_labels
from uvo_core.services.search import find_procurers, find_suppliers

router = APIRouter(prefix="/api/companies", tags=["companies"])
# Deprecated Slovak paths, kept for one release and hidden from OpenAPI. Registered at the
# bottom of this module with the same handlers, so behaviour and models are shared.
legacy_router = APIRouter(include_in_schema=False)

_EMPTY: dict = {"items": []}


async def _empty() -> dict:
    return _EMPTY


def _first_award(item: dict) -> dict:
    awards = item.get("awards") or []
    return awards[0] if awards else {}


@router.get("/{ico}", response_model=CompanyProfile)
async def get_company_profile(ico: str, db: Db) -> CompanyProfile:

    # Identity (point lookups), aggregate stats and both top-contract lists are
    # independent, so run them concurrently; top lists are ignored for absent roles.
    entity, core, top_s_items, top_p_items = await asyncio.gather(
        get_entity_by_ico(db, ico),
        _company_core_agg(db, ico),
        top_contracts_by_value(db, ico, "supplier", 5),
        top_contracts_by_value(db, ico, "procurer", 5),
    )

    supplier_items = [entity["supplier"]] if entity["supplier"] else []
    procurer_items = [entity["procurer"]] if entity["procurer"] else []

    if not supplier_items and not procurer_items:
        raise HTTPException(status_code=404, detail="Company not found")

    supplier = supplier_items[0] if supplier_items else {}
    procurer = procurer_items[0] if procurer_items else {}
    name = supplier.get("name") or procurer.get("name") or ""

    roles = entity_roles(entity)

    # Stats from aggregation
    def _block(facet_key: str) -> CompanyStatsBlock | None:
        rows = core.get(facet_key) or []
        if not rows:
            return None
        r = rows[0]
        return CompanyStatsBlock(
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

    # Top contracts: largest by value (dedicated sorted query, not the newest-first search).
    top_s_result = {"items": top_s_items if supplier_items else []}
    top_p_result = {"items": top_p_items if procurer_items else []}

    top_s_rows: list[CompanyTopContract] = []
    for c in top_s_result.get("items", []):
        procurer_info = c.get("procurer") or {}
        top_s_rows.append(
            CompanyTopContract(
                id=str(c.get("_id") or c.get("id") or ""),
                title=c.get("title") or "",
                value=contract_value(c) or None,
                year=year_from_date(contract_date(c)) or None,
                counterparty_name=procurer_info.get("name"),
                counterparty_ico=procurer_info.get("ico"),
                role="supplier",
            )
        )

    top_p_rows: list[CompanyTopContract] = []
    for c in top_p_result.get("items", []):
        award_name, award_ico = award_supplier(_first_award(c))
        top_p_rows.append(
            CompanyTopContract(
                id=str(c.get("_id") or c.get("id") or ""),
                title=c.get("title") or "",
                value=contract_value(c) or None,
                year=year_from_date(contract_date(c)) or None,
                counterparty_name=award_name,
                counterparty_ico=award_ico,
                role="procurer",
            )
        )

    top_contracts = sorted(top_s_rows + top_p_rows, key=lambda x: x.value or 0, reverse=True)[:5]

    # CPV from aggregation
    labels = _load_cpv_labels()
    top_cpvs: list[CompanyTopCpv] = []
    for r in core.get("cpv") or []:
        code = _cpv_prefix(r.get("_id"))
        top_cpvs.append(
            CompanyTopCpv(
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

    return CompanyProfile(
        ico=ico,
        name=name,
        roles=roles,
        primary_role=primary,
        stats=CompanyStats(as_supplier=as_supplier, as_procurer=as_procurer),
        top_cpvs=top_cpvs,
        top_contracts=top_contracts,
        spend_by_year=spend_by_year,
    )


@router.get("/{ico}/partners", response_model=PartnerListResponse)
async def get_company_partners(
    ico: str,
    db: Db,
    role: str = Query("all"),
    sort: str = Query("value"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000, description="Result offset; deep paging is bounded"),
) -> PartnerListResponse:
    result = await _company_partners_agg(db, ico, role, sort, limit, offset)
    return PartnerListResponse(
        total=result["total"],
        items=[PartnerRow(**p) for p in result["items"]],
    )


@router.get("/{ico}/cpv-profile", response_model=CpvProfileResponse)
async def get_company_cpv_profile(ico: str, db: Db) -> CpvProfileResponse:
    core, market_rows = await asyncio.gather(
        _company_core_agg(db, ico),
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


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    db: Db,
    q: str | None = Query(None),
    role: str = Query("all"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000, description="Result offset; deep paging is bounded"),
) -> CompanyListResponse:
    name_query = q or None

    supplier_coro = (
        find_suppliers(db, name_query=name_query, limit=100)
        if role in ("supplier", "all")
        else _empty()
    )
    procurer_coro = (
        find_procurers(db, name_query=name_query, limit=100)
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

    return CompanyListResponse(
        total=total,
        items=[CompanyCard(**f) for f in page],
    )


# Old path -> (handler, response model). Remove together with the rollout notes in
# docs/plans/2026-10-19-english-identifiers.md section 7.
_LEGACY_ROUTES = (
    ("/api/firmy", list_companies, CompanyListResponse),
    ("/api/firma/{ico}", get_company_profile, CompanyProfile),
    ("/api/firma/{ico}/partneri", get_company_partners, PartnerListResponse),
    ("/api/firma/{ico}/cpv-profile", get_company_cpv_profile, CpvProfileResponse),
)
for _path, _endpoint, _model in _LEGACY_ROUTES:
    legacy_router.add_api_route(_path, _endpoint, methods=["GET"], response_model=_model)
