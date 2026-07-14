"""In-memory port fakes for domain-level tests (zero containers).

These compute the same read-models the Mongo adapters do, in pure Python over a
list of notice dicts, so scoring and dashboard-shaping logic can be tested
without MongoDB. They mirror the adapters' value/date precedence:
``final_value`` → ``estimated_value`` for spend, ``award_date`` →
``publication_date`` for the effective date.
"""

from __future__ import annotations

from collections import defaultdict


def _value(notice: dict) -> float:
    for key in ("final_value", "estimated_value"):
        v = notice.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _date(notice: dict) -> str | None:
    return notice.get("award_date") or notice.get("publication_date")


def _year_str(notice: dict) -> str:
    return (_date(notice) or "0000")[:4]


def _supplier_icos(notice: dict) -> set[str]:
    icos: set[str] = set()
    for award in notice.get("awards") or []:
        ico = (award.get("supplier") or {}).get("ico")
        if ico:
            icos.add(ico)
    return icos


class InMemoryNoticeRepository:
    """NoticeRepository fake — text search is a no-op; filters applied in Python."""

    def __init__(self, notices: list[dict] | None = None) -> None:
        self.notices = list(notices or [])

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
        rows = [
            n for n in self.notices if n.get("notice_type", "contract_award") == "contract_award"
        ]
        if cpv_codes:
            rows = [n for n in rows if n.get("cpv_code") in cpv_codes]
        if procurer_id:
            rows = [n for n in rows if (n.get("procurer") or {}).get("ico") == procurer_id]
        if supplier_ico:
            rows = [n for n in rows if supplier_ico in _supplier_icos(n)]
        if value_min is not None:
            rows = [n for n in rows if _value(n) >= value_min]
        if value_max is not None:
            rows = [n for n in rows if _value(n) <= value_max]
        total = len(rows)
        page = rows[offset : offset + limit]
        return {"items": page, "total": total, "limit": limit, "offset": offset}

    async def get_by_source_id(self, procurement_id: str) -> dict:
        for n in self.notices:
            if n.get("source_id") == procurement_id:
                return n
        return {"error": f"Procurement {procurement_id} not found", "status_code": 404}


