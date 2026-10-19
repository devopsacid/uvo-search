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

    def __init__(
        self, component: str, *, source: str | None = None, instance_id: str | None = None
    ) -> None:
        self.component = component
        self.source = source or ""
        self.instance_id = instance_id or ""
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

        for family, help_text, key in (
            (
                "uvo_worker_stream_lag",
                "Entries not yet delivered to the consumer group",
                "stream_lag",
            ),
            (
                "uvo_worker_stream_pending",
                "Delivered but unacked entries (PEL size)",
                "stream_pending",
            ),
        ):
            per_stream = GaugeMetricFamily(family, help_text, labels=["component", "stream"])
            for stream, value in (self.snapshot.get(key) or {}).items():
                per_stream.add_metric([self.component, stream], value or 0)
            yield per_stream

        dead = GaugeMetricFamily(
            "uvo_worker_dead_letter_length",
            "Entries parked in the notices:dead stream",
            labels=["component"],
        )
        dead.add_metric([self.component], self.snapshot.get("dead_letter_length") or 0)
        yield dead

        last_ok = GaugeMetricFamily(
            "uvo_worker_last_success_timestamp_seconds",
            "Unix time of the last successful batch/cycle (0 = none yet)",
            labels=["component"],
        )
        last_ok.add_metric([self.component], self.snapshot.get("last_success_at") or 0)
        yield last_ok

        redis_gauge = GaugeMetricFamily(
            "uvo_worker_redis_connected",
            "1 when the Redis connection is healthy",
        )
        redis_gauge.add_metric([], 1 if self.snapshot.get("redis_connected") else 0)
        yield redis_gauge

        # Counters below are only emitted when the worker tracks them, so e.g. an
        # extractor never reports dedup_runs.
        for family, help_text, key in (
            (
                "uvo_worker_cycles_completed",
                "Extraction/processing cycles completed since start",
                "cycles_completed",
            ),
            (
                "uvo_worker_cycles_skipped_locked",
                "Cycles skipped because another instance held the lock",
                "cycles_skipped_locked",
            ),
            ("uvo_worker_dedup_runs", "Dedup passes run since start", "dedup_runs"),
        ):
            if key in self.snapshot:
                counter = CounterMetricFamily(family, help_text, labels=["component"])
                counter.add_metric([self.component], self.snapshot.get(key) or 0)
                yield counter

        if "last_error" in self.snapshot:
            err = GaugeMetricFamily(
                "uvo_worker_last_error",
                "1 when the most recent cycle ended in an error",
                labels=["component"],
            )
            err.add_metric([self.component], 0 if self.snapshot["last_error"] is None else 1)
            yield err

        if self.snapshot.get("started_at_ts") is not None:
            started = GaugeMetricFamily(
                "uvo_worker_start_timestamp_seconds",
                "Unix time the worker process started",
                labels=["component"],
            )
            started.add_metric([self.component], self.snapshot["started_at_ts"])
            yield started

        info = GaugeMetricFamily(
            "uvo_worker_info",
            "Constant 1; labels identify the worker instance",
            labels=["component", "source", "instance_id"],
        )
        info.add_metric(
            [
                self.component,
                self.source,
                self.instance_id or str(self.snapshot.get("instance_id") or ""),
            ],
            1,
        )
        yield info


def build_registry(
    component: str, *, source: str | None = None, instance_id: str | None = None
) -> WorkerMetricsCollector:
    """Create the per-process metrics collector for `component`.

    Name kept as `build_registry` for call-site continuity; it returns a
    `WorkerMetricsCollector`, not a `prometheus_client.CollectorRegistry` --
    a fresh instance per process keeps workers independent, same intent as
    the CollectorRegistry-per-process approach this replaced.
    """
    return WorkerMetricsCollector(component, source=source, instance_id=instance_id)


def render_metrics(collector: WorkerMetricsCollector, snapshot: dict) -> bytes:
    """Project a worker metrics dict onto the collector and render it."""
    collector.snapshot = snapshot
    return generate_latest(collector)
