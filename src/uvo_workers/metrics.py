"""Prometheus metrics rendering for worker health endpoints."""

from prometheus_client import generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


class WorkerMetricsCollector:
    """Reports a worker's metrics snapshot as Prometheus families.

    The snapshot values (batches_processed, notices_written, ...) are already
    monotonic cumulative totals maintained by the worker's own event loop, so
    each scrape just re-reports the latest snapshot as-is -- no delta
    reconciliation against prometheus_client's private Counter/Gauge
    internals (`._value.get()`) is needed, which is deliberate: an earlier
    version of this module reached into those internals and a
    prometheus_client upgrade changing that private layout would have broken
    `/metrics` at runtime with no test coverage to catch it.

    `generate_latest()` only requires an object with a `.collect()` method
    (see prometheus_client.registry.Collector) -- this is passed straight to
    it rather than registered on a CollectorRegistry, since the registry adds
    no value here (there's exactly one collector, constructed fresh per
    worker process) and would just be another layer to reach through.
    """

    def __init__(self, component: str) -> None:
        self.component = component
        self.snapshot: dict = {}

    def collect(self):
        batches = CounterMetricFamily(
            "uvo_worker_batches_processed",
            "Batches processed since start",
            labels=["component"],
        )
        batches.add_metric([self.component], self.snapshot.get("batches_processed") or 0)
        yield batches

        notices = CounterMetricFamily(
            "uvo_worker_notices_written",
            "Notices written since start",
            labels=["component"],
        )
        notices.add_metric([self.component], self.snapshot.get("notices_written") or 0)
        yield notices

        redis_gauge = GaugeMetricFamily(
            "uvo_worker_redis_connected",
            "1 when the Redis connection is healthy",
        )
        redis_gauge.add_metric([], 1 if self.snapshot.get("redis_connected") else 0)
        yield redis_gauge


def build_registry(component: str) -> WorkerMetricsCollector:
    """Create the per-process metrics collector for `component`.

    Name kept as `build_registry` for call-site continuity; it returns a
    `WorkerMetricsCollector`, not a `prometheus_client.CollectorRegistry` --
    a fresh instance per process keeps workers independent, same intent as
    the CollectorRegistry-per-process approach this replaced.
    """
    return WorkerMetricsCollector(component)


def render_metrics(collector: WorkerMetricsCollector, snapshot: dict) -> bytes:
    """Project a worker metrics dict onto the collector and render it."""
    collector.snapshot = snapshot
    return generate_latest(collector)
