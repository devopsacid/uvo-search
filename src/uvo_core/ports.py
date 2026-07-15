"""Port definitions (``typing.Protocol``) for uvo_core's driven adapters.

Each port has one production adapter (Mongo/Neo4j today) plus an in-memory fake
(``uvo_core.testing``) sufficient for domain-level tests. Conformance is checked
structurally by mypy — adapters do not inherit these Protocols.

``NoticeStream`` and ``CheckpointStore`` are declared here so the write-side
(Phase 5) has a stable target; their production adapters land in that phase.
"""

from __future__ import annotations

from typing import Any, Protocol


class NoticeRepository(Protocol):
    """Read/write access to the canonical ``notices`` collection."""

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
    ) -> dict: ...

    async def get_by_source_id(self, procurement_id: str) -> dict: ...

    async def find_dedup_candidates(
        self, filter: dict, projection: dict | None = None
    ) -> list[dict]: ...

    async def upsert_batch(self, notices: list[dict]) -> dict: ...  # Phase 5

    async def persist_match_groups(self, groups: list[dict]) -> int: ...  # Phase 5


class CompanyRepository(Protocol):
    """Procurer/supplier entity lookup and vector search."""

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
    ) -> dict: ...

    async def vector_search(
        self, model: Any, query: str, limit: int = 10, role: str = "all"
    ) -> dict: ...


class CompanyAnalytics(Protocol):
    """Read-model aggregations over ``notices`` for profiles and dashboards.

    This is the surface the scoring engine (Phase 4) consumes — kept explicit
    and DB-free-fakeable so scoring never imports motor.
    """

    async def core_stats(self, ico: str) -> dict: ...

    async def partners(
        self, ico: str, role: str, sort_by: str, limit: int, offset: int
    ) -> dict: ...

    async def market_cpv(self, limit: int = 20) -> list[dict]: ...

    async def top_suppliers(self, n: int = 10) -> list[dict]: ...

    async def top_procurers(self, n: int = 10) -> list[dict]: ...

    async def spend_by_year(
        self, ico: str | None = None, entity_type: str | None = None
    ) -> list[dict]: ...

    async def cpv_breakdown(
        self,
        ico: str | None = None,
        entity_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict]: ...

    async def monthly_buckets(self, year: int) -> list[dict]: ...

    async def award_timeline(self, ico: str) -> list[dict]: ...


class GraphStore(Protocol):
    """Neo4j-backed relationship queries."""

    async def ego_network(self, ico: str, max_hops: int = 2) -> dict: ...

    async def cpv_network(self, cpv_code: str, year: int) -> dict: ...

    async def supplier_concentration(self, procurer_ico: str, top_n: int = 10) -> dict: ...


class NoticeStream(Protocol):  # pragma: no cover — Phase 5
    """Redis Streams transport for ingested notices."""

    async def xadd_notice(self, payload: dict) -> str: ...

    async def read_group(self, group: str, consumer: str, count: int) -> list: ...

    async def ack(self, group: str, message_id: str) -> None: ...


class CheckpointStore(Protocol):  # pragma: no cover — Phase 5
    """Per-source extractor checkpoint state."""

    async def get(self, source: str) -> dict: ...

    async def save(self, source: str, state: dict) -> None: ...
