# src/uvo_api/routers/suppliers.py
"""Suppliers endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import map_contract_row
from uvo_api.db import Db
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
from uvo_core.adapters.mongo.analytics import entity_profile
from uvo_core.adapters.mongo.entities import get_entity_by_ico
from uvo_core.services.search import find_suppliers, search_procurements

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    db: Db,
    q: str | None = Query(None),
    ico: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000, description="Result offset; deep paging is bounded"),
) -> SupplierListResponse:
    result = await find_suppliers(
        db, name_query=q or None, ico=ico or None, limit=limit, offset=offset
    )
    items = result.get("items", [])
    total = int(result.get("total") or len(items))

    cards = [
        SupplierCard(
            ico=str(s.get("ico") or ""),
            name=s.get("name") or "",
            contract_count=int(s.get("contract_count") or 0),
            total_value=float(s.get("total_value") or 0),
        )
        for s in items
    ]
    return SupplierListResponse(
        data=cards,
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


async def _require_supplier(db, ico: str) -> dict:
    """Identity record for a supplier (cached point lookup); 404 when unknown."""
    entity = await get_entity_by_ico(db, ico)
    supplier = entity["supplier"]
    if not supplier:
        raise HTTPException(status_code=404, detail=f"Supplier {ico} not found")
    return supplier


@router.get("/{ico}/summary", response_model=SupplierSummary)
async def get_supplier_summary(ico: str, db: Db) -> SupplierSummary:
    supplier, profile = await asyncio.gather(
        _require_supplier(db, ico), entity_profile(db, ico, "supplier")
    )

    total_value = float(supplier.get("total_value") or profile["total_value"])
    count = int(supplier.get("contract_count") or profile["contract_count"])

    return SupplierSummary(
        ico=str(supplier.get("ico") or ico),
        name=supplier.get("name") or "",
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        spend_by_year=[
            SpendByYear(year=y["year"], total_value=y["total_value"])
            for y in profile["spend_by_year"]
        ],
    )


@router.get("/{ico}", response_model=SupplierDetail)
async def get_supplier_detail(ico: str, db: Db) -> SupplierDetail:
    supplier, profile, contracts_result = await asyncio.gather(
        _require_supplier(db, ico),
        entity_profile(db, ico, "supplier"),
        # Only the displayed contract rows come from the (paged) search; every
        # aggregate figure below is computed over the full population.
        search_procurements(db, supplier_ico=ico, limit=100),
    )
    rows: list[ContractRow] = [map_contract_row(c) for c in contracts_result.get("items", [])]

    top_procurers = [
        ProcurerRelation(
            ico=p["ico"],
            name=p["name"],
            contract_count=p["contract_count"],
            total_value=p["total_value"],
        )
        for p in profile["partners"]
    ]

    total_value = float(supplier.get("total_value") or profile["total_value"])
    count = int(supplier.get("contract_count") or profile["contract_count"])

    return SupplierDetail(
        ico=str(supplier.get("ico") or ico),
        name=supplier.get("name") or "",
        contract_count=count,
        total_value=total_value,
        avg_value=total_value / count if count else 0,
        years_active=profile["years_active"],
        top_procurers=top_procurers,
        contracts=rows,
    )
