# src/uvo_api/routers/procurers.py
"""Procurers endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import map_contract_row
from uvo_api.db import Db
from uvo_api.models import (
    ConcentrationResponse,
    ContractRow,
    PaginationMeta,
    ProcurerCard,
    ProcurerDetail,
    ProcurerListResponse,
    ProcurerSummary,
    SpendByYear,
    SupplierRelation,
    SupplierShare,
)
from uvo_core.adapters.mongo.analytics import entity_profile
from uvo_core.adapters.mongo.entities import get_entity_by_ico
from uvo_core.services.search import find_procurers, search_procurements

router = APIRouter(prefix="/api/procurers", tags=["procurers"])


@router.get("", response_model=ProcurerListResponse)
async def list_procurers(
    db: Db,
    q: str | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000, description="Result offset; deep paging is bounded"),
) -> ProcurerListResponse:
    result = await find_procurers(
        db, name_query=q or None, ico=ico or None, limit=limit, offset=offset
    )
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


async def _require_procurer(db, ico: str) -> dict:
    """Identity record for a procurer (cached point lookup); 404 when unknown."""
    entity = await get_entity_by_ico(db, ico)
    procurer = entity["procurer"]
    if not procurer:
        raise HTTPException(status_code=404, detail=f"Procurer {ico} not found")
    return procurer


def _spend_by_year(profile: dict) -> list[SpendByYear]:
    return [
        SpendByYear(year=y["year"], total_value=y["total_value"]) for y in profile["spend_by_year"]
    ]


@router.get("/{ico}/summary", response_model=ProcurerSummary)
async def get_procurer_summary(ico: str, db: Db) -> ProcurerSummary:
    procurer, profile = await asyncio.gather(
        _require_procurer(db, ico), entity_profile(db, ico, "procurer")
    )

    total_spend = float(procurer.get("total_value") or profile["total_value"])
    count = int(procurer.get("contract_count") or profile["contract_count"])

    return ProcurerSummary(
        ico=str(procurer.get("ico") or ico),
        name=procurer.get("name") or "",
        contract_count=count,
        total_spend=total_spend,
        avg_value=total_spend / count if count else 0,
        spend_by_year=_spend_by_year(profile),
    )


@router.get("/{ico}", response_model=ProcurerDetail)
async def get_procurer_detail(ico: str, db: Db) -> ProcurerDetail:
    procurer, profile, contracts_result = await asyncio.gather(
        _require_procurer(db, ico),
        entity_profile(db, ico, "procurer"),
        # Only the displayed contract rows come from the (paged) search; every
        # aggregate figure below is computed over the full population.
        search_procurements(db, procurer_id=ico, limit=100),
    )
    rows: list[ContractRow] = [map_contract_row(c) for c in contracts_result.get("items", [])]

    top_suppliers = [
        SupplierRelation(
            ico=p["ico"],
            name=p["name"],
            contract_count=p["contract_count"],
            total_value=p["total_value"],
        )
        for p in profile["partners"]
    ]

    total_spend = float(procurer.get("total_value") or profile["total_value"])
    count = int(procurer.get("contract_count") or profile["contract_count"])

    return ProcurerDetail(
        ico=str(procurer.get("ico") or ico),
        name=procurer.get("name") or "",
        contract_count=count,
        total_spend=total_spend,
        avg_value=total_spend / count if count else 0,
        years_active=profile["years_active"],
        top_suppliers=top_suppliers,
        contracts=rows,
    )


@router.get("/{ico}/concentration", response_model=ConcentrationResponse)
async def get_procurer_concentration(
    ico: str,
    db: Db,
    top_n: int = Query(10, ge=1, le=50),
) -> ConcentrationResponse:
    """Supplier concentration for a procurer with HHI computed over all suppliers."""
    procurer, profile = await asyncio.gather(
        _require_procurer(db, ico), entity_profile(db, ico, "procurer", top_n)
    )
    procurer_name = procurer.get("name") or ""
    total_spend = profile["partner_total_value"]

    if not total_spend:
        return ConcentrationResponse(
            procurer_ico=ico,
            procurer_name=procurer_name,
            top_suppliers=[],
            hhi=0.0,
        )

    top_suppliers = [
        SupplierShare(
            ico=p["ico"],
            name=p["name"],
            total_value=p["total_value"],
            share=round(p["total_value"] / total_spend * 100, 2),
        )
        for p in profile["partners"][:top_n]
    ]

    return ConcentrationResponse(
        procurer_ico=ico,
        procurer_name=procurer_name,
        top_suppliers=top_suppliers,
        hhi=round(profile["hhi"], 1),
    )
