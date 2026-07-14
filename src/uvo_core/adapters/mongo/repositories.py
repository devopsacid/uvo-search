"""MongoDB repository adapters wrapping the moved query pipelines.

These classes bind a Motor database handle to the existing (cached) query
functions so routers depend on the ports rather than free functions. The
pipelines themselves are unchanged.
"""

from __future__ import annotations

from typing import Any

from uvo_core.adapters.mongo.procurements import fetch_procurement_detail, search_procurements
from uvo_core.adapters.mongo.subjects import entity_search
from uvo_core.services.search import vector_search_companies


class MongoNoticeRepository:
    """NoticeRepository port backed by the ``notices`` collection."""

    def __init__(self, db) -> None:
        self._db = db

    async def search(
        self,
        *,
        text_query: str | None = None,
        cpv_codes: list[str] | None = None,
        procurer_id: str | None = None,
        supplier_ico: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        value_min: float | None = None,
        value_max: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        return await search_procurements(
            self._db,
            text_query=text_query,
            cpv_codes=cpv_codes,
            procurer_id=procurer_id,
            supplier_ico=supplier_ico,
            date_from=date_from,
            date_to=date_to,
            value_min=value_min,
            value_max=value_max,
            limit=limit,
            offset=offset,
        )

    async def get_by_source_id(self, procurement_id: str) -> dict:
        return await fetch_procurement_detail(self._db, procurement_id)

    async def find_dedup_candidates(
        self, filter: dict, projection: dict | None = None
    ) -> list[dict]:
        return await self._db.notices.find(filter, projection).to_list(length=None)

    async def upsert_batch(self, notices: list[dict]) -> dict:
        raise NotImplementedError("upsert_batch lands in Phase 5 (write-side)")

    async def persist_match_groups(self, groups: list[dict]) -> int:
        raise NotImplementedError("persist_match_groups lands in Phase 5 (write-side)")


class MongoCompanyRepository:
    """CompanyRepository port for procurer/supplier entity lookup + vector search."""

    def __init__(self, db) -> None:
        self._db = db

    async def find(
        self,
        collection: str,
        lookup_match_field: str,
        *,
        name_query: str | None = None,
        ico: str | None = None,
        sort_by: str = "name",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        return await entity_search(
            self._db,
            collection,
            lookup_match_field,
            name_query=name_query,
            ico=ico,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    async def vector_search(
        self, model: Any, query: str, limit: int = 10, role: str = "all"
    ) -> dict:
        return await vector_search_companies(self._db, model, query, limit, role)
