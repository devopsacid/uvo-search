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


def test_cycle_and_dedup_counters_are_rendered_when_present():
    registry = build_registry("dedup-worker")
    text = render_metrics(
        registry,
        {"cycles_completed": 9, "cycles_skipped_locked": 2, "dedup_runs": 4},
    ).decode()
    assert 'uvo_worker_cycles_completed_total{component="dedup-worker"} 9.0' in text
    assert 'uvo_worker_cycles_skipped_locked_total{component="dedup-worker"} 2.0' in text
    assert 'uvo_worker_dedup_runs_total{component="dedup-worker"} 4.0' in text


def test_new_families_are_omitted_when_snapshot_lacks_the_keys():
    registry = build_registry("extractor-crz")
    text = render_metrics(registry, {"batches_processed": 1}).decode()
    for family in (
        "uvo_worker_cycles_completed",
        "uvo_worker_cycles_skipped_locked",
        "uvo_worker_dedup_runs",
        "uvo_worker_last_error{",
        "uvo_worker_start_timestamp_seconds{",
    ):
        assert family not in text


def test_last_error_gauge_is_one_only_when_an_error_is_set():
    registry = build_registry("ingestor")
    errored = render_metrics(registry, {"last_error": "boom"}).decode()
    assert 'uvo_worker_last_error{component="ingestor"} 1.0' in errored
    clean = render_metrics(registry, {"last_error": None}).decode()
    assert 'uvo_worker_last_error{component="ingestor"} 0.0' in clean


def test_start_timestamp_gauge_comes_from_started_at_ts():
    registry = build_registry("ingestor")
    text = render_metrics(registry, {"started_at_ts": 1700000000.0}).decode()
    assert 'uvo_worker_start_timestamp_seconds{component="ingestor"} 1.7e+09' in text


def test_worker_info_carries_source_and_instance_id():
    registry = build_registry("extractor-crz", source="crz", instance_id="abc123")
    text = render_metrics(registry, {}).decode()
    assert (
        'uvo_worker_info{component="extractor-crz",instance_id="abc123",source="crz"} 1.0' in text
    )


def test_worker_info_defaults_to_empty_labels():
    registry = build_registry("ingestor")
    text = render_metrics(registry, {}).decode()
    assert 'uvo_worker_info{component="ingestor",instance_id="",source=""} 1.0' in text


def test_worker_context_stamps_start_time_and_passes_info(monkeypatch):
    import time

    from uvo_workers import context as ctx_mod

    seen = {}
    real = ctx_mod.build_registry

    def spy(name, **kw):
        seen.update(name=name, **kw)
        return real(name, **kw)

    monkeypatch.setattr(ctx_mod, "build_registry", spy)
    before = time.time()
    ctx = ctx_mod.WorkerContext(
        name="n",
        component="extractor-crz",
        registry_name="extractor-crz",
        start_message="s",
        stop_message="e",
        health_port=0,
        source="crz",
        instance_id="i-1",
    )
    assert before <= ctx.metrics["started_at_ts"] <= time.time()
    ctx.build_collector()
    assert seen == {"name": "extractor-crz", "source": "crz", "instance_id": "i-1"}
