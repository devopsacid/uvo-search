"""The ingestor must provision indexes itself — it is the only writer in a
worker-only deployment, where the legacy orchestrator never runs."""

import inspect

from uvo_workers import ingestor


def test_ingestor_calls_ensure_indexes():
    source = inspect.getsource(ingestor.run_ingestor)
    assert "ensure_indexes" in source, (
        "run_ingestor must call ensure_indexes at startup; the pipeline Job that "
        "used to do it is excluded from the kustomize base"
    )


def test_ingestor_calls_ensure_constraints():
    source = inspect.getsource(ingestor.run_ingestor)
    assert "ensure_constraints" in source, (
        "run_ingestor must call ensure_constraints — MERGE is only atomic when "
        "backed by a uniqueness constraint"
    )


def test_index_bootstrap_failed_is_a_valid_log_event():
    """Every event name the ingestor logs must exist in the LogEvent literal.

    `index_bootstrap_failed` was emitted without being added to the literal, so
    the failure handler itself raised a pydantic ValidationError — masking the
    original bootstrap error it was trying to report.
    """
    import inspect
    import re

    from uvo_pipeline.ingestion_log import LogEvent
    from uvo_workers import dedup, ingestor, runner

    allowed = set(LogEvent.__args__)
    for module in (ingestor, runner, dedup):
        emitted = set(re.findall(r'event="([a-z_]+)"', inspect.getsource(module)))
        unknown = emitted - allowed
        assert not unknown, (
            f"{module.__name__} logs event(s) missing from LogEvent: {sorted(unknown)}"
        )
