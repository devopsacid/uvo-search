# src/uvo_api/routers/search.py
"""Unified entity search across suppliers and procurers."""

import asyncio
import re

from fastapi import APIRouter, Query
from pydantic import BaseModel

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.mcp_client import call_tool

router = APIRouter(prefix="/api/search", tags=["search"])

_ICO_RE = re.compile(r"^\d{8}$")


class EntityHit(BaseModel):
    ico: str
    name: str
    type: str  # "supplier" | "procurer"
    contract_count: int
    total_value: float


class EntitySearchResponse(BaseModel):
    items: list[EntityHit]


class FirmaHit(BaseModel):
    ico: str
    name: str
    roles: list[str]  # ["supplier"], ["procurer"], or ["supplier", "procurer"]
    contract_count: int


class ZakazkaHit(BaseModel):
    id: str
    title: str
    procurer_name: str | None
    value: float | None
    year: int | None


class UnifiedSearchResponse(BaseModel):
    q: str
    firmy: list[FirmaHit]
    zakazky: list[ZakazkaHit]


def _as_hit(item: dict, kind: str) -> EntityHit:
    return EntityHit(
        ico=str(item.get("ico") or ""),
        name=item.get("name") or "",
        type=kind,
        contract_count=int(item.get("contract_count") or 0),
        total_value=float(item.get("total_value") or 0),
    )


def _entity_to_firma(item: dict, role: str) -> FirmaHit:
    return FirmaHit(
        ico=str(item.get("ico") or ""),
        name=item.get("name") or "",
        roles=[role],
        contract_count=int(item.get("contract_count") or 0),
    )


def _contract_to_zakazka(item: dict) -> ZakazkaHit:
    procurer = item.get("procurer") or {}
    raw_value = contract_value(item)
    year = year_from_date(contract_date(item))
    return ZakazkaHit(
        id=str(item.get("_id") or item.get("id") or ""),
        title=item.get("title") or "",
        procurer_name=procurer.get("name") or None,
        value=raw_value if raw_value else None,
        year=year if year else None,
    )


def _merge_firmy(suppliers: list[dict], procurers: list[dict], limit: int) -> list[FirmaHit]:
    merged: dict[str, FirmaHit] = {}
    for item in suppliers:
        ico = str(item.get("ico") or "")
        merged[ico] = _entity_to_firma(item, "supplier")
    for item in procurers:
        ico = str(item.get("ico") or "")
        if ico in merged:
            merged[ico].roles.append("procurer")
        else:
            merged[ico] = _entity_to_firma(item, "procurer")
    return list(merged.values())[:limit]


@router.get("/entities", response_model=EntitySearchResponse)
async def search_entities(
    q: str = Query("", description="Name fragment; empty returns top suppliers/procurers."),
    limit: int = Query(10, ge=1, le=50),
) -> EntitySearchResponse:
    """Search suppliers and procurers by name, merged and sorted by relevance.

    The MCP `find_supplier` / `find_procurer` tools do the matching; we merge
    results and rank: exact name match first, then name prefix match, then
    anything else, with ties broken by contract count (desc).
    """
    per = max(1, limit // 2 + 2)
    args: dict = {"limit": per}
    if q:
        args["name_query"] = q

    supp_result = await call_tool("find_supplier", args)
    proc_result = await call_tool("find_procurer", args)

    hits: list[EntityHit] = []
    for s in supp_result.get("items", []):
        hits.append(_as_hit(s, "supplier"))
    for p in proc_result.get("items", []):
        hits.append(_as_hit(p, "procurer"))

    needle = q.strip().lower()
    def rank(h: EntityHit) -> tuple:
        n = h.name.lower()
        exact = 0 if n == needle else 1
        prefix = 0 if needle and n.startswith(needle) else 1
        return (exact, prefix, -h.contract_count)

    hits.sort(key=rank)
    return EntitySearchResponse(items=hits[:limit])


@router.get("/unified", response_model=UnifiedSearchResponse)
async def unified_search(
    q: str = Query("", description="Search query."),
    limit: int = Query(8, ge=1, le=20),
) -> UnifiedSearchResponse:
    """Return companies (firmy) and contracts (zakazky) grouped in one response.

    8-digit numeric queries are treated as ICO lookups — only firmy is populated.
    Queries shorter than 2 characters return empty results immediately.
    """
    if len(q.strip()) < 2:
        return UnifiedSearchResponse(q=q, firmy=[], zakazky=[])

    if _ICO_RE.match(q.strip()):
        supp_result, proc_result = await asyncio.gather(
            call_tool("find_supplier", {"ico": q.strip(), "limit": limit}),
            call_tool("find_procurer", {"ico": q.strip(), "limit": limit}),
        )
        firmy = _merge_firmy(
            supp_result.get("items", []),
            proc_result.get("items", []),
            limit,
        )
        return UnifiedSearchResponse(q=q, firmy=firmy, zakazky=[])

    entity_args = {"name_query": q.strip(), "limit": limit}
    contract_args = {"text_query": q.strip(), "limit": limit}

    (supp_result, proc_result), contract_result = await asyncio.gather(
        asyncio.gather(
            call_tool("find_supplier", entity_args),
            call_tool("find_procurer", entity_args),
        ),
        call_tool("search_completed_procurements", contract_args),
    )

    firmy = _merge_firmy(
        supp_result.get("items", []),
        proc_result.get("items", []),
        limit,
    )
    zakazky = [_contract_to_zakazka(i) for i in contract_result.get("items", [])][:limit]

    return UnifiedSearchResponse(q=q, firmy=firmy, zakazky=zakazky)
