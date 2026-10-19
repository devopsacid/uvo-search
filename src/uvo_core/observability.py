"""Process-wide Prometheus metrics shared by the delivery processes (API, MCP).

Everything registers on the default ``prometheus_client`` registry, so one
``/metrics`` endpoint per process exposes core, API and process metrics together.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Pinned (not CONTENT_TYPE_LATEST, which newer prometheus_client bumps to 1.0.0) so it
# matches the worker /metrics endpoints and the scrape config.
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

CACHE_REQUESTS = Counter(
    "uvo_cache_requests",
    "async_ttl_cache lookups by outcome (hit, miss, inflight)",
    ["cache", "result"],
)

CACHED_CALL_DURATION = Histogram(
    "uvo_cached_call_duration_seconds",
    "Duration of the underlying call on a cache miss",
    ["cache"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

READY = Gauge("uvo_ready", "1 when the service reports ready", ["service"])


def set_ready(service: str, ok: bool) -> None:
    """Record the latest readiness verdict for ``service``."""
    READY.labels(service=service).set(1 if ok else 0)


def render_default_registry() -> bytes:
    """Render the default registry in the Prometheus text exposition format."""
    return generate_latest()
