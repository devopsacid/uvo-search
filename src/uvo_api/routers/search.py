# src/uvo_api/routers/search.py
"""Unified entity search across suppliers and procurers."""

import asyncio
import logging
import re

from fastapi import APIRouter, Query
from pydantic import BaseModel

from uvo_api._schema import contract_date, contract_value, year_from_date
from uvo_api.db import Db, OptionalEmbedder
from uvo_core.domain.companies import merge_companies_by_ico
from uvo_core.services.search import (
    find_procurers,
    find_suppliers,
    search_procurements,
    vector_search_companies,
)

logger = logging.getLogger(__name__)

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


class CompanyHit(BaseModel):
    ico: str
    name: str
    roles: list[str]  # ["supplier"], ["procurer"], or ["supplier", "procurer"]
    contract_count: int


class ContractHit(BaseModel):
    id: str
    title: str
    procurer_name: str | None
    value: float | None
    year: int | None


class UnifiedSearchResponse(BaseModel):
    q: str
    companies: list[CompanyHit]
    contracts: list[ContractHit]


async def _vector_hits(db, embedder, query: str, limit: int) -> dict:
    """Vector branch; an unavailable embedder degrades to "no vector hits" (not an error)."""
    if embedder is None:
        logger.debug("vector search skipped: embedder unavailable")
        return {}
    return await vector_search_companies(db, embedder, query, limit)


def _as_hit(item: dict, kind: str) -> EntityHit:
    return EntityHit(
        ico=str(item.get("ico") or ""),
        name=item.get("name") or "",
        type=kind,
        contract_count=int(item.get("contract_count") or 0),
        total_value=float(item.get("total_value") or 0),
    )


def _to_company_hit(row: dict) -> CompanyHit:
    return CompanyHit(
        ico=row["ico"],
        name=row["name"],
        roles=row["roles"],
        contract_count=row["contract_count"],
    )


def _to_contract_hit(item: dict) -> ContractHit:
    procurer = item.get("procurer") or {}
    raw_value = contract_value(item)
    year = year_from_date(contract_date(item))
    return ContractHit(
        id=str(item.get("_id") or item.get("id") or ""),
        title=item.get("title") or "",
        procurer_name=procurer.get("name") or None,
        value=raw_value if raw_value else None,
        year=year if year else None,
    )


def _merge_companies(suppliers: list[dict], procurers: list[dict], limit: int) -> list[CompanyHit]:
    rows = merge_companies_by_ico(suppliers, procurers)
    return [_to_company_hit(r) for r in rows][:limit]


def _merge_companies_with_vector(
    suppliers: list[dict],
    procurers: list[dict],
    vector_items: list[dict],
    limit: int,
) -> list[CompanyHit]:
    """Merge text and vector hits; vector hits ranked first, then text hits fill remaining slots."""
    rows = merge_companies_by_ico(suppliers, procurers, vector=vector_items)
    return [_to_company_hit(r) for r in rows][:limit]


@router.get("/entities", response_model=EntitySearchResponse)
async def search_entities(
    db: Db,
    embedder: OptionalEmbedder,
    q: str = Query("", description="Name fragment; empty returns top suppliers/procurers."),
    limit: int = Query(10, ge=1, le=50),
) -> EntitySearchResponse:
    """Search suppliers and procurers by name, merged and sorted by relevance.

    The shared supplier/procurer/vector searches do the matching; we merge
    results and rank: exact name match first, then name prefix match, then
    anything else, with ties broken by contract count (desc).
    """
    per = max(1, limit // 2 + 2)
    name_query = q or None

    if q:
        supp_result, proc_result, vec_result = await asyncio.gather(
            find_suppliers(db, name_query=name_query, limit=per),
            find_procurers(db, name_query=name_query, limit=per),
            _vector_hits(db, embedder, q, limit),
        )
    else:
        supp_result, proc_result = await asyncio.gather(
            find_suppliers(db, name_query=name_query, limit=per),
            find_procurers(db, name_query=name_query, limit=per),
        )
        vec_result = {}

    vec_items = vec_result.get("items", [])

    seen_icos: set[str] = {str(v.get("ico") or "") for v in vec_items}
    hits: list[EntityHit] = []
    for v in vec_items:
        hits.append(
            EntityHit(
                ico=str(v.get("ico") or ""),
                name=v.get("name") or "",
                type="supplier" if "supplier" in (v.get("roles") or []) else "procurer",
                contract_count=0,
                total_value=0.0,
            )
        )
    for s in supp_result.get("items", []):
        if str(s.get("ico") or "") not in seen_icos:
            hits.append(_as_hit(s, "supplier"))
    for p in proc_result.get("items", []):
        if str(p.get("ico") or "") not in seen_icos:
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
    db: Db,
    embedder: OptionalEmbedder,
    q: str = Query("", description="Search query."),
    limit: int = Query(8, ge=1, le=20),
) -> UnifiedSearchResponse:
    """Return companies and contracts grouped in one response.

    8-digit numeric queries are treated as ICO lookups — only companies is populated.
    Queries shorter than 2 characters return empty results immediately.
    """
    if len(q.strip()) < 2:
        return UnifiedSearchResponse(q=q, companies=[], contracts=[])

    if _ICO_RE.match(q.strip()):
        supp_result, proc_result = await asyncio.gather(
            find_suppliers(db, ico=q.strip(), limit=limit),
            find_procurers(db, ico=q.strip(), limit=limit),
        )
        companies = _merge_companies(
            supp_result.get("items", []),
            proc_result.get("items", []),
            limit,
        )
        return UnifiedSearchResponse(q=q, companies=companies, contracts=[])

    needle = q.strip()
    branches = {
        "supplier": find_suppliers(db, name_query=needle, limit=limit),
        "procurer": find_procurers(db, name_query=needle, limit=limit),
        "vector": _vector_hits(db, embedder, needle, limit),
        "contracts": search_procurements(db, text_query=needle, limit=limit),
    }
    outcomes = await asyncio.gather(*branches.values(), return_exceptions=True)

    results: dict[str, dict] = {}
    failures: list[BaseException] = []
    for name, outcome in zip(branches, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            # One slow/broken branch (e.g. vector search) must not blank the others.
            logger.warning("unified search branch %r failed: %s", name, outcome, exc_info=outcome)
            failures.append(outcome)
            results[name] = {}
        else:
            results[name] = outcome
    if len(failures) == len(branches):
        raise failures[0]

    supp_result, proc_result = results["supplier"], results["procurer"]
    vec_result, contract_result = results["vector"], results["contracts"]

    vec_items = vec_result.get("items", [])
    companies = _merge_companies_with_vector(
        supp_result.get("items", []),
        proc_result.get("items", []),
        vec_items,
        limit,
    )
    contracts = [_to_contract_hit(i) for i in contract_result.get("items", [])][:limit]

    return UnifiedSearchResponse(q=q, companies=companies, contracts=contracts)
