# src/uvo_api/routers/firma.py
"""Unified company profile endpoint — handles any company regardless of role."""

import asyncio
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.mcp_client import call_tool
from uvo_api.models import (
    FirmaProfile,
    FirmaStats,
    FirmaStatsBlock,
    FirmaTopContract,
    FirmaTopCpv,
    SpendByYear,
)
from uvo_api.routers.dashboard import _cpv_prefix, _load_cpv_labels

router = APIRouter(prefix="/api/firma", tags=["firma"])

_EMPTY: dict = {"items": []}


async def _empty() -> dict:
    return _EMPTY


def _first_award(item: dict) -> dict:
    awards = item.get("awards") or []
    return awards[0] if awards else {}


def _stats_block(entity: dict, contracts: list[dict]) -> FirmaStatsBlock:
    count = int(entity.get("contract_count") or len(contracts))
    total = float(entity.get("total_value") or sum(contract_value(c) for c in contracts))
    dates = [d for c in contracts if (d := contract_date(c))]
    last_at = max(dates) if dates else None
    return FirmaStatsBlock(contract_count=count, total_value=total, last_contract_at=last_at)


@router.get("/{ico}", response_model=FirmaProfile)
async def get_firma_profile(ico: str) -> FirmaProfile:
    # Parallel identity lookup
    supplier_result, procurer_result = await asyncio.gather(
        call_tool("find_supplier", {"ico": ico, "limit": 1}),
        call_tool("find_procurer", {"ico": ico, "limit": 1}),
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

    # Fetch top-5 contracts per role + aggregation batch (100) — all in parallel
    top_s_coro = (
        call_tool("search_completed_procurements", {"supplier_ico": ico, "limit": 5, "sort_by": "value_desc"})
        if supplier_items else _empty()
    )
    top_p_coro = (
        call_tool("search_completed_procurements", {"procurer_id": ico, "limit": 5, "sort_by": "value_desc"})
        if procurer_items else _empty()
    )
    agg_s_coro = (
        call_tool("search_completed_procurements", {"supplier_ico": ico, "limit": 100})
        if supplier_items else _empty()
    )
    agg_p_coro = (
        call_tool("search_completed_procurements", {"procurer_id": ico, "limit": 100})
        if procurer_items else _empty()
    )

    top_s_result, top_p_result, agg_s_result, agg_p_result = await asyncio.gather(
        top_s_coro, top_p_coro, agg_s_coro, agg_p_coro
    )

    top_supplier_contracts: list[dict] = top_s_result.get("items", [])
    top_procurer_contracts: list[dict] = top_p_result.get("items", [])
    agg_supplier_contracts: list[dict] = agg_s_result.get("items", [])
    agg_procurer_contracts: list[dict] = agg_p_result.get("items", [])

    # Stats blocks
    as_supplier = _stats_block(supplier, agg_supplier_contracts) if supplier_items else None
    as_procurer = _stats_block(procurer, agg_procurer_contracts) if procurer_items else None

    # Primary role: more contracts wins; supplier wins on tie
    supplier_count = as_supplier.contract_count if as_supplier else 0
    procurer_count = as_procurer.contract_count if as_procurer else 0
    if not supplier_items:
        primary_role = "procurer"
    elif not procurer_items or supplier_count >= procurer_count:
        primary_role = "supplier"
    else:
        primary_role = "procurer"

    # Top contracts from both roles merged, sorted by value desc, capped at 5
    top_s_rows: list[FirmaTopContract] = []
    for c in top_supplier_contracts:
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
    for c in top_procurer_contracts:
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

    # CPV aggregation over combined agg contracts
    labels = _load_cpv_labels()
    cpv_count: dict[str, int] = defaultdict(int)
    cpv_value: dict[str, float] = defaultdict(float)
    for c in agg_supplier_contracts + agg_procurer_contracts:
        prefix = _cpv_prefix(c.get("cpv_code"))
        cpv_count[prefix] += 1
        cpv_value[prefix] += contract_value(c)

    top_cpvs: list[FirmaTopCpv] = [
        FirmaTopCpv(
            code=code,
            label=labels.get(code, {"sk": code}).get("sk", code),
            contract_count=cpv_count[code],
            total_value=cpv_value[code],
        )
        for code in sorted(cpv_count, key=lambda k: cpv_value[k], reverse=True)[:5]
    ]

    # Spend by year over all agg contracts combined
    by_year: dict[int, float] = defaultdict(float)
    for c in agg_supplier_contracts + agg_procurer_contracts:
        year = year_from_date(contract_date(c))
        if year > 0:
            by_year[year] += contract_value(c)

    spend_by_year = [SpendByYear(year=y, total_value=v) for y, v in sorted(by_year.items())]

    return FirmaProfile(
        ico=ico,
        name=name,
        roles=roles,
        primary_role=primary_role,
        stats=FirmaStats(as_supplier=as_supplier, as_procurer=as_procurer),
        top_cpvs=top_cpvs,
        top_contracts=top_contracts,
        spend_by_year=spend_by_year,
    )
