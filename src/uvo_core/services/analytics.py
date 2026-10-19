"""Analytics dashboard use-cases (metric definition D1).

Thin orchestration over the ``DashboardAnalytics`` port: apply the default period,
validate (``FilterValidationError``, a ``ValueError``, which the API maps to 422),
call the port and wrap the result with ``meta``. The FastAPI router calls these
in-process; there is no string dispatch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime

from uvo_core.domain.analytics import DashboardFilter
from uvo_core.ports import DashboardAnalytics

logger = logging.getLogger(__name__)

DEFINITION = "D1"

_DELTA_KEYS = {
    "contract_count_pct": "contract_count",
    "total_value_pct": "total_value",
    "avg_value_pct": "avg_value",
    "procurer_count_pct": "procurer_count",
    "supplier_count_pct": "supplier_count",
}


def utc_now_z(now: datetime | None = None) -> str:
    """ISO-8601 UTC timestamp with a ``Z`` suffix."""
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> date:
    return datetime.now(UTC).date()


def _effective(f: DashboardFilter, today: date | None) -> DashboardFilter:
    effective = f.with_defaults(today or _today())
    effective.validate()
    return effective


def _meta(f: DashboardFilter) -> dict:
    return {"definition": DEFINITION, "filters": f.as_meta(), "generated_at": utc_now_z()}


def _delta_pct(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


async def summary(analytics: DashboardAnalytics, f: DashboardFilter, *, today: date | None = None):
    """Current-period KPIs, the previous equal-length period and percentage deltas."""
    f = _effective(f, today)
    prev_filter = f.previous_period()
    if prev_filter is None:
        current, previous = await analytics.summary(f), None
    else:
        current, previous = await asyncio.gather(
            analytics.summary(f), analytics.summary(prev_filter)
        )
    deltas = {
        key: _delta_pct(current[field], previous[field]) if previous else None
        for key, field in _DELTA_KEYS.items()
    }
    return {"meta": _meta(f), "current": current, "previous": previous, "deltas": deltas}


async def timeseries(
    analytics: DashboardAnalytics,
    f: DashboardFilter,
    granularity: str = "month",
    split_by: str | None = None,
    top: int = 5,
    *,
    today: date | None = None,
) -> dict:
    f = _effective(f, today)
    return {"meta": _meta(f), **await analytics.timeseries(f, granularity, split_by, top)}


async def top(
    analytics: DashboardAnalytics,
    f: DashboardFilter,
    dimension: str,
    metric: str = "total_value",
    n: int = 10,
    *,
    today: date | None = None,
) -> dict:
    f = _effective(f, today)
    return {"meta": _meta(f), **await analytics.top(f, dimension, metric, n)}


async def concentration(
    analytics: DashboardAnalytics,
    f: DashboardFilter,
    dimension: str = "supplier",
    *,
    today: date | None = None,
) -> dict:
    f = _effective(f, today)
    return {"meta": _meta(f), **await analytics.concentration(f, dimension)}


async def cpv_breakdown(
    analytics: DashboardAnalytics,
    f: DashboardFilter,
    level: str = "division",
    *,
    today: date | None = None,
) -> dict:
    f = _effective(f, today)
    return {"meta": _meta(f), **await analytics.cpv(f, level)}


async def coverage(analytics: DashboardAnalytics) -> dict:
    """Source freshness, quality and monthly volume; ignores the common filters."""
    return await analytics.coverage()


async def warm_default_dashboards(analytics: DashboardAnalytics, today: date | None = None) -> None:
    """Best-effort pre-computation of the landing page aggregates for the default period.

    Each call is independent: a failure is logged at WARNING and never stops the rest.
    """
    f = DashboardFilter()
    jobs = {
        "summary": summary(analytics, f, today=today),
        "timeseries": timeseries(analytics, f, "month", None, 5, today=today),
        "top procurer": top(analytics, f, "procurer", "total_value", 10, today=today),
        "top supplier": top(analytics, f, "supplier", "total_value", 10, today=today),
        "cpv": cpv_breakdown(analytics, f, "division", today=today),
        "coverage": coverage(analytics),
    }
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    for name, result in zip(jobs, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("dashboard warm-up failed for %s: %s", name, result)
