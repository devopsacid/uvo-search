"""Prometheus metrics for the API: request middleware, ``/metrics`` and refreshers.

``install_metrics(app)`` wires the pure-ASGI middleware and the ``/metrics`` route.
``start_background(app)`` returns the two long-lived refresher tasks (readiness every
30 s, per-source data freshness every 300 s); the app lifespan owns and cancels them.
Every refresher tolerates ``app.state.resources`` being absent (TestClient without
the lifespan) and never raises, so a Mongo outage cannot kill the loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from importlib import metadata

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from uvo_core.adapters.mongo.health import mongo_ready
from uvo_core.observability import CONTENT_TYPE, render_default_registry, set_ready
from uvo_pipeline.health import collect as collect_health

logger = logging.getLogger(__name__)

READY_INTERVAL_S = 30.0
SOURCE_STATS_INTERVAL_S = 300.0
UNMATCHED = "unmatched"

HTTP_REQUESTS = Counter(
    "uvo_api_http_requests",
    "HTTP requests by method, matched route template and status",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "uvo_api_http_request_duration_seconds",
    "HTTP request duration by method and matched route template",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_IN_PROGRESS = Gauge("uvo_api_http_requests_in_progress", "HTTP requests being served")
SOURCE_NOTICES = Gauge("uvo_source_notices_total", "Notices stored per source", ["source"])
SOURCE_LAST_INGESTED = Gauge(
    "uvo_source_last_ingested_timestamp_seconds",
    "Unix time of the newest ingested notice per source (0 when none)",
    ["source"],
)
SOURCE_INGESTED_24H = Gauge(
    "uvo_source_ingested_24h", "Notices ingested in the last 24 hours per source", ["source"]
)
BUILD_INFO = Gauge(
    "uvo_build_info", "Constant 1; labels identify the build", ["version", "git_sha"]
)


def _route_template(scope: Scope) -> str:
    """Matched route template (bounded cardinality), or ``unmatched``.

    Mounted sub-apps (``/v1``) report routes relative to the mount, so the mount's
    ``root_path`` is prefixed back on.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not path:
        return UNMATCHED
    return f"{scope.get('root_path', '')}{path}"


class MetricsMiddleware:
    """Pure-ASGI request counter/timer; adds no per-request allocations beyond labels."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = 500  # until the app starts a response; an exception before that is a 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        HTTP_IN_PROGRESS.inc()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            HTTP_IN_PROGRESS.dec()
            method = scope["method"]
            route = _route_template(scope)
            HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
            HTTP_DURATION.labels(method=method, route=route).observe(time.perf_counter() - started)


def _version() -> str:
    try:
        return metadata.version("uvo-search")
    except metadata.PackageNotFoundError:
        return "unknown"


def install_metrics(app: FastAPI, *, service: str = "uvo-api") -> None:
    """Add the metrics middleware and ``GET /metrics`` (outside ``/api``) to ``app``.

    Call once, after the routers are included. ``service`` is the ``uvo_ready``
    label value the refresher in :func:`start_background` reports under.
    """
    app.state.metrics_service = service
    BUILD_INFO.labels(version=_version(), git_sha=os.environ.get("GIT_SHA", "unknown")).set(1)
    app.add_middleware(MetricsMiddleware)

    async def metrics(request: Request) -> Response:
        return Response(render_default_registry(), media_type=CONTENT_TYPE)

    app.add_route("/metrics", metrics, methods=["GET"], include_in_schema=False)


def _service(app: FastAPI) -> str:
    return getattr(app.state, "metrics_service", "uvo-api")


async def refresh_ready(app: FastAPI) -> None:
    """Set ``uvo_ready`` from the same checks ``/readyz`` performs."""
    resources = getattr(app.state, "resources", None)
    ok = False
    if resources is not None:
        try:
            ok = await mongo_ready(resources.db) and await resources.index_probe.ready(resources.db)
        except Exception:  # noqa: BLE001 - a failing probe means "not ready", never a crash
            logger.warning("readiness refresh failed", exc_info=True)
    set_ready(_service(app), ok)


def _to_epoch(value: object) -> float:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return 0.0
    else:
        return 0.0
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp()


async def refresh_source_stats(app: FastAPI) -> None:
    """Publish per-source totals, 24 h ingestion and last-ingested time."""
    resources = getattr(app.state, "resources", None)
    if resources is None:
        return
    try:
        report = await collect_health(resources.db)
    except Exception:  # noqa: BLE001 - keep the last values; the loop retries
        logger.warning("source stats refresh failed", exc_info=True)
        return
    for row in report.get("sources", []):
        source = row["source"]
        SOURCE_NOTICES.labels(source=source).set(row.get("total") or 0)
        SOURCE_INGESTED_24H.labels(source=source).set(row.get("last_24h") or 0)
        SOURCE_LAST_INGESTED.labels(source=source).set(_to_epoch(row.get("last_ingested_at")))


async def _loop(refresh, app: FastAPI, interval: float) -> None:
    while True:
        await refresh(app)
        await asyncio.sleep(interval)


def start_background(app: FastAPI) -> list[asyncio.Task]:
    """Start the readiness and source-freshness refreshers; the caller cancels them."""
    return [
        asyncio.create_task(_loop(refresh_ready, app, READY_INTERVAL_S), name="metrics-ready"),
        asyncio.create_task(
            _loop(refresh_source_stats, app, SOURCE_STATS_INTERVAL_S), name="metrics-sources"
        ),
    ]
