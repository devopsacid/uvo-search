"""Cheap supplier/procurer identity lookups and collection totals.

These replace routing through the Atlas ``$search``-backed ``entity_search`` for
two hot-path needs that never required a search: "does this ICO exist, and what is
its name" (a point lookup) and "how many suppliers/procurers are there" (a
collection-size estimate).
"""

from __future__ import annotations

import asyncio

from uvo_core.cache import _make_key, async_ttl_cache

# Identity + denormalised contract stats maintained by loaders.recompute_entity_stats.
_ENTITY_PROJECTION = {"_id": 0, "ico": 1, "name": 1, "contract_count": 1, "total_value": 1}


@async_ttl_cache(maxsize=2000, ttl=300, key_from=lambda db, ico: _make_key((ico,), {}))
async def get_entity_by_ico(db, ico: str) -> dict:
    """Look up a company by ICO in both roles with two concurrent point reads.

    Returns ``{"supplier": doc | None, "procurer": doc | None}``; both ``None`` means
    the ICO is unknown. Uses ``find_one`` + projection on the unique ``ico`` index.
    """
    supplier, procurer = await asyncio.gather(
        db["suppliers"].find_one({"ico": ico}, _ENTITY_PROJECTION),
        db["procurers"].find_one({"ico": ico}, _ENTITY_PROJECTION),
    )
    return {"supplier": supplier, "procurer": procurer}


def entity_roles(entity: dict) -> list[str]:
    """Role names (``supplier`` / ``procurer``) present in a ``get_entity_by_ico`` result."""
    return [role for role in ("supplier", "procurer") if entity.get(role)]


def entity_name(entity: dict) -> str:
    """Display name, preferring the supplier record (matches the previous behaviour)."""
    return (entity.get("supplier") or entity.get("procurer") or {}).get("name") or ""


@async_ttl_cache(maxsize=1, ttl=600, key_from=lambda db: _make_key((), {}))
async def entity_totals(db) -> dict:
    """Total number of suppliers and procurers via metadata-only size estimates."""
    suppliers, procurers = await asyncio.gather(
        db["suppliers"].estimated_document_count(),
        db["procurers"].estimated_document_count(),
    )
    return {"suppliers": int(suppliers), "procurers": int(procurers)}


def clear_entity_caches() -> None:
    """Drop the identity / totals caches (called with the analytics caches)."""
    get_entity_by_ico.cache_clear()
    entity_totals.cache_clear()
