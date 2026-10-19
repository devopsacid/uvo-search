"""In-memory port fakes for domain-level tests (zero containers).

These compute the same read-models the Mongo adapters do, in pure Python over a
list of notice dicts, so scoring and dashboard-shaping logic can be tested
without MongoDB. They mirror the adapters' value/date precedence:
``final_value`` → ``estimated_value`` for spend, ``award_date`` →
``publication_date`` for the effective date.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import median as _statistics_median

from uvo_core.adapters.mongo.dashboards import (
    coverage_since,
    shape_concentration,
    shape_coverage,
    shape_cpv,
    shape_summary,
    shape_timeseries,
    shape_top,
)
from uvo_core.adapters.mongo.procurements import split_cpv
from uvo_core.domain.analytics import (
    D1_NOTICE_TYPE,
    DashboardFilter,
    cpv_division,
    cpv_group,
)


def _median(values: list[float]) -> float:
    """Median of a value list (0.0 when empty), mirroring the adapter's $median."""
    return float(_statistics_median(values)) if values else 0.0


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
        source: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        rows = [
            n for n in self.notices if n.get("notice_type", "contract_award") == "contract_award"
        ]
        if source:
            rows = [n for n in rows if n.get("source") == source]
        if cpv_codes:
            exact, prefixes = split_cpv(cpv_codes)
            rows = [
                n
                for n in rows
                if n.get("cpv_code") in exact
                or any(str(n.get("cpv_code") or "").startswith(p) for p in prefixes)
            ]
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
        values: dict[str, list[float]] = defaultdict(list)
        for n in self._awarded():
            code = n.get("cpv_code")
            if not code:
                continue
            values[code].append(float(n.get("final_value") or 0))
        rows = sorted(
            (
                {"_id": k, "count": len(v), "total": sum(v), "median": _median(v)}
                for k, v in values.items()
            ),
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

    async def award_timeline(self, ico: str) -> list[dict]:
        rows: list[dict] = []
        for notice in self._awarded():
            date = _date(notice)
            value = float(notice.get("final_value") or 0)
            cpv = notice.get("cpv_code")
            procedure_type = notice.get("procedure_type")
            if (notice.get("procurer") or {}).get("ico") == ico:
                for award in notice.get("awards") or []:
                    supplier = award.get("supplier") or {}
                    rows.append(
                        {
                            "date": date,
                            "counterparty_ico": supplier.get("ico"),
                            "value": value,
                            "cpv_code": cpv,
                            "procedure_type": procedure_type,
                        }
                    )
            if ico in _supplier_icos(notice):
                procurer = notice.get("procurer") or {}
                rows.append(
                    {
                        "date": date,
                        "counterparty_ico": procurer.get("ico"),
                        "value": value,
                        "cpv_code": cpv,
                        "procedure_type": procedure_type,
                    }
                )
        return rows

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


class InMemoryDashboardAnalytics:
    """DashboardAnalytics fake: metric definition D1 computed in plain Python.

    It produces the same *raw rows* the Mongo pipelines return and hands them to the
    shared ``shape_*`` functions, so it is an independent check of the pipelines'
    filtering and grouping (the E2E test compares both over the shared 30-notice
    fixture) while the shaping rules live in one place.
    """

    def __init__(self, notices: list[dict] | None = None) -> None:
        self.notices = list(notices or [])

    # -- D1 selection -------------------------------------------------------------

    def _selected(self, f: DashboardFilter) -> list[dict]:
        lo, hi = f.date_from or "", f.date_to or "9999-12-31"
        out = []
        for n in self.notices:
            if n.get("notice_type") != D1_NOTICE_TYPE:
                continue
            day = n.get("award_date")
            if day is None:
                day = n.get("publication_date")
            if day is None or not (lo <= day <= hi):
                continue
            if f.cpv and not str(n.get("cpv_code") or "").startswith(f.cpv):
                continue
            if f.source and n.get("source") != f.source:
                continue
            if f.procurer_ico and (n.get("procurer") or {}).get("ico") != f.procurer_ico:
                continue
            if f.supplier_ico and f.supplier_ico not in _supplier_icos(n):
                continue
            out.append(n)
        return out

    @staticmethod
    def _day(notice: dict) -> str:
        day = notice.get("award_date")
        return day if day is not None else (notice.get("publication_date") or "")

    @staticmethod
    def _supplier_names(notices: list[dict]) -> dict[str, str]:
        names: dict[str, str] = {}
        for n in notices:
            for award in n.get("awards") or []:
                s = award.get("supplier") or {}
                if s.get("ico") and s.get("name") and s["ico"] not in names:
                    names[s["ico"]] = s["name"]
        return names

    @staticmethod
    def _entity_groups(notices: list[dict], dimension: str) -> dict[str, dict]:
        groups: dict[str, dict] = {}
        for n in notices:
            if dimension == "procurer":
                keys = [(n.get("procurer") or {}).get("ico")]
            elif dimension == "supplier":
                keys = sorted(_supplier_icos(n))
            else:
                keys = [cpv_division(n.get("cpv_code"))]
            for key in keys:
                if not key:
                    continue
                g = groups.setdefault(key, {"_id": key, "count": 0, "total": 0.0})
                g["count"] += 1
                g["total"] += _value(n)
                if dimension == "procurer":
                    g.setdefault("name", (n.get("procurer") or {}).get("name"))
        return groups

    # -- port ----------------------------------------------------------------------

    async def summary(self, f: DashboardFilter) -> dict:
        sel = self._selected(f)
        procurers = {(n.get("procurer") or {}).get("ico") for n in sel} - {None, ""}
        suppliers = set().union(*(_supplier_icos(n) for n in sel)) if sel else set()
        row = {
            "totals": [{"count": len(sel), "total": sum(_value(n) for n in sel)}] if sel else [],
            "procurers": [{"n": len(procurers)}] if procurers else [],
            "suppliers": [{"n": len(suppliers)}] if suppliers else [],
        }
        return shape_summary([row], f)

    async def timeseries(
        self, f: DashboardFilter, granularity: str, split_by: str | None, top: int
    ) -> dict:
        width = 4 if granularity == "year" else 7
        cells: dict[tuple, dict] = {}
        for n in self._selected(f):
            gid: dict = {"period": self._day(n)[:width]}
            if split_by == "source":
                gid["key"] = n.get("source")
            elif split_by == "cpv_division":
                gid["key"] = cpv_division(n.get("cpv_code"))
            cell = cells.setdefault(tuple(gid.items()), {"_id": gid, "count": 0, "total": 0.0})
            cell["count"] += 1
            cell["total"] += _value(n)
        return shape_timeseries(list(cells.values()), f, granularity, split_by, top)

    async def top(self, f: DashboardFilter, dimension: str, metric: str, n: int) -> dict:
        sel = self._selected(f)
        field = "total" if metric == "total_value" else "count"
        groups = sorted(
            self._entity_groups(sel, dimension).values(), key=lambda g: (-g[field], g["_id"])
        )[:n]
        if dimension == "supplier":
            names = self._supplier_names(sel)
            for g in groups:
                g["name"] = names.get(g["_id"])
        total = [{"count": len(sel), "total": sum(_value(x) for x in sel)}] if sel else []
        return shape_top([{"total": total, "items": groups}], dimension, metric, n)

    async def concentration(self, f: DashboardFilter, dimension: str) -> dict:
        sel = self._selected(f)
        groups = [g for g in self._entity_groups(sel, dimension).values() if g["total"] > 0]
        if dimension == "supplier":
            names = self._supplier_names(sel)
            for g in groups:
                g["name"] = names.get(g["_id"])
        top = sorted(groups, key=lambda g: (-g["total"], g["_id"]))[:10]
        total = sum(g["total"] for g in groups)
        totals = (
            [{"total": total, "sumsq": sum(g["total"] ** 2 for g in groups), "n": len(groups)}]
            if groups
            else []
        )
        return shape_concentration([{"totals": totals, "top": top}], dimension)

    async def cpv(self, f: DashboardFilter, level: str) -> dict:
        normalise = cpv_division if level == "division" else cpv_group
        groups: dict[str, dict] = {}
        for n in self._selected(f):
            key = normalise(n.get("cpv_code"))
            g = groups.setdefault(key, {"_id": key, "count": 0, "total": 0.0})
            g["count"] += 1
            g["total"] += _value(n)
        return shape_cpv(list(groups.values()), level)

    async def coverage(self) -> dict:
        now = datetime.now(UTC)
        since = coverage_since(now)
        per_source: dict[str, dict] = {}
        monthly: dict[tuple[str, str], int] = {}
        for n in self.notices:
            source = n.get("source") or "unknown"
            g = per_source.setdefault(
                source,
                {
                    "_id": source,
                    "notices_total": 0,
                    "contract_awards": 0,
                    "last_publication": None,
                    "last_ingested": None,
                    "with_value": 0,
                    "with_cpv": 0,
                    "with_supplier": 0,
                    "with_procurer": 0,
                },
            )
            g["notices_total"] += 1
            for key, field in (
                ("last_publication", "publication_date"),
                ("last_ingested", "ingested_at"),
            ):
                v = n.get(field)
                if v and (g[key] is None or v > g[key]):
                    g[key] = v
            if n.get("notice_type") == D1_NOTICE_TYPE:
                g["contract_awards"] += 1
                g["with_value"] += 1 if _value(n) > 0 else 0
                g["with_cpv"] += 1 if n.get("cpv_code") else 0
                g["with_supplier"] += 1 if _supplier_icos(n) else 0
                g["with_procurer"] += 1 if (n.get("procurer") or {}).get("ico") else 0
            pub = n.get("publication_date") or ""
            if pub >= since:
                key = (pub[:7], source)
                monthly[key] = monthly.get(key, 0) + 1
        monthly_rows = [
            {"_id": {"period": p, "source": s}, "count": c} for (p, s), c in monthly.items()
        ]
        canonical_ids = [n["canonical_id"] for n in self.notices if n.get("canonical_id")]
        return shape_coverage(
            list(per_source.values()),
            monthly_rows,
            len(canonical_ids),
            len(set(canonical_ids)),
            now,
        )
