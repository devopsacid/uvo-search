"""Workers expose Prometheus metrics for alerting and autoscaling."""

from uvo_workers.metrics import build_registry, render_metrics


def test_renders_counter_values_from_snapshot():
    registry = build_registry("ingestor")
    payload = render_metrics(registry, {"batches_processed": 7, "notices_written": 300})
    text = payload.decode()
    assert "uvo_worker_batches_processed_total" in text
    assert "7.0" in text


def test_readiness_is_exposed_as_a_gauge():
    registry = build_registry("ingestor")
    payload = render_metrics(registry, {"redis_connected": False, "last_error": "boom"})
    assert "uvo_worker_redis_connected 0.0" in payload.decode()


def test_unknown_snapshot_keys_are_ignored():
    registry = build_registry("ingestor")
    render_metrics(registry, {"something_new": 1, "batches_processed": 2})
