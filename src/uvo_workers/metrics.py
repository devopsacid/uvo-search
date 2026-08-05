"""Prometheus metrics rendering for worker health endpoints."""

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest


def build_registry(component: str) -> CollectorRegistry:
    """Create a registry with the standard worker metric family.

    A fresh registry per process keeps the workers independent and avoids the
    global default registry, which makes tests order-dependent.
    """
    registry = CollectorRegistry()
    registry._uvo = {  # noqa: SLF001 - deliberate handle for render_metrics
        "batches": Counter(
            "uvo_worker_batches_processed",
            "Batches processed since start",
            ["component"],
            registry=registry,
        ),
        "notices": Counter(
            "uvo_worker_notices_written",
            "Notices written since start",
            ["component"],
            registry=registry,
        ),
        "redis": Gauge(
            "uvo_worker_redis_connected",
            "1 when the Redis connection is healthy",
            registry=registry,
        ),
        "component": component,
    }
    return registry


def render_metrics(registry: CollectorRegistry, snapshot: dict) -> bytes:
    """Project a worker metrics dict onto the registry and render it."""
    handles = registry._uvo  # noqa: SLF001
    component = handles["component"]

    batches = snapshot.get("batches_processed")
    if batches is not None:
        current = handles["batches"].labels(component=component)._value.get()  # noqa: SLF001
        handles["batches"].labels(component=component).inc(max(0, batches - current))

    notices = snapshot.get("notices_written")
    if notices is not None:
        current = handles["notices"].labels(component=component)._value.get()  # noqa: SLF001
        handles["notices"].labels(component=component).inc(max(0, notices - current))

    handles["redis"].set(1 if snapshot.get("redis_connected") else 0)
    return generate_latest(registry)