class InMemoryCompanyAnalytics:
    """CompanyAnalytics fake over an in-memory notice list."""

    def __init__(self, notices: list[dict] | None = None) -> None:
        self.notices = list(notices or [])

    def _awarded(self) -> list[dict]:
        return [
            n for n in self.notices if n.get("notice_type", "contract_award") == "contract_award"
        ]

    def _filtered(self, ico: str | None, entity_type: str | None) -> list[dict]:
        rows = self._awarded()
        if ico and entity_type == "supplier":
            rows = [n for n in rows if ico in _supplier_icos(n)]
        elif ico and entity_type == "procurer":
            rows = [n for n in rows if (n.get("procurer") or {}).get("ico") == ico]
        return rows

    async def core_stats(self, ico: str) -> dict:
        related = [
            n
            for n in self.notices
            if ico in _supplier_icos(n) or (n.get("procurer") or {}).get("ico") == ico
        ]

        def _block(predicate) -> list[dict]:
            sub = [n for n in related if predicate(n)]
            if not sub:
                return []
            return [
                {
                    "count": len(sub),
                    "total": sum(float(n.get("final_value") or 0) for n in sub),
                    "last": max(
                        (n.get("award_date") for n in sub if n.get("award_date")), default=None
                    ),
                }
            ]

        cpv: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
        for n in related:
            b = cpv[n.get("cpv_code")]
            b["count"] += 1
            b["total"] += float(n.get("final_value") or 0)
        cpv_rows = sorted(
            ({"_id": k, **v} for k, v in cpv.items()),
            key=lambda r: r["total"],
            reverse=True,
        )[:5]

        spend: dict[str, float] = defaultdict(float)
        for n in related:
            spend[_year_str(n)] += float(n.get("final_value") or 0)

        return {
            "as_supplier": _block(lambda n: ico in _supplier_icos(n)),
            "as_procurer": _block(lambda n: (n.get("procurer") or {}).get("ico") == ico),
            "cpv": cpv_rows,
            "spend_by_year": [{"_id": y, "total": t} for y, t in sorted(spend.items())],
        }

    async def spend_by_year(
        self, ico: str | None = None, entity_type: str | None = None
    ) -> list[dict]:
        buckets: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})
        for n in self._filtered(ico, entity_type):
            b = buckets[_year_str(n)]
            b["total"] += _value(n)
            b["count"] += 1
        return [{"_id": y, **v} for y, v in sorted(buckets.items())]

    async def cpv_breakdown(
        self,
        ico: str | None = None,
        entity_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict]:
        buckets: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})
        for n in self._filtered(ico, entity_type):
            if year_from is not None or year_to is not None:
                try:
                    y = int(_year_str(n))
                except ValueError:
                    continue
                if year_from is not None and y < year_from:
                    continue
                if year_to is not None and y > year_to:
                    continue
            b = buckets[n.get("cpv_code")]
            b["total"] += _value(n)
            b["count"] += 1
        return [{"_id": k, **v} for k, v in buckets.items()]

    async def monthly_buckets(self, year: int) -> list[dict]:
        buckets: dict[int, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
        prefix = f"{year}-"
        for n in self._awarded():
            d = _date(n) or ""
            if not d.startswith(prefix) or len(d) < 7:
                continue
            b = buckets[int(d[5:7])]
            b["count"] += 1
            b["total"] += _value(n)
        return [{"_id": m, **v} for m, v in sorted(buckets.items())]

    async def market_cpv(self, limit: int = 20) -> list[dict]:
        buckets: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
        for n in self._awarded():
            code = n.get("cpv_code")
            if not code:
                continue
            b = buckets[code]
            b["count"] += 1
            b["total"] += float(n.get("final_value") or 0)
        rows = sorted(
            ({"_id": k, **v} for k, v in buckets.items()),
            key=lambda r: r["total"],
            reverse=True,
        )
        return rows[:limit]

    async def _top_entities(self, get_icos, get_name, n: int) -> list[dict]:
        buckets: dict[str, dict] = defaultdict(
            lambda: {"total_value": 0.0, "contract_count": 0, "name": ""}
        )
        for notice in self._awarded():
            for ico, name in get_icos(notice):
                if not ico:
                    continue
                b = buckets[ico]
                b["total_value"] += float(notice.get("final_value") or 0)
                b["contract_count"] += 1
                b["name"] = b["name"] or name or ""
        rows = sorted(
            ({"_id": k, **v} for k, v in buckets.items()),
            key=lambda r: r["total_value"],
            reverse=True,
        )
        return rows[:n]

    async def top_suppliers(self, n: int = 10) -> list[dict]:
        def icos(notice: dict):
            for award in notice.get("awards") or []:
                supplier = award.get("supplier") or {}
                yield supplier.get("ico"), supplier.get("name")

        return await self._top_entities(icos, None, n)

    async def top_procurers(self, n: int = 10) -> list[dict]:
        def icos(notice: dict):
            procurer = notice.get("procurer") or {}
            yield procurer.get("ico"), procurer.get("name")

        return await self._top_entities(icos, None, n)

    async def partners(self, ico: str, role: str, sort_by: str, limit: int, offset: int) -> dict:
        sort_field = "contract_count" if sort_by == "count" else "total_value"
        rows: dict[tuple[str, str], dict] = {}

        def _accumulate(notice: dict, counter_ico, counter_name, counter_role: str) -> None:
            key = (counter_ico, counter_role)
            row = rows.setdefault(
                key,
                {
                    "ico": counter_ico,
                    "name": counter_name,
                    "role": counter_role,
                    "contract_count": 0,
                    "total_value": 0.0,
                    "last_contract_at": None,
                },
            )
            row["contract_count"] += 1
            row["total_value"] += float(notice.get("final_value") or 0)
            ad = notice.get("award_date")
            if ad and (row["last_contract_at"] is None or ad > row["last_contract_at"]):
                row["last_contract_at"] = ad

        for notice in self._awarded():
            if role in ("all", "procurer") and ico in _supplier_icos(notice):
                p = notice.get("procurer") or {}
                _accumulate(notice, p.get("ico"), p.get("name"), "procurer")
            if role in ("all", "supplier") and (notice.get("procurer") or {}).get("ico") == ico:
                for award in notice.get("awards") or []:
                    s = award.get("supplier") or {}
                    if s.get("ico"):
                        _accumulate(notice, s.get("ico"), s.get("name"), "supplier")

        ordered = sorted(rows.values(), key=lambda r: r.get(sort_field) or 0, reverse=True)
        return {"total": len(ordered), "items": ordered[offset : offset + limit]}
