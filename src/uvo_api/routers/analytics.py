"""Analytics dashboard endpoints (``/api/analytics/*``, metric definition D1).

Routers only parse and shape: defaults, validation and the aggregations live in
``uvo_core.services.analytics``. Invalid filters become the standard FastAPI 422
body; an aggregate that exceeds ``maxTimeMS`` becomes ``504 {"detail": "analytics_timeout"}``;
a backend outage keeps the global 503 mapping.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pymongo.errors import ExecutionTimeout

from uvo_api.db import get_dashboard_analytics
from uvo_api.models import (
    AnalyticsConcentrationResponse,
    AnalyticsCoverageResponse,
    AnalyticsCpvResponse,
    AnalyticsSummaryResponse,
    AnalyticsTimeseriesResponse,
    AnalyticsTopResponse,
)
from uvo_core.domain.analytics import DashboardFilter, FilterValidationError
from uvo_core.ports import DashboardAnalytics
from uvo_core.services import analytics as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

Analytics = Annotated[DashboardAnalytics, Depends(get_dashboard_analytics)]


def common_filter(
    date_from: str | None = Query(
        None, description="Inclusive ISO start date; default 1 January of (year - 4)."
    ),
    date_to: str | None = Query(None, description="Inclusive ISO end date; default today."),
    cpv: str | None = Query(None, description="CPV prefix, 2-8 digits (anchored prefix match)."),
    source: str | None = Query(None, description="vestnik | crz | ted | uvo | itms."),
    procurer_ico: str | None = Query(None, description="Procurer ICO, 1-12 digits."),
    supplier_ico: str | None = Query(None, description="Supplier ICO, 1-12 digits."),
) -> DashboardFilter:
    """The six common filters; semantics and validation are in the service layer."""
    return DashboardFilter(
        date_from=date_from,
        date_to=date_to,
        cpv=cpv,
        source=source,
        procurer_ico=procurer_ico,
        supplier_ico=supplier_ico,
    )


Filters = Annotated[DashboardFilter, Depends(common_filter)]


async def _guard[T](call: Awaitable[T]) -> T:
    """Map filter validation to 422 and an aggregate time-out to 504."""
    try:
        return await call
    except FilterValidationError as exc:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("query", exc.field), "msg": str(exc), "input": None}]
        ) from exc
    except ExecutionTimeout as exc:
        logger.warning("analytics aggregate exceeded maxTimeMS: %s", exc)
        raise HTTPException(status_code=504, detail="analytics_timeout") from exc


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(analytics: Analytics, f: Filters) -> dict:
    """KPIs for the period, the previous equal-length period and percentage deltas."""
    return await _guard(svc.summary(analytics, f))


@router.get("/timeseries", response_model=AnalyticsTimeseriesResponse)
async def analytics_timeseries(
    analytics: Analytics,
    f: Filters,
    granularity: Literal["month", "quarter", "year"] = Query("month"),
    split_by: Literal["source", "cpv_division"] | None = Query(None),
    top: int = Query(5, ge=1, le=10, description="Series kept with split_by; the rest is 'other'."),
) -> dict:
    """Zero-filled contract count and value per period, optionally split into series."""
    return await _guard(svc.timeseries(analytics, f, granularity, split_by, top))


@router.get("/top", response_model=AnalyticsTopResponse)
async def analytics_top(
    analytics: Analytics,
    f: Filters,
    dimension: Literal["procurer", "supplier", "cpv_division"] = Query(...),
    metric: Literal["total_value", "contract_count"] = Query("total_value"),
    n: int = Query(10, ge=1, le=50),
) -> dict:
    """Top-N entities by value or count, with shares and an 'other' remainder."""
    return await _guard(svc.top(analytics, f, dimension, metric, n))


@router.get("/concentration", response_model=AnalyticsConcentrationResponse)
async def analytics_concentration(
    analytics: Analytics,
    f: Filters,
    dimension: Literal["supplier", "procurer"] = Query("supplier"),
) -> dict:
    """HHI, CR4/CR10 and the cumulative top-10 curve."""
    return await _guard(svc.concentration(analytics, f, dimension))


@router.get("/cpv", response_model=AnalyticsCpvResponse)
async def analytics_cpv(
    analytics: Analytics,
    f: Filters,
    level: Literal["division", "group"] = Query("division"),
) -> dict:
    """Value and count per CPV division (or group)."""
    return await _guard(svc.cpv_breakdown(analytics, f, level))


@router.get("/coverage", response_model=AnalyticsCoverageResponse)
async def analytics_coverage(analytics: Analytics) -> dict:
    """Per-source freshness and field coverage; ignores the common filters."""
    return await _guard(svc.coverage(analytics))
