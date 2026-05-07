# src/uvo_api/routers/firma.py
"""Unified company profile endpoint — handles any company regardless of role."""

import asyncio
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.mcp_client import call_tool
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
from uvo_api.routers.dashboard import _cpv_prefix, _fetch_contracts_sample, _load_cpv_labels

router = APIRouter(prefix="/api/firma", tags=["firma"])
firmy_router = APIRouter(prefix="/api/firmy", tags=["firmy"])

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


@router.get("/{ico}/partneri", response_model=PartnerListResponse)
async def get_firma_partneri(
    ico: str,
    role: str = Query("all"),
    sort: str = Query("value"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PartnerListResponse:
    # Fetch contracts where ICO is supplier and where ICO is procurer in parallel
    supplier_contracts_coro = _fetch_contracts_sample({"supplier_ico": ico})
    procurer_contracts_coro = _fetch_contracts_sample({"procurer_id": ico})

    (supplier_contracts, _), (procurer_contracts, _) = await asyncio.gather(
        supplier_contracts_coro, procurer_contracts_coro
    )

    # Aggregate by counterparty ICO
    # Key: (counterparty_ico, role_of_counterparty)
    # When ICO was supplier → counterparty is the procurer → counterparty role = "procurer"
    # When ICO was procurer → counterparty is the supplier → counterparty role = "supplier"
    Partner = dict  # {ico, name, role, contract_count, total_value, last_contract_at}

    agg: dict[tuple[str | None, str], dict] = {}

    for c in supplier_contracts:
        procurer_info = c.get("procurer") or {}
        cp_ico = procurer_info.get("ico") or None
        cp_name = procurer_info.get("name") or None
        cp_role = "procurer"
        key = (cp_ico, cp_role)
        if key not in agg:
            agg[key] = {"ico": cp_ico, "name": cp_name, "role": cp_role, "contract_count": 0, "total_value": 0.0, "last_contract_at": None}
        entry = agg[key]
        entry["contract_count"] += 1
        entry["total_value"] += contract_value(c)
        date = contract_date(c)
        if date and (entry["last_contract_at"] is None or date > entry["last_contract_at"]):
            entry["last_contract_at"] = date

    for c in procurer_contracts:
        award = _first_award(c)
        cp_ico = award.get("supplier_ico") or award.get("ico") or None
        cp_name = award.get("supplier_name") or award.get("name") or None
        cp_role = "supplier"
        key = (cp_ico, cp_role)
        if key not in agg:
            agg[key] = {"ico": cp_ico, "name": cp_name, "role": cp_role, "contract_count": 0, "total_value": 0.0, "last_contract_at": None}
        entry = agg[key]
        entry["contract_count"] += 1
        entry["total_value"] += contract_value(c)
        date = contract_date(c)
        if date and (entry["last_contract_at"] is None or date > entry["last_contract_at"]):
            entry["last_contract_at"] = date

    partners = list(agg.values())

    # Apply role filter
    if role == "supplier":
        partners = [p for p in partners if p["role"] == "supplier"]
    elif role == "procurer":
        partners = [p for p in partners if p["role"] == "procurer"]

    # Sort
    if sort == "count":
        partners.sort(key=lambda p: p["contract_count"], reverse=True)
    else:
        partners.sort(key=lambda p: p["total_value"], reverse=True)

    total = len(partners)
    page = partners[offset: offset + limit]

    return PartnerListResponse(
        total=total,
        items=[PartnerRow(**p) for p in page],
    )


@router.get("/{ico}/cpv-profile", response_model=CpvProfileResponse)
async def get_firma_cpv_profile(ico: str) -> CpvProfileResponse:
    # Fetch up to 500 contracts for this ICO (both roles) and market sample in parallel
    company_s_coro = _fetch_contracts_sample({"supplier_ico": ico})
    company_p_coro = _fetch_contracts_sample({"procurer_id": ico})
    market_coro = _fetch_contracts_sample({})

    (company_s, _), (company_p, _), (market_all, _) = await asyncio.gather(
        company_s_coro, company_p_coro, market_coro
    )

    company_contracts = company_s + company_p

    labels = _load_cpv_labels()

    # Aggregate CPVs for company
    cpv_count: dict[str, int] = defaultdict(int)
    cpv_value: dict[str, float] = defaultdict(float)
    for c in company_contracts:
        prefix = _cpv_prefix(c.get("cpv_code"))
        cpv_count[prefix] += 1
        cpv_value[prefix] += contract_value(c)

    top_codes = sorted(cpv_count, key=lambda k: cpv_value[k], reverse=True)[:10]

    company_total = sum(cpv_value[code] for code in top_codes) or 1.0
    for_company: list[CpvProfileRow] = [
        CpvProfileRow(
            code=code,
            label=labels.get(code, {"sk": code}).get("sk", code),
            total_value=cpv_value[code],
            contract_count=cpv_count[code],
            percentage=round(cpv_value[code] / company_total * 100, 1),
        )
        for code in top_codes
    ]

    # Market baseline — aggregate same CPV codes from market sample
    top_codes_set = set(top_codes)
    mkt_count: dict[str, int] = defaultdict(int)
    mkt_value: dict[str, float] = defaultdict(float)
    for c in market_all:
        prefix = _cpv_prefix(c.get("cpv_code"))
        if prefix in top_codes_set:
            mkt_count[prefix] += 1
            mkt_value[prefix] += contract_value(c)

    mkt_total = sum(mkt_value[code] for code in top_codes) or 1.0
    market_baseline: list[CpvProfileRow] = [
        CpvProfileRow(
            code=code,
            label=labels.get(code, {"sk": code}).get("sk", code),
            total_value=mkt_value[code],
            contract_count=mkt_count[code],
            percentage=round(mkt_value[code] / mkt_total * 100, 1),
        )
        for code in top_codes
        if mkt_count[code] > 0
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
        call_tool("find_supplier", {**search_args, "limit": 100})
        if role in ("supplier", "all") else _empty()
    )
    procurer_coro = (
        call_tool("find_procurer", {**search_args, "limit": 100})
        if role in ("procurer", "all") else _empty()
    )

    supplier_result, procurer_result = await asyncio.gather(supplier_coro, procurer_coro)

    # Merge by ICO
    merged: dict[str, dict] = {}

    for item in supplier_result.get("items", []):
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

    for item in procurer_result.get("items", []):
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

    items = sorted(merged.values(), key=lambda x: x["contract_count"], reverse=True)
    total = len(items)
    page = items[offset: offset + limit]

    return FirmaListResponse(
        total=total,
        items=[FirmaCard(**f) for f in page],
    )
