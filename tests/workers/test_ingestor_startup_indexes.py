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
