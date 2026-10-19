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


def test_repeated_scrapes_reflect_the_latest_snapshot():
    """Each render reports the snapshot's own cumulative value directly --
    no stored delta state carried between calls, unlike the previous
    Counter.inc()-based implementation this replaced.
    """
    registry = build_registry("ingestor")

    first = render_metrics(registry, {"batches_processed": 5}).decode()
    assert 'uvo_worker_batches_processed_total{component="ingestor"} 5.0' in first

    second = render_metrics(registry, {"batches_processed": 5}).decode()
    assert 'uvo_worker_batches_processed_total{component="ingestor"} 5.0' in second

    third = render_metrics(registry, {"batches_processed": 41}).decode()
    assert 'uvo_worker_batches_processed_total{component="ingestor"} 41.0' in third


def test_stream_health_gauges_are_rendered():
    registry = build_registry("ingestor")
    payload = render_metrics(
        registry,
        {
            "stream_lag": {"notices:crz": 12, "notices:ted": 0},
            "stream_pending": {"notices:crz": 3},
            "dead_letter_length": 4,
            "last_success_at": 1700000000.0,
        },
    ).decode()
    assert 'uvo_worker_stream_lag{component="ingestor",stream="notices:crz"} 12.0' in payload
    assert 'uvo_worker_stream_pending{component="ingestor",stream="notices:crz"} 3.0' in payload
    assert 'uvo_worker_dead_letter_length{component="ingestor"} 4.0' in payload
    assert 'uvo_worker_last_success_timestamp_seconds{component="ingestor"} 1.7e+09' in payload


def test_stream_health_gauges_default_to_absent_or_zero():
    registry = build_registry("extractor-crz")
    payload = render_metrics(registry, {}).decode()
    assert "uvo_worker_stream_lag{" not in payload
    assert 'uvo_worker_dead_letter_length{component="extractor-crz"} 0.0' in payload
    assert 'uvo_worker_last_success_timestamp_seconds{component="extractor-crz"} 0.0' in payload
