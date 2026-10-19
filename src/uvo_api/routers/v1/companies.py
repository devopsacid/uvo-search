"""Public /v1 company endpoints — search, core record, procurement profile."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from uvo_api.db import Db, get_analytics, get_graph_store
from uvo_api.routers.v1._common import decode_cursor, next_pagination
from uvo_api.routers.v1.models import (
    CompanyCard,
    CompanyListResponse,
    CompanyProfile,
    CompanyProfileResponse,
    CompanyRecord,
    CompanyRecordResponse,
    CompanyRisk,
    CompanyRiskResponse,
    Counterparty,
    CpvBreakdownRow,
    Pagination,
    SpendYear,
)
from uvo_api.v1_errors import ApiV1Error
from uvo_core.adapters.mongo.entities import entity_name, entity_roles, get_entity_by_ico
from uvo_core.domain.companies import merge_companies_by_ico
from uvo_core.domain.cpv import cpv_prefix as _cpv_prefix
from uvo_core.domain.cpv import load_cpv_labels as _load_cpv_labels
from uvo_core.domain.scoring import cpv_concentration
from uvo_core.ports import CompanyAnalytics, GraphStore
from uvo_core.services.risk import company_risk_profile
from uvo_core.services.search import find_procurers, find_suppliers

router = APIRouter(prefix="/companies", tags=["companies"])

Analytics = Annotated[CompanyAnalytics, Depends(get_analytics)]
OptionalGraphStore = Annotated[GraphStore | None, Depends(get_graph_store)]

# find_suppliers / find_procurers cap at 100 rows; we merge + slice a page from that.
_MERGE_FETCH = 100


async def _resolve_identity(db, ico: str) -> tuple[list[str], str]:
    """(roles, display name) for an ICO; raises the v1 404 when the company is unknown."""
    entity = await get_entity_by_ico(db, ico)
    roles = entity_roles(entity)
    if not roles:
        raise ApiV1Error(404, "company_not_found", f"No company found for ICO {ico}.")
    return roles, entity_name(entity)


@router.get("", response_model=CompanyListResponse)
async def search_companies(
    db: Db,
    q: str | None = Query(None, description="Company name fragment."),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> CompanyListResponse:
    """Search suppliers and procurers by name, merged into a single company view."""
    offset = decode_cursor(cursor)
    name_query = q or None

    supplier_result, procurer_result = await asyncio.gather(
        find_suppliers(db, name_query=name_query, limit=_MERGE_FETCH),
        find_procurers(db, name_query=name_query, limit=_MERGE_FETCH),
    )
    merged = merge_companies_by_ico(
        supplier_result.get("items", []),
        procurer_result.get("items", []),
        accumulate=True,
        skip_empty_ico=True,
        sort_by_count=True,
    )
    total = len(merged)
    page = merged[offset : offset + limit]

    return CompanyListResponse(
        data=[CompanyCard(**c) for c in page],
        pagination=next_pagination(offset, limit, len(page), total),
    )


@router.get("/{ico}", response_model=CompanyRecordResponse)
async def get_company(ico: str, db: Db) -> CompanyRecordResponse:
    """Core identity record for a company by ICO."""
    roles, name = await _resolve_identity(db, ico)
    return CompanyRecordResponse(data=CompanyRecord(ico=ico, name=name, roles=roles))


def _cpv_breakdown(rows: list[dict]) -> tuple[list[CpvBreakdownRow], float]:
    labels = _load_cpv_labels()
    values = [float(r.get("total") or 0.0) for r in rows]
    shares, hhi = cpv_concentration(values)
    breakdown = [
        CpvBreakdownRow(
            code=_cpv_prefix(r.get("_id")),
            label=labels.get(_cpv_prefix(r.get("_id")), {}).get("sk") or _cpv_prefix(r.get("_id")),
            contract_count=int(r.get("count") or 0),
            total_value=float(r.get("total") or 0.0),
            share=round(share * 100, 1),
        )
        for r, share in zip(rows, shares)
    ]
    return breakdown, hhi


@router.get("/{ico}/profile", response_model=CompanyProfileResponse)
async def get_company_profile(ico: str, db: Db, analytics: Analytics) -> CompanyProfileResponse:
    """Flagship procurement profile: totals, spend by year, counterparties, CPV mix."""
    (roles, name), core, partners = await asyncio.gather(
        _resolve_identity(db, ico),
        analytics.core_stats(ico),
        analytics.partners(ico, "all", "value", 10, 0),
    )

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


@router.get("/{ico}/risk", response_model=CompanyRiskResponse)
async def get_company_risk(
    ico: str, db: Db, analytics: Analytics, graph: OptionalGraphStore
) -> CompanyRiskResponse:
    """Red-flag risk profile: supplier concentration, single-pair dependency,
    market-value deviation, and award clustering, blended into a 0-100 score."""
    roles, name = await _resolve_identity(db, ico)

    profile = await company_risk_profile(ico, analytics, graph)

    return CompanyRiskResponse(
        data=CompanyRisk(name=name, roles=roles, **profile),
        pagination=Pagination(),
    )
